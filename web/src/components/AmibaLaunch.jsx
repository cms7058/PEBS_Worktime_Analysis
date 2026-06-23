import { useEffect, useRef, useState } from 'react'
import { api, setToken } from '../api'

// 阿米巴「产品工作台 → 打开工作台」→ 浏览器跳到 /amiba/launch?平台令牌+产品+连接器令牌
// 本页用平台令牌核验登录、建本工具会话、按产品建/绑工序，然后带着会话进入主应用。
export default function AmibaLaunch() {
  const [state, setState] = useState('working') // working | error
  const [msg, setMsg] = useState('')
  const once = useRef(false)

  useEffect(() => {
    if (once.current) return
    once.current = true
    const q = new URLSearchParams(window.location.search)
    const body = {
      amiba_endpoint: q.get('amiba_endpoint') || '',
      platform_token: q.get('platform_token') || '',
      username: q.get('username') || '',
      tool: q.get('tool') || 'worktime',
      enterprise_id: q.get('enterprise_id') || '',
      enterprise_name: q.get('enterprise_name') || '',
      product_id: q.get('product_id') || '',
      part_no: q.get('part_no') || '',
      product_name: q.get('product_name') || '',
      connector_token: q.get('connector_token') || '',
    }
    if (!body.platform_token || !body.username || !body.product_id) {
      setState('error'); setMsg('登录参数不完整（缺 平台令牌 / 用户名 / 产品）')
      return
    }
    api.amibaLaunch(body)
      .then((res) => {
        setToken(res.token)
        // 让主应用进入后自动选中本产品对应的工序
        if (res.processId) localStorage.setItem('pebs_focus_process', String(res.processId))
        window.location.replace('/')
      })
      .catch((e) => { setState('error'); setMsg(e.message) })
  }, [])

  return (
    <div style={wrap}>
      <div className="card" style={box}>
        <h1 style={{ marginTop: 0 }}>登入 PEBS 视频工时</h1>
        {state === 'working' && <p>正在用阿米巴平台令牌登录并按产品建项目…</p>}
        {state === 'error' && (
          <>
            <p style={{ color: '#dc2626' }}>✗ 登录失败</p>
            <p className="hint">{msg}</p>
            <a href="/" style={btn}>返回</a>
          </>
        )}
      </div>
    </div>
  )
}

const wrap = { minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }
const box = { maxWidth: 440 }
const btn = { display: 'inline-block', marginTop: 12, padding: '8px 16px', background: '#3b82f6', color: '#fff', borderRadius: 6, textDecoration: 'none' }
