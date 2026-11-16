ALTER TABLE observations DROP CONSTRAINT observations_period_type_check;
ALTER TABLE observations ADD CONSTRAINT observations_period_type_check
    CHECK (period_type IN ('annual', 'quarterly', 'monthly', 'weekly'));

ALTER TABLE metrics DROP CONSTRAINT metrics_unit_check;
ALTER TABLE metrics ADD CONSTRAINT metrics_unit_check
    CHECK (unit IN ('billion', '%', 'million_users', '倍', 'price'));

INSERT INTO metrics (id, name, category, unit, formula, display_order) VALUES
    ('stock_price', '股价', 'valuation', 'price', '每周最后一个交易日的未复权收盘价', 0)
ON CONFLICT (id) DO NOTHING;
