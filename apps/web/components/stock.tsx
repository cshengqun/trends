"use client";

import { ArrowLeft, BarChart3, Database, LineChart } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Chart } from "./chart";
import { SignalCard, State } from "./common";
import { MockLabel } from "./shell";
import { displayDate, marketName, metricUnit, metricValue, type EntityDetail, type Insight, type Metric, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";

export function Stock({ symbol }: { symbol: string }) {
  const [metric, setMetric] = useState("revenue");
  const [range, setRange] = useState(5);
  const [mode, setMode] = useState<"line" | "bar">("line");
  const entity = useData<EntityDetail>("/entities/" + encodeURIComponent(symbol));
  const definitions = useData<Metric[]>("/metrics");
  const seriesQuery = new URLSearchParams({ entity_id: symbol, metric_id: metric, period: "annual" });
  const series = useData<Observation[]>(entity.status === "success" ? "/series?" + seriesQuery.toString() : null);
  const insights = useData<Insight[]>(entity.status === "success" ? "/insights?entity_id=" + encodeURIComponent(symbol) : null);
  const all = series.status === "success" ? series.data : [];
  const latest = all.at(-1);
  const cutoff = latest && range ? Number(latest.period_end.slice(0, 4)) - range + 1 : 0;
  const points = all.filter((point) => Number(point.period_end.slice(0, 4)) >= cutoff);
  const selected = definitions.status === "success" ? definitions.data.find((item) => item.id === metric) : undefined;
  const unit = metricUnit(latest?.unit ?? selected?.unit ?? "", latest?.currency);
  return <>
    <Link href="/stocks" className="back-link"><ArrowLeft size={16} /> 股票探索</Link>
    {entity.status === "loading" ? <State type="loading" /> : entity.status === "error" ?
      <State type="error" message={entity.message} retry={entity.retry} /> : <>
      <div className="page-heading">
        <div className="row gap"><span className="eyebrow mono">{entity.data.symbol} · {entity.data.exchange}</span><MockLabel /></div>
        <h1>{entity.data.name}</h1>
        <p>{marketName(entity.data.market)} · {entity.data.industry} · 最新样本 FY {entity.data.latest_period?.slice(0, 4) ?? "—"} · 入库 {displayDate(entity.data.data_updated_at)}</p>
      </div>
      {entity.data.latest_metrics.length > 0 && <section className="metric-overview" aria-label="最近年度关键指标">
        {entity.data.latest_metrics.filter((item) => ["revenue", "net_margin", "operating_cash", "debt_ratio"].includes(item.metric_id)).map((item) =>
          <button key={item.metric_id} type="button" className={metric === item.metric_id ? "panel metric-tile selected" : "panel metric-tile"}
            aria-pressed={metric === item.metric_id} onClick={() => setMetric(item.metric_id)}>
            <small>{item.name}</small>
            <strong className="mono">{metricValue(item.value, item.unit)} <small>{metricUnit(item.unit, item.currency)}</small></strong>
          </button>)}
      </section>}
      <section className="panel detail-chart">
        <div className="detail-toolbar">
          <div>
            <label className="sr-only" htmlFor="metric-select">财务指标</label>
            {definitions.status === "success" && <select id="metric-select" value={metric} onChange={(event) => setMetric(event.target.value)}>
              {definitions.data.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>}
            {definitions.status === "error" && <State type="error" message={definitions.message} retry={definitions.retry} />}
            {definitions.status === "loading" && <span className="muted">加载指标…</span>}
          </div>
          <div className="row gap">
            <div className="tabs" aria-label="历史范围">
              {[3, 5, 10, 0].map((years) => <button key={years} className={range === years ? "selected" : ""} onClick={() => setRange(years)} aria-pressed={range === years}>{years ? years + " 年" : "全部"}</button>)}
            </div>
            <div className="tabs" aria-label="图表类型">
              <button aria-label="折线图" aria-pressed={mode === "line"} onClick={() => setMode("line")} className={mode === "line" ? "selected" : ""}><LineChart size={16} /></button>
              <button aria-label="柱状图" aria-pressed={mode === "bar"} onClick={() => setMode("bar")} className={mode === "bar" ? "selected" : ""}><BarChart3 size={16} /></button>
            </div>
          </div>
        </div>
        <div className="chart-value">
          <strong className="mono">{latest ? metricValue(latest.value, latest.unit) : "—"}</strong><span>{unit} · 年度</span>
        </div>
        {series.status === "loading" ? <State type="loading" /> : series.status === "error" ?
          <State type="error" message={series.message} retry={series.retry} /> : !points.length ?
          <State type="empty" message="该样本缺少此指标" /> :
          <Chart points={points} unit={latest?.unit ?? ""} label={selected?.name ?? latest?.metric_name ?? "指标"} axisUnit={unit} mode={mode} />}
        <div className="chart-note">{selected?.formula && <span>计算口径 · {selected.formula}</span>}
          <span>当前数据频率 · 年度</span>
        </div>
      </section>
      <section className="section">
        <div className="section-title"><div><h2>趋势洞察</h2><p>基于财务样本的规则检测</p></div></div>
        {insights.status === "loading" ? <State type="loading" /> : insights.status === "error" ?
          <State type="error" message={insights.message} retry={insights.retry} /> : insights.data.length ?
          <div className="signal-grid">{insights.data.map((signal) => <SignalCard insight={signal} key={signal.id} />)}</div> : <State type="empty" />}
      </section>
      <section className="section">
        <div className="section-title"><h2>指标数据来源</h2></div>
        {latest ? <div className="panel source-card"><Database size={19} /><div><strong>{latest.source_label}</strong><p>FY {latest.period_end.slice(0, 4)} · {latest.published_at ? "披露 " + displayDate(latest.published_at) : "无财报披露日期"} · 入库 {displayDate(latest.available_at)} · 计算版本 {latest.calculation_version}</p><code>{latest.document_ref}</code></div><MockLabel /></div> :
          series.status === "loading" ? <State type="loading" /> :
          series.status === "error" ? <State type="error" message={series.message} retry={series.retry} /> : <State type="empty" />}
      </section>
    </>}
  </>;
}
