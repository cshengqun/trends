"use client";

import { Activity, ArrowUpRight, Compass, Database, Layers3, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

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

export function MockLabel() {
  return <span className="mock-label"><span />MOCK</span>;
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const links = [["/", "趋势发现", Compass], ["/stocks", "股票探索", Layers3]] as const;
  return <div className="shell">
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
      <div className="sidebar-status"><Database size={16} /><div><strong>数据环境</strong><small>Mock · 年度财务样本</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><CompanySearch /><MockLabel /></header>
      <main className="main-content">{children}</main>
      <footer className="site-footer"><span>Trends · 用趋势理解世界。</span><span>全部财务数值为 Mock 模拟数据</span></footer>
    </div>
  </div>;
}
