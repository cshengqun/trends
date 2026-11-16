"""Fetch AKShare financial and market data into a private PostgreSQL database."""

import argparse
import calendar
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import logging
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import akshare as ak
import psycopg
from psycopg.types.json import Jsonb

LOG = logging.getLogger(__name__)
SNAPSHOT = Path(__file__).with_name("data") / "disclosures.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
CURRENCIES = {"人民币": "CNY", "RMB": "CNY", "港元": "HKD", "港币": "HKD", "美元": "USD"}
FIELDS = ("revenue", "net_income")
BILLION = Decimal(10**9)
SCALES = {"yuan": 1, "thousand": 1000, "million": 10**6, "billion": 10**9}
SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now(),
    first_quarter date NOT NULL,
    last_quarter date NOT NULL,
    status text NOT NULL CHECK (status IN ('success','partial','failed')),
    observations_seen integer NOT NULL,
    observations_written integer NOT NULL,
    details jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS quarterly_metrics (
    symbol text NOT NULL,
    quarter_end date NOT NULL,
    metric_id text NOT NULL,
    revision integer NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    currency text NOT NULL,
    reference_date date,
    source text NOT NULL,
    provenance jsonb NOT NULL,
    captured_at timestamptz NOT NULL,
    PRIMARY KEY (symbol, quarter_end, metric_id, revision)
);
CREATE OR REPLACE VIEW latest_quarterly_metrics AS
    SELECT DISTINCT ON (symbol, quarter_end, metric_id) *
    FROM quarterly_metrics
    ORDER BY symbol, quarter_end, metric_id, revision DESC;
