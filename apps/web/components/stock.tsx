"use client";

import { CircleHelp } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Chart } from "./chart";
import { State } from "./common";
import { displayDate, fmt, marketName, metricUnit, metricValue, periodLabel, type EntityDetail, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";
import { comparisonWeeks, longTrendWeeks, rsiWeeks, shortTrendWeeks, weeklyInsights, weeklyInsightWindows } from "@/lib/weekly-insights";

const quarterlyCharts = [
  { title: "营收与利润", unit: "billion", note: "单季营业收入与归母净利润", metrics: [
    { id: "revenue", name: "营收", empty: "暂无可核实的单季营收" },
    { id: "net_income", name: "利润", empty: "暂无可核实的单季归母净利润" },
  ] },
  { title: "营收增长率与利润增长率", unit: "%", note: "同币种单季同比，利润增长率要求基期利润为正", metrics: [
    { id: "revenue_growth", name: "营收增长率", empty: "暂无可比较的上年同期营收" },
    { id: "profit_growth", name: "利润增长率", empty: "暂无可比较的上年同期盈利数据" },
  ] },
  { title: "PE", unit: "倍", note: "季末市盈率（TTM），亏损时留空", metrics: [
    { id: "pe_ttm", name: "PE", empty: "暂无可用的季末 PE" },
  ] },
  { title: "股息率", unit: "%", note: "季末近 12 个月现金股息收益率", metrics: [
    { id: "dividend_yield", name: "股息率", empty: "暂无可核实的季末股息率" },
  ] },
] as const;

type Dashboard = { end_date: string; points: Observation[] };
type QuarterlyChart = typeof quarterlyCharts[number];

export function Stock({ symbol }: { symbol: string }) {
  const encoded = encodeURIComponent(symbol);
  const entity = useData<EntityDetail>("/entities/" + encoded);
  const dashboard = useData<Dashboard>(entity.status === "success" ? "/entities/" + encoded + "/quarterly" : null);
  return <>
    {entity.status === "loading" ? <State type="loading" /> : entity.status === "error" ?
      <State type="error" message={entity.message} retry={entity.retry} /> : <>
      <div className="stock-heading">
        <div className="stock-heading-title">
          <h1>{entity.data.name}</h1>
          <span className="eyebrow mono">{entity.data.symbol}</span>
        </div>
        <p>{marketName(entity.data.market)} · {entity.data.exchange} · {entity.data.industry}</p>
      </div>
      {entity.data.profile && <section className="panel company-profile" aria-label="公司业务">
        <div className="company-profile-grid">
          <div><h2>商业模式</h2><p>{entity.data.profile.business_model}</p></div>
          <div><h2>目标用户</h2><p>{entity.data.profile.target_users}</p></div>
        </div>
        <a className="text-link" href={entity.data.profile.source_url} target="_blank" rel="noreferrer">
          资料来源 · {entity.data.profile.source_label}
        </a>
      </section>}
      <WeeklyPrice symbol={symbol} />
      {dashboard.status === "loading" ? <State type="loading" /> : dashboard.status === "error" ?
        <State type="error" message={dashboard.message} retry={dashboard.retry} /> : <QuarterlyDashboard {...dashboard.data} />}
    </>}
  </>;
}

function WeeklyPrice({ symbol }: { symbol: string }) {
  const params = new URLSearchParams({ entity_id: symbol, metric_id: "stock_price", period: "weekly" });
  const series = useData<Observation[]>("/series?" + params);
  const points = series.status === "success" ? series.data : [];
  const latest = points.at(-1);
  return <section className="panel weekly-price" aria-label="股价周线">
    <h2>股价周线</h2>
    <p className="quarterly-note">近两年 · 每周最后一个交易日 · 未复权收盘价</p>
    {series.status === "loading" ? <State type="loading" /> : series.status === "error" ?
      <State type="error" message={series.message} retry={series.retry} /> : !latest ?
        <State type="empty" message="暂无股价记录" /> : <>
        <div className="quarterly-value">
          <strong className="mono">{fmt(latest.value, 3)}</strong>
          <span>{latest.currency} · {displayDate(latest.market_date ?? latest.period_end)}</span>
        </div>
        <Chart points={points} unit="price" label="股价" axisUnit={latest.currency} period="weekly" />
        <a className="text-link weekly-price-source" href={latest.document_ref} target="_blank" rel="noreferrer">
          {latest.source_label}
        </a>
        <WeeklyInsights points={points} currency={latest.currency} />
      </>}
  </section>;
}

function WeeklyInsights({ points, currency }: { points: Observation[]; currency: string }) {
  const { close, trend, momentum, range, weeks } = weeklyInsights(points);
  if (close === undefined) return null;

  const shortAverage = `${shortTrendWeeks} 周均线`;
  const longAverage = `${longTrendWeeks} 周均线`;
  const cards = [
    {
      title: "均线趋势",
      description: `比较最新周收盘价和 ${shortTrendWeeks} 周、${longTrendWeeks} 周均线，判断中期趋势方向。收盘价、短均线、长均线依次由高到低为多头排列，依次由低到高为空头排列。`,
      required: weeklyInsightWindows.trend,
      result: trend && {
        label: close > trend.short && trend.short > trend.long ? "收盘与均线呈多头排列" :
          close < trend.short && trend.short < trend.long ? "收盘与均线呈空头排列" : "收盘与均线方向未同步",
        evidence: `${shortAverage} ${fmt(trend.short, 3)} · ${longAverage} ${fmt(trend.long, 3)} ${currency}`,
      },
    },
    {
      title: "动量（RSI）",
      description: `用 ${rsiWeeks} 周平滑后的平均涨幅与跌幅衡量价格动量。接近 100 表示上涨动量强，接近 0 表示下跌动量强。强趋势中，RSI 可能持续处于超买或超卖区。`,
      required: weeklyInsightWindows.momentum,
      result: momentum === null ? null : {
        label: momentum >= 70 ? "处于超买区" : momentum <= 30 ? "处于超卖区" : "处于中性区",
        evidence: `RSI(${rsiWeeks}) 为 ${fmt(momentum)} · 超买 ≥ 70，超卖 ≤ 30`,
      },
    },
    {
      title: "收盘区间",
      description: `把最新周收盘价与此前 ${comparisonWeeks} 周的最高和最低收盘价比较，观察价格是否走出原有区间。突破后可继续观察后续周收盘能否维持在原区间之外。`,
      required: weeklyInsightWindows.range,
      result: range && {
        label: close > range.high ? "收盘突破区间上沿" :
          close < range.low ? "收盘跌破区间下沿" : "收盘处于区间内",
        evidence: `此前 ${comparisonWeeks} 周收盘范围 ${fmt(range.low, 3)}–${fmt(range.high, 3)} ${currency}`,
      },
    },
  ];

  return <section className="weekly-insights" aria-label="周线技术洞察">
    <h3>周线技术洞察</h3>
    <p className="quarterly-note">按有收盘记录的交易周计算。除权除息可能影响未复权数据的结果。</p>
    <ul className="weekly-insight-grid">
      {cards.map(({ title, description, result, required }) => <li key={title}>
        <WeeklyInsightTitle title={title} description={description} />
        {result ? <><strong>{result.label}</strong><p>{result.evidence}</p></> :
          <p>需要 {required} 周收盘记录，当前有 {weeks} 周。</p>}
      </li>)}
    </ul>
  </section>;
}

function WeeklyInsightTitle({ title, description }: { title: string; description: string }) {
  const id = useId();
  const element = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function dismissOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function dismissOutside(event: PointerEvent) {
      if (event.target instanceof Node && !element.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("keydown", dismissOnEscape);
    document.addEventListener("pointerdown", dismissOutside);
    return () => {
      document.removeEventListener("keydown", dismissOnEscape);
      document.removeEventListener("pointerdown", dismissOutside);
    };
  }, [open]);

  return <div ref={element} className="weekly-insight-title"
    onPointerLeave={(event) => { if (event.pointerType === "mouse") setOpen(false); }}>
    <h4><button type="button" aria-describedby={id}
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setOpen(true); }}
      onFocus={(event) => { if (event.currentTarget.matches(":focus-visible")) setOpen(true); }}
      onBlur={() => setOpen(false)}
      onClick={() => setOpen((visible) => !visible)}>
      {title}<CircleHelp aria-hidden="true" size={13} />
    </button></h4>
    <div id={id} role="tooltip" className="weekly-insight-tooltip" hidden={!open}>
      <span>{description}</span>
    </div>
  </div>;
}

