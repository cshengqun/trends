"""Compare the current disclosure snapshot with the Lixinger financial API."""

import argparse
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SNAPSHOT = Path(__file__).with_name("data") / "disclosures.json"
SCALES = {"yuan": 1, "thousand": 1000, "million": 10**6, "billion": 10**9}
PERIOD_FIELDS = {"quarterly": ("q", "c"), "semiannual": ("hy", "c"), "annual": ("y", "t")}


def field_candidates(sector):
    revenue = ("toi", "oi") if sector == "non_financial" else ("oi",)
    profit = ("npatshaoehopc", "npatoshopc")
    return {"revenue": revenue, "net_income": profit}


def fetch_reports(token, market, sector, code, start, end, fields):
    metrics = [
        f"{granularity}.ps.{field}.{expression}"
        for granularity, expression in PERIOD_FIELDS.values()
        for candidates in fields.values()
        for field in candidates
    ]
    request = Request(
        f"https://open.lixinger.com/api/{market.lower()}/company/fs/{sector}",
        data=json.dumps({
            "token": token, "stockCodes": [code], "startDate": start.isoformat(),
            "endDate": end.isoformat(), "metricsList": metrics,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=25) as response:
        body = json.load(response, parse_float=Decimal)
    if body.get("code") != 1 or not isinstance(body.get("data"), list):
        raise ValueError("Provider rejected the request or returned an invalid response")
    if any(row.get("stockCode") != code for row in body["data"]):
        raise ValueError("Unexpected stock code in the provider response")
    return body["data"]


def compare(reports, baseline, fields):
    coverage = {period: {} for period in PERIOD_FIELDS}
    comparisons = []
    for period, (granularity, expression) in PERIOD_FIELDS.items():
        for metric, candidates in fields.items():
            for field in candidates:
                field_name = f"{granularity}.ps.{field}.{expression}"
                observed = {}
                for report in reports:
                    value = report.get(granularity, {}).get("ps", {}).get(field, {}).get(expression)
                    if value is None:
                        continue
                    end = date.fromisoformat(report["date"][:10]).isoformat()
                    observed.setdefault(end, set()).add((report.get("currency"), value))
                coverage[period][field_name] = sorted(observed)
                for (baseline_period, end, baseline_metric), (currency, expected) in baseline.items():
                    if (period, metric) != (baseline_period, baseline_metric):
                        continue
                    points = observed.get(end, set())
                    if not points:
                        status = "missing"
                    elif len(points) > 1:
                        status = "ambiguous"
                    else:
                        actual_currency, actual = next(iter(points))
                        if actual_currency != currency:
                            status = "currency_mismatch"
                        else:
                            status = "exact_match" if actual == expected else "value_differs"
                    comparisons.append({"period_end": end, "field": field_name, "status": status})
    return {"coverage": coverage, "comparisons": comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--symbol", action="append", help="Company symbol from the Trends watchlist")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be on or before --end")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    companies = {company[0]: company for company in snapshot["companies"]}
    symbols = args.symbol or list(companies)
    if set(symbols) - companies.keys():
        parser.error("Unknown symbol in the Trends watchlist")
    token = os.environ.get("LIXINGER_TOKEN")
    if not token:
        parser.error("Set LIXINGER_TOKEN in the environment")

    result = {}
    for symbol in symbols:
        _, _, market, _, industry = companies[symbol]
        sector = {"银行": "bank", "保险": "insurance"}.get(industry, "non_financial")
        code = symbol.split(".")[0]
        if market == "HK":
            code = code.zfill(5)
        fields = field_candidates(sector)
        baseline = {
            (row["period"], row["end"], metric): (row["currency"], Decimal(value) * SCALES[row["scale"]])
            for filing in snapshot["filings"] if filing["symbol"] == symbol
            for row in filing["rows"] if args.start.isoformat() <= row["end"] <= args.end.isoformat()
            for metric, value in row["values"].items() if metric in fields
        }
        try:
            reports = fetch_reports(token, market, sector, code, args.start, args.end, fields)
            result[symbol] = compare(reports, baseline, fields)
        except (URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
            result[symbol] = {"error": type(error).__name__}
    print(json.dumps(result, indent=2))
    return int(any("error" in company for company in result.values()))


if __name__ == "__main__":
    raise SystemExit(main())
