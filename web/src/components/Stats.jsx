import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

function Histogram({ data, width = 420, height = 140 }) {
  const { t } = useI18n()
  if (!data?.counts?.length) return <div className="hint">{t('样本不足，无直方图')}</div>
  const max = Math.max(...data.counts)
  const barW = width / data.counts.length
  return (
    <svg width={width} height={height + 20}>
      {data.counts.map((c, i) => {
        const h = max ? (c / max) * height : 0
        return <rect key={i} x={i * barW + 2} y={height - h} width={barW - 4} height={h}
                     rx="2" fill="#3b82f6" />
      })}
      {data.edges.map((e, i) => (
        i % Math.ceil(data.edges.length / 6) === 0 && (
          <text key={i} x={i * barW} y={height + 14} fontSize="10" fill="#6b7280">{e}</text>
        )
      ))}
    </svg>
  )
}

function DescribeBlock({ title, d }) {
  const { t } = useI18n()
  if (!d || !d.n) return null
  const dist = d.distribution
  const notes = []
  if (dist) {
    if (dist.shapiro_raw && !dist.shapiro_raw['normal_at_0.05']) {
      notes.push(dist.shapiro_log?.['lognormal_at_0.05']
        ? t('分布右偏，近似对数正态（工时数据的典型形态）')
        : t('未通过正态/对数正态检验，建议检查异常样本'))
    }
    if (dist.suspected_bimodal) notes.push(t('疑似双峰：可能存在两种作业方法或人员熟练度差异'))
    if (dist.skewness > 1) notes.push(t('右侧长尾明显：存在偶发等待或异常慢循环'))
  }
  return (
    <div className="card">
      <h2>{title}</h2>
      <div>
        <span className="metric"><div className="v">{d.median}s</div><div className="l">{t('中位数')}</div></span>
        <span className="metric"><div className="v">{d.median_ci95 ? `${d.median_ci95[0]}–${d.median_ci95[1]}` : '—'}</div><div className="l">{t('95% 置信区间')}</div></span>
        <span className="metric"><div className="v">{d.p25} / {d.p75} / {d.p90}</div><div className="l">P25 / P75 / P90</div></span>
        <span className="metric"><div className="v">{d.cv != null ? `${(d.cv * 100).toFixed(0)}%` : '—'}</div><div className="l">{t('变异系数')}</div></span>
        <span className="metric"><div className="v">{d.n}</div><div className="l">{t('有效循环')}</div></span>
      </div>
      <Histogram data={d.histogram} />
      {notes.map((n, i) => <p key={i} className="hint">⚠ {n}</p>)}
    </div>
  )
}

export default function Stats({ process, setError }) {
  const { t } = useI18n()
  const [stats, setStats] = useState(null)
  const [eff, setEff] = useState(null)

  useEffect(() => {
    if (!process) return
    setStats(null); setEff(null)
    api.statistics(process.id).then(setStats).catch((e) => setError(e.message))
    api.efficiency(process.id).then(setEff).catch(() => setEff(null))
  }, [process, setError])

  if (!process) return <div className="card"><div className="empty">{t('请先选择工序')}</div></div>
  if (!stats) return <div className="card"><div className="empty">{t('加载中…')}</div></div>

  const statusEntries = Object.entries(stats.cycles_by_status ?? {})

  return (
    <>
      <div className="card" data-tour="stats-overview">
        <h2>{t('数据概览 —')} {process.name}</h2>
        {statusEntries.length === 0 ? <div className="empty">{t('该工序还没有分析数据')}</div> :
          statusEntries.map(([s, n]) => (
            <span key={s} className="metric">
              <div className="v">{n}</div><div className="l"><span className={`status ${s}`}>{s}</span></div>
            </span>
          ))}
        <p className="hint">{t('统计只纳入 complete 循环；其余状态单独计数，确保无样本被静默丢弃。')}</p>
      </div>

      <div data-tour="cycle-dist">
        <DescribeBlock title={t('循环工时分布')} d={stats.cycle_time} />
      </div>
      <div className="row">
        {Object.entries(stats.step_time ?? {}).map(([step, d]) => (
          <div key={step} style={{ flex: 1, minWidth: 380 }}>
            <DescribeBlock title={`${t('工步：')}${step}`} d={d} />
          </div>
        ))}
      </div>

      {eff && eff.steps?.some((s) => s.standard_seconds != null) && (
        <div className="card" data-tour="efficiency-table">
          <h2>{t('实测 vs 标准工时（PMTS）')}</h2>
          <table>
            <thead><tr><th>{t('工步')}</th><th>{t('实测中位')}</th><th>{t('标准工时')}</th>
              <th>{t('方法')}</th><th>{t('效率比')}</th><th>{t('改善空间')}</th></tr></thead>
            <tbody>
              {eff.steps.map((s) => (
                <tr key={s.step}>
                  <td>{s.step}</td>
                  <td>{s.measured_median != null ? `${s.measured_median}s` : '—'}</td>
                  <td>{s.standard_seconds != null ? `${s.standard_seconds}s` : t('未定义')}</td>
                  <td>{s.source ?? '—'}</td>
                  <td>{s.efficiency != null ? (
                    <b style={{ color: s.efficiency >= 0.95 ? '#15803d' : '#dc2626' }}>
                      {(s.efficiency * 100).toFixed(0)}%
                    </b>) : '—'}</td>
                  <td>{s.gap_seconds != null ? `${s.gap_seconds > 0 ? '+' : ''}${s.gap_seconds}s` : '—'}</td>
                </tr>
              ))}
              {eff.cycle_standard_seconds != null && (
                <tr style={{ fontWeight: 600 }}>
                  <td>{t('循环合计')}</td>
                  <td>{eff.cycle_measured_median}s</td>
                  <td>{eff.cycle_standard_seconds}s</td>
                  <td></td>
                  <td>{eff.cycle_efficiency != null ? `${(eff.cycle_efficiency * 100).toFixed(0)}%` : '—'}</td>
                  <td>{eff.cycle_gap_seconds != null ? `+${eff.cycle_gap_seconds}s` : '—'}</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="hint">
            {t('实测工步耗时包含手进出 ROI 的路径段，会系统性略长于纯操作理论值； 循环级差值还含工步间移动时间。对比应关注趋势而非个位百分比。')}
          </p>
        </div>
      )}
    </>
  )
}
