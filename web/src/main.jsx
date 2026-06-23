import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import AmibaRegister from './components/AmibaRegister.jsx'
import AmibaLaunch from './components/AmibaLaunch.jsx'
import { I18nProvider } from './i18n.jsx'
import './index.css'

// 简易按 pathname 分流：阿米巴接入/平台登录是独立入口页，其余走主应用。
function pickRoot() {
  const p = window.location.pathname
  if (p === '/register') return <AmibaRegister />
  if (p.startsWith('/amiba/launch')) return <AmibaLaunch />
  return <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <I18nProvider>
      {pickRoot()}
    </I18nProvider>
  </StrictMode>,
)
