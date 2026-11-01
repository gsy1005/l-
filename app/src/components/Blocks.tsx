import { memo } from 'react'
import { splitChartTokens } from '../lib/site'
import type { SiteBlock, SiteData } from '../lib/site'
import SourceChart from './SourceChart'

/** 渲染含图表占位符的 HTML 片段 */
export const HtmlChunk = memo(function HtmlChunk({ html, charts }: { html: string; charts: SiteData['charts'] }) {
  const parts = splitChartTokens(html)
  return (
    <>
      {parts.map((p, i) =>
        'chartId' in p ? (
          <SourceChart key={i} id={p.chartId} raw={charts[p.chartId]} />
        ) : (
          <span key={i} dangerouslySetInnerHTML={{ __html: p.html }} />
        ),
      )}
    </>
  )
})

export function Block({ b, charts }: { b: SiteBlock; charts: SiteData['charts'] }) {
  switch (b.t) {
    case 'html':
      return (
        <div className={b.cls || undefined}>
          <HtmlChunk html={b.html || ''} charts={charts} />
        </div>
      )
    case 'chart':
      return <SourceChart id={b.id || ''} raw={charts[b.id || '']} />
    case 'cardgrid':
      return (
        <div className={b.kind || 'mc-grid'}>
          {(b.cards || []).map((c, i) => (
            <div key={i} className={c.cls || undefined}>
              <HtmlChunk html={c.html || ''} charts={charts} />
            </div>
          ))}
        </div>
      )
    case 'expander':
      return (
        <details className="fp-expand">
          <summary>{b.summary}</summary>
          {(b.blocks || []).map((c, i) => <Block key={i} b={c} charts={charts} />)}
        </details>
      )
    case 'layer':
      return <div className="layer-header" dangerouslySetInnerHTML={{ __html: b.html || '' }} />
    default:
      return null
  }
}
