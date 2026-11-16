"use client";

import { useState } from "react";
import { Chart } from "./chart";
import { State } from "./common";
import { displayDate, fmt, marketName, metricUnit, metricValue, periodLabel, type EntityDetail, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";

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
      </>}
  </section>;
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
