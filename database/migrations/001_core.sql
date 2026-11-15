CREATE TABLE entities (
    id text PRIMARY KEY,
    kind text NOT NULL DEFAULT 'stock',
    name text NOT NULL,
    symbol text NOT NULL UNIQUE,
    market text NOT NULL,
    exchange text NOT NULL,
    industry text NOT NULL
);

CREATE TABLE metrics (
    id text PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL,
    unit text NOT NULL CHECK (unit IN ('billion', '%')),
    formula text NOT NULL,
    display_order integer NOT NULL
);

CREATE TABLE sources (
    id text PRIMARY KEY,
    label text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('mock', 'official', 'licensed')),
    document_ref text NOT NULL,
    raw_payload jsonb NOT NULL,
    published_at timestamptz,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id text NOT NULL REFERENCES entities,
    metric_id text NOT NULL REFERENCES metrics,
    period_start date NOT NULL,
    period_end date NOT NULL CHECK (period_end >= period_start),
    period_type text NOT NULL CHECK (period_type IN ('annual', 'quarterly')),
    published_at timestamptz,
    available_at timestamptz NOT NULL,
    value numeric NOT NULL,
    currency text NOT NULL,
    unit text NOT NULL,
    source_id text NOT NULL REFERENCES sources,
    calculation_version text NOT NULL,
    quality_status text NOT NULL CHECK (quality_status IN ('mock', 'verified')),
    revision integer NOT NULL CHECK (revision > 0),
    UNIQUE (entity_id, metric_id, period_type, period_end, revision)
);

CREATE TABLE insights (
    id text PRIMARY KEY,
    entity_id text NOT NULL REFERENCES entities,
    metric_id text NOT NULL REFERENCES metrics,
    category text NOT NULL,
    rule_id text NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    delta numeric NOT NULL,
    delta_unit text NOT NULL,
    period_end date NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    method text NOT NULL DEFAULT 'rule',
    data_kind text NOT NULL DEFAULT 'mock'
);

CREATE INDEX insights_by_entity ON insights (entity_id, period_end DESC, id);

CREATE TABLE insight_evidence (
    insight_id text NOT NULL REFERENCES insights ON DELETE CASCADE,
    observation_id bigint NOT NULL REFERENCES observations,
    PRIMARY KEY (insight_id, observation_id)
);

CREATE TABLE data_ingestion_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adapter text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN ('success', 'failed')),
    observations_written integer NOT NULL DEFAULT 0
);
