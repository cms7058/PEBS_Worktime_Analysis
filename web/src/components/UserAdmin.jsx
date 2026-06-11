import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

// 用户管理对话框：管理员可见。
// 不用 window.prompt/confirm（部分内嵌浏览器会拦截）：
// 改密在行内展开输入框；删除/改角色用二次点击确认。
export default function UserAdmin({ currentUser, onClose, setError }) {
  const { t } = useI18n()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ username: '', password: '', role: 'user' })
  const [pwEdit, setPwEdit] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [notice, setNotice] = useState('')

  const reload = () => api.listUsers().then(setUsers).catch((e) => setError(e.message))
  useEffect(() => { reload() }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!confirm) return
    const timer = setTimeout(() => setConfirm(null), 4000)
    return () => clearTimeout(timer)
  }, [confirm])

  const add = async () => {
    if (!form.username || !form.password) return setError(t('用户名和密码必填'))
    try {
      await api.createUser(form)
      setForm({ username: '', password: '', role: 'user' })
      setNotice(t('用户已创建'))
      reload()
    } catch (e) { setError(`${t('新增失败')}: ${e.message}`) }
  }

  const savePassword = async () => {
    if (!pwEdit?.value || pwEdit.value.length < 4) return setError(t('密码至少 4 位'))
    try {
      await api.setUserPassword(pwEdit.id, pwEdit.value)
      setPwEdit(null)
      setNotice(t('密码已更新'))
    } catch (e) { setError(`${t('改密失败')}: ${e.message}`) }
  }

  const twoStep = (key, fn) => () => {
    if (confirm === key) { setConfirm(null); fn() }
    else setConfirm(key)
  }

  const toggleRole = (u) => twoStep(`role:${u.id}`, async () => {
    try {
      await api.setUserRole(u.id, u.role === 'admin' ? 'user' : 'admin')
      reload()
    } catch (e) { setError(`${t('改角色失败')}: ${e.message}`) }
  })

  const remove = (u) => twoStep(`del:${u.id}`, async () => {
    try { await api.deleteUser(u.id); reload() }
    catch (e) { setError(`${t('删除失败')}: ${e.message}`) }
  })

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{t('用户管理')}</h2>
          <button className="ghost" onClick={onClose}>{t('关闭')}</button>
        </div>

        {notice && (
          <div className="notice-banner" onClick={() => setNotice('')}>✓ {notice}</div>
        )}

        <div className="card" style={{ margin: 0, marginBottom: 12 }}>
          <h2>{t('新增用户')}</h2>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <label className="field" style={{ flex: 1 }}>
              <span>{t('用户名')}</span>
              <input type="text" value={form.username}
                     onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>{t('初始密码')}</span>
              <input type="text" value={form.password}
                     onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </label>
            <label className="field" style={{ width: 130 }}>
              <span>{t('角色')}</span>
              <select value={form.role}
                      onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="user">{t('普通用户')}</option>
                <option value="admin">{t('管理员')}</option>
              </select>
            </label>
            <button className="primary" onClick={add} style={{ marginBottom: 10 }}>{t('新增')}</button>
          </div>
        </div>

        <div className="card" style={{ margin: 0 }}>
          <table>
            <thead><tr><th>ID</th><th>{t('用户名')}</th><th>{t('角色')}</th><th>{t('创建时间')}</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td><b>{u.username}</b>{u.id === currentUser.id && <span className="hint">{t('（你）')}</span>}</td>
                  <td>
                    <span className={`status ${u.role === 'admin' ? 'complete' : 'incomplete'}`}>
                      {u.role === 'admin' ? t('管理员') : t('普通用户')}
                    </span>
                  </td>
                  <td className="hint">{u.created_at?.slice(0, 16).replace('T', ' ')}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {pwEdit?.id === u.id ? (
                      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                        <input type="text" autoFocus placeholder={t('新密码（≥4位）')}
                               style={{ width: 160 }}
                               value={pwEdit.value}
                               onChange={(e) => setPwEdit({ id: u.id, value: e.target.value })}
                               onKeyDown={(e) => e.key === 'Enter' && savePassword()} />
                        <button className="primary" style={{ padding: '4px 10px' }}
                                onClick={savePassword}>{t('确定')}</button>
                        <button className="ghost" style={{ padding: '4px 10px' }}
                                onClick={() => setPwEdit(null)}>{t('取消')}</button>
                      </span>
                    ) : (
                      <>
                        <button className="ghost"
                                onClick={() => { setPwEdit({ id: u.id, value: '' }); setConfirm(null) }}>
                          {t('改密')}
                        </button>{' '}
                        {u.id !== currentUser.id && (
                          <>
                            <button className={`ghost ${confirm === `role:${u.id}` ? 'danger' : ''}`}
                                    onClick={toggleRole(u)}>
                              {confirm === `role:${u.id}` ? t('再点一次确认') :
                                (u.role === 'admin' ? t('降为用户') : t('升为管理员'))}
                            </button>{' '}
                            <button className="ghost danger" onClick={remove(u)}>
                              {confirm === `del:${u.id}` ? t('确认删除？') : t('删除')}
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
