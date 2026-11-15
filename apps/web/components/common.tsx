"use client";

import Link from "next/link";
import { ArrowRight, ArrowUpRight, CircleAlert, Database, LoaderCircle } from "lucide-react";
import { Chart } from "./chart";
import { DataLabel } from "./shell";
import { categoryName, deltaLabel, displayDate, marketName, periodLabel, type Entity, type Insight } from "@/lib/data";

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

const companyStyles: Record<string, [string, string]> = {
  "0700.HK": ["腾", "#6da7ff"], "1810.HK": ["米", "#ff9b65"], "3690.HK": ["美", "#f8cf67"],
  "000333.SZ": ["M", "#78caee"], "600941.SH": ["中", "#78ddb1"], "601318.SH": ["平", "#f2a788"],
};

export function CompanyTable({ companies }: { companies: Entity[] }) {
  if (!companies.length) return <State type="empty" message="没有找到匹配的公司" />;
  return <div className="panel company-table"><table>
    <thead><tr><th>公司</th><th>股票代码</th><th>市场</th><th>行业</th><th>最近期间</th><th><span className="sr-only">详情</span></th></tr></thead>
    <tbody>{companies.map((company) => {
      const [initial, color] = companyStyles[company.symbol] ?? [company.name[0], "#64efbc"];
      const href = "/stocks/" + encodeURIComponent(company.symbol);
      return <tr key={company.id}>
        <td><Link className="company-name" href={href}><span className="company-mark" style={{ color, backgroundColor: color + "20" }}>{initial}</span><strong>{company.name}</strong></Link></td>
        <td className="mono">{company.symbol}</td><td>{marketName(company.market)} <small>{company.exchange}</small></td><td>{company.industry}</td>
        <td className="mono">{company.latest_period ?? "—"}</td><td><Link href={href} aria-label={company.name + "详情"}><ArrowRight size={17} /></Link></td>
      </tr>;
    })}</tbody>
  </table></div>;
}
