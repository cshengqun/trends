"""Import selected factual figures verified against issuer disclosures."""

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

SNAPSHOT = Path(__file__).with_name("data") / "disclosures.json"
VERSION = "filing-v1"
MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}
SCALES = {"yuan": 10**9, "thousand": 10**6, "million": 1000, "billion": 1}
METRIC_DEFINITIONS = (
    ("revenue", "营业收入", "growth", "billion", "以发行人报告的营业收入为准", 1),
    ("net_income", "归母净利润", "growth", "billion", "以发行人报告的归属于母公司股东的净利润为准", 3),
    ("global_mau", "全球月活跃用户", "operations", "million_users", "发行人披露的指定自然月月活跃用户数", 11),
)
CST = timezone(timedelta(hours=8))


def duration_start(end, frequency):
    if end.day != calendar.monthrange(end.year, end.month)[1]:
        raise ValueError("Period end must be the last day of its month")
    first = end.year * 12 + end.month - MONTHS[frequency]
    year, month = divmod(first, 12)
    return date(year, month + 1, 1)


def amount(metric, value, currency, scale):
    if not isinstance(value, str):
        raise ValueError("Use a decimal string for every disclosed figure")
    value = Decimal(value)
    if not value.is_finite():
        raise ValueError("Non-finite disclosed figure")
    if metric == "global_mau" and currency == "" and scale == "million_users" and value > 0:
        return value, "million_users"
    if metric in ("revenue", "net_income") and currency in ("CNY", "USD", "HKD") and scale in SCALES:
        if metric == "revenue" and value <= 0:
            raise ValueError("Revenue must be positive")
        return value / SCALES[scale], "billion"
    raise ValueError(f"Unexpected metric or unit: {metric}, {currency}, {scale}")


def load_snapshot(path=SNAPSHOT):
    document = json.loads(path.read_text(encoding="utf-8"))
    companies = {row[0]: row for row in document["companies"]}
    if len(companies) != len(document["companies"]):
        raise ValueError("Duplicate company")
    keys = set()
    for symbol, name, market, exchange, industry in companies.values():
        if not name or not industry or market not in ("CN", "HK"):
            raise ValueError(f"Invalid company {symbol}")
        if exchange not in ("HKEX", "SSE", "SZSE") or (market == "HK") != (exchange == "HKEX"):
            raise ValueError(f"Invalid exchange {symbol}")
    for filing in document["filings"]:
        symbol = filing["symbol"]
        url = urlsplit(filing["url"])
        published = date.fromisoformat(filing["published"])
        if symbol not in companies or url.scheme != "https" or not url.hostname or not filing["label"]:
            raise ValueError(f"Invalid filing {symbol}")
        for row in filing["rows"]:
            freq = row["period"]
            end = date.fromisoformat(row["end"])
            if freq not in MONTHS or end >= published or published > datetime.now(CST).date():
                raise ValueError(f"Invalid disclosure date or period: {symbol}, {end}")
            duration_start(end, freq)
            for metric, value in row["values"].items():
                key = (symbol, metric, freq, end)
                if key in keys:
                    raise ValueError(f"Duplicate observation {key}")
                keys.add(key)
                amount(metric, value, row["currency"], row["scale"])
    if {key[0] for key in keys} != set(companies):
        raise ValueError("Every requested company must have a verified observation")
    return document


def insert_observation(conn, symbol, source_id, row, metric, raw, published_at):
    freq = row["period"]
    end = date.fromisoformat(row["end"])
    start = duration_start(end, freq)
    currency = row["currency"]
    value, unit = amount(metric, raw, currency, row["scale"])
    key = (symbol, metric, freq, end)
    existing = conn.execute("""
        SELECT id, value, currency, unit, period_start FROM observations
        WHERE entity_id=%s AND metric_id=%s AND period_type=%s AND period_end=%s
        AND source_id=%s AND calculation_version=%s AND quality_status='verified'
    """, (*key, source_id, VERSION)).fetchone()
    if existing:
        if existing[1:] != (value, currency, unit, start):
            raise ValueError(f"Changed filing observation {key}; create a new source revision")
        return existing[0], 0, value, unit

    observation_id = conn.execute("""
        INSERT INTO observations (entity_id, metric_id, period_type, period_end, period_start,
            value, currency, unit, source_id, calculation_version, published_at, available_at,
            quality_status, revision)
        SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'verified',COALESCE(MAX(revision),0)+1
        FROM observations WHERE entity_id=%s AND metric_id=%s AND period_type=%s AND period_end=%s
        RETURNING id
    """, (*key, start, value, currency, unit, source_id, VERSION, published_at, published_at, *key)).fetchone()[0]
    return observation_id, 1, value, unit


