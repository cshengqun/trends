ALTER TABLE observations DROP CONSTRAINT observations_period_type_check;
ALTER TABLE observations ADD CONSTRAINT observations_period_type_check
    CHECK (period_type IN ('annual', 'quarterly', 'monthly'));

ALTER TABLE metrics DROP CONSTRAINT metrics_unit_check;
ALTER TABLE metrics ADD CONSTRAINT metrics_unit_check
    CHECK (unit IN ('billion', '%', 'million_users'));

ALTER TABLE insights ADD COLUMN period_type text NOT NULL DEFAULT 'annual'
    CHECK (period_type IN ('annual', 'quarterly', 'monthly'));

CREATE INDEX observations_by_quality ON observations
    (quality_status, entity_id, metric_id, period_type, period_end DESC, revision DESC);