"""


@dataclass(frozen=True)
class Point:
    value: Decimal
    unit: str
    currency: str
    reference_date: date | None
    source: str
    provenance: dict


def as_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def quarter_end(value, offset=0):
    index = value.year * 4 + (value.month - 1) // 3 + offset
    year, quarter = divmod(index, 4)
    month = 3 * (quarter + 1)
    return date(year, month, calendar.monthrange(year, month)[1])


def quarter_start(end):
    return quarter_end(end, -1) + timedelta(days=1)


def records(frame):
    return frame.to_dict(orient="records")


def fetch(security, method, failures, **kwargs):
    try:
        return records(getattr(ak, method)(**kwargs))
    except Exception as error:
        failures.append({"symbol": security, "adapter": method, "error": type(error).__name__})
        LOG.warning("%s %s: %s", security, method, str(error).split("\n", 1)[0][:250])
        return []


def original_disclosures(document):
    data = {}
    for filing in document["filings"]:
        for row in filing["rows"]:
            end = as_date(row["end"])
            for metric in FIELDS:
                if metric in row["values"]:
                    value = Decimal(row["values"][metric]) * SCALES[row["scale"]] / BILLION
                    data[filing["symbol"], end, row["period"], metric] = Point(
                        value, "billion", row["currency"], as_date(filing["published"]),
                        "issuer-disclosure", {"url": filing["url"]},
                    )
    return data


def comparable(point, reference):
    return point.currency == reference.currency and abs(point.value - reference.value) <= max(
        abs(reference.value) * Decimal("0.005"), Decimal("0.0005"),
    )


def financial_points(symbol, market, rows, reference, first, last, notes):
    result = {}
    by_date = {as_date(row.get("REPORT_DATE")): row for row in rows}
    method = "stock_profit_sheet_by_quarterly_em" if market == "CN" else "stock_financial_hk_analysis_indicator_em"
    hk_anchor = reference.get((symbol, date(2025, 12, 31), "annual", "revenue"))
    if market == "HK" and hk_anchor and (annual := by_date.get(date(2025, 12, 31))):
        amount = number(annual.get("OPERATE_INCOME"))
        currency = CURRENCIES.get(annual.get("CURRENCY"), annual.get("CURRENCY"))
        if amount is not None and not comparable(
            Point(amount / BILLION, "billion", currency, None, method, {}), hk_anchor
        ):
            notes.append({"symbol": symbol, "reason": "issuer_currency_or_scale_mismatch"})
            return result
    columns = ("OPERATE_INCOME", "PARENT_NETPROFIT" if market == "CN" else "HOLDER_PROFIT")
    for end, row in by_date.items():
        if end is None or not first <= end <= last or quarter_end(end) != end:
            continue
        if market == "CN" and (not as_date(row.get("NOTICE_DATE")) or
                               as_date(row.get("NOTICE_DATE")) > datetime.now(SHANGHAI).date()):
            continue
        reported = row.get("CURRENCY")
        currency = CURRENCIES.get(reported, reported)
        if currency not in ("CNY", "HKD", "USD"):
            continue
        basis = None
        if market == "HK":
            start = as_date(row.get("START_DATE"))
            if start is None or start > quarter_start(end):
                continue
            if start < quarter_start(end):
                basis = by_date.get(quarter_end(end, -1))
                if not basis or as_date(basis.get("START_DATE")) != start or basis.get("CURRENCY") != reported:
                    continue
        for metric, column in zip(FIELDS, columns, strict=True):
            amount = number(row.get(column))
            prior = number(basis.get(column)) if basis else Decimal(0)
            if amount is None or prior is None or (metric == "revenue" and amount <= prior):
                continue
            point = Point(
                (amount - prior) / BILLION, "billion", currency, as_date(row.get("NOTICE_DATE")),
                "AKShare/Eastmoney",
                {"method": method, "field": column, "basis": str(quarter_end(end, -1)) if basis else None},
            )
            official = reference.get((symbol, end, "quarterly", metric))
            if official and not comparable(point, official):
                notes.append({"symbol": symbol, "quarter": str(end), "metric": metric,
                              "reason": "issuer_value_mismatch"})
                continue
            result[end, metric] = point
    return result


def dividends(rows, market):
    result = set()
    for row in rows:
        if market == "CN":
            day = as_date(row.get("除权除息日"))
            if not day or row.get("方案进度") != "实施分配":
                continue
            cash = (number(row.get("现金分红-现金分红比例")) or Decimal(0)) / 10
            split = 1 + (number(row.get("送转股份-送转总比例")) or Decimal(0)) / 10
        else:
            day = as_date(row.get("除净日"))
            if not day:
                continue
            plan = str(row.get("分红方案", ""))
            if plan.startswith("特殊说明:每") and "分派" in plan and "股份" in plan:
                continue
            match = re.search(r"(?:^每股派港币|相当于港币)([0-9]+(?:\.[0-9]+)?)元", plan)
            cash = number(match[1]) if match else None
            split = Decimal(1)
        result.add((day, cash, split))
    return sorted(result, key=lambda item: item[0])


def market_points(quarters, market, prices, pe_series, payouts):
    result = {}
    for end in quarters:
        day = max((d for d in prices if end - timedelta(days=10) <= d <= end), default=None)
        if day is None:
            continue
        pe = pe_series.get(day)
        if pe is not None and pe > 0:
            source = "AKShare/Eastmoney" if market == "CN" else "AKShare/Baidu"
            result[end, "pe_ttm"] = Point(pe, "倍", "", day, source, {"method": "last_trading_day"})
        prior = day.replace(year=day.year - 1, day=min(day.day, calendar.monthrange(day.year - 1, day.month)[1]))
        cashflows = [(ex, cash, split) for ex, cash, split in payouts if prior < ex <= day]
        if not payouts or any(cash is None for _, cash, _ in cashflows):
            continue
        shares, total = Decimal(1), Decimal(0)
        for _, cash, split in reversed(cashflows):
            shares *= split
            total += cash / shares
        coverage = [{"ex_date": str(ex), "cash_per_share": str(cash), "split_factor": str(split)}
                    for ex, cash, split in cashflows]
        source = "AKShare/Eastmoney" if market == "CN" else "AKShare/Eastmoney+Sina"
        result[end, "dividend_yield"] = Point(
            (total * 100 / prices[day]).quantize(Decimal("0.000001")), "%", "", day,
            source, {"close": str(prices[day]), "cashflows": coverage},
        )
    return result


def series(rows, date_col, value_col, positive=False):
    return {day: value for row in rows if (day := as_date(row.get(date_col))) is not None
            and (value := number(row.get(value_col))) is not None and (not positive or value > 0)}


def company_points(symbol, market, quarters, reference, failures, notes):
    code, exchange = symbol.split(".")
    if market == "CN":
        financial = fetch(symbol, "stock_profit_sheet_by_quarterly_em", failures, symbol=exchange + code)
        market_data = fetch(symbol, "stock_value_em", failures, symbol=code)
        price = series(market_data, "数据日期", "当日收盘价", positive=True)
        pe = series(market_data, "数据日期", "PE(TTM)")
        div = fetch(symbol, "stock_fhps_detail_em", failures, symbol=code)
    else:
        code = code.zfill(5)
        financial = fetch(symbol, "stock_financial_hk_analysis_indicator_em", failures, symbol=code, indicator="报告期")
        market_data = fetch(symbol, "stock_hk_hist_sina", failures, symbol=code)
        price = series(market_data, "date", "close", positive=True)
        pe_data = fetch(symbol, "stock_hk_valuation_baidu", failures,
                        symbol=code, indicator="市盈率(TTM)", period="近三年")
        pe = series(pe_data, "date", "value")
        div = fetch(symbol, "stock_hk_dividend_payout_em", failures, symbol=code)

    financial = financial_points(symbol, market, financial, reference,
                                 quarter_end(quarters[0], -4), quarters[-1], notes)
    result = market_points(quarters, market, price, pe, dividends(div, market))
    for end in quarters:
        for metric in FIELDS:
            point = financial.get((end, metric))
            if point is None:
                continue
            result[end, metric] = point
            prior_end = quarter_end(end, -4)
            prior = financial.get((prior_end, metric)) or reference.get((symbol, prior_end, "quarterly", metric))
            if prior and prior.currency == point.currency and prior.value > 0:
                growth = "revenue_growth" if metric == "revenue" else "profit_growth"
                result[end, growth] = Point(
                    (100 * (point.value / prior.value - 1)).quantize(Decimal("0.000001")), "%", "",
                    point.reference_date, point.source,
                    {"current_value": str(point.value), "prior_value": str(prior.value),
                     "prior_quarter": str(prior_end), "prior_source": prior.source,
                     "prior_details": prior.provenance},
                )
    return result


def store(connection, captured, quarters, points, failures, notes, coverage):
    written = 0
    status = "partial" if failures else "success"
    if not points:
        status = "failed"
    with connection.transaction():
        for (symbol, end, metric), point in points.items():
            previous = connection.execute("""
                SELECT revision,value,unit,currency,reference_date,source,provenance
                FROM latest_quarterly_metrics WHERE symbol=%s AND quarter_end=%s AND metric_id=%s
            """, (symbol, end, metric)).fetchone()
            values = (point.value, point.unit, point.currency, point.reference_date, point.source, point.provenance)
            if previous and previous[1:] == values:
                continue
            connection.execute("""
                INSERT INTO quarterly_metrics
                (symbol,quarter_end,metric_id,revision,value,unit,currency,reference_date,source,provenance,captured_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (symbol, end, metric, previous[0] + 1 if previous else 1, *values[:-1],
                  Jsonb(point.provenance), captured))
            written += 1
        connection.execute("""
            INSERT INTO sync_runs
            (started_at,first_quarter,last_quarter,status,observations_seen,observations_written,details)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (captured, quarters[0], quarters[-1], status, len(points), written,
              Jsonb({"coverage": coverage, "failures": failures, "review": notes, "akshare": ak.__version__})))
    LOG.info("status=%s quarters=%s..%s seen=%s written=%s failures=%s review=%s",
             status, quarters[0], quarters[-1], len(points), written, len(failures), len(notes))
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarters", type=int, default=8, choices=range(1, 9), metavar="1..8")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    captured = datetime.now(SHANGHAI)
    quarters = [quarter_end(captured.date(), -n) for n in range(args.quarters, 0, -1)]
    document = json.loads(SNAPSHOT.read_text())
    reference = original_disclosures(document)
    with psycopg.connect(os.environ["AKSHARE_DATABASE_URL"], autocommit=True, connect_timeout=10) as connection:
        if connection.info.dbname != "trends_akshare":
            raise RuntimeError("AKSHARE_DATABASE_URL must point to the private trends_akshare database")
        if not connection.execute("SELECT pg_try_advisory_lock(823103)").fetchone()[0]:
            raise RuntimeError("Another AKShare sync is already running")
        connection.execute(SCHEMA)
        failures, notes, coverage = [], [], {}
        points = {}
        for symbol, _, market, *_ in document["companies"]:
            LOG.info("Fetching %s", symbol)
            found = company_points(symbol, market, quarters, reference, failures, notes)
            points.update({(symbol, end, metric): point for (end, metric), point in found.items()})
            coverage[symbol] = dict(Counter(metric for _, metric in found))
        return int(store(connection, captured, quarters, points, failures, notes, coverage) != "success")


if __name__ == "__main__":
    raise SystemExit(main())