def yoy_insights(conn, values):
    # Use the last current/prior period pair with the same unit and currency.
    for (symbol, metric, freq), by_period in values.items():
        for end in sorted(by_period, reverse=True):
            previous_year = end.year - 1
            previous = date(previous_year, end.month, calendar.monthrange(previous_year, end.month)[1])
            if previous not in by_period:
                continue
            current_id, current, currency, unit = by_period[end]
            previous_id, prior, prior_currency, prior_unit = by_period[previous]
            if prior <= 0 or (currency, unit) != (prior_currency, prior_unit):
                continue
            delta = ((current / prior - 1) * 100).quantize(Decimal("0.01"))
            if abs(delta) >= 5:
                code = f"{symbol.lower()}-{metric}-{freq}-{end.isoformat()}-yoy"
                name, category = next((item[1], item[2]) for item in METRIC_DEFINITIONS if item[0] == metric)
                title = name + ("同比增长" if delta > 0 else "同比下降")
                conn.execute("""
                    INSERT INTO insights (id, entity_id, metric_id, category, rule_id, title, summary,
                        delta, delta_unit, period_end, period_type, data_kind)
                    VALUES (%s,%s,%s,%s,'YOY',%s,%s,%s,'%%',%s,%s,'official')
                    ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, delta=EXCLUDED.delta
                    WHERE insights.title IS DISTINCT FROM EXCLUDED.title
                       OR insights.delta IS DISTINCT FROM EXCLUDED.delta
                """,
                    (code, symbol, metric, category, title, "按同一披露频率、同一币种的上年同期计算。", delta, end, freq))
                conn.execute("""
                    DELETE FROM insight_evidence WHERE insight_id=%s AND observation_id NOT IN (%s,%s)
                """, (code, previous_id, current_id))
                conn.execute("""
                    INSERT INTO insight_evidence (insight_id, observation_id) VALUES (%s,%s),(%s,%s)
                    ON CONFLICT DO NOTHING
                """, (code, previous_id, code, current_id))
            break


def import_disclosures(conn, document):
    started = datetime.now(timezone.utc)
    written = 0
    signals = defaultdict(dict)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(823102)")
        with conn.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO entities (id, symbol, name, market, exchange, industry)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
            """, [(symbol, symbol, name, market, exchange, industry)
                  for symbol, name, market, exchange, industry in document["companies"]])
            cursor.executemany("""
                INSERT INTO metrics (id, name, category, unit, formula, display_order)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
            """, METRIC_DEFINITIONS)
        for filing in document["filings"]:
            symbol = filing["symbol"]
            source_key = f"{symbol}|{filing['url']}|{filing['published']}"
            source_id = hashlib.sha256(source_key.encode()).hexdigest()[:24]
            # Publication is typically reported as a date. Use the end of that
            # local day so same-day queries do not see data before disclosure.
            disclosed_on = date.fromisoformat(filing["published"])
            published = datetime.combine(disclosed_on, datetime.max.time(), tzinfo=CST)
            conn.execute("""
                INSERT INTO sources (id, label, kind, document_ref, raw_payload, published_at)
                VALUES (%s,%s,'official',%s,%s,%s) ON CONFLICT (id) DO NOTHING
            """, (source_id, filing["label"], filing["url"], Jsonb(filing), published))
            for row in filing["rows"]:
                for metric, raw in row["values"].items():
                    observation_id, inserted, value, unit = insert_observation(
                        conn, symbol, source_id, row, metric, raw, published)
                    written += inserted
                    end = date.fromisoformat(row["end"])
                    signals[(symbol, metric, row["period"])][end] = observation_id, value, row["currency"], unit
        yoy_insights(conn, signals)
        conn.execute("""
            INSERT INTO data_ingestion_runs (adapter, started_at, status, observations_written)
            VALUES ('issuer-disclosures',%s,'success',%s)
        """, (started, written))
    return written
