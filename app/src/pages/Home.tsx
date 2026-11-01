import { useMemo } from 'react'
import { useSite } from '../lib/site'
import { Block, HtmlChunk } from '../components/Blocks'
import '../source.css'
import '../App.css'

const NAV_LABELS: Record<string, string> = {
  'sec-lpi': '压力指数',
  'sec-funding': '资金与流动性',
  'sec-fedbs': '美联储资产负债表',
  'sec-credit': '信用',
  'sec-rates': '利率与期限溢价',
  'sec-crowding': '拥挤度',
  'sec-amplifiers': '放大器',
  'sec-recovery': '修复信号',
  'sec-calendar': '压力日历',
  'sec-methods': '方法',
}

export default function Home() {
  const { site, err } = useSite()

  const meta = useMemo(() => {
    if (!site) return { updated: '', health: '' }
    const u = site.headerHtml.match(/(?:Last updated|更新于)[:：]?\s*([\d-]+\s[\d:]+\s*UTC)/)
    const h = site.headerHtml.match(/(\d+\/\d+)\s*(?:current|最新)/)
    return { updated: u?.[1] ?? '', health: h ? `${h[1]} 最新` : '' }
  }, [site])

  if (err) {
    return <div style={{ padding: 40, color: '#f87171', background: '#0d0f14', minHeight: '100vh' }}>
      数据加载失败: {err} — 请先运行 python scripts/scrape_source.py</div>
  }
  if (!site) {
    return <div style={{ padding: 40, color: '#94a3b8', background: '#0d0f14', minHeight: '100vh' }}>正在加载 …</div>
  }

  return (
    <div className="src-page">
      <div className="header">
        <div className="header-left">
          <h1>美元流动性监测面板<span>/ 市场脆弱性</span></h1>
          <p>四层风险体系: 脆弱度 · 金融状况 · 拥挤度 · 放大器 · 每小时自动更新</p>
        </div>
        <div className="header-right">
          {meta.updated && <span>更新于 {meta.updated}</span>}
          {meta.health && <span>数据源 {meta.health}</span>}
        </div>
      </div>

      <nav className="sec-nav">
        <a href="#overview">总览</a>
        {site.sections.map(s => (
          <a key={s.id} href={`#${s.id}`}>{NAV_LABELS[s.id] ?? s.id}</a>
        ))}
      </nav>

      {site.blocks.map((b, i) => <Block key={i} b={b} charts={site.charts} />)}

      {site.sections.map(s => (
        <details key={s.id} className="sec" id={s.id} open={s.open}>
          <summary className="sec-sum">
            <HtmlChunk html={s.summaryHtml} charts={site.charts} />
          </summary>
          <div className="sec-body">
            {s.blocks.map((b, i) => <Block key={i} b={b} charts={site.charts} />)}
          </div>
        </details>
      ))}

      <footer style={{ borderTop: '1px solid var(--border, #1e2530)', padding: '18px 14px', textAlign: 'center', fontSize: 12, color: 'var(--faint, #64748b)' }}>
        数据快照生成于 {site.generatedAt} · 仅供研究, 不构成投资建议
      </footer>
    </div>
  )
}
