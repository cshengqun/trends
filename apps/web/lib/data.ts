export type Entity = {
  id: string; symbol: string; name: string; market: "HK" | "CN"; exchange: string;
  industry: string; latest_period: string | null; data_updated_at: string | null;
};

export type Metric = {
  id: string; name: string; category: string; unit: string; formula: string;
};

export type Point = { period_end: string; value: number };
export const periods = ["weekly", "monthly", "quarterly", "annual"] as const;
export type Period = typeof periods[number];
export const periodNames: Record<Period, string> = { weekly: "周线", monthly: "月度", quarterly: "季度", annual: "年度" };
export type DataKind = "official" | "mock";
export type LatestMetric = Point & { metric_id: string; name: string; unit: string; currency: string; period_type: Period };
export type EntityDetail = Entity & {
  latest_metrics: LatestMetric[];
  available_series: { metric_id: string; period_type: Period }[];
  profile: { business_model: string; target_users: string; source_label: string; source_url: string } | null;
};
export type Observation = Point & {
  id: number; metric_name: string; metric_id: string; currency: string; unit: string;
  published_at: string | null; available_at: string; source_id: string; source_label: string;
  source_kind: string; document_ref: string; calculation_version: string; quality_status: string;
  market_date?: string | null;
  supporting_documents?: { url: string; label: string }[];
  period_start: string; period_type: Period;
};

export type EarningsEstimate = Point & {
  metric_id: "revenue" | "net_income";
  period_type: "quarterly" | "semiannual" | "annual";
  captured_at: string;
  method: "consensus" | "annual_less_ytd";
  currency: string;
  growth: number | null;
  prior_value: number | null;
  analyst_count: number | null;
  source_label: string;
  source_url: string;
};

export type Insight = {
  id: string; entity_id: string; entity_name: string; symbol: string; category: string;
  rule_id: string; title: string; summary: string; metric_name: string; metric_id: string;
  delta: number; delta_unit: string; period_end: string; generated_at: string; data_updated_at: string | null;
  data_kind: DataKind; method: string; spark: Point[]; period_type: Period; metric_unit: string;
};

export type Overview = {
  company_count: number; insight_count: number; market_count: number;
  latest_period: string | null; last_updated_at: string | null; data_kind: DataKind;
};

export const categories = {
  growth: "成长性",
  profitability: "盈利能力",
  cash_flow: "现金流",
  financial_health: "财务健康",
  valuation: "估值",
  operations: "经营数据",
};

export function categoryName(category: string) {
  return categories[category as keyof typeof categories] ?? category;
}

export function marketName(market: Entity["market"]) {
  return market === "HK" ? "港股" : "A 股";
}

export function fmt(value: number, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits }).format(value);
}

export function deltaLabel(value: number, unit: string) {
  return (value > 0 ? "+" : "") + fmt(value) + (unit === "pp" ? " pp" : "%");
}

export function metricValue(value: number, unit: string) {
  return unit === "billion" ? fmt(value * 10) : fmt(value);
}

export function metricUnit(unit: string, currency = "CNY") {
  if (unit === "billion") return currency === "CNY" ? "亿元 CNY" : "亿 " + currency;
  if (unit === "price") return currency;
  if (unit === "million_users") return "百万用户";
  return unit;
}

export function periodLabel(value: string, period: Period) {
  const year = value.slice(0, 4);
  if (period === "weekly") return value.slice(0, 10);
  if (period === "annual") return "FY " + year;
  if (period === "quarterly") return year + " Q" + Math.ceil(Number(value.slice(5, 7)) / 3);
  return value.slice(0, 7);
}

export function displayDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date(value));
}
