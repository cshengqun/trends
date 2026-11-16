"use client";

import { useEffect, useRef } from "react";
import { init, use, type ComposeOption } from "echarts/core";
import { BarChart, LineChart, type BarSeriesOption, type LineSeriesOption } from "echarts/charts";
import { GridComponent, TooltipComponent, type GridComponentOption, type TooltipComponentOption } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { fmt, periodLabel, periodNames, type Period, type Point } from "@/lib/data";

use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

type Option = ComposeOption<BarSeriesOption | LineSeriesOption | GridComponentOption | TooltipComponentOption>;
const dayMilliseconds = 86_400_000;

function monthIndex(value: string) {
  return Number(value.slice(0, 4)) * 12 + Number(value.slice(5, 7)) - 1;
}

export function Chart({ points, unit, label, mode = "line", size = "full", down = false, axisUnit, period = "annual", startDate, endDate }: {
  points: Point[]; unit: string; label: string; mode?: "line" | "bar";
  size?: "full" | "spark" | "hero"; down?: boolean; axisUnit?: string; period?: Period;
  startDate?: string; endDate?: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || (!points.length && (!startDate || !endDate))) return;
    const spark = size === "spark";
    const hero = size === "hero";
    const color = down ? "#f4a37d" : "#64efbc";
    const weekly = period === "weekly";
    const dateIndex = weekly ? (value: string) => Date.parse(value) / dayMilliseconds : monthIndex;
    const step = weekly ? 7 : period === "annual" ? 12 : period === "quarterly" ? 3 : 1;
    const values = new Map(points.map(({ period_end, value }) =>
      [dateIndex(period_end), unit === "billion" ? value * 10 : value]));
    const dates = [...values.keys()];
    const start = startDate ? dateIndex(startDate) : Math.min(...dates);
    const end = endDate ? dateIndex(endDate) : Math.max(...dates);
    const indices = spark ? dates : Array.from({ length: Math.floor((end - start) / step) + 1 },
      (_, i) => start + i * step);
    const labels = indices.map((index) => weekly ? new Date(index * dayMilliseconds).toISOString().slice(0, 10) :
      periodLabel(Math.floor(index / 12) + "-" + String(index % 12 + 1).padStart(2, "0"), period));
    const dataset = indices.map((index) => values.get(index) ?? null);
    const graph = init(element.current);
    const option: Option = {
      animation: false,
      grid: spark ? { left: 2, right: 2, top: 4, bottom: 4 } :
        { left: hero ? 12 : 58, right: 15, top: 16, bottom: 30 },
      tooltip: spark ? undefined : {
        trigger: "axis", confine: true, backgroundColor: "#101e2a", borderColor: "#2c4350",
        textStyle: { color: "#ecf4fa" }, valueFormatter: (value) => value == null ? "缺失" :
          fmt(Number(value), weekly ? 3 : 2) + " " + axisUnit,
      },
      xAxis: {
        type: "category", data: labels.map(String), show: !spark, boundaryGap: mode === "bar",
        axisTick: { show: false }, axisLabel: { color: "#889eab", hideOverlap: true, fontSize: 11,
          interval: weekly ? 12 : undefined },
        axisLine: { lineStyle: { color: "#283845" } },
      },
      yAxis: {
        type: "value", show: !spark, scale: mode !== "bar",
        splitNumber: hero ? 3 : 5,
        axisLabel: { show: !hero, color: "#889eab", fontSize: 11 },
        splitLine: { lineStyle: { color: "#243640", type: "dashed" } },
      },
      series: mode === "bar" ? [{
        type: "bar", name: label, data: dataset, barMaxWidth: 34,
        itemStyle: { color, borderRadius: [4, 4, 0, 0] },
      }] : [{
        type: "line", name: label, data: dataset, connectNulls: false, smooth: weekly ? false : 0.23,
        showSymbol: weekly ? points.length === 1 : !spark && (!hero || points.length <= 4),
        symbolSize: 6, lineStyle: { color, width: spark ? 2 : 2.5 },
        itemStyle: { color },
        areaStyle: { color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: down ? "#f4a37d29" : "#64efbc38" }, { offset: 1, color: "#64efbc00" }],
        } },
      }],
    };
    graph.setOption(option);
    const observer = new ResizeObserver(() => graph.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); graph.dispose(); };
  }, [points, unit, label, mode, size, down, axisUnit, period, startDate, endDate]);
  return <div ref={element} className={`chart chart-${size}`} role={size === "spark" ? undefined : "img"}
    aria-hidden={size === "spark" || undefined} aria-label={size === "spark" ? undefined : label + periodNames[period] + "趋势图"} />;
}
