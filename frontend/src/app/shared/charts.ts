import type { EChartsOption } from 'echarts';
import { Bucket, Histogram } from '../core/models';

/** Validated categorical slots (dataviz reference palette), assigned in fixed order, never cycled. */
const CATEGORICAL = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
/** Log levels are state, so they use the reserved status palette (+ text label everywhere). */
export const LEVEL_COLORS: Record<string, string> = {
  critical: '#d03b3b', error: '#ec835a', warning: '#fab219', info: '#3987e5', debug: '#898781',
};
const LEVEL_ORDER = ['debug', 'info', 'warning', 'error', 'critical'];
const OTHER = '#898781';

/** Chart chrome for the dark console surface. Builders always produce dark options. */
const CHROME = {
  text: '#c3c2b7',
  muted: '#898781',
  grid: '#2c2c2a',
  axis: '#383835',
  surface: '#12151a',
  tooltipBg: '#1f242b',
  primary: '#f0efec',
};

function chrome() {
  return CHROME;
}

/**
 * Dark → light color mapping applied by <lh-chart> in light mode: chrome tokens plus the
 * categorical palette's light steps (same hues, validated for the light surface).
 * Status/level colors are mode-invariant and pass through unchanged.
 */
const LIGHT_EQUIVALENT: Record<string, string> = {
  [CHROME.text]: '#52514e',
  [CHROME.grid]: '#e1e0d9',
  [CHROME.axis]: '#c3c2b7',
  [CHROME.surface]: '#ffffff',
  [CHROME.tooltipBg]: '#ffffff',
  [CHROME.primary]: '#0b0b0b',
  '#3987e5': '#2a78d6', '#d95926': '#eb6834', '#199e70': '#1baf7a', '#c98500': '#eda100',
  '#d55181': '#e87ba4', '#9085e9': '#6250d6', '#e66767': '#e34948',
};

/** Re-color an option built for dark mode. Functions (formatters) are kept by reference. */
export function themeChart<T>(option: T, mode: 'dark' | 'light'): T {
  if (mode === 'dark') return option;
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') return LIGHT_EQUIVALENT[v] ?? v;
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object') {
      return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, walk(x)]));
    }
    return v;
  };
  return walk(option) as T;
}

/** Stable color per entity: levels use status colors, others take slots by first appearance. */
export function colorFor(name: string, index: number): string {
  if (name in LEVEL_COLORS) return LEVEL_COLORS[name];
  if (name === 'Other') return OTHER;
  return CATEGORICAL[index] ?? OTHER;
}

function base(): EChartsOption {
  const c = chrome();
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: c.text },
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: c.tooltipBg, borderColor: c.axis, textStyle: { color: c.primary, fontSize: 12 },
      confine: true,
    },
    legend: { top: 0, left: 0, textStyle: { color: c.text }, icon: 'roundRect', itemWidth: 10, itemHeight: 10 },
  };
}

function sortSeries(names: string[]): string[] {
  const levels = names.filter(n => LEVEL_ORDER.includes(n)).sort((a, b) => LEVEL_ORDER.indexOf(a) - LEVEL_ORDER.indexOf(b));
  return [...levels, ...names.filter(n => !LEVEL_ORDER.includes(n))];
}

/** Stacked bars over time (one series per split value), or a single 2px line. */
export function timeSeriesOption(h: Histogram, opts: { valueKey?: 'count' | 'value'; unit?: string } = {}): EChartsOption {
  const c = chrome();
  const names = sortSeries(h.series ?? []).slice(0, 8);
  const hasSplit = names.length > 0;
  const series: any[] = hasSplit
    ? names.map((name, i) => ({
        name, type: 'bar', stack: 'total', barCategoryGap: '20%',
        itemStyle: { color: colorFor(name, i), borderColor: c.surface, borderWidth: 1 },
        emphasis: { focus: 'series' },
        data: h.buckets.map(b => [b.key, b.series?.[name] ?? 0]),
      }))
    : [{
        name: opts.valueKey === 'value' ? 'value' : 'events', type: 'line', showSymbol: false, smooth: false,
        lineStyle: { width: 2, color: colorFor('series', 0) }, itemStyle: { color: colorFor('series', 0) },
        areaStyle: { opacity: 0.08 },
        data: h.buckets.map(b => [b.key, opts.valueKey === 'value' ? b.value : b.count]),
      }];
  if (hasSplit && (h.series?.length ?? 0) > 8) {
    const shown = new Set(names);
    series.push({
      name: 'Other', type: 'bar', stack: 'total', itemStyle: { color: OTHER, borderColor: c.surface, borderWidth: 1 },
      data: h.buckets.map(b => [b.key, Object.entries(b.series ?? {}).filter(([k]) => !shown.has(k)).reduce((s, [, v]) => s + v, 0)]),
    });
  }
  return {
    ...base(),
    legend: hasSplit ? { ...(base().legend as object) } : { show: false },
    tooltip: { ...(base().tooltip as object), trigger: 'axis', axisPointer: { type: hasSplit ? 'shadow' : 'line' } },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: c.axis } }, axisLabel: { color: c.muted, hideOverlap: true },
             splitLine: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: c.muted, formatter: (v: number) => compact(v) + (opts.unit ?? '') },
             splitLine: { lineStyle: { color: c.grid } } },
    series,
  };
}

