"""Capture earnings estimates by fiscal period for the Trends watchlist."""

import calendar
from dataclasses import astuple, dataclass
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
import json
import logging
import os
import re

from akshare.utils import http
import pandas as pd
import psycopg

from akshare_sync import BILLION, SHANGHAI, SNAPSHOT, number

LOG = logging.getLogger(__name__)
CN_FIELDS = {"revenue": "TOTAL_OPERATE_INCOME", "net_income": "PARENT_NETPROFIT"}
HK_CURRENCIES = {"百万元人民币": "CNY", "百万港元": "HKD", "百万美元": "USD"}


@dataclass(frozen=True)
class Estimate:
    entity_id: str
    metric_id: str
    period_type: str
    period_end: date
    method: str
    value: Decimal
    currency: str
    prior_value: Decimal | None
    analyst_count: int | None
    source_label: str
    source_url: str


def at_year_end(year, month=12):
    return date(year, month, calendar.monthrange(year, month)[1])


def positive_count(raw):
    count = number(raw)
    return int(count) if count is not None and count > 0 and count == int(count) else None


def china_estimates(symbol, rows, actuals):
    code, exchange = symbol.split(".")
    url = f"https://emweb.eastmoney.com/PC_HSF10/ProfitForecast/Index?code={exchange}{code}&type=web"
    annual_actuals = {int(row["YEAR"]): row for row in rows if row["YEAR_MARK"] == "A"}
    for row in rows:
        if row["YEAR_MARK"] != "E":
            continue
        year = int(row["YEAR"])
        for metric, field in CN_FIELDS.items():
            amount = number(row.get(field))
            count = positive_count(row.get(field + "_COUNT"))
            if amount is None or count is None or (metric == "revenue" and amount <= 0):
                continue
            end = at_year_end(year)
            prior = number(annual_actuals.get(year - 1, {}).get(field))
            forecast = amount / BILLION
            yield Estimate(symbol, metric, "annual", end, "consensus", forecast, "CNY",
                           prior / BILLION if prior is not None else None, count, "东方财富机构预期", url)
            reported = [actuals.get((symbol, metric, at_year_end(year, month))) for month in (3, 6, 9)]
            if all(point is not None and point[1] == "CNY" for point in reported):
                q4 = forecast - sum(point[0] for point in reported)
                if metric == "revenue" and q4 <= 0:
                    continue
                base = actuals.get((symbol, metric, at_year_end(year - 1)))
                yield Estimate(symbol, metric, "quarterly", end, "annual_less_ytd", q4, "CNY",
                               base[0] if base and base[1] == "CNY" else None, count, "东方财富机构预期", url)


def hong_kong_estimates(symbol, tables):
    historical = next(t for t in tables if "财政年度" in t.columns
                      and re.fullmatch(r"\d{2}/\d{4}", str(t.columns[1])))
    fiscal_month, prior_year = map(int, historical.columns[1].split("/"))
    raw_prior = str(historical.iloc[0, 1]).replace(",", "")
    forecasts = next(t for t in tables if "财政年度" in t.columns
                     and any(str(col).startswith("最高") for col in t.columns))
    column = next(col for col in forecasts if str(col).startswith("纯利/(亏损)"))
    unit = re.search(r"\(([^()]+)\)$", column)[1]
    currency = HK_CURRENCIES[unit]
    prior = number(raw_prior.removesuffix(unit).strip()) if raw_prior.endswith(unit) else None
    code = int(symbol.split(".")[0])
    url = f"https://www.etnet.com.hk/www/sc/stocks/realtime/quote_profit.php?code={code}"
    for row in forecasts.to_dict(orient="records"):
        year = number(row["财政年度"])
        value = number(row[column])
        if year is None or year != int(year) or year <= prior_year or value is None:
            continue
        yield Estimate(symbol, "net_income", "annual", at_year_end(int(year), fiscal_month),
                       "consensus", value / 1000, currency,
                       prior / 1000 if prior is not None and year == prior_year + 1 else None,
                       None, "经济通综合盈利预测（纯利口径）", url)


def fetch(company, actuals):
    symbol, _, market, *_ = company
    code, exchange = symbol.split(".")
    if market == "CN":
        url = "https://emweb.securities.eastmoney.com/PC_HSF10/ProfitForecast/PageAjax"
        response = http.get(url, params={"code": exchange + code}, timeout=12)
        response.raise_for_status()
        return list(china_estimates(symbol, response.json()["yctj_list"], actuals))
    url = "https://www.etnet.com.hk/www/sc/stocks/realtime/quote_profit.php"
    response = http.get(url, params={"code": int(code)}, timeout=12)
    response.raise_for_status()
    return list(hong_kong_estimates(symbol, pd.read_html(StringIO(response.text), header=0)))


def quarterly_actuals(conn, captured):
    rows = conn.execute("""
        SELECT DISTINCT ON (o.entity_id, o.metric_id, o.period_end)
               o.entity_id, o.metric_id, o.period_end, o.value, o.currency
        FROM observations o JOIN sources s ON s.id = o.source_id
        WHERE o.period_type = 'quarterly' AND o.metric_id IN ('revenue', 'net_income')
          AND o.quality_status = 'verified' AND o.available_at <= %s
          AND o.period_end >= (%s AT TIME ZONE 'Asia/Shanghai')::date - interval '3 years'
        ORDER BY o.entity_id, o.metric_id, o.period_end, (s.kind <> 'official'), o.revision DESC
    """, (captured, captured)).fetchall()
    return {(symbol, metric, end): (value, currency) for symbol, metric, end, value, currency in rows}


def publish(conn, captured, estimates):
    written = 0
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(823104)")
        for point in estimates:
            written += conn.execute("""
                INSERT INTO earnings_forecasts
                (entity_id, metric_id, period_type, period_end, method, value, currency,
                 prior_value, analyst_count, source_label, source_url, captured_at)
                SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM (
                        SELECT value, currency, prior_value, analyst_count
                        FROM earnings_forecasts WHERE entity_id = %s AND metric_id = %s
                          AND period_type = %s AND period_end = %s AND method = %s
                        ORDER BY captured_at DESC LIMIT 1
                    ) previous
                    WHERE (value, currency, prior_value, analyst_count)
                      IS NOT DISTINCT FROM (%s, %s, %s, %s)
                )
                ON CONFLICT DO NOTHING
            """, (*astuple(point), captured, point.entity_id, point.metric_id, point.period_type,
                  point.period_end, point.method, point.value, point.currency,
                  point.prior_value, point.analyst_count)).rowcount
    return written


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    captured = datetime.now(SHANGHAI)
    companies = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["companies"]
    with psycopg.connect(os.environ["AKSHARE_PUBLISH_DATABASE_URL"], autocommit=True, connect_timeout=10) as conn:
        if conn.info.dbname != "trends_disclosures":
            raise RuntimeError("Unexpected earnings forecast publication database")
        actuals = quarterly_actuals(conn, captured)
        estimates, failed = [], []
        for company in companies:
            try:
                points = fetch(company, actuals)
                if not points:
                    raise ValueError("No estimates")
                estimates.extend(points)
                LOG.info("%s estimates=%s", company[0], len(points))
            except Exception as error:
                failed.append(company[0])
                LOG.warning("%s %s: %s", company[0], type(error).__name__, str(error).split("\n", 1)[0][:200])
        LOG.info("points=%s new_revisions=%s failed=%s", len(estimates), publish(conn, captured, estimates), failed)
        return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
