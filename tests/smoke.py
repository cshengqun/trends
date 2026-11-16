"""Verify a running Trends deployment via HTTP and Chromium."""

import json
import sys
import time
from datetime import date, timedelta
from urllib.error import URLError
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"


def api(path, **query):
    suffix = "?" + urlencode(query) if query else ""
    with urlopen(BASE + "/api/v1" + path + suffix, timeout=8) as response:
        return json.load(response)["data"]


def verify_api():
    for attempt in range(60):
        try:
            health = api("/health")
            assert health["database"] == "postgresql"
            break
        except (URLError, TimeoutError):
            if attempt == 59:
                raise
            time.sleep(3)

    if health["data_kind"] == "official":
        verify_disclosures_api()
        return "official"

    overview = api("/overview")
    assert overview["company_count"] == 6 and overview["market_count"] == 2
    assert overview["latest_period"] == "2025-12-31" and overview["data_kind"] == "mock"
    assert [entity["symbol"] for entity in api("/entities", q="腾讯", market="HK")] == ["0700.HK"]
    assert len(api("/metrics")) == 10
    assert api("/entities/0700.HK")["exchange"] == "HKEX"
    observations = api("/series", entity_id="0700.HK", metric_id="revenue", period="annual")
    assert len(observations) == 10 and observations[0]["period_end"] == "2016-12-31"
    assert all(row["quality_status"] == "mock" and row["currency"] == "CNY" and
               row["published_at"] is None for row in observations)
    assert not api("/series", entity_id="0700.HK", metric_id="revenue", period="quarterly")
    signals = api("/insights", limit=100)
    assert len(signals) == overview["insight_count"]
    assert {signal["rule_id"] for signal in signals} == {"R1", "R2", "R3", "R4", "R5"}
    cash_signal, = api("/insights", category="cash_flow")
    path = "/insights/" + cash_signal["id"]
    assert api(path)["method"] == "rule"
    evidence = api(path + "/evidence")
    assert len(evidence) == 6
    assert {row["metric_id"] for row in evidence} == {"net_income", "operating_cash"}
    assert all(row["source_kind"] == "mock" and row["calculation_version"] == "annual-v1"
               for row in evidence)
    return "mock"


