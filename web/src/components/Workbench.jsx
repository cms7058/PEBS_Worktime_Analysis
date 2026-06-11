import { useEffect, useMemo, useRef, useState } from 'react'
import yaml from 'js-yaml'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

const COLORS = ['#16a34a', '#ea580c', '#2563eb', '#9333ea']
const CANVAS_W = 640
const KEYPOINT_OPTIONS = [
  ['left_wrist', '左手腕'], ['right_wrist', '右手腕'],
  ['left_index_tip', '左食指尖'], ['right_index_tip', '右食指尖'],
]
const EVENT_OPTIONS = [['roi_enter', '进入区域'], ['roi_exit', '离开区域']]

// 可视化配置工作台：左侧画布画 ROI，右侧表单编辑工步；YAML 仅作为高级视图
export default function Workbench({ process, reload, setError }) {
  const { t } = useI18n()
  const [configText, setConfigText] = useState('')
  const [batches, setBatches] = useState([])
  const [batchId, setBatchId] = useState(null)
  const [tSec, setTSec] = useState(2)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showYaml, setShowYaml] = useState(false)
  const canvasRef = useRef(null)
  const imgRef = useRef(null)
  const dragRef = useRef(null)

  const parsed = useMemo(() => {
    try { return { cfg: yaml.load(configText) ?? {}, err: null } }
    catch (e) { return { cfg: null, err: e.message } }
  }, [configText])
  const cfg = parsed.cfg

  useEffect(() => {
    if (!process) return
    api.getProcess(process.id)
      .then((p) => { setConfigText(p.config_yaml); setDirty(false) })
      .catch((e) => setError(`${t('加载配置失败')}: ${e.message}`))
    api.listBatches(process.id)
      .then((bs) => { setBatches(bs); setBatchId((cur) => bs.some((b) => b.id === cur) ? cur : bs[0]?.id ?? null) })
      .catch((e) => setError(`${t('加载批次失败')}: ${e.message}`))
  }, [process, setError])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!batchId) { imgRef.current = null; draw(); return }
    const img = new Image()
    img.onload = () => { imgRef.current = img; draw() }
    img.onerror = () => { imgRef.current = null; draw() }
    img.src = api.frameUrl(batchId, tSec)
  }, [batchId, tSec])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { draw() })

  function draw(tempRect) {
    const canvas = canvasRef.current
    if (!canvas) return
    const img = imgRef.current
    const ratio = img ? img.height / img.width : 9 / 16
    canvas.width = CANVAS_W
    canvas.height = Math.round(CANVAS_W * ratio)
    const ctx = canvas.getContext('2d')
    if (img) ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    else {
      ctx.fillStyle = '#e5e7eb'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = '#6b7280'; ctx.font = '14px sans-serif'
      ctx.fillText(batches.length ? t('底图加载中…') : t('先到「批次分析」上传一段视频（可选不立即分析）'), 20, 30)
    }
    ;(cfg?.rois ?? []).forEach((roi, i) => {
      const [x1, y1, x2, y2] = roi.rect
      ctx.strokeStyle = COLORS[i % COLORS.length]
      ctx.lineWidth = 2
      ctx.strokeRect(x1 * canvas.width, y1 * canvas.height,
        (x2 - x1) * canvas.width, (y2 - y1) * canvas.height)
      ctx.fillStyle = COLORS[i % COLORS.length]
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText(roi.name, x1 * canvas.width + 4, y1 * canvas.height + 16)
    })
    if (tempRect) {
      ctx.strokeStyle = '#dc2626'; ctx.setLineDash([5, 4])
      ctx.strokeRect(tempRect.x, tempRect.y, tempRect.w, tempRect.h)
      ctx.setLineDash([])
    }
  }

  const norm = (e) => {
    const rect = canvasRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }
  const onMouseDown = (e) => { dragRef.current = norm(e) }
  const onMouseMove = (e) => {
    if (!dragRef.current) return
    const p = norm(e); const s = dragRef.current
    draw({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) })
  }
  const onMouseUp = (e) => {
    const s = dragRef.current; dragRef.current = null
    if (!s || !cfg) return
    const p = norm(e)
    const canvas = canvasRef.current
    if (Math.abs(p.x - s.x) < 8 || Math.abs(p.y - s.y) < 8) { draw(); return }
    const existing = new Set((cfg.rois ?? []).map((r) => r.name))
    let n = (cfg.rois?.length ?? 0) + 1
    while (existing.has(`${t('区域')}${n}`)) n++
    const name = `${t('区域')}${n}`
    const rect = [
      Math.min(s.x, p.x) / canvas.width, Math.min(s.y, p.y) / canvas.height,
      Math.max(s.x, p.x) / canvas.width, Math.max(s.y, p.y) / canvas.height,
    ].map((v) => Math.round(v * 1000) / 1000)
    update((c) => { c.rois = [...(c.rois ?? []), { name, rect }] })
  }

  function update(mutator) {
    const next = yaml.load(configText) ?? {}
    mutator(next)
    setConfigText(yaml.dump(next, { lineWidth: 100, flowLevel: 3 }))
    setDirty(true)
  }

  const save = async () => {
    if (parsed.err) return setError(`${t('YAML 语法错误')}: ${parsed.err}`)
    if (!(cfg?.steps ?? []).length) return setError(t('至少需要一个工步'))
    setSaving(true)
    try {
      await api.updateProcess(process.id, { config_yaml: configText })
      setDirty(false); await reload()
    } catch (e) { setError(`${t('保存失败')}: ${e.message}`) } finally { setSaving(false) }
  }

  if (!process) return <div className="card"><div className="empty">{t('请先在工序库创建或选择一个工序')}</div></div>

  const roiNames = (cfg?.rois ?? []).map((r) => r.name)
  const keypoints = cfg?.keypoints ?? []

  return (
    <div className="row">
      {/* 左：ROI 画布 */}
      <div className="card" style={{ flex: '0 0 680px' }}>
        <h2>{t('区域（ROI）—')} {process.name}</h2>
        <div className="row" style={{ marginBottom: 10, alignItems: 'center' }}>
          <select style={{ width: 240 }} value={batchId ?? ''} onChange={(e) => setBatchId(Number(e.target.value))}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>{t('批次')}{b.id} {b.label || ''}（{b.status}）</option>
            ))}
            {!batches.length && <option value="">{t('（无视频，先上传批次）')}</option>}
          </select>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
            <span className="hint">t={tSec}s</span>
            <input type="range" min="0" max="60" step="0.5" value={tSec}
                   onChange={(e) => setTSec(Number(e.target.value))} style={{ flex: 1 }} />
          </label>
        </div>
        <div className="canvas-wrap">
          <canvas ref={canvasRef} onMouseDown={onMouseDown} onMouseMove={onMouseMove}
                  onMouseUp={onMouseUp} onMouseLeave={() => { dragRef.current = null; draw() }} />
        </div>
        <p className="hint">{t('在画面上按住拖拽即可新增区域；先选一帧手不遮挡工位的画面再画框。')}</p>
        {(cfg?.rois ?? []).map((roi, i) => (
          <div key={i} style={{ fontSize: 13, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: COLORS[i % COLORS.length], fontWeight: 600 }}>■</span>
            <input type="text" value={roi.name} style={{ width: 130 }}
                   onChange={(e) => update((c) => { c.rois[i].name = e.target.value })} />
            <span className="hint">[{roi.rect.join(', ')}]</span>
            <button className="ghost danger" style={{ padding: '1px 8px' }}
                    onClick={() => update((c) => { c.rois.splice(i, 1) })}>{t('删')}</button>
          </div>
        ))}
      </div>

      {/* 右：可视化工步配置 */}
      <div className="card" style={{ minWidth: 420 }}>
        <h2>{t('工序配置')} {dirty && <span className="hint">{t('（未保存）')}</span>}</h2>
        {parsed.err ? (
          <p style={{ color: '#dc2626', fontSize: 12 }}>{t('YAML 解析失败')}：{parsed.err}{t('（请在高级视图修复）')}</p>
        ) : (
          <>
            <label className="field">
              <span>{t('工序标识')}</span>
              <input type="text" value={cfg?.process ?? ''}
                     onChange={(e) => update((c) => { c.process = e.target.value })} />
            </label>
            <div className="field">
              <span style={{ display: 'block', marginBottom: 4 }}>
                {t('跟踪关键点（近景手部视角选食指尖，能看到上半身选手腕）')}
              </span>
              {KEYPOINT_OPTIONS.map(([kp, label]) => (
                <label key={kp} style={{ marginRight: 14, fontSize: 13 }}>
                  <input type="checkbox" checked={keypoints.includes(kp)}
                         onChange={(e) => update((c) => {
                           c.keypoints = e.target.checked
                             ? [...(c.keypoints ?? []), kp]
                             : (c.keypoints ?? []).filter((k) => k !== kp)
                         })} /> {t(label)}
                </label>
              ))}
            </div>

            <h2 style={{ marginTop: 18 }}>{t('工步序列')}
              <span className="hint">　{t('按顺序执行，全部完成记为一个循环')}</span>
            </h2>
            {(cfg?.steps ?? []).map((step, i) => (
              <StepCard key={i} step={step} idx={i} total={cfg.steps.length}
                        roiNames={roiNames} keypoints={keypoints} update={update} />
            ))}
            <button className="ghost" style={{ marginBottom: 14 }}
                    onClick={() => update((c) => {
                      c.steps = [...(c.steps ?? []), {
                        name: `${t('工步')}${(c.steps?.length ?? 0) + 1}`,
                        start: { event: 'roi_enter', roi: roiNames[0] ?? '', keypoint: 'any' },
                        end: { event: 'roi_exit', roi: roiNames[0] ?? '', keypoint: 'same' },
                      }]
                    })}>{t('+ 添加工步')}</button>
          </>
        )}

        <div>
          <button className="primary" disabled={saving || !dirty} onClick={save}>
            {saving ? t('保存中…') : t('保存配置')}
          </button>{' '}
          <button className="ghost" onClick={() => setShowYaml(!showYaml)}>
            {showYaml ? t('收起 YAML') : t('高级：查看/编辑 YAML')}
          </button>
        </div>
        {showYaml && (
          <textarea className="yaml" style={{ marginTop: 10 }} value={configText}
                    onChange={(e) => { setConfigText(e.target.value); setDirty(true) }} />
        )}
      </div>
    </div>
  )
}

