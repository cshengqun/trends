"use client";

import { Activity, Database, Layers3 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { createContext, useContext, type ReactNode } from "react";
import { type DataKind, type Overview } from "@/lib/data";
import { useData } from "@/lib/use-data";
import { StockPicker } from "./stock-picker";

const DataContext = createContext<DataKind | undefined>(undefined);
export function useDataKind() {
  return useContext(DataContext);
}

export function DataLabel({ kind }: { kind?: DataKind }) {
  const context = useDataKind();
  const resolved = kind ?? context;
  if (!resolved) return null;
  return <span className={resolved === "official" ? "mock-label official-label" : "mock-label"}>
    <span />{resolved === "official" ? "真实数据" : "MOCK"}
  </span>;
}

export function Shell({ children }: { children: ReactNode }) {
  const { symbol } = useParams<{ symbol?: string }>();
  const overview = useData<Overview>("/overview");
  const kind = overview.status === "success" ? overview.data.data_kind : undefined;
  const active = Boolean(symbol);
  return <DataContext.Provider value={kind}><div className="shell">
    <aside className="sidebar">
      <Link href="/stocks" className="brand"><span className="brand-icon"><Activity size={22} /></span><span>Trends<span className="brand-dot">.</span></span></Link>
      <nav className="navigation" aria-label="主导航">
        <div className="nav-caption">研究工作台</div>
        <Link href="/stocks" className={active ? "nav-link active" : "nav-link"} aria-current={active ? "page" : undefined}>
          <Layers3 size={18} />股票探索
        </Link>
      </nav>
      <div className="sidebar-status"><Database size={16} /><div><strong>数据来源</strong><small>{kind === "official" ? "公司披露与市场数据" : kind === "mock" ? "Mock · 年度财务样本" : "—"}</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar">{symbol ? <StockPicker symbol={symbol.toUpperCase()} /> : null}<DataLabel /></header>
      <main className="main-content">{children}</main>
      <footer className="site-footer"><span>Trends · 用趋势理解世界。</span>{kind === "mock" && <span>全部财务数值为 Mock 模拟数据</span>}</footer>
    </div>
  </div></DataContext.Provider>;
}