def verify_disclosures_api():
    expected = {
        "0100.HK", "2513.HK", "9880.HK", "9988.HK", "3690.HK", "1810.HK", "0700.HK",
        "000333.SZ", "600036.SH", "002371.SZ", "600900.SH", "600941.SH", "601318.SH",
        "600938.SH", "600887.SH", "300866.SZ", "300750.SZ",
    }
    overview = api("/overview")
    assert overview["data_kind"] == "official" and overview["company_count"] >= len(expected)
    assert expected.issubset({item["symbol"] for item in api("/entities", limit=100)})
    assert [item["symbol"] for item in api("/entities", q="00100")] == ["0100.HK"]
    for symbol in sorted(expected):
        profile = api("/entities/" + symbol)["profile"]
        assert profile["business_model"] and profile["target_users"], symbol
        assert profile["source_label"] and profile["source_url"].startswith("https://"), symbol
    if any(metric["id"] == "stock_price" for metric in api("/metrics")):
        for symbol in sorted(expected):
            weekly = api("/series", entity_id=symbol, metric_id="stock_price", period="weekly")
            assert 0 < len(weekly) <= 104, symbol
            assert len({row["period_end"] for row in weekly}) == len(weekly), symbol
            for row in weekly:
                friday = date.fromisoformat(row["period_end"])
                trading_day = date.fromisoformat(row["market_date"])
                assert friday.weekday() == 4 and friday - timedelta(days=4) <= trading_day <= friday
                assert row["value"] > 0 and row["currency"] == ("HKD" if symbol.endswith(".HK") else "CNY")
    mini = api("/series", entity_id="0100.HK", metric_id="revenue", period="annual")
    assert any(row["period_end"] == "2025-12-31" and row["currency"] == "USD" and row["value"] == 0.079038 for row in mini)
    tencent = api("/series", entity_id="0700.HK", metric_id="revenue", period="quarterly")
    assert any(row["period_start"] == "2026-04-01" and row["value"] == 204.785 for row in tencent)
    domestic_quarters = {
        "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30",
        "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30",
    }
    hong_kong_quarters = domestic_quarters - {"2026-09-30"} | {"2024-09-30"}
    for symbol in expected - {"0100.HK", "2513.HK", "9880.HK"}:
        expected_quarters = hong_kong_quarters if symbol.endswith(".HK") else domestic_quarters
        for metric in ("revenue", "net_income"):
            quarterly = api("/series", entity_id=symbol, metric_id=metric, period="quarterly")
            assert expected_quarters.issubset({row["period_end"] for row in quarterly}), (symbol, metric)
    midea = api("/series", entity_id="000333.SZ", metric_id="revenue", period="quarterly")
    derived = next(row for row in midea if row["period_end"] == "2026-06-30")
    assert derived["value"] == 128.943889 and derived["supporting_documents"][0]["url"].startswith("https://")
    dashboard = api("/entities/000333.SZ/quarterly")
    by_metric = {}
    for point in dashboard["points"]:
        by_metric.setdefault(point["metric_id"], {})[point["period_end"]] = point
    assert dashboard["end_date"] >= "2026-09-30"
    current = by_metric["revenue_growth"]["2026-09-30"]
    revenue = by_metric["revenue"]
    expected_growth = round((Decimal(str(revenue["2026-09-30"]["value"])) /
                             Decimal(str(revenue["2025-09-30"]["value"])) - 1) * 100, 6)
    assert Decimal(str(current["value"])) == expected_growth
    assert len(current["supporting_documents"]) >= 1
    if dashboard["end_date"] == "2026-09-30":
        assert len(revenue) == 12 and "2023-12-31" in revenue
    assert by_metric["profit_growth"]["2026-09-30"]["unit"] == "%"
    mau = api("/series", entity_id="1810.HK", metric_id="global_mau", period="monthly")
    months = {row["period_end"]: row["value"] for row in mau}
    assert months.get("2025-12-31") == 754.1 and months.get("2026-06-30") == 766.5
    assert "2026-05-31" not in months
    assert api("/series", entity_id="1810.HK", metric_id="revenue", period="monthly") == []
    assert all(row["quality_status"] == "verified" and row["document_ref"].startswith("https://")
               for row in mini + tencent + mau)
    assert all(row["source_kind"] == "official" and row["published_at"] for row in mini + mau)
    assert all(row["source_kind"] in ("official", "licensed") for row in tencent)
    if "pe_ttm" in by_metric:
        for metric in ("pe_ttm", "dividend_yield"):
            market_points = by_metric[metric].values()
            assert all(point["source_kind"] == "licensed" and point["market_date"] <= point["period_end"]
                       for point in market_points)
    signals = api("/insights", entity_id="0700.HK", limit=100)
    signal = next(item for item in signals if item["metric_id"] == "revenue" and
                  item["period_type"] == "quarterly" and item["period_end"] == "2026-06-30")
    evidence = api("/insights/" + signal["id"] + "/evidence")
    assert signal["data_kind"] == "official"
    assert {row["period_end"] for row in evidence} == {"2025-06-30", "2026-06-30"}


def verify_browser(kind):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(BASE)
        expect(page.get_by_role("heading", name="股票探索")).to_be_visible()
        expect(page.get_by_role("link", name="趋势发现", exact=True)).to_have_count(0)
        search = page.get_by_role("searchbox", name="筛选公司")
        search.fill("小米")
        page.get_by_role("link", name="小米集团", exact=False).first.click()
        expect(page.get_by_role("heading", name="小米集团")).to_be_visible()
        for metric in ("营收", "营收增长率", "利润", "利润增长率", "PE", "股息率"):
            expect(page.get_by_role("img", name=metric + "季度趋势图", exact=True)).to_be_visible()
        expect(page.locator(".quarterly-plot canvas")).to_have_count(6)
        expect(page.get_by_text("近 3 年", exact=False)).to_be_visible()
        if kind == "official":
            expect(page.get_by_role("heading", name="商业模式")).to_be_visible()
            expect(page.get_by_role("heading", name="目标用户")).to_be_visible()
            order = page.locator(".company-profile, .weekly-price, .quarterly-grid").evaluate_all(
                "(nodes) => nodes.map((node) => node.classList.contains('company-profile') ? 'company' : "
                "node.classList.contains('weekly-price') ? 'price' : 'quarterly')"
            )
            assert order == ["company", "price", "quarterly"]
            if any(metric["id"] == "stock_price" for metric in api("/metrics")):
                expect(page.get_by_role("img", name="股价周线趋势图")).to_be_visible()
            expect(page.get_by_role("link", name="资料来源 · 小米集团 2025 年年度报告")).to_be_visible()
            page.get_by_text("指标数据来源", exact=True).click()
            expect(page.get_by_role("link", name="小米 2026 年第二季度业绩公告")).to_be_visible()

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile.goto(page.url)
        expect(mobile.get_by_role("heading", name="小米集团")).to_be_visible()
        expect(mobile.get_by_role("img", name="营收季度趋势图", exact=True)).to_be_visible()
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


if __name__ == "__main__":
    kind = verify_api()
    verify_browser(kind)
    print("Trends API and browser smoke checks passed")
