import { useEffect, useState } from 'react'

export interface TraceDef {
  name?: string
  color?: string
  dash?: string
  type: 'bar' | 'line' | 'area' | 'scatter'
  x: (string | number)[]
  y: (number | null)[]
  markerColors?: string[]
  fill?: string
  fillcolor?: string
}

export interface ChartDef {
  id: string
  title?: string
  unit?: string
  mini?: boolean
  defaultRange?: string
  traces: TraceDef[]
  refs: { y: number; label?: string; color?: string; dash?: string }[]
  bands: { x0: string; x1: string; label?: string }[]
  numericX: boolean
}

export interface SiteBlock {
  t: 'html' | 'chart' | 'cardgrid' | 'expander' | 'layer'
  cls?: string
  html?: string
  id?: string
  kind?: string
  cards?: SiteBlock[]
  summary?: string
  blocks?: SiteBlock[]
}

export interface SiteData {
  generatedAt: string
  headerHtml: string
  blocks: SiteBlock[]
  sections: { id: string; open: boolean; summaryHtml: string; blocks: SiteBlock[] }[]
  charts: Record<string, RawChart>
}

export type RawChart = Record<string, unknown> & { kind?: string; traces?: unknown[] }

export function useSite() {
  const [site, setSite] = useState<SiteData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    fetch('site.json')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setSite)
      .catch(e => setErr(String(e)))
  }, [])
  return { site, err }
}

const isDateStr = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}/.test(v)

export function normalizeChart(raw: RawChart, id: string): ChartDef | null {
  if (!raw || !Array.isArray(raw.traces)) return null
  const traces: TraceDef[] = []
  const refs: ChartDef['refs'] = []
  const bands: ChartDef['bands'] = []
  for (const t of raw.traces as Record<string, unknown>[]) {
    if (!Array.isArray(t.x) || !Array.isArray(t.y)) continue
    const line = (t.line ?? {}) as Record<string, unknown>
    const marker = (t.marker ?? {}) as Record<string, unknown>
    const typeStr = (t.type as string) || ''
    const mode = String(t.mode ?? '')
    traces.push({
      name: t.name as string,
      color: (line.color ?? (typeof marker.color === 'string' ? marker.color : undefined) ?? t.color) as string,
      dash: line.dash as string,
      type: typeStr === 'bar' ? 'bar' : (mode.includes('markers') && !mode.includes('lines')) ? 'scatter' : t.fill ? 'area' : 'line',
      x: t.x as (string | number)[],
      y: t.y as (number | null)[],
      markerColors: Array.isArray(marker.color) ? marker.color as string[] : undefined,
      fill: t.fill as string,
      fillcolor: t.fillcolor as string,
    })
  }
  if (!traces.length) return null
  const layout = (raw.layout ?? {}) as Record<string, unknown>
  for (const sh of (layout.shapes ?? []) as Record<string, unknown>[]) {
    const ln = (sh.line ?? {}) as Record<string, unknown>
    if (sh.type === 'line' && sh.y0 === sh.y1 && typeof sh.y0 === 'number') {
      refs.push({ y: sh.y0 as number, color: ln.color as string, dash: ln.dash as string })
    }
  }
  for (const r of (raw.refs ?? []) as Record<string, unknown>[]) {
    if (typeof r.y === 'number') refs.push({ y: r.y as number, label: r.label as string, color: r.color as string })
  }
  const band = raw.band as Record<string, unknown> | undefined
  if (band && band.x0 && band.x1) bands.push({ x0: String(band.x0), x1: String(band.x1), label: band.label as string })
  return {
    id,
    title: (raw.title as string) || undefined,
    unit: (raw.unit as string) || undefined,
    mini: !!raw.mini,
    defaultRange: (raw.default_range as string) || undefined,
    traces,
    refs,
    bands,
    numericX: !isDateStr(traces[0].x[0]),
  }
}

const NUL = String.fromCharCode(0)
const TOKEN_RE = new RegExp(NUL + 'CHART:([\\w-]+)' + NUL)

/** 把含图表占位符的 html 拆成片段 */
export function splitChartTokens(html: string): ({ html: string } | { chartId: string })[] {
  const parts = html.split(TOKEN_RE)
  const out: ({ html: string } | { chartId: string })[] = []
  parts.forEach((p, i) => {
    if (i % 2 === 1) out.push({ chartId: p })
    else if (p) out.push({ html: p })
  })
  return out
}
