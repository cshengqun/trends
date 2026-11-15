from math import isfinite

VERSION = "annual-v1"

METRICS = (
    ("revenue", "营业收入", "growth", "billion", "年度营收", 1),
    ("revenue_yoy", "营收同比", "growth", "%", "（本期营收 ÷ 上年同期营收 − 1）× 100", 2),
    ("net_income", "归母净利润", "growth", "billion", "年度归母净利润", 3),
    ("net_income_yoy", "净利润同比", "growth", "%", "（本期归母净利润 ÷ 上年同期正值归母净利润 − 1）× 100", 4),
    ("gross_margin", "毛利率", "profitability", "%", "（营业收入 − 营业成本）÷ 营业收入 × 100", 5),
    ("net_margin", "净利率", "profitability", "%", "归母净利润 ÷ 营业收入 × 100", 6),
    ("roe", "净资产收益率", "profitability", "%", "归母净利润 ÷ 期初期末平均净资产 × 100（模拟口径）", 7),
    ("operating_cash", "经营现金流", "cash_flow", "billion", "年度经营活动现金流净额", 8),
    ("free_cash", "自由现金流", "cash_flow", "billion", "经营活动现金流净额 − 资本开支", 9),
    ("debt_ratio", "资产负债率", "financial_health", "%", "总负债 ÷ 总资产 × 100", 10),
)


def growth(current, previous):
    return (current / previous - 1) * 100 if previous > 0 else None


def calculate(statements):
    previous = None
    result = {}
    for row in statements:
        if (previous and (row.year <= previous.year or row.currency != previous.currency)):
            raise ValueError("Annual statements must be unique, ordered and in one currency")
        required = (row.revenue, row.net_income, row.operating_cash, row.assets, row.liabilities)
        optional = (row.capex, row.cost_of_revenue)
        if (any(not isfinite(value) for value in required)
                or any(value is not None and (not isfinite(value) or value < 0) for value in optional)
                or row.revenue <= 0 or row.assets <= 0 or not 0 <= row.liabilities <= row.assets
                or row.currency != "CNY"):
            raise ValueError(f"Invalid statement for {row.year}")
        comparable = previous is not None and previous.year == row.year - 1
        equity = row.assets - row.liabilities
        average_equity = (equity + previous.assets - previous.liabilities) / 2 if comparable else 0
        values = {
            "revenue": row.revenue,
            "revenue_yoy": growth(row.revenue, previous.revenue) if comparable else None,
            "net_income": row.net_income,
            "net_income_yoy": growth(row.net_income, previous.net_income) if comparable else None,
            "gross_margin": (1 - row.cost_of_revenue / row.revenue) * 100 if row.cost_of_revenue is not None else None,
            "net_margin": row.net_income / row.revenue * 100,
            "roe": row.net_income / average_equity * 100 if average_equity > 0 else None,
            "operating_cash": row.operating_cash,
            "free_cash": row.operating_cash - row.capex if row.capex is not None else None,
            "debt_ratio": row.liabilities / row.assets * 100,
        }
        result[row.year] = {metric: round(value, 4) for metric, value in values.items() if value is not None}
        previous = row
    return result


def detect(history):
    year = max(history)
    if not all(y in history for y in range(year - 2, year + 1)):
        return
    prior, before, current = [history[y] for y in range(year - 2, year + 1)]
    if all("revenue_yoy" in row for row in (prior, before, current)):
        yearly_growth = current["revenue_yoy"] - before["revenue_yoy"]
        if yearly_growth >= 5 and current["revenue_yoy"] > before["revenue_yoy"] >= prior["revenue_yoy"]:
            yield "R1", "revenue_yoy", "营收增长加速", "营收同比增速连续提升，最新年度较上年提高。", yearly_growth, "pp", ("revenue_yoy",), 3
        if yearly_growth <= -3 and current["revenue_yoy"] < before["revenue_yoy"] <= prior["revenue_yoy"]:
            yield "R2", "revenue_yoy", "营收增长放缓", "营收同比增速连续回落，最新年度较上年下降。", yearly_growth, "pp", ("revenue_yoy",), 3
    margin_delta = current["net_margin"] - prior["net_margin"]
    if before["net_margin"] != prior["net_margin"] and (
        current["net_margin"] > before["net_margin"] > prior["net_margin"] or
        current["net_margin"] < before["net_margin"] < prior["net_margin"]
    ) and abs(margin_delta) >= 2:
        title = "净利率持续改善" if margin_delta > 0 else "净利率持续下降"
        yield "R3", "net_margin", title, "净利率连续两年同向变化，区间变化达到规则阈值。", margin_delta, "pp", ("net_margin",), 3
    cash_delta = growth(current["operating_cash"], prior["operating_cash"])
    if (current["net_income"] > before["net_income"] > prior["net_income"]
            and current["operating_cash"] < before["operating_cash"] < prior["operating_cash"]
            and cash_delta is not None):
        yield "R4", "operating_cash", "利润与现金流背离", "归母净利润连续上升，经营现金流同期连续下降。", cash_delta, "%", ("operating_cash", "net_income"), 3
    if len(history) >= 5:
        historical_min = min(row["debt_ratio"] for y, row in history.items() if y != year)
        if current["debt_ratio"] < historical_min:
            yield "R5", "debt_ratio", "资产负债率创样本新低", "最新年度资产负债率低于此前全部样本年度。", current["debt_ratio"] - historical_min, "pp", ("debt_ratio",), year - min(history) + 1
