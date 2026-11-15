import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from financials import METRICS, VERSION, calculate, detect
from mock_source import MockAnnualAdapter
from official_data import import_disclosures, load_snapshot

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"
LOGGER = logging.getLogger("trends.pipeline")


def connect():
    for attempt in range(6):
        try:
            return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)
        except psycopg.OperationalError:
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)


def migrate(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(823101)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)")
        if not MIGRATIONS.is_dir():
            raise RuntimeError("Missing SQL migrations directory")
        applied = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name not in applied:
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))


def write_profile(conn, entity, statements, adapter):
    entity_id = entity["id"]
    history = calculate(statements)
    conn.execute("""
        INSERT INTO entities (id, name, symbol, market, exchange, industry)
        VALUES (%(id)s, %(name)s, %(symbol)s, %(market)s, %(exchange)s, %(industry)s)
        ON CONFLICT (id) DO NOTHING
    """, entity)
    lookup = {}
    written = 0
    for statement in statements:
        year = statement.year
        for metric, value in history[year].items():
            unit = "billion" if metric in ("revenue", "net_income", "operating_cash", "free_cash") else "%"
            params = (entity_id, metric, date(year, 1, 1), date(year, 12, 31),
                      value, statement.currency, unit, adapter.id, VERSION)
            row = conn.execute("""
                INSERT INTO observations (
                    entity_id, metric_id, period_start, period_end, period_type, available_at,
                    value, currency, unit, source_id, calculation_version, quality_status, revision
                )
                VALUES (%s, %s, %s, %s, 'annual', now(), %s, %s, %s, %s, %s, 'mock', 1)
                ON CONFLICT (entity_id, metric_id, period_type, period_end, revision) DO NOTHING
                RETURNING id
            """, params).fetchone()
            if row:
                written += 1
            else:
                row = conn.execute("""
                    SELECT id FROM observations WHERE entity_id = %s AND metric_id = %s
                    AND period_type = 'annual' AND period_end = %s AND revision = 1
                    AND source_id = %s AND calculation_version = %s AND value = %s
                """, (entity_id, metric, params[3], adapter.id, VERSION, value)).fetchone()
                if not row:
                    raise ValueError("Existing observation differs; assign a new revision")
            lookup[(year, metric)] = row[0]

    year = max(history)
    categories = {row[0]: row[2] for row in METRICS}
    for rule, metric, title, summary, delta, unit, evidence, years in detect(history):
        insight_id = f"{entity_id.lower()}-{rule.lower()}-{year}"
        conn.execute("""
            INSERT INTO insights (id, entity_id, metric_id, category, rule_id, title, summary,
                                  delta, delta_unit, period_end)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
        """, (insight_id, entity_id, metric, categories[metric], rule, title, summary,
              round(delta, 4), unit, date(year, 12, 31)))
        with conn.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO insight_evidence (insight_id, observation_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, [(insight_id, observation) for (y, m), observation in lookup.items()
                  if y >= year - years + 1 and m in evidence])
    return written


def run(conn, adapter):
    started_at = datetime.now(timezone.utc)
    try:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(823102)")
            records = list(adapter.read())
            conn.execute("""
                INSERT INTO sources (id, label, kind, document_ref, raw_payload)
                VALUES (%s, %s, 'mock', %s, %s) ON CONFLICT (id) DO NOTHING
            """, (adapter.id, adapter.label, adapter.document_ref, Jsonb(adapter.payload(records))))
            with conn.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO metrics (id, name, category, unit, formula, display_order)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
                """, METRICS)
            written = sum(write_profile(conn, entity, statements, adapter) for entity, statements in records)
            conn.execute("""
                INSERT INTO data_ingestion_runs (adapter, started_at, status, observations_written)
                VALUES (%s, %s, 'success', %s)
            """, (adapter.id, started_at, written))
    except Exception:
        with conn.transaction():
            conn.execute("""
                INSERT INTO data_ingestion_runs (adapter, started_at, status)
                VALUES (%s, %s, 'failed')
            """, (adapter.id, started_at))
        raise
    LOGGER.info("Mock import completed, %d new observations", written)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with connect() as database:
        migrate(database)
        mode = os.getenv("TRENDS_DATA_MODE", "mock") or "mock"
        if mode == "official":
            written = import_disclosures(database, load_snapshot())
            LOGGER.info("Issuer disclosure import completed, %d new observations", written)
        elif mode == "mock":
            run(database, MockAnnualAdapter())
        else:
            raise ValueError("TRENDS_DATA_MODE must be mock or official")
