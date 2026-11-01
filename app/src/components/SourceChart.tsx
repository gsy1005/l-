import { useMemo, useState } from 'react'
import {
  ComposedChart, Line, Bar, Area, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea,
  ResponsiveContainer, CartesianGrid, Cell, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { normalizeChart } from '../lib/site'
import type { RawChart } from '../lib/site'

const RANGES: [string, number][] = [['3M', 92], ['6M', 183], ['1Y', 365], ['3Y', 1096], ['Max', 0]]

const TOOLTIP = {
  contentStyle: { background: '#151a23', border: '1px solid #2a3342', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
}

function filterByRange(rows: Record<string, number | string | null>[], days: number) {
  if (!days || !rows.length) return rows
  const maxD = String(rows[rows.length - 1].x)
  const cut = new Date(new Date(maxD).getTime() - days * 86400000).toISOString().slice(0, 10)
  return rows.filter(r => String(r.x) >= cut)
}

export default function SourceChart({ id, raw }: { id: string; raw: RawChart | undefined }) {
  const def = useMemo(() => (raw ? normalizeChart(raw, id) : null), [raw, id])
  const [range, setRange] = useState<string | null>(null)

  const { rows, numeric } = useMemo(() => {
    if (!def) return { rows: [], numeric: false }
    if (def.numericX) return { rows: [], numeric: true }
    const map = new Map<string, Record<string, number | string | null>>()
    def.traces.forEach((t, ti) => {
      t.x.forEach((x, i) => {
        const key = String(x)
        const row = map.get(key) ?? { x: key }
        row[`t${ti}`] = t.y[i]
        if (t.markerColors) row[`c${ti}`] = t.markerColors[i]
        map.set(key, row)
      })
    })
    return { rows: [...map.values()].sort((a, b) => String(a.x).localeCompare(String(b.x))), numeric: false }
  }, [def])

  if (!def) {
    return <div style={{ color: '#64748b', fontSize: 12, padding: '18px 0', textAlign: 'center' }}>图表数据暂缺</div>
  }

  // 数值坐标图 (regime clock 等)
  if (numeric) {
    return (
      <div>
        <ResponsiveContainer width="100%" height={def.mini ? 56 : 300}>
          <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="#1e2530" strokeDasharray="3 3" />
            <XAxis dataKey="x" type="number" tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} />
            <YAxis dataKey="y" type="number" tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} width={40} />
            <ZAxis range={[40]} />
            <Tooltip {...TOOLTIP} cursor={{ strokeDasharray: '3 3' }} />
            {def.traces.map((t, i) => (
              <Scatter key={i} name={t.name} data={t.x.map((x, j) => ({ x, y: t.y[j] }))}
                fill={t.color || '#38bdf8'} line={t.type !== 'scatter'} lineType="fitting" />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const activeRange = range ?? def.defaultRange ?? (def.mini ? '1Y' : '3Y')
  const days = RANGES.find(r => r[0] === activeRange)?.[1] ?? 0
  const data = filterByRange(rows, days)
  const height = def.mini ? 56 : 240

  return (
    <div>
      {!def.mini && (
        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', marginBottom: 2 }}>
          {RANGES.map(([r]) => (
            <button key={r} onClick={() => setRange(r)}
              style={{
                fontSize: 11, padding: '1px 7px', borderRadius: 5, cursor: 'pointer',
                border: '1px solid ' + (r === activeRange ? '#6366f1' : '#2a3342'),
                background: r === activeRange ? 'rgba(99,102,241,.15)' : 'transparent',
                color: r === activeRange ? '#a5b4fc' : '#64748b',
              }}>{r}</button>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: def.mini ? 0 : 6 }}>
          {!def.mini && <CartesianGrid stroke="#1e2530" strokeDasharray="3 3" vertical={false} />}
          <XAxis dataKey="x" hide={def.mini} tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false}
            axisLine={{ stroke: '#2a3342' }} minTickGap={def.mini ? 9999 : 50}
            tickFormatter={(v: string) => (v.length >= 7 ? v.slice(0, 7) : v)} />
          <YAxis hide={def.mini} tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} axisLine={false}
            width={44} domain={['auto', 'auto']} />
          {!def.mini && <Tooltip {...TOOLTIP} />}
          {def.refs.map((r, i) => (
            <ReferenceLine key={`ref${i}`} y={r.y} stroke={r.color || '#475569'}
              strokeDasharray={r.dash === 'dot' ? '2 4' : r.dash === 'dash' ? '6 4' : undefined}
              label={r.label && !def.mini ? { value: r.label, position: 'insideTopRight', fontSize: 9, fill: r.color || '#64748b' } : undefined} />
          ))}
          {def.bands.map((b, i) => (
            <ReferenceArea key={`band${i}`} x1={b.x0} x2={b.x1} fill="#f59e0b" fillOpacity={0.08}
              label={b.label && !def.mini ? { value: b.label, position: 'insideTop', fontSize: 9, fill: '#f59e0b' } : undefined} />
          ))}
          {def.traces.map((t, i) => {
            const color = t.color || '#38bdf8'
            if (t.type === 'bar') {
              return (
                <Bar key={i} dataKey={`t${i}`} name={t.name} fill={color} radius={def.mini ? 0 : [2, 2, 0, 0]}>
                  {t.markerColors ? data.map((r, j) => <Cell key={j} fill={(r[`c${i}`] as string) || color} />) : null}
                </Bar>
              )
            }
            if (t.type === 'area') {
              return <Area key={i} type="monotone" dataKey={`t${i}`} name={t.name} stroke={color}
                fill={t.fillcolor || color} fillOpacity={0.25} strokeWidth={1.4} dot={false} connectNulls
                strokeDasharray={t.dash === 'dot' ? '2 4' : t.dash === 'dash' ? '6 4' : undefined} />
            }
            return <Line key={i} type="monotone" dataKey={`t${i}`} name={t.name} stroke={color}
              strokeWidth={def.mini ? 1.2 : 1.6} dot={false} connectNulls
              strokeDasharray={t.dash === 'dot' ? '2 4' : t.dash === 'dash' ? '6 4' : undefined} />
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
