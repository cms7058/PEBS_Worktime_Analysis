import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

const TEMPLATE = `process: new_process
keypoints: [left_wrist, right_wrist]

rois:
  - name: parts_bin
    rect: [0.05, 0.35, 0.30, 0.75]
  - name: fixture
    rect: [0.45, 0.40, 0.75, 0.85]

steps:
  - name: pick
    start: {event: roi_enter, roi: parts_bin, keypoint: any}
    end:   {event: roi_exit,  roi: parts_bin, keypoint: same}
    max_duration: 5.0
  - name: place
    start: {event: roi_enter, roi: fixture, keypoint: any}
    end:   {event: roi_exit,  roi: fixture, keypoint: same}
    max_duration: 8.0
`

export default function ProcessLibrary({ processes, reload, onSelect, setError }) {
  const { t } = useI18n()
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [configYaml, setConfigYaml] = useState(TEMPLATE)
  const [busy, setBusy] = useState(false)
  const [confirmDel, setConfirmDel] = useState(null)

  const submit = async () => {
    if (!name.trim()) return setError(t('请填写工序名称'))
    setBusy(true)
    try {
      const p = await api.createProcess({ name, description, config_yaml: configYaml })
      setShowForm(false); setName(''); setDescription('')
      await reload()
      onSelect(p.id, 'workbench')
    } catch (e) { setError(`${t('创建失败')}: ${e.message}`) } finally { setBusy(false) }
  }

  const clone = async (p) => {
    try { await api.cloneProcess(p.id, `${p.name}${t('-副本')}`); await reload() }
    catch (e) { setError(`${t('复制失败')}: ${e.message}`) }
  }

  const remove = async (p) => {
    if (confirmDel !== p.id) {
      setConfirmDel(p.id)
      setTimeout(() => setConfirmDel(null), 4000)
      return
    }
    setConfirmDel(null)
    try { await api.deleteProcess(p.id); await reload() }
    catch (e) { setError(`${t('删除失败')}: ${e.message}`) }
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>{t('工序库')}</h2>
          <button className="primary" data-tour="new-process" onClick={() => setShowForm(!showForm)}>
            {showForm ? t('收起') : t('+ 新建工序')}
          </button>
        </div>
        {showForm && (
          <div style={{ marginTop: 14 }} data-tour="new-process-form">
            <div className="row">
              <label className="field" style={{ flex: 1 }}>
                <span>{t('名称')}</span>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field" style={{ flex: 2 }}>
                <span>{t('描述')}</span>
                <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
              </label>
            </div>
            <label className="field">
              <span>{t('配置 YAML（ROI 坐标可先用模板值，建完后到「配置工作台」对着画面拖框调整）')}</span>
              <textarea className="yaml" value={configYaml} onChange={(e) => setConfigYaml(e.target.value)} />
            </label>
            <button className="primary" disabled={busy} onClick={submit}>
              {busy ? t('创建中…') : t('创建并进入工作台')}
            </button>
          </div>
        )}
      </div>

      <div className="card">
        {processes.length === 0 ? (
          <div className="empty">{t('还没有工序，点「+ 新建工序」开始')}</div>
        ) : (
          <table>
            <thead><tr><th>ID</th><th>{t('名称')}</th><th>{t('描述')}</th><th>{t('更新时间')}</th><th></th></tr></thead>
            <tbody>
              {processes.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td><b>{p.name}</b></td>
                  <td>{p.description}</td>
                  <td>{p.updated_at?.slice(0, 16).replace('T', ' ')}</td>
                  <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                    <button className="ghost" onClick={() => onSelect(p.id, 'workbench')}>{t('配置')}</button>{' '}
                    <button className="ghost" onClick={() => onSelect(p.id, 'batches')}>{t('批次')}</button>{' '}
                    <button className="ghost" onClick={() => clone(p)}>{t('复制')}</button>{' '}
                    <button className="ghost danger" onClick={() => remove(p)}>
                      {confirmDel === p.id ? t('确认删除？') : t('删除')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
