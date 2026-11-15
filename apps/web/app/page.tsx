"use client";

import { Activity, ArrowRight, Building2, CalendarDays, ChartNoAxesCombined, Globe2, Radio } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Chart } from "@/components/chart";
import { CompanyTable, SignalCard, State } from "@/components/common";
import { CompanySearch, DataLabel, useDataKind } from "@/components/shell";
import { categories, deltaLabel, displayDate, periodNames, type Entity, type Insight, type Observation, type Overview } from "@/lib/data";
import { useData } from "@/lib/use-data";

export default function Discover() {
  const [category, choose] = useState("");
  const overview = useData<Overview>("/overview");
  const companies = useData<Entity[]>("/entities");
  const signals = useData<Insight[]>("/insights?limit=6&category=" + category);
  const kind = useDataKind();
  const featuredPeriod = kind === "official" ? "quarterly" : "annual";
  const featured = useData<Observation[]>(kind ? "/series?entity_id=0700.HK&metric_id=revenue&period=" + featuredPeriod : null);
  const featuredPoints = featured.status === "success" ? featured.data.slice(-6) : [];
  const latest = featuredPoints.at(-1);
  const prior = latest && featuredPoints.find((point) => point.period_end.slice(5, 7) === latest.period_end.slice(5, 7) &&
    Number(point.period_end.slice(0, 4)) === Number(latest.period_end.slice(0, 4)) - 1);
  const stats = overview.status === "success" ? overview.data : null;
  const metrics = [
    { label: "覆盖公司", value: stats?.company_count, suffix: "家", icon: Building2 },
    { label: "已发现趋势", value: stats?.insight_count, suffix: "条", icon: Activity },
    { label: "覆盖市场", value: stats?.market_count, suffix: "个", icon: Globe2 },
    { label: kind === "official" ? "最近披露" : "最新入库", value: stats ? displayDate(stats.last_updated_at) : undefined, suffix: "", icon: CalendarDays },
  ];
  return <>
    <section className="hero panel">
      <div className="hero-content">
        <div className="eyebrow"><Radio size={15} /> 股票基本面研究</div>
        <h1>看见变化，<br /><em>发现机会。</em></h1>
        <p>用财务数据识别企业的增长、盈利与现金流变化。<br className="desktop-break" /> 从一条趋势出发，回到可核对的指标与证据。</p>
        <CompanySearch hero />
      </div>
      <div className="featured panel">
        <div className="row between"><div className="eyebrow"><ChartNoAxesCombined size={16} /> 营收趋势</div><DataLabel /></div>
        <div className="featured-title"><Link href="/stocks/0700.HK">腾讯控股</Link><span className="mono">0700.HK</span></div>
        <div className="row between featured-caption"><span>营业收入 · {periodNames[featuredPeriod]} · 亿元 CNY</span>
          {latest && prior && <span className="up mono">{deltaLabel((latest.value / prior.value - 1) * 100, "%")} 同比</span>}
        </div>
        {featured.status === "error" ? <State type="error" message={featured.message} retry={featured.retry} /> :
          featured.status === "loading" ? <State type="loading" /> :
            featuredPoints.length ? <Chart points={featuredPoints} unit="billion" label="营业收入" axisUnit="亿元 CNY" size="hero" period={featuredPeriod} /> : <State type="empty" />}
      </div>
    </section>

    {overview.status === "error" ? <State type="error" message={overview.message} retry={overview.retry} /> :
      <section className="stats panel" aria-label="数据概览" aria-busy={overview.status === "loading"}>
        {metrics.map(({ label, value, suffix, icon: Icon }) => <div className="stat" key={label}>
          <div className="stat-icon"><Icon size={18} /></div><div><small>{label}</small><strong className="mono">{value ?? "—"} {suffix && value != null && <span>{suffix}</span>}</strong></div>
        </div>)}
      </section>}
    <section className="section">
      <div className="section-title"><div><h2>趋势发现</h2><p>由财务指标触发的规则信号</p></div></div>
      <div className="tabs" aria-label="趋势分类">
        {[["", "全部趋势"], ...Object.entries(categories)].map(([key, label]) =>
          <button key={key} className={category === key ? "selected" : ""} aria-pressed={category === key} onClick={() => choose(key)}>{label}</button>)}
      </div>
      {signals.status === "loading" ? <State type="loading" /> : signals.status === "error" ?
        <State type="error" message={signals.message} retry={signals.retry} /> : !signals.data.length ?
          <State type="empty" message={category === "valuation" ? "暂无估值数据" : "这个分类暂无趋势信号"} /> :
          <div className="signal-grid">{signals.data.map((signal) => <SignalCard insight={signal} key={signal.id} />)}</div>}
    </section>
    <section className="section">
      <div className="section-title"><div><h2>覆盖公司</h2><p>探索 A 股与港股公司的财务与经营数据</p></div><Link className="text-link" href="/stocks">查看全部 <ArrowRight size={16} /></Link></div>
      {companies.status === "loading" ? <State type="loading" /> : companies.status === "error" ?
        <State type="error" message={companies.message} retry={companies.retry} /> : <CompanyTable companies={companies.data} />}
    </section>
  </>;
}
