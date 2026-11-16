import type { Point } from "./data";

export const shortTrendWeeks = 10;
export const longTrendWeeks = 30;
export const rsiWeeks = 14;
export const comparisonWeeks = 20;

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
  let volatility = null;
  if (close !== undefined && closes.length >= weeklyInsightWindows.range) {
    const history = closes.slice(-weeklyInsightWindows.range);
    const priorCloses = history.slice(0, -1);
    range = { low: Math.min(...priorCloses), high: Math.max(...priorCloses) };
    const returns = history.slice(1).map((value, index) => value / history[index] - 1);
    const averageReturn = mean(returns);
    volatility = 100 * Math.sqrt(mean(returns.map((value) => (value - averageReturn) ** 2)));
  }
  return { close, trend, momentum, range, volatility, weeks: closes.length };
}
