"use client";

import Link from "next/link";
import { ArrowUpRight, CircleAlert, Database, LoaderCircle } from "lucide-react";
import { Chart } from "./chart";
import { DataLabel } from "./shell";
import { categoryName, deltaLabel, displayDate, periodLabel, type Insight } from "@/lib/data";

export function State({ type, message, retry }: { type: "loading" | "error" | "empty"; message?: string; retry?: () => void }) {
  const Icon = type === "loading" ? LoaderCircle : type === "error" ? CircleAlert : Database;
  return <div className="state" role={type === "error" ? "alert" : "status"}>
    <Icon className={type === "loading" ? "spin" : ""} size={20} />
    <span>{message ?? (type === "loading" ? "正在加载数据…" : "暂无可用数据")}</span>
    {retry && <button type="button" className="secondary-button" onClick={retry}>重试</button>}
  </div>;
}

export function SignalCard({ insight }: { insight: Insight }) {
  return <Link className="signal-card panel" href={"/insights/" + insight.id}>
    <div className="row between"><span className={`category ${insight.category}`}>{categoryName(insight.category)}</span><ArrowUpRight className="muted" size={17} /></div>
    <div><div className="signal-company">{insight.entity_name} <span className="mono">{insight.symbol}</span></div><h3>{insight.title}</h3><p>{insight.summary}</p></div>
    <div className="signal-data"><div><strong className={insight.delta < 0 ? "down" : "up"}>{deltaLabel(insight.delta, insight.delta_unit)}</strong><small>{insight.metric_name}</small></div>
      <Chart points={insight.spark} label={insight.metric_name} unit={insight.metric_unit} period={insight.period_type} size="spark" down={insight.delta < 0} />
    </div>
    <div className="signal-footer"><span className="mono">{periodLabel(insight.period_end, insight.period_type)} · {insight.data_kind === "official" ? "披露" : "入库"} {displayDate(insight.data_updated_at)}</span><DataLabel kind={insight.data_kind} /></div>
  </Link>;
}
