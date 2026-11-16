"use client";

import { ChevronDown, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { type Entity } from "@/lib/data";
import { useData } from "@/lib/use-data";

export function StockPicker({ symbol }: { symbol: string }) {
  const router = useRouter();
  const stocks = useData<Entity[]>("/entities?limit=100");
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const search = query.trim().toLowerCase();
  const options = stocks.status === "success" ? stocks.data.filter((stock) =>
    stock.name.toLowerCase().includes(search) || stock.symbol.toLowerCase().includes(search) ||
    (stock.market === "HK" && stock.symbol.replace(/^0+|\.HK$/g, "") === search.replace(/^0+|\.hk$/g, "")),
  ) : [];
  const activeOption = open ? options[activeIndex] : undefined;
  const activeId = activeOption ? listId + "-" + activeOption.symbol : undefined;

  useEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  function openPicker() {
    setOpen(true);
    if (stocks.status === "error") stocks.retry();
  }

  function closePicker() {
    setOpen(false);
    setQuery("");
    setActiveIndex(-1);
  }

  function choose(stock: Entity) {
    closePicker();
    if (stock.symbol !== symbol) router.push("/stocks/" + encodeURIComponent(stock.symbol));
  }

  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closePicker();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openPicker();
      if (options.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActiveIndex((index) => index < 0 && step < 0 ? options.length - 1 :
          Math.max(0, Math.min(options.length - 1, index + step)));
      }
    } else if (event.key === "Enter" && open && (activeOption || options.length === 1)) {
      event.preventDefault();
      choose(activeOption ?? options[0]);
    }
  }

  return <div className="stock-picker" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) closePicker();
  }}>
    <div className="search stock-picker-field">
      <Search size={16} aria-hidden="true" />
      <input ref={input} role="combobox" type="text" aria-label="选择股票"
        aria-autocomplete="list" aria-expanded={open} aria-controls={listId} aria-activedescendant={activeId}
        placeholder="搜索股票名称或代码" value={query} maxLength={40} autoComplete="off"
        onFocus={openPicker} onClick={() => { if (!open) openPicker(); }} onKeyDown={handleKey}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(-1);
          if (!open) openPicker();
        }} />
      <button type="button" tabIndex={-1} aria-label={open ? "收起股票列表" : "展开股票列表"}
        aria-expanded={open} aria-controls={listId}
        onMouseDown={(event) => event.preventDefault()} onClick={() => {
          if (open) closePicker();
          else {
            if (document.activeElement === input.current) openPicker();
            else input.current?.focus();
          }
        }}><ChevronDown size={16} aria-hidden="true" /></button>
    </div>
    <div className="stock-picker-popup" hidden={!open}>
      <ul id={listId} className="stock-picker-options" role="listbox" aria-label="可选股票">
        {open ? options.map((stock, index) =>
          <li key={stock.symbol} id={listId + "-" + stock.symbol} role="option"
            aria-selected={stock.symbol === symbol} className={index === activeIndex ? "active" : undefined}
            onMouseDown={(event) => event.preventDefault()} onClick={() => choose(stock)}>
            <span>{stock.name}</span><span className="mono">{stock.symbol}</span>
          </li>,
        ) : null}
      </ul>
      {open && options.length === 0 ? <div className="stock-picker-message" role="status">
        {stocks.status === "loading" ? "正在加载股票…" :
          stocks.status === "error" ? "股票列表加载失败，请重新打开下拉框" : "没有匹配的股票"}
      </div> : null}
    </div>
  </div>;
}
