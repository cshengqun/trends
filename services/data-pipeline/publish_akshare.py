"""Publish AKShare points reviewed by the private sync into the Trends disclosure database."""

import calendar
from datetime import datetime, time
import hashlib
import json
import logging
import os
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

LOG = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_METRICS = ("revenue", "net_income", "pe_ttm", "dividend_yield")


def document(symbol, metric):
    code, market = symbol.split(".")
    if market != "HK":
        if metric == "pe_ttm":
            return "东方财富估值（经 AKShare）", f"https://data.eastmoney.com/gzfx/detail/{code}.html", []
        if metric == "dividend_yield":
            return (
                "东方财富行情及派息（经 AKShare）", f"https://data.eastmoney.com/yjfp/detail/{code}.html",
                [{"label": "季末收盘价", "url": f"https://data.eastmoney.com/gzfx/detail/{code}.html"}],
            )
        return "东方财富利润表（经 AKShare）", (
            f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={market}{code}#lrb-0"
        ), []
    code = code.zfill(5)
    f10 = f"https://emweb.securities.eastmoney.com/PC_HKF10/pages/home/index.html?code={code}&type=web&color=w"
    if metric == "pe_ttm":
        return "百度股市通估值（经 AKShare）", f"https://gushitong.baidu.com/stock/hk-{code}", []
    if metric == "dividend_yield":
        return "东方财富派息及新浪收盘价（经 AKShare）", f"{f10}#/CoreReading", [
            {"label": "季末收盘价", "url": f"https://stock.finance.sina.com.cn/hkstock/quotes/{code}.html"},
        ]
    return "东方财富利润表（经 AKShare）", f"{f10}#/newfinancialanalysis", []


def publish(private, public):
    batch = private.execute("""
        SELECT quarter_end,symbol,metric_id,value,unit,currency,reference_date,revision,source,provenance
        FROM latest_quarterly_metrics WHERE metric_id=ANY(%s)
        ORDER BY symbol,quarter_end,metric_id
    """, (list(BASE_METRICS),)).fetchall()
    if not batch:
        raise RuntimeError("The private AKShare database has no publishable points")

    written = 0
    with public.transaction():
        public.execute("SELECT pg_advisory_xact_lock(823102)")
        for end, symbol, metric, value, unit, currency, reference_date, revision, source, provenance in batch:
            start = end.replace(month=end.month - 2, day=1)
            if end.month % 3 or end.day != calendar.monthrange(end.year, end.month)[1]:
                raise ValueError(f"Unexpected quarter end for {symbol}: {end}")
            label, url, supporting = document(symbol, metric)
            raw = {
                "provider": source, "private_revision": revision, "metric": metric,
                "supporting_documents": supporting, "calculation": provenance,
            }
            published = None
            if reference_date:
                if metric in ("pe_ttm", "dividend_yield"):
                    raw["market_date"] = reference_date.isoformat()
                else:
                    published = datetime.combine(reference_date, time.max, SHANGHAI)
            digest = json.dumps((symbol, str(end), str(value), unit, currency, str(reference_date), raw),
                                ensure_ascii=False, sort_keys=True)
            source_id = "akshare-" + hashlib.sha256(digest.encode()).hexdigest()[:24]

            public.execute("""
                INSERT INTO sources (id,label,kind,document_ref,raw_payload,published_at)
                VALUES (%s,%s,'licensed',%s,%s,%s) ON CONFLICT (id) DO NOTHING
            """, (source_id, label, url, Jsonb(raw), published))
            inserted = public.execute("""
                INSERT INTO observations
                (entity_id,metric_id,period_start,period_end,period_type,published_at,available_at,
                value,currency,unit,source_id,calculation_version,quality_status,revision)
                SELECT %s,%s,%s,%s,'quarterly',%s,
                       greatest(now(),%s),%s,%s,%s,%s,'akshare-quarterly-v1','verified',
                       coalesce((SELECT max(revision) FROM observations
                                 WHERE entity_id=%s AND metric_id=%s AND period_end=%s AND period_type='quarterly'),0)+1
                WHERE NOT EXISTS (SELECT FROM observations WHERE entity_id=%s AND metric_id=%s AND period_end=%s
                                  AND period_type='quarterly' AND source_id=%s)
            """, (symbol, metric, start, end, published, published, value, currency, unit, source_id,
                  symbol, metric, end, symbol, metric, end, source_id))
            written += inserted.rowcount
    LOG.info("AKShare publication points=%s new_revisions=%s", len(batch), written)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with psycopg.connect(os.environ["AKSHARE_DATABASE_URL"], autocommit=True, connect_timeout=10) as private, \
         psycopg.connect(os.environ["AKSHARE_PUBLISH_DATABASE_URL"], autocommit=True, connect_timeout=10) as public:
        if private.info.dbname != "trends_akshare" or public.info.dbname != "trends_disclosures":
            raise RuntimeError("Unexpected AKShare source or publication database")
        publish(private, public)


if __name__ == "__main__":
    main()
