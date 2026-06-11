import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 把助手的 Markdown 回复渲染成卡片化富文本：
// - 表格 → 卡片；若末列是数值，叠加一张水平条形图
// - 标题/列表/代码块/引用 → 基本排版
// - 段落紧凑，不浪费助手面板的纵向空间

const NUMERIC = /(-?\d+(?:\.\d+)?)\s*(s|ms|%)?/

function parseNumber(cell) {
  if (cell == null) return null
  const m = String(cell).match(NUMERIC)
  return m ? Number(m[1]) : null
}

function flatten(node) {
  if (node == null) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(flatten).join('')
  if (node.props?.children) return flatten(node.props.children)
  return ''
}

// 从 react-markdown 传入的 table 子节点里提取 head/body 文本矩阵.
// children 是 React 元素，按 element.type 识别（字符串或组件名）.
const TAG = (n) => (typeof n?.type === 'string' ? n.type
  : n?.type?.displayName ?? n?.type?.name ?? null)

function extractRows(children) {
  const arr = Array.isArray(children) ? children : [children]
  const sections = { head: [], body: [] }
  const rowOf = (tr) => {
    const cells = []
    const kids = tr?.props?.children
    const list = Array.isArray(kids) ? kids : kids ? [kids] : []
    list.forEach((td) => {
      const t = TAG(td)
      if (t === 'th' || t === 'td') cells.push(flatten(td.props.children).trim())
    })
    return cells
  }
  const collect = (node, target) => {
    const kids = node?.props?.children
    const list = Array.isArray(kids) ? kids : kids ? [kids] : []
    list.forEach((tr) => {
      if (TAG(tr) === 'tr') {
        const row = rowOf(tr)
        if (row.length) target.push(row)
      }
    })
  }
  arr.forEach((n) => {
    const t = TAG(n)
    if (t === 'thead') collect(n, sections.head)
    else if (t === 'tbody') collect(n, sections.body)
  })
  // 兜底：有些版本不分 thead/tbody，children 里直接是 tr
  if (!sections.head.length && !sections.body.length) {
    arr.forEach((n, i) => {
      if (TAG(n) === 'tr') {
        const row = rowOf(n)
        if (row.length) (i === 0 ? sections.head : sections.body).push(row)
      }
    })
  }
  return sections
}

function TableCard({ children }) {
  const { head, body } = useMemo(() => extractRows(children), [children])
  // 找一列全是数值的列作为条形图依据，优先取最右侧数值列
  let chartCol = -1
  if (body.length >= 2) {
    const cols = body[0].length
    for (let c = cols - 1; c >= 1; c--) {
      const vals = body.map((r) => parseNumber(r[c]))
      if (vals.every((v) => v != null && Number.isFinite(v))) { chartCol = c; break }
    }
  }
  const chartData = chartCol >= 0
    ? body.map((r) => ({ label: r[0], raw: r[chartCol], value: parseNumber(r[chartCol]) }))
    : null
  const max = chartData ? Math.max(...chartData.map((d) => Math.abs(d.value)), 0.0001) : 0

  return (
    <div className="md-table-card">
      <div className="md-table-scroll">
        <table className="md-table">
          {head.length > 0 && (
            <thead><tr>{head[0].map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
          )}
          <tbody>
            {body.map((row, i) => (
              <tr key={i}>{row.map((c, j) => <td key={j}>{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {chartData && (
        <svg className="md-chart" viewBox={`0 0 200 ${chartData.length * 20 + 4}`} preserveAspectRatio="none">
          {chartData.map((d, i) => {
            const w = (Math.abs(d.value) / max) * 130
            const neg = d.value < 0
            return (
              <g key={i} transform={`translate(0, ${i * 20 + 2})`}>
                <text x="0" y="12" fontSize="9" fill="#374151">{d.label}</text>
                <rect x="60" y="4" width={w} height="11" rx="2"
                      fill={neg ? '#ef4444' : '#3b82f6'} />
                <text x={62 + w} y="12" fontSize="9" fill="#374151">{d.raw}</text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

const COMPONENTS = {
  table: TableCard,
  h1: ({ children }) => <div className="md-h">{children}</div>,
  h2: ({ children }) => <div className="md-h">{children}</div>,
  h3: ({ children }) => <div className="md-h">{children}</div>,
  h4: ({ children }) => <div className="md-h md-h-sub">{children}</div>,
  p: ({ children }) => <div className="md-p">{children}</div>,
  ul: ({ children }) => <ul className="md-list">{children}</ul>,
  ol: ({ children }) => <ol className="md-list">{children}</ol>,
  code: ({ inline, children }) =>
    inline ? <code className="md-code-inline">{children}</code>
           : <pre className="md-code"><code>{children}</code></pre>,
  blockquote: ({ children }) => <div className="md-quote">{children}</div>,
  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
}

export default function RichMessage({ text }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {text}
    </ReactMarkdown>
  )
}
