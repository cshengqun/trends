CREATE TABLE earnings_forecasts (
    entity_id text NOT NULL REFERENCES entities,
    metric_id text NOT NULL REFERENCES metrics CHECK (metric_id IN ('revenue', 'net_income')),
    period_type text NOT NULL CHECK (period_type IN ('quarterly', 'semiannual', 'annual')),
    period_end date NOT NULL,
    captured_at timestamptz NOT NULL,
    method text NOT NULL CHECK (method IN ('consensus', 'annual_less_ytd')),
    value numeric NOT NULL,
    currency text NOT NULL CHECK (currency IN ('CNY', 'HKD', 'USD')),
    prior_value numeric,
    analyst_count integer CHECK (analyst_count > 0),
    source_label text NOT NULL,
    source_url text NOT NULL,
    PRIMARY KEY (entity_id, period_type, period_end, metric_id, captured_at, method)
);
