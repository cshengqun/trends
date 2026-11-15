"""Synthetic annual statement fixtures. Company names identify demo profiles only."""

from dataclasses import asdict, dataclass

SOURCE_ID = "mock-annual-v1"
START_YEAR = 2016

# Revenue in CNY billions. Margins and cash conversion ratios generate raw amounts.
PROFILES = (
    ("0700.HK", "腾讯控股", "HK", "HKEX", "互联网与社交", (135, 172, 216, 263, 320, 385, 420, 460, 520, 620), (21, 21, 19, 20, 21, 22, 20, 21, 23, 25), (112, 115, 115)),
    ("1810.HK", "小米集团", "HK", "HKEX", "消费电子", (65, 86, 117, 142, 160, 205, 216, 227, 260, 330), (4, 4, 4, 5, 5, 7, 4, 4, 5, 7), (96, 102, 105)),
    ("3690.HK", "美团", "HK", "HKEX", "本地生活服务", (21, 33, 49, 69, 85, 110, 139, 171, 212, 245), (2, 2, 3, 3, 2, 2, 3, 4, 6, 8), (136, 69, 39)),
    ("000333.SZ", "美的集团", "CN", "SZSE", "家用电器", (119, 148, 176, 196, 215, 250, 270, 305, 337, 355), (8, 8, 8, 9, 9, 9, 10, 10, 11, 12), (100, 107, 118)),
    ("600941.SH", "中国移动", "CN", "SSE", "通信服务", (590, 610, 641, 648, 680, 739, 802, 875, 911, 944), (13, 13, 13, 13, 14, 14, 14, 15, 15, 15), (150, 150, 151)),
    ("601318.SH", "中国平安", "CN", "SSE", "保险", (610, 703, 769, 842, 881, 921, 954, 1000, 1070, 1110), (11, 12, 12, 11, 10, 10, 9, 9, 10, 11), (94, 94, 98)),
)


@dataclass(frozen=True)
class AnnualStatement:
    year: int
    currency: str
    revenue: float
    net_income: float
    cost_of_revenue: float | None
    operating_cash: float
    capex: float | None
    assets: float
    liabilities: float


class MockAnnualAdapter:
    id = SOURCE_ID
    label = "Trends 年度财务模拟样本 v1"
    document_ref = "services/data-pipeline/mock_source.py"

    def read(self):
        for symbol, name, market, exchange, industry, revenues, margins, cash_ratios in PROFILES:
            entity = dict(id=symbol, name=name, symbol=symbol, market=market,
                          exchange=exchange, industry=industry)
            statements = []
            for index, (revenue, margin) in enumerate(zip(revenues, margins, strict=True)):
                profit = round(revenue * margin / 100, 4)
                cash_ratio = ([110] * (len(revenues) - 3) + list(cash_ratios))[index]
                assets = revenue * 2
                liability_ratio = (82 - index) if industry == "保险" else (59 - index)
                statements.append(AnnualStatement(
                    START_YEAR + index, "CNY", revenue, profit,
                    None if industry == "保险" else revenue * (0.73 - index * 0.004),
                    round(profit * cash_ratio / 100, 4),
                    None if industry == "保险" else revenue * 0.036,
                    assets, assets * liability_ratio / 100,
                ))
            yield entity, statements

    @staticmethod
    def payload(records):
        return [
            {"entity": entity, "statements": [asdict(statement) for statement in statements]}
            for entity, statements in records
        ]
