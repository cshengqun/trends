"use client";

import { Activity, ArrowUpRight, Compass, Database, Layers3, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useState, type FormEvent, type ReactNode } from "react";
import { type DataKind, type Overview } from "@/lib/data";
import { useData } from "@/lib/use-data";

const DataContext = createContext<DataKind | undefined>(undefined);
export function useDataKind() {
  return useContext(DataContext);
}

export function CompanySearch({ hero = false }: { hero?: boolean }) {
  const router = useRouter();
  const [value, setValue] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const query = value.trim();
    router.push(query ? "/stocks?q=" + encodeURIComponent(query) : "/stocks");
  }
  return <form className={hero ? "search hero-search" : "search"} onSubmit={submit} role="search">
    <Search size={17} aria-hidden="true" />
    <input type="search" maxLength={40} aria-label="搜索公司名称或代码" placeholder={hero ? "搜索公司名称或股票代码" : "搜索公司或代码…"} value={value} onChange={(event) => setValue(event.target.value)} />
    {hero && <button type="submit" aria-label="搜索"><ArrowUpRight size={18} /></button>}
  </form>;
}

export function DataLabel({ kind }: { kind?: DataKind }) {
  const context = useDataKind();
  const resolved = kind ?? context;
  if (!resolved) return null;
  return <span className={resolved === "official" ? "mock-label official-label" : "mock-label"}>
    <span />{resolved === "official" ? "官方披露" : "MOCK"}
  </span>;
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const overview = useData<Overview>("/overview");
  const kind = overview.status === "success" ? overview.data.data_kind : undefined;
  const links = [["/", "趋势发现", Compass], ["/stocks", "股票探索", Layers3]] as const;
  return <DataContext.Provider value={kind}><div className="shell">
    <aside className="sidebar">
      <Link href="/" className="brand"><span className="brand-icon"><Activity size={22} /></span><span>Trends<span className="brand-dot">.</span></span></Link>
      <nav className="navigation" aria-label="主导航">
        <div className="nav-caption">研究工作台</div>
        {links.map(([url, name, Icon]) => {
          const active = url === "/" ? pathname === "/" || pathname.startsWith("/insights/") : pathname.startsWith("/stocks");
          return <Link href={url} key={url} className={active ? "nav-link active" : "nav-link"} aria-current={active ? "page" : undefined}>
            <Icon size={18} />{name}
          </Link>;
        })}
      </nav>
      <div className="sidebar-status"><Database size={16} /><div><strong>数据来源</strong><small>{kind === "official" ? "公司公告与财报" : kind === "mock" ? "Mock · 年度财务样本" : "—"}</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><CompanySearch /><DataLabel /></header>
      <main className="main-content">{children}</main>
      <footer className="site-footer"><span>Trends · 用趋势理解世界。</span><span>{kind === "official" ? "数据以发行人披露为准" : kind === "mock" ? "全部财务数值为 Mock 模拟数据" : ""}</span></footer>
    </div>
  </div></DataContext.Provider>;
}
