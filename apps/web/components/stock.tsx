"use client";

import { ArrowLeft, BarChart3, Database, LineChart } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Chart } from "./chart";
import { SignalCard, State } from "./common";
import { DataLabel } from "./shell";
import { displayDate, marketName, metricUnit, metricValue, periodLabel, periodNames, periods, type Period, type EntityDetail, type Insight, type Metric, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";

export function Stock({ symbol }: { symbol: string }) {
  const [metric, setMetric] = useState("revenue");
  const [chosenPeriod, setPeriod] = useState<Period>();
  const [range, setRange] = useState(2);
  const [mode, setMode] = useState<"line" | "bar">("line");
  const entity = useData<EntityDetail>("/entities/" + encodeURIComponent(symbol));
  const definitions = useData<Metric[]>("/metrics");
  const available = entity.status === "success" ? entity.data.available_series : [];
  const availablePeriods = periods.filter((period) => available.some((row) => row.metric_id === metric && row.period_type === period));
  const period = chosenPeriod && availablePeriods.includes(chosenPeriod) ? chosenPeriod : availablePeriods[0];
  const seriesQuery = new URLSearchParams({ entity_id: symbol, metric_id: metric, period: period ?? "annual" });
  const series = useData<Observation[]>(period ? "/series?" + seriesQuery.toString() : null);
  const insights = useData<Insight[]>(entity.status === "success" ? "/insights?entity_id=" + encodeURIComponent(symbol) : null);
  const all = series.status === "success" ? series.data : [];
  const latest = all.at(-1);
  const cutoff = latest && range ? (Number(latest.period_end.slice(0, 4)) - range) + latest.period_end.slice(4) : "";
  const points = all.filter((point) => point.period_end > cutoff);
  const selected = definitions.status === "success" ? definitions.data.find((item) => item.id === metric) : undefined;
  const unit = metricUnit(latest?.unit ?? selected?.unit ?? "", latest?.currency);
  const filings = [...new Map([...points].reverse().map((point) => [point.source_id, point])).values()];
  function selectMetric(value: string) {
    setMetric(value);
    setPeriod(undefined);
  }
  return <>
    <Link href="/stocks" className="back-link"><ArrowLeft size={16} /> 股票探索</Link>
    {entity.status === "loading" ? <State type="loading" /> : entity.status === "error" ?
      <State type="error" message={entity.message} retry={entity.retry} /> : <>
      <div className="page-heading">
        <div className="row gap"><span className="eyebrow mono">{entity.data.symbol} · {entity.data.exchange}</span><DataLabel /></div>
        <h1>{entity.data.name}</h1>
        <p>{marketName(entity.data.market)} · {entity.data.industry} · 最新数据期间 {entity.data.latest_period ?? "—"}</p>
      </div>
      {entity.data.latest_metrics.length > 0 && <section className="metric-overview" aria-label="最新关键指标">
        {entity.data.latest_metrics.filter((item) => ["revenue", "net_income", "global_mau", "net_margin", "operating_cash", "debt_ratio"].includes(item.metric_id)).map((item) =>
          <button key={item.metric_id} type="button" className={metric === item.metric_id ? "panel metric-tile selected" : "panel metric-tile"}
            aria-pressed={metric === item.metric_id} onClick={() => selectMetric(item.metric_id)}>
            <small>{item.name} · {periodLabel(item.period_end, item.period_type)}</small>
            <strong className="mono">{metricValue(item.value, item.unit)} <small>{metricUnit(item.unit, item.currency)}</small></strong>
          </button>)}
      </section>}
      <section className="panel detail-chart">
        <div className="detail-toolbar">
          <div>
            <label className="sr-only" htmlFor="metric-select">财务指标</label>
            {definitions.status === "success" && <select id="metric-select" value={metric} onChange={(event) => selectMetric(event.target.value)}>
              {definitions.data.filter((item) => available.some((row) => row.metric_id === item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>}
            {definitions.status === "error" && <State type="error" message={definitions.message} retry={definitions.retry} />}
            {definitions.status === "loading" && <span className="muted">加载指标…</span>}
          </div>
          <div className="row gap">
            <div className="tabs" aria-label="历史范围">
              {[2, 3, 5, 10, 0].map((years) => <button key={years} className={range === years ? "selected" : ""} onClick={() => setRange(years)} aria-pressed={range === years}>{years ? years + " 年" : "全部"}</button>)}
            </div>
            <div className="tabs" aria-label="图表类型">
              <button aria-label="折线图" aria-pressed={mode === "line"} onClick={() => setMode("line")} className={mode === "line" ? "selected" : ""}><LineChart size={16} /></button>
              <button aria-label="柱状图" aria-pressed={mode === "bar"} onClick={() => setMode("bar")} className={mode === "bar" ? "selected" : ""}><BarChart3 size={16} /></button>
            </div>
          </div>
        </div>
        <div className="tabs" aria-label="数据频率">
          {availablePeriods.map((value) => <button key={value} className={period === value ? "selected" : ""}
            aria-pressed={period === value} onClick={() => setPeriod(value)}>{periodNames[value]}</button>)}
        </div>
        <div className="chart-value">
          <strong className="mono">{latest ? metricValue(latest.value, latest.unit) : "—"}</strong><span>{unit}{period && " · " + periodNames[period]}</span>
        </div>
        {series.status === "loading" ? <State type="loading" /> : series.status === "error" ?
          <State type="error" message={series.message} retry={series.retry} /> : !points.length ?
          <State type="empty" message="该样本缺少此指标" /> :
          <Chart points={points} unit={latest?.unit ?? ""} label={selected?.name ?? latest?.metric_name ?? "指标"} axisUnit={unit} mode={mode} period={period} />}
        <div className="chart-note">{selected?.formula && <span>计算口径 · {selected.formula}</span>}
          {period && <span>当前数据频率 · {periodNames[period]}</span>}
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
        {latest ? filings.map((source) => <div key={source.source_id} className="panel source-card"><Database size={19} /><div>
          <strong>{source.source_kind === "official" ? <a className="text-link" href={source.document_ref} target="_blank" rel="noreferrer">{source.source_label}</a> : source.source_label}</strong>
          <p>{source.published_at ? "披露 " + displayDate(source.published_at) : "计算版本 " + source.calculation_version}</p>
          {source.supporting_documents?.map((doc) => <p key={doc.url}><a className="text-link" href={doc.url} target="_blank" rel="noreferrer">计算依据 · {doc.label}</a></p>)}
          {source.source_kind === "mock" && <code>{source.document_ref}</code>}
        </div><DataLabel kind={source.source_kind === "official" ? "official" : "mock"} /></div>) :
          series.status === "loading" ? <State type="loading" /> :
          series.status === "error" ? <State type="error" message={series.message} retry={series.retry} /> : <State type="empty" />}
      </section>
    </>}
  </>;
}
