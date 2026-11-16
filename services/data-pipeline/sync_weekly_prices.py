"""Append completed trading weeks or backfill the two-year closing-price window."""

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import logging
import os

import akshare as ak
from akshare.utils import http
import psycopg
from psycopg.types.json import Jsonb

from akshare_sync import SHANGHAI, SNAPSHOT, records, series

LOG = logging.getLogger(__name__)
WEEKS = 104
REQUEST_WEEKS = 20


def latest_complete_friday(today):
    week = today - timedelta(days=5)
    return week + timedelta(days=4 - week.weekday())


def weekly_closes(daily, first, last):
    result = {}
    for market_date, price in sorted(daily.items()):
        weekday = market_date.weekday()
        if weekday > 4:
            continue
        friday = market_date + timedelta(days=4 - weekday)
        if first <= friday <= last:
            result[friday] = (market_date, price.quantize(Decimal("0.001")))
    return result


def fetch_history(symbol, market):
    code = symbol.split(".")[0]
    if market == "CN":
        rows = records(ak.stock_value_em(symbol=code))
        return (
            series(rows, "数据日期", "当日收盘价", positive=True), "CNY",
            "东方财富收盘价（经 AKShare）", f"https://data.eastmoney.com/gzfx/detail/{code}.html",
        )
    code = code.zfill(5)
    rows = records(ak.stock_hk_hist_sina(symbol=code, adjust=""))
    return (
        series(rows, "date", "close", positive=True), "HKD",
        "新浪港股收盘价（经 AKShare）", f"https://stock.finance.sina.com.cn/hkstock/quotes/{code}.html",
    )


def fetch_range(symbol, market, first, last):
    code = symbol.split(".")[0]
    daily = {}
    while first <= last:
        end = min(last, first + timedelta(weeks=REQUEST_WEEKS - 1))
        start = first - timedelta(days=4)
        limit = ((end - first).days // 7 + 1) * 5
        if market == "CN":
            response = http.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={
                "reportName": "RPT_VALUEANALYSIS_DET", "columns": "TRADE_DATE,CLOSE_PRICE",
                "filter": f'''(SECURITY_CODE="{code}")(TRADE_DATE>='{start}')(TRADE_DATE<='{end}')''',
                "sortColumns": "TRADE_DATE", "sortTypes": "-1", "pageSize": limit,
                "source": "WEB", "client": "WEB",
            }, timeout=20)
            response.raise_for_status()
            document = response.json()
            if document.get("success") is True and document["result"]["pages"] == 1:
                daily.update(series(document["result"]["data"], "TRADE_DATE", "CLOSE_PRICE", positive=True))
            elif document.get("code") != 9201:
                raise ValueError("Unexpected response for the A-share quote range")
        else:
            ticker = f"hk{code.zfill(5)}"
            response = http.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params={
                "param": f"{ticker},day,{start},{end},{limit},",
            }, timeout=20)
            response.raise_for_status()
            document = response.json()
            symbol_data = (document.get("data") or {}).get(ticker)
            if document.get("code") != 0 or not isinstance(symbol_data, dict):
                raise ValueError("Unexpected response for the Hong Kong quote range")
            daily.update(series(({"date": row[0], "close": row[2]} for row in symbol_data.get("day", [])),
                                "date", "close", positive=True))
        first = end + timedelta(weeks=1)
    if market == "CN":
        return daily, "CNY", "东方财富收盘价（经 AKShare）", f"https://data.eastmoney.com/gzfx/detail/{code}.html"
    return daily, "HKD", "腾讯自选股港股收盘价", f"https://gu.qq.com/hk{code.zfill(5)}"


def publish(conn, batches):
    written = 0
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(823102)")
        for symbol, weeks, currency, label, url in batches:
            previous = dict(conn.execute("""
                SELECT DISTINCT ON (period_end) period_end, source_id
                FROM observations WHERE entity_id=%s AND metric_id='stock_price' AND period_type='weekly'
                    AND period_end BETWEEN %s AND %s
                ORDER BY period_end, revision DESC
            """, (symbol, min(weeks), max(weeks))).fetchall())
            for friday, (market_date, price) in weeks.items():
                key = f"{symbol}|{market_date}|{price.normalize()}"
                source_id = "close-" + hashlib.sha256(key.encode()).hexdigest()[:24]
                if previous.get(friday) == source_id:
                    continue
                payload = {"market_date": market_date.isoformat(), "method": "weekly_unadjusted_close"}
                conn.execute("""
                    INSERT INTO sources (id,label,kind,document_ref,raw_payload)
                    VALUES (%s,%s,'licensed',%s,%s) ON CONFLICT (id) DO NOTHING
                """, (source_id, label, url, Jsonb(payload)))
                conn.execute("""
                    INSERT INTO observations
                    (entity_id,metric_id,period_start,period_end,period_type,available_at,value,currency,unit,
                     source_id,calculation_version,quality_status,revision)
                    SELECT %s,'stock_price',%s,%s,'weekly',now(),%s,%s,'price',%s,'weekly-close-v1','verified',
                        coalesce(max(revision),0)+1
                    FROM observations WHERE entity_id=%s AND metric_id='stock_price'
                        AND period_type='weekly' AND period_end=%s
                """, (symbol, friday - timedelta(days=4), friday, price, currency, source_id, symbol, friday))
                written += 1
    return written


def sync(conn, companies, last, backfill=False):
    first = last - timedelta(weeks=WEEKS - 1)
    saved = dict(conn.execute("""
        SELECT entity_id, max(period_end) FROM observations
        WHERE metric_id='stock_price' AND period_type='weekly' AND period_end<=%s
        GROUP BY entity_id
    """, (last,)).fetchall())
    batches = []
    failed = []
    skipped = 0
    for symbol, _, market, *_ in companies:
        history = backfill or symbol not in saved
        start = first if history else max(first, saved[symbol] + timedelta(weeks=1))
        if start > last:
            skipped += 1
            continue
        try:
            daily, currency, label, url = fetch_history(symbol, market) if history else fetch_range(
                symbol, market, start, last)
            weeks = weekly_closes(daily, start, last)
            if weeks:
                batches.append((symbol, weeks, currency, label, url))
            LOG.info("%s first=%s last=%s weekly_closes=%s", symbol, start, last, len(weeks))
        except Exception as error:
            LOG.warning("%s %s: %s", symbol, type(error).__name__, str(error).split("\n", 1)[0][:250])
            failed.append(symbol)
    written = publish(conn, batches) if batches else 0
    LOG.info("last=%s jobs=%s skipped=%s new_revisions=%s failed=%s",
             last, len(companies) - skipped, skipped, written, failed)
    return int(bool(failed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true", help="re-fetch the full two-year window")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    last = latest_complete_friday(datetime.now(SHANGHAI).date())
    companies = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["companies"]
    with psycopg.connect(os.environ["AKSHARE_PUBLISH_DATABASE_URL"], autocommit=True, connect_timeout=10) as conn:
        if conn.info.dbname != "trends_disclosures":
            raise RuntimeError("Unexpected weekly price publication database")
        return sync(conn, companies, last, args.backfill)


if __name__ == "__main__":
    raise SystemExit(main())