/** Horizontal ranked bars; labels on the left, values at the bar end. */
export function barOption(buckets: Bucket[], opts: { valueKey?: 'count' | 'value'; colorByKey?: boolean } = {}): EChartsOption {
  const c = chrome();
  const rows = [...buckets].reverse();
  const key = opts.valueKey ?? 'count';
  return {
    ...base(),
    legend: { show: false },
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    tooltip: { ...(base().tooltip as object), trigger: 'item' },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', data: rows.map(b => truncate(String(b.key), 40)), axisTick: { show: false },
             axisLine: { lineStyle: { color: c.axis } }, axisLabel: { color: c.text } },
    series: [{
      type: 'bar', barMaxWidth: 18,
      data: rows.map(b => ({
        value: (b as any)[key] ?? 0, name: String(b.key),
        itemStyle: { color: opts.colorByKey ? colorFor(String(b.key), 0) : colorFor('series', 0), borderRadius: [0, 4, 4, 0] },
      })),
      label: { show: true, position: 'right', color: c.text, formatter: (p: any) => compact(p.value) },
    }],
  };
}

/** Part-to-whole donut, capped at 8 slices with the remainder folded into "Other". */
export function donutOption(buckets: Bucket[]): EChartsOption {
  const c = chrome();
  const top = buckets.slice(0, 7);
  const rest = buckets.slice(7).reduce((s, b) => s + b.count, 0);
  const data = [...top.map((b, i) => ({ name: String(b.key), value: b.count, itemStyle: { color: colorFor(String(b.key), i) } }))];
  if (rest) data.push({ name: 'Other', value: rest, itemStyle: { color: OTHER } });
  return {
    ...base(),
    legend: { ...(base().legend as object), type: 'scroll', orient: 'vertical', left: 'left', top: 'middle' },
    tooltip: { ...(base().tooltip as object), trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['55%', '80%'], center: ['65%', '50%'], avoidLabelOverlap: true,
      itemStyle: { borderColor: c.surface, borderWidth: 2 }, label: { show: false }, data,
    }],
  };
}

/** Prometheus range result (series of [ms, value]) as 2px lines. */
export function metricLinesOption(series: { labels: Record<string, string>; points: [number, number][] }[], unit = ''): EChartsOption {
  const c = chrome();
  const named = series.slice(0, 8).map((s, i) => {
    const label = Object.entries(s.labels).filter(([k]) => !['__name__', 'job', 'instance'].includes(k))
      .map(([k, v]) => `${k}=${v}`).join(', ') || 'value';
    return { name: label, type: 'line', showSymbol: false, data: s.points,
             lineStyle: { width: 2, color: colorFor(label, i) }, itemStyle: { color: colorFor(label, i) } };
  });
  return {
    ...base(),
    legend: named.length > 1 ? base().legend : { show: false },
    tooltip: { ...(base().tooltip as object), trigger: 'axis',
               valueFormatter: (v: any) => (typeof v === 'number' ? v.toFixed(2) : v) + unit },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: c.axis } }, axisLabel: { color: c.muted, hideOverlap: true } },
    yAxis: { type: 'value', axisLabel: { color: c.muted, formatter: (v: number) => compact(v) + unit },
             splitLine: { lineStyle: { color: c.grid } } },
    series: named as any,
  };
}

export function compact(v: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