function QuarterlyDashboard({ end_date, points }: Dashboard) {
  const endYear = Number(end_date.slice(0, 4));
  const endQuarter = Math.ceil(Number(end_date.slice(5, 7)) / 3);
  const startMonth = new Date(Date.UTC(endYear, (endQuarter - 12) * 3 + 2, 1)).toISOString().slice(0, 10);
  return <>
    <p className="quarterly-period">近 3 年 · {periodLabel(startMonth, "quarterly")} 至 {periodLabel(end_date, "quarterly")}</p>
    <div className="quarterly-grid">
      {quarterlyCharts.map((chart) =>
        <QuarterlyCard key={chart.title} chart={chart} points={points} startDate={startMonth} endDate={end_date} />
      )}
    </div>
  </>;
}

function QuarterlyCard({ chart, points, startDate, endDate }: {
  chart: QuarterlyChart; points: Observation[]; startDate: string; endDate: string;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const { title, unit, note, metrics } = chart;
  const comparison = metrics.length > 1;
  const series = metrics.map((metric, index) => {
    const observations = points.filter((point) => point.metric_id === metric.id);
    return { ...metric, label: metric.name, points: observations, latest: observations.at(-1),
      color: index === 0 ? "#64efbc" : "#b5adff" };
  }).filter((metric) => selected === null || selected === metric.id);
  const axisUnit = metricUnit(unit, series.find(({ latest }) => latest)?.latest?.currency);

  return <section className="panel quarterly-card" aria-label={title}>
    <h2>{title}</h2>
    <p className="quarterly-note">{note}</p>
    {comparison ? <div className="tabs quarterly-filters" role="group" aria-label="显示指标">
      <button type="button" aria-pressed={selected === null} onClick={() => setSelected(null)}>全部</button>
      {metrics.map((metric) => <button key={metric.id} type="button" aria-pressed={selected === metric.id}
        onClick={() => setSelected(metric.id)}>{metric.name}</button>)}
    </div> : null}
    <div className={comparison ? "quarterly-summaries" : undefined}>
      {series.map(({ id, label, latest, color, empty }) => <div key={id}>
        {comparison ? <div className="quarterly-series-name">
          <span aria-hidden="true" style={{ backgroundColor: color }} />{label}
        </div> : null}
        <div className="quarterly-value">
          <strong className="mono">{latest ? metricValue(latest.value, unit) : "—"}</strong>
          {latest ? <span>{metricUnit(unit, latest.currency)} · {periodLabel(latest.period_end, "quarterly")}</span> :
            comparison ? <span>{empty}</span> : null}
        </div>
      </div>)}
    </div>
    <div className="quarterly-plot">
      <Chart {...(comparison ? { series } : { points: series[0].points })}
        unit={unit} label={series.map(({ label }) => label).join("与")} axisUnit={axisUnit}
        period="quarterly" startDate={startDate} endDate={endDate} />
      {!comparison && !series[0].latest ? <span className="quarterly-empty">{series[0].empty}</span> : null}
    </div>
  </section>;
}
