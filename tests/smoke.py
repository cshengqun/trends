"""Verify a running Trends deployment via HTTP and Chromium."""

import json
import sys
import time
from urllib.error import URLError
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
    mini = api("/series", entity_id="0100.HK", metric_id="revenue", period="annual")
    assert any(row["period_end"] == "2025-12-31" and row["currency"] == "USD" and row["value"] == 0.079038 for row in mini)
    tencent = api("/series", entity_id="0700.HK", metric_id="revenue", period="quarterly")
    assert any(row["period_start"] == "2026-04-01" and row["value"] == 204.785 for row in tencent)
    mau = api("/series", entity_id="1810.HK", metric_id="global_mau", period="monthly")
    months = {row["period_end"]: row["value"] for row in mau}
    assert months.get("2025-12-31") == 754.1 and months.get("2026-06-30") == 766.5
    assert "2026-05-31" not in months
    assert api("/series", entity_id="1810.HK", metric_id="revenue", period="monthly") == []
    assert all(row["quality_status"] == "verified" and row["source_kind"] == "official" and
               row["document_ref"].startswith("https://") and row["published_at"]
               for row in mini + tencent + mau)
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
        expect(page.get_by_role("heading", name="趋势发现")).to_be_visible()
        expect(page.locator(".featured canvas")).to_be_visible(timeout=15000)
        if kind == "official":
            page.get_by_role("link", name="股票探索", exact=True).click()
            search = page.get_by_role("searchbox", name="筛选公司")
            search.fill("小米")
            page.get_by_role("link", name="小米集团", exact=False).first.click()
            expect(page.get_by_role("img", name="营业收入季度趋势图")).to_be_visible()
            page.get_by_role("button", name="年度", exact=True).click()
            expect(page.get_by_role("img", name="营业收入年度趋势图")).to_be_visible()
            page.get_by_label("财务指标").select_option("global_mau")
            expect(page.get_by_role("img", name="全球月活跃用户月度趋势图")).to_be_visible()
            expect(page.get_by_role("link", name="小米 2026 年第二季度业绩公告")).to_be_visible()
            browser.close()
            return
        page.get_by_role("button", name="现金流", exact=True).click()
        page.get_by_role("link", name="利润与现金流背离").click()
        expect(page.get_by_role("heading", name="美团 · 利润与现金流背离")).to_be_visible()
        expect(page.locator("tbody tr")).to_have_count(6)
        page.get_by_role("link", name="趋势发现", exact=True).first.click()
        top_search = page.locator("header").get_by_role("searchbox")
        top_search.fill("小米")
        top_search.press("Enter")
        expect(page.get_by_role("link", name="小米集团", exact=False).first).to_be_visible()
        page.get_by_role("link", name="小米集团", exact=False).first.click()
        expect(page.get_by_role("heading", name="小米集团")).to_be_visible()
        page.get_by_label("财务指标").select_option("net_margin")
        page.get_by_role("button", name="3 年", exact=True).click()
        page.get_by_role("button", name="柱状图").click()
        expect(page.get_by_role("img", name="净利率年度趋势图")).to_be_visible()
        expect(page.locator(".chart-full canvas")).to_be_visible()

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile.goto(BASE)
        expect(mobile.locator(".featured canvas")).to_be_visible()
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


if __name__ == "__main__":
    kind = verify_api()
    verify_browser(kind)
    print("Trends API and browser smoke checks passed")
