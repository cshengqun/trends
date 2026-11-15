"use client";

import { ArrowLeft, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { Chart } from "./chart";
import { State } from "./common";
import { DataLabel } from "./shell";
import { categoryName, deltaLabel, displayDate, metricUnit, metricValue, periodLabel, type Insight, type Observation } from "@/lib/data";
import { useData } from "@/lib/use-data";

export function InsightDetail({ id }: { id: string }) {
  const path = "/insights/" + encodeURIComponent(id);
  const insight = useData<Insight>(path);
  const evidence = useData<Observation[]>(insight.status === "success" ? path + "/evidence" : null);
  return <>
    <Link href="/" className="back-link"><ArrowLeft size={16} /> 趋势发现</Link>
    {insight.status === "loading" ? <State type="loading" /> : insight.status === "error" ?
      <State type="error" message={insight.message} retry={insight.retry} /> : (() => {
        const signal = insight.data;
        const chartRows = evidence.status === "success" ? evidence.data.filter((row) => row.metric_id === signal.metric_id) : [];
        const unit = chartRows[0]?.unit ?? "";
        return <>
          <div className="page-heading">
            <div className="row gap"><span className={`category ${signal.category}`}>{categoryName(signal.category)}</span><DataLabel kind={signal.data_kind} /></div>
            <h1>{signal.entity_name} · {signal.title}</h1>
            <p>{signal.symbol} · {periodLabel(signal.period_end, signal.period_type)} · 规则 {signal.rule_id} · 生成于 {displayDate(signal.generated_at)}</p>
            <Link className="text-link" href={"/stocks/" + encodeURIComponent(signal.symbol)}>查看公司 <ArrowUpRight size={16} /></Link>
          </div>
          <section className="panel detail-chart">
            <div className="eyebrow">观察事实 · {signal.metric_name}</div>
            <div className="chart-value"><strong className={signal.delta < 0 ? "down mono" : "up mono"}>{deltaLabel(signal.delta, signal.delta_unit)}</strong></div>
            <p className="muted">{signal.summary}</p>
            {evidence.status === "loading" ? <State type="loading" /> : evidence.status === "error" ?
              <State type="error" message={evidence.message} retry={evidence.retry} /> : chartRows.length ?
              <Chart points={chartRows} unit={unit} axisUnit={metricUnit(unit, chartRows[0].currency)} label={signal.metric_name} period={signal.period_type} down={signal.delta < 0} /> : <State type="empty" />}
          </section>
          <section className="section">
            <div className="section-title"><div><h2>数据证据</h2><p>参与规则判断的观测记录</p></div></div>
            {evidence.status === "loading" ? <State type="loading" /> : evidence.status === "error" ?
              <State type="error" message={evidence.message} retry={evidence.retry} /> : !evidence.data.length ?
              <State type="empty" /> : <div className="panel company-table"><table>
                <thead><tr><th>财务期间</th><th>指标</th><th>数值</th><th>来源</th><th>计算版本</th></tr></thead>
                <tbody>{evidence.data.map((row) => <tr key={row.id}>
                  <td className="mono">{periodLabel(row.period_end, row.period_type)}</td><td>{row.metric_name}</td>
                  <td className="mono">{metricValue(row.value, row.unit)} {metricUnit(row.unit, row.currency)}</td>
                  <td><DataLabel kind={row.source_kind === "official" ? "official" : "mock"} /> {row.source_label}<small className="block-source">{row.source_kind === "official" ? <a href={row.document_ref} target="_blank" rel="noreferrer">原始披露 · {displayDate(row.published_at)}</a> : row.document_ref}</small></td>
                  <td className="mono">{row.calculation_version}</td>
                </tr>)}</tbody>
              </table></div>}
          </section>
          <section className="section"><div className="section-title"><h2>后续验证</h2></div>
            <div className="panel source-card"><div><strong>下一财务期 · {signal.metric_name}</strong><p>按相同披露口径复核下一期的方向和幅度。</p></div></div>
          </section>
        </>;
      })()}
  </>;
}
