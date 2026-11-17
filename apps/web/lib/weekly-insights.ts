import type { Point } from "./data";

export const shortTrendWeeks = 10;
export const longTrendWeeks = 30;
export const rsiWeeks = 14;
export const comparisonWeeks = 20;
export const drawdownWeeks = 52;

export const weeklyInsightWindows = {
  trend: longTrendWeeks,
  momentum: rsiWeeks + 1,
  range: comparisonWeeks + 1,
  volatility: comparisonWeeks + 1,
};

function mean(values: number[]) {
  const first = values[0];
  return first + values.reduce((sum, value) => sum + (value - first), 0) / values.length;
}

function wilderRsi(closes: number[]) {
  const changes = closes.slice(1).map((close, index) => close - closes[index]);
  let averageGain = mean(changes.slice(0, rsiWeeks).map((change) => Math.max(change, 0)));
  let averageLoss = mean(changes.slice(0, rsiWeeks).map((change) => Math.max(-change, 0)));
  for (const change of changes.slice(rsiWeeks)) {
    averageGain = (averageGain * (rsiWeeks - 1) + Math.max(change, 0)) / rsiWeeks;
    averageLoss = (averageLoss * (rsiWeeks - 1) + Math.max(-change, 0)) / rsiWeeks;
  }
  if (averageGain === 0 && averageLoss === 0) return 50;
  return 100 * averageGain / (averageGain + averageLoss);
}

function bounds(closes: number[]) {
  return { low: Math.min(...closes), high: Math.max(...closes) };
}

type Breakout = {
  start: Point;
  direction: "up" | "down";
  range: ReturnType<typeof bounds>;
  followUp?: { point: Point; status: "confirmed" | "returned" | "reversed" };
};

export function weeklyBreakouts(points: readonly Point[]): Breakout[] {
  const events: Breakout[] = [];
  let pending: Breakout | undefined;
  let previousDirection: Breakout["direction"] | null = null;

  for (let index = comparisonWeeks; index < points.length; index++) {
    const point = points[index];
    if (pending) {
      const { low, high } = pending.range;
      const confirmed = pending.direction === "up" ? point.value > high : point.value < low;
      const returned = low <= point.value && point.value <= high;
      pending.followUp = { point, status: confirmed ? "confirmed" : returned ? "returned" : "reversed" };
      pending = undefined;
    }

    const range = bounds(points.slice(index - comparisonWeeks, index).map(({ value }) => value));
    const direction = point.value > range.high ? "up" : point.value < range.low ? "down" : null;
    if (direction && direction !== previousDirection) {
      pending = { start: point, direction, range };
      events.push(pending);
    }
    previousDirection = direction;
  }
  return events;
}

export function weeklyMaximumDrawdown<T extends Point>(points: readonly T[]) {
  const latest = points.at(-1);
  if (!latest) return null;

  // Friday-to-Friday window, including the latest week. Holidays add no prices.
  const start = Date.parse(latest.period_end) - (drawdownWeeks - 1) * 7 * 86_400_000;
  if (Date.parse(points[0].period_end) > start) return null;

  let high: T | undefined;
  let result: { peak: T; trough: T; percent: number } | null = null;
  for (const point of points) {
    if (Date.parse(point.period_end) < start) continue;
    if (!high || point.value > high.value) high = point;
    const percent = 100 * (high.value - point.value) / high.value;
    if (!result || percent > result.percent) result = { peak: high, trough: point, percent };
  }
  return result;
}

export function weeklyInsights(points: readonly Point[]) {
  // The API returns trading weeks in ascending order. Weeks without a close contribute no sample.
  const closes = points.map(({ value }) => value);
  const close = closes.at(-1);
  const trend = closes.length >= weeklyInsightWindows.trend ? {
    short: mean(closes.slice(-shortTrendWeeks)),
    long: mean(closes.slice(-longTrendWeeks)),
  } : null;
  const momentum = closes.length >= weeklyInsightWindows.momentum ? wilderRsi(closes) : null;

  let range = null;
  if (closes.length >= weeklyInsightWindows.range) {
    const priorCloses = closes.slice(-weeklyInsightWindows.range, -1);
    range = bounds(priorCloses);
  }
  let volatility = null;
  if (closes.length >= weeklyInsightWindows.volatility) {
    const history = closes.slice(-weeklyInsightWindows.volatility);
    const returns = history.slice(1).map((value, index) => value / history[index] - 1);
    const averageReturn = mean(returns);
    volatility = 100 * Math.sqrt(mean(returns.map((value) => (value - averageReturn) ** 2)));
  }
  return { close, trend, momentum, range, volatility, weeks: closes.length };
}