// 事件选择器：事件类型 + 区域 + 触发关键点
function EventEditor({ label, value, roiNames, keypoints, allowSame, onChange }) {
  const { t } = useI18n()
  const v = value ?? {}
  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6, fontSize: 13 }}>
      <span className="hint" style={{ width: 38 }}>{label}</span>
      <select value={v.keypoint ?? 'any'} style={{ width: 150 }}
              onChange={(e) => onChange({ ...v, keypoint: e.target.value })}>
        <option value="any">{t('任意手')}</option>
        {allowSame && <option value="same">{t('与起始同一只手')}</option>}
        {keypoints.map((k) => <option key={k} value={k}>{k}</option>)}
      </select>
      <select value={v.event ?? 'roi_enter'} style={{ width: 130 }}
              onChange={(e) => onChange({ ...v, event: e.target.value })}>
        {EVENT_OPTIONS.map(([ev, l]) => <option key={ev} value={ev}>{t(l)}</option>)}
      </select>
      <select value={v.roi ?? ''} style={{ flex: 1 }}
              onChange={(e) => onChange({ ...v, roi: e.target.value })}>
        {!v.roi && <option value="">{t('（选择区域）')}</option>}
        {roiNames.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
    </div>
  )
}

// 单个工步卡片：起止事件、超时上限、标准工时（MODAPTS 实时计算）
function StepCard({ step, idx, total, roiNames, keypoints, update }) {
  const { t } = useI18n()
  const std = step.standard
  const stdType = !std ? 'none' : (std.seconds != null ? 'seconds' : 'modapts')
  const [calc, setCalc] = useState(null)

  const sequence = useMemo(() => (std?.sequence ?? []).join(' '), [std])

  useEffect(() => {
    if (stdType !== 'modapts' || !std?.sequence?.length) { setCalc(null); return }
    const timer = setTimeout(() => {
      api.pmtsCalc(std.sequence, std.method ?? 'modapts', std.allowance ?? 0)
        .then(setCalc)
        .catch((e) => setCalc({ error: e.message }))
    }, 500)
    return () => clearTimeout(timer)
  }, [sequence, std?.allowance, stdType])   // eslint-disable-line react-hooks/exhaustive-deps

  const mut = (fn) => update((c) => fn(c.steps[idx], c))

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 12px', marginBottom: 10 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <b style={{ fontSize: 13 }}>#{idx + 1}</b>
        <input type="text" value={step.name ?? ''} style={{ width: 140 }}
               onChange={(e) => mut((s) => { s.name = e.target.value })} />
        <span style={{ flex: 1 }} />
        <button className="ghost" style={{ padding: '1px 7px' }} disabled={idx === 0}
                onClick={() => update((c) => {
                  [c.steps[idx - 1], c.steps[idx]] = [c.steps[idx], c.steps[idx - 1]]
                })}>↑</button>
        <button className="ghost" style={{ padding: '1px 7px' }} disabled={idx === total - 1}
                onClick={() => update((c) => {
                  [c.steps[idx + 1], c.steps[idx]] = [c.steps[idx], c.steps[idx + 1]]
                })}>↓</button>
        <button className="ghost danger" style={{ padding: '1px 7px' }}
                onClick={() => update((c) => { c.steps.splice(idx, 1) })}>{t('删')}</button>
      </div>

      <EventEditor label={t('开始')} value={step.start} roiNames={roiNames}
                   keypoints={keypoints} allowSame={false}
                   onChange={(v) => mut((s) => { s.start = v })} />
      <EventEditor label={t('结束')} value={step.end} roiNames={roiNames}
                   keypoints={keypoints} allowSame
                   onChange={(v) => mut((s) => { s.end = v })} />

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, marginBottom: 6 }}>
        <span className="hint">{t('超时上限')}</span>
        <input type="number" min="0" step="0.5" style={{ width: 80 }}
               value={step.max_duration ?? ''}
               placeholder={t('不限')}
               onChange={(e) => mut((s) => {
                 if (e.target.value === '') delete s.max_duration
                 else s.max_duration = Number(e.target.value)
               })} />
        <span className="hint">{t('秒（超过记异常）')}</span>
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, flexWrap: 'wrap' }}>
        <span className="hint">{t('标准工时')}</span>
        <select value={stdType} style={{ width: 160 }}
                onChange={(e) => mut((s) => {
                  if (e.target.value === 'none') delete s.standard
                  else if (e.target.value === 'seconds') s.standard = { seconds: 1.0 }
                  else s.standard = { method: 'modapts', sequence: ['M4', 'G1'] }
                })}>
          <option value="none">{t('不设置')}</option>
          <option value="modapts">{t('MODAPTS 序列')}</option>
          <option value="seconds">{t('直接给秒数')}</option>
        </select>
        {stdType === 'seconds' && (
          <>
            <input type="number" min="0" step="0.1" style={{ width: 80 }}
                   value={std.seconds}
                   onChange={(e) => mut((s) => { s.standard.seconds = Number(e.target.value) })} />
            <span className="hint">{t('秒')}</span>
          </>
        )}
        {stdType === 'modapts' && (
          <>
            <input type="text" style={{ width: 150 }} value={sequence}
                   placeholder={t('如 M4 G3 M4 P2')}
                   onChange={(e) => mut((s) => {
                     s.standard.sequence = e.target.value.split(/[\s,，]+/).filter(Boolean)
                   })} />
            <span className="hint">{t('宽放')}</span>
            <input type="number" min="0" max="99" style={{ width: 60 }}
                   value={Math.round((std.allowance ?? 0) * 100)}
                   onChange={(e) => mut((s) => {
                     s.standard.allowance = Number(e.target.value) / 100
                   })} />
            <span className="hint">%</span>
            {calc && (calc.error
              ? <span style={{ color: '#dc2626' }}>✗ {calc.error}</span>
              : <b style={{ color: '#15803d' }}>= {calc.standard_seconds}s</b>)}
          </>
        )}
      </div>
      {stdType === 'modapts' && (
        <p className="hint" style={{ margin: '4px 0 0' }}>
          {t('常用：M1手指 M2手腕 M3小臂 M4大臂 M5伸臂 / G1简单抓 G3复杂抓 / P0放下 P2对准放 P5精确放')}
        </p>
      )}
    </div>
  )
}
