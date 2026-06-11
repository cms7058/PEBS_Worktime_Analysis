import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import ProcessLibrary from './components/ProcessLibrary.jsx'
import Workbench from './components/Workbench.jsx'
import Batches from './components/Batches.jsx'
import Stats from './components/Stats.jsx'
import AssistantPanel from './components/AssistantPanel.jsx'
import Login from './components/Login.jsx'
import UserAdmin from './components/UserAdmin.jsx'
import { useI18n } from './i18n.jsx'

const TABS = [
  ['library', '工序库'],
  ['workbench', '配置工作台'],
  ['batches', '批次分析'],
  ['stats', '统计看板'],
]

export default function App() {
  const { t, lang, toggle } = useI18n()
  const [user, setUser] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [tab, setTab] = useState('library')
  const [processes, setProcesses] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState('')
  const [showUserAdmin, setShowUserAdmin] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  // 点击页面其他区域关闭用户菜单
  useEffect(() => {
    if (!menuOpen) return
    const close = () => setMenuOpen(false)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [menuOpen])

  const [assistantWidth, setAssistantWidth] = useState(
    () => Number(localStorage.getItem('assistantWidth')) || 360)
  const dragRef = useRef(null)
  const widthRef = useRef(assistantWidth)
  useEffect(() => {
    const onMove = (e) => {
      if (!dragRef.current) return
      const w = Math.min(720, Math.max(260, window.innerWidth - e.clientX))
      widthRef.current = w
      setAssistantWidth(w)
    }
    const onUp = () => {
      if (dragRef.current) {
        localStorage.setItem('assistantWidth', String(widthRef.current))
        dragRef.current = null
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [])
  const startDrag = () => {
    dragRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  // 鉴权初始化
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    if (!getToken()) { setAuthReady(true); return }
    api.me().then(setUser).catch(() => setToken(''))
      .finally(() => setAuthReady(true))
  }, [])

  const reload = useCallback(async () => {
    if (!user) return
    try {
      const list = await api.listProcesses()
      setProcesses(list)
      setSelectedId((cur) => (list.some((p) => p.id === cur) ? cur : list[0]?.id ?? null))
    } catch (e) { setError(`${t('加载工序失败')}: ${e.message}`) }
  }, [user])

  useEffect(() => { reload() }, [reload])

  const logout = async () => {
    try { await api.logout() } catch { /* 忽略 */ }
    setToken(''); setUser(null); setProcesses([])
  }

  if (!authReady) return null
  if (!user) {
    return <Login onSuccess={(token, u) => { setToken(token); setUser(u) }} />
  }

  const selected = processes.find((p) => p.id === selectedId) ?? null
  const tabLabel = t(TABS.find(([k]) => k === tab)?.[1] ?? tab)
  const view = {
    library: <ProcessLibrary processes={processes} reload={reload}
                             onSelect={(id, nextTab) => { setSelectedId(id); if (nextTab) setTab(nextTab) }}
                             setError={setError} />,
    workbench: <Workbench process={selected} reload={reload} setError={setError} />,
    batches: <Batches process={selected} setError={setError} />,
    stats: <Stats process={selected} setError={setError} />,
  }[tab]

  return (
    <>
      <header className="topbar">
        <h1>{t('PEBS 工时分析')}</h1>
        <nav>
          {TABS.map(([key, label]) => (
            <button key={key} className={tab === key ? 'active' : ''}
                    onClick={() => setTab(key)}>{t(label)}</button>
          ))}
        </nav>
        <div className="spacer" />
        {tab !== 'library' && (
          <select value={selectedId ?? ''} onChange={(e) => setSelectedId(Number(e.target.value))}
                  style={{ marginRight: 12 }}>
            {processes.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {!processes.length && <option value="">{t('（暂无工序）')}</option>}
          </select>
        )}
        <div className="user-menu" onClick={(e) => e.stopPropagation()}>
          <button className="ghost topbar-btn" onClick={() => setMenuOpen(!menuOpen)}>
            👤 {user.username}
            {user.role === 'admin' && <span className="role-badge">{t('管理员')}</span>}
            <span style={{ marginLeft: 6, fontSize: 10 }}>{menuOpen ? '▲' : '▼'}</span>
          </button>
          {menuOpen && (
            <div className="dropdown">
              <button onClick={() => { toggle(); setMenuOpen(false) }}>
                🌐 {lang === 'en' ? '切换为中文' : 'Switch to English'}
              </button>
              {user.role === 'admin' && (
                <button onClick={() => { setShowUserAdmin(true); setMenuOpen(false) }}>
                  ⚙ {t('用户管理')}
                </button>
              )}
              <button onClick={() => { setMenuOpen(false); logout() }}>
                ⏻ {t('注销')}
              </button>
            </div>
          )}
        </div>
      </header>
      <div className="layout">
        <main>
          {error && (
            <div className="error-banner" onClick={() => setError('')}>
              {error}{t('（点击关闭）')}
            </div>
          )}
          {view}
        </main>
        <div className="resizer" onMouseDown={startDrag} title={t('拖动调整助手面板宽度')} />
        <AssistantPanel tab={tab} tabLabel={tabLabel} process={selected}
                        width={assistantWidth}
                        onDataChanged={reload} setError={setError} />
      </div>
      {showUserAdmin && (
        <UserAdmin currentUser={user} onClose={() => setShowUserAdmin(false)} setError={setError} />
      )}
    </>
  )
}
