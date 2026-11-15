ALTER TABLE metrics DROP CONSTRAINT metrics_unit_check;
ALTER TABLE metrics ADD CONSTRAINT metrics_unit_check
    CHECK (unit IN ('billion', '%', 'million_users', '倍'));

INSERT INTO metrics (id, name, category, unit, formula, display_order) VALUES
    ('revenue_growth', '营收增长率', 'growth', '%', '单季营收同比，使用同币种上年同期', 2),
    ('profit_growth', '利润增长率', 'profitability', '%', '单季归母净利润同比，上年同期利润须为正', 4),
    ('pe_ttm', '市盈率（PE TTM）', 'valuation', '倍', '季末最后交易日的滚动市盈率，市盈率非正时留空', 12),
    ('dividend_yield', '股息率', 'valuation', '%', '截至季末最后交易日近 12 个月每股现金股息除以未复权收盘价', 13)
ON CONFLICT (id) DO NOTHING;
