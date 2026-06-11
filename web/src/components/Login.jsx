import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n.jsx'

export default function Login({ onSuccess }) {
  const { t, lang, toggle } = useI18n()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!username || !password) return setError(t('请输入用户名和密码'))
    setBusy(true); setError('')
    try {
      const r = await api.login(username, password)
      onSuccess(r.token, r.user)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <h1>{t('PEBS 工时分析')}</h1>
          <button type="button" className="ghost" onClick={toggle}>
            {lang === 'en' ? '中文' : 'EN'}
          </button>
        </div>
        <p className="hint" style={{ marginBottom: 20 }}>{t('视频工时/工步采集分析系统')}</p>
        <label className="field">
          <span>{t('用户名')}</span>
          <input type="text" autoFocus value={username}
                 onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('密码')}</span>
          <input type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="error-banner" style={{ marginTop: 0 }}>{error}</div>}
        <button className="primary" disabled={busy} style={{ width: '100%', padding: '10px' }}>
          {busy ? t('登录中…') : t('登录')}
        </button>
        <p className="hint" style={{ marginTop: 16, textAlign: 'center' }}>
          {t('首次部署默认管理员 admin / admin123，登录后请在「用户管理」修改密码。')}
        </p>
      </form>
    </div>
  )
}
