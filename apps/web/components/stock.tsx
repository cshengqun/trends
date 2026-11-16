"use client";

import { ArrowLeft, Database } from "lucide-react";
import Link from "next/link";
import { Chart } from "./chart";
import { State } from "./common";
import { DataLabel } from "./shell";
import { displayDate, marketName, metricUnit, metricValue, periodLabel, type EntityDetail, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";

const metrics = [
  { id: "revenue", name: "营收", unit: "billion", note: "单季营业收入", empty: "暂无可核实的单季营收" },
  { id: "revenue_growth", name: "营收增长率", unit: "%", note: "同币种单季营收同比", empty: "暂无可比较的上年同期营收" },
  { id: "net_income", name: "利润", unit: "billion", note: "单季归母净利润", empty: "暂无可核实的单季归母净利润" },
  { id: "profit_growth", name: "利润增长率", unit: "%", note: "单季归母净利润同比，基期利润须为正", empty: "暂无可比较的上年同期盈利数据" },
  { id: "pe_ttm", name: "PE", unit: "倍", note: "季末市盈率（TTM），亏损时留空", empty: "暂无可用的季末 PE" },
  { id: "dividend_yield", name: "股息率", unit: "%", note: "季末近 12 个月现金股息收益率", empty: "暂无可核实的季末股息率" },
] as const;

type Dashboard = { end_date: string; points: Observation[] };

export function Stock({ symbol }: { symbol: string }) {
  const encoded = encodeURIComponent(symbol);
  const entity = useData<EntityDetail>("/entities/" + encoded);
  const dashboard = useData<Dashboard>(entity.status === "success" ? "/entities/" + encoded + "/quarterly" : null);
  return <>
    <Link href="/stocks" className="back-link"><ArrowLeft size={16} /> 股票探索</Link>
    {entity.status === "loading" ? <State type="loading" /> : entity.status === "error" ?
      <State type="error" message={entity.message} retry={entity.retry} /> : <>
      <div className="page-heading">
        <div className="row gap"><span className="eyebrow mono">{entity.data.symbol} · {entity.data.exchange}</span><DataLabel /></div>
        <h1>{entity.data.name}</h1>
        <p>{marketName(entity.data.market)} · {entity.data.industry}</p>
      </div>
      {dashboard.status === "loading" ? <State type="loading" /> : dashboard.status === "error" ?
        <State type="error" message={dashboard.message} retry={dashboard.retry} /> : <QuarterlyDashboard {...dashboard.data} />}
    </>}
  </>;
}

function QuarterlyDashboard({ end_date, points }: Dashboard) {
  const endYear = Number(end_date.slice(0, 4));
  const endQuarter = Math.ceil(Number(end_date.slice(5, 7)) / 3);
  const startMonth = new Date(Date.UTC(endYear, (endQuarter - 12) * 3 + 2, 1)).toISOString().slice(0, 10);
  const filings = [...new Map([...points].reverse().filter((point) =>
    point.metric_id !== "revenue_growth" && point.metric_id !== "profit_growth"
  ).map((point) => [point.source_id, point])).values()];
  return <>
    <p className="quarterly-period">近 3 年 · {periodLabel(startMonth, "quarterly")} 至 {periodLabel(end_date, "quarterly")}</p>
    <div className="quarterly-grid">
      {metrics.map((metric) => {
        const series = points.filter((point) => point.metric_id === metric.id);
        const latest = series.at(-1);
        const unit = metric.unit === "billion" && !latest ? "" : metricUnit(metric.unit, latest?.currency);
        return <section key={metric.id} className="panel quarterly-card" aria-label={metric.name}>
          <h2>{metric.name}</h2>
          <p className="quarterly-note">{metric.note}</p>
          <div className="quarterly-value">
            <strong className="mono">{latest ? metricValue(latest.value, metric.unit) : "—"}</strong>
            {latest && <span>{unit} · {periodLabel(latest.period_end, "quarterly")}</span>}
          </div>
          <div className="quarterly-plot">
            <Chart points={series} unit={metric.unit} label={metric.name} axisUnit={unit} period="quarterly"
              startDate={startMonth} endDate={end_date} />
            {!latest && <span className="quarterly-empty">{metric.empty}</span>}
          </div>
        </section>;
      })}
    </div>
    {filings.length > 0 && <details className="section panel quarterly-sources">
      <summary>指标数据来源</summary>
      {filings.map((source) => <div key={source.source_id} className="source-card"><Database size={19} /><div>
        <strong>{source.source_kind === "mock" ? source.source_label :
          <a className="text-link" href={source.document_ref} target="_blank" rel="noreferrer">{source.source_label}</a>}</strong>
        <p>{source.market_date ? "交易日 " + displayDate(source.market_date) :
          source.published_at ? "披露 " + displayDate(source.published_at) :
          source.source_kind === "licensed" ? "上线 " + displayDate(source.available_at) : "计算版本 " + source.calculation_version}</p>
        {source.supporting_documents?.map((doc) => <p key={doc.url}>
          <a className="text-link" href={doc.url} target="_blank" rel="noreferrer">计算依据 · {doc.label}</a>
        </p>)}
      </div></div>)}
    </details>}
  </>;
}
