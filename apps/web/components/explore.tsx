"use client";

import { Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { CompanyTable, State } from "./common";
import { type Entity } from "@/lib/data";
import { useData } from "@/lib/use-data";

export function Explore({ initialQuery }: { initialQuery: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [market, setMarket] = useState("");
  const deferredQuery = useDeferredValue(query);
  const params = new URLSearchParams({ q: deferredQuery.trim(), market });
  const list = useData<Entity[]>("/entities?" + params.toString());
  return <>
    <div className="page-heading"><h1>股票探索</h1><p>按公司名称、股票代码和市场查找财务与经营数据。</p></div>
    <div className="explore-controls">
      <label className="search"><Search size={17} /><input type="search" maxLength={40} value={query} onChange={(event) => setQuery(event.target.value)} aria-label="筛选公司" placeholder="搜索公司名称或股票代码" /></label>
      <div className="tabs" aria-label="股票市场">
        {[["", "全部市场"], ["CN", "A 股"], ["HK", "港股"]].map(([value, label]) =>
          <button key={value} className={market === value ? "selected" : ""} onClick={() => setMarket(value)} aria-pressed={market === value}>{label}</button>)}
      </div>
    </div>
    {list.status === "loading" ? <State type="loading" /> : list.status === "error" ?
      <State type="error" message={list.message} retry={list.retry} /> : <CompanyTable companies={list.data} />}
  </>;
}
