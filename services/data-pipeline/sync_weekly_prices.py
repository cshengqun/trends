"""Fetch and publish the last 104 completed trading weeks of closing prices."""

from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import logging
import os

import akshare as ak
import psycopg
from psycopg.types.json import Jsonb

from akshare_sync import SHANGHAI, SNAPSHOT, records, series

LOG = logging.getLogger(__name__)
WEEKS = 104


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


def fetch_closes(symbol, market):
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


def publish(conn, batches):
    written = 0
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(823102)")
        for symbol, weeks, currency, label, url in batches:
            previous = dict(conn.execute("""
                SELECT DISTINCT ON (period_end) period_end, source_id
                FROM observations WHERE entity_id=%s AND metric_id='stock_price' AND period_type='weekly'
                ORDER BY period_end, revision DESC
            """, (symbol,)).fetchall())
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


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    last = latest_complete_friday(datetime.now(SHANGHAI).date())
    first = last - timedelta(weeks=WEEKS - 1)
    companies = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["companies"]
    batches = []
    failed = []
    for symbol, _, market, *_ in companies:
        try:
            daily, currency, label, url = fetch_closes(symbol, market)
            weeks = weekly_closes(daily, first, last)
            if not weeks:
                raise ValueError("No weekly closes in the requested window")
            batches.append((symbol, weeks, currency, label, url))
            LOG.info("%s weekly_closes=%s latest=%s", symbol, len(weeks), max(weeks))
        except Exception as error:
            LOG.warning("%s %s: %s", symbol, type(error).__name__, str(error).split("\n", 1)[0][:250])
            failed.append(symbol)
    if batches:
        with psycopg.connect(os.environ["AKSHARE_PUBLISH_DATABASE_URL"], autocommit=True, connect_timeout=10) as conn:
            if conn.info.dbname != "trends_disclosures":
                raise RuntimeError("Unexpected weekly price publication database")
            written = publish(conn, batches)
        LOG.info("first=%s last=%s companies=%s points=%s new_revisions=%s failed=%s",
                 first, last, len(batches), sum(len(batch[1]) for batch in batches), written, failed)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
