import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

export default function Batches({ process, setError }) {
  const { t } = useI18n()
  const [batches, setBatches] = useState([])
  const [uploading, setUploading] = useState(false)
  const [detail, setDetail] = useState(null)
  const fileRef = useRef(null)
  const [form, setForm] = useState({ label: '', backend: 'hands', sample_fps: 10, autostart: true })

  const reload = useCallback(() => {
    if (!process) return
    api.listBatches(process.id).then(setBatches).catch((e) => setError(e.message))
  }, [process, setError])

  useEffect(() => { reload() }, [reload])

  useEffect(() => {
    if (!batches.some((b) => b.status === 'pending' || b.status === 'running')) return
    const timer = setInterval(reload, 3000)
    return () => clearInterval(timer)
  }, [batches, reload])

  const upload = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return setError(t('请选择视频文件'))
    const fd = new FormData()
    fd.append('video', file)
    fd.append('label', form.label)
    fd.append('backend', form.backend)
    fd.append('sample_fps', form.sample_fps)
    fd.append('autostart', form.autostart)
    setUploading(true)
    try {
      await api.uploadBatch(process.id, fd)
      fileRef.current.value = ''
      reload()
    } catch (e) { setError(`${t('上传失败')}: ${e.message}`) } finally { setUploading(false) }
  }

  const openDetail = async (b) => {
    try { setDetail({ batch: b, cycles: await api.batchCycles(b.id) }) }
    catch (e) { setError(e.message) }
  }

  const run = async (b) => {
    try { await api.runBatch(b.id); reload() }
    catch (e) { setError(`${t('启动失败')}: ${e.message}`) }
  }

  if (!process) return <div className="card"><div className="empty">{t('请先选择工序')}</div></div>

  return (
    <>
      <div className="card">
        <h2>{t('上传采集批次 —')} {process.name}</h2>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: 2 }}>
            <span>{t('视频文件')}</span>
            <input type="file" ref={fileRef} accept="video/*" />
          </label>
          <label className="field" style={{ flex: 1, minWidth: 160 }}>
            <span>{t('批次标签（班次/日期）')}</span>
            <input type="text" value={form.label}
                   onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </label>
          <label className="field" style={{ width: 190 }}>
            <span>{t('感知后端')}</span>
            <select value={form.backend} onChange={(e) => setForm({ ...form, backend: e.target.value })}>
              <option value="pose">{t('pose（可见上半身）')}</option>
              <option value="hands">{t('hands（近景手部）')}</option>
            </select>
          </label>
          <label className="field" style={{ width: 110 }}>
            <span>{t('采样 fps')}</span>
            <input type="number" value={form.sample_fps} min="1" max="30"
                   onChange={(e) => setForm({ ...form, sample_fps: Number(e.target.value) })} />
          </label>
          <label className="field" style={{ width: 180 }}>
            <span>{t('上传后')}</span>
            <select value={form.autostart}
                    onChange={(e) => setForm({ ...form, autostart: e.target.value === 'true' })}>
              <option value="true">{t('立即分析')}</option>
              <option value="false">{t('仅上传（先画 ROI）')}</option>
            </select>
          </label>
          <button className="primary" disabled={uploading} onClick={upload}
                  style={{ marginBottom: 10 }}>
            {uploading ? t('上传中…') : t('上传')}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>{t('批次列表')}</h2>
        {batches.length === 0 ? <div className="empty">{t('暂无批次')}</div> : (
          <table>
            <thead><tr><th>ID</th><th>{t('标签')}</th><th>{t('后端')}</th><th>{t('状态')}</th>
              <th>{t('循环数')}</th><th>{t('节拍中位')}</th><th>{t('异常')}</th><th></th></tr></thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.id}>
                  <td>{b.id}</td>
                  <td>{b.label}</td>
                  <td>{b.backend}</td>
                  <td><span className={`status ${b.status}`}>{b.status}</span>
                      {b.error && <div className="hint">{b.error}</div>}</td>
                  <td>{b.summary ? `${b.summary.cycles_complete}/${b.summary.cycles_total}` : '—'}</td>
                  <td>{b.summary?.cycle_time_median != null ? `${b.summary.cycle_time_median}s` : '—'}</td>
                  <td>{b.summary?.anomalies ?? '—'}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {(b.status === 'pending' && !b.summary) || b.status === 'failed' ? (
                      <button className="ghost" onClick={() => run(b)}>{t('开始分析')}</button>
                    ) : null}{' '}
                    {b.status === 'done' && <button className="ghost" onClick={() => openDetail(b)}>{t('循环明细')}</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="card">
          <h2>{t('批次')} {detail.batch.id} {t('循环明细')}
            <button className="ghost" style={{ float: 'right' }} onClick={() => setDetail(null)}>{t('关闭')}</button>
          </h2>
          <table>
            <thead><tr><th>#</th><th>{t('起止 (s)')}</th><th>{t('时长')}</th><th>{t('状态')}</th>
              <th>{t('工步分解')}</th><th>{t('异常')}</th></tr></thead>
            <tbody>
              {detail.cycles.map((c) => (
                <tr key={c.cycle_idx}>
                  <td>{c.cycle_idx}</td>
                  <td>{c.t_start} – {c.t_end ?? '…'}</td>
                  <td>{c.duration != null ? `${c.duration}s` : '—'}</td>
                  <td><span className={`status ${c.status}`}>{c.status}</span></td>
                  <td>{c.steps.map((s) => `${s.step} ${s.duration ?? '?'}s`).join(' + ')}</td>
                  <td className="hint">{c.anomalies.map((a) => a.detail ?? a.type).join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
