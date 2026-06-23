import { useEffect, useRef, useState } from 'react'
import { api, setToken } from '../api'

// 阿米巴「重新接入/换令牌」→ 浏览器跳到 /register，携带：
//   连接器令牌(amiba_token) + 企业 + source（数据回填通道）
//   平台登录令牌(platform_token) + 用户名（登录凭证）
//   选定的产品(product_id/part_no/product_name/enterprise_name)
// 本页：① 登记连接器（hello）② 用平台令牌登录建会话 ③ 若带产品则按产品建计时项目
//   → 存好会话与项目上下文 → 直接进入真正的工时操作页（顶部内嵌该产品计时横幅）。
export default function AmibaRegister() {
  const [state, setState] = useState('working') // working | ok | error
  const [msg, setMsg] = useState('')
  const once = useRef(false)

  useEffect(() => {
    if (once.current) return
    once.current = true
    ;(async () => {
      const q = new URLSearchParams(window.location.search)
      const amiba_endpoint = q.get('amiba_endpoint') || ''
      const amiba_token = q.get('amiba_token') || ''
      const enterprise_id = q.get('enterprise_id') || ''
      const source = q.get('source') || 'worktime'
      const platform_token = q.get('platform_token') || ''
      const username = q.get('username') || ''
      const product_id = q.get('product_id') || ''

      if (!amiba_endpoint || !amiba_token || !enterprise_id) {
        setState('error'); setMsg('接入参数不完整（缺 amiba_endpoint / amiba_token / enterprise_id）')
        return
      }
      try {
        // ① 登记连接器（数据回填通道）+ hello
        await api.amibaRegister({ amiba_endpoint, amiba_token, enterprise_id, source })

        // ② / ③ 平台登录（+ 带产品则建计时项目）
        if (platform_token && username) {
          if (product_id) {
            const d = await api.amibaLaunch({
              amiba_endpoint, platform_token, username, tool: source,
              enterprise_id, enterprise_name: q.get('enterprise_name') || '',
              product_id, part_no: q.get('part_no') || '', product_name: q.get('product_name') || '',
              connector_token: amiba_token, team: [],
            })
            setToken(d.token)
            localStorage.setItem('worktime-amiba-project', JSON.stringify({
              projectId: d.projectId, productName: d.productName, partNo: d.partNo, enterpriseName: d.enterpriseName,
            }))
            window.location.replace('/')
            return
          }
          const d = await api.amibaPlatformLogin({ amiba_endpoint, platform_token, username, tool: source, enterprise_id })
          setToken(d.token)
          window.location.replace('/')
          return
        }

        setState('ok'); setMsg('已与阿米巴建立数据回填通道。')
      } catch (e) {
        setState('error'); setMsg(e.message)
      }
    })()
  }, [])

  return (
    <div style={wrap}>
      <div className="card" style={box}>
        <h1 style={{ marginTop: 0 }}>接入 PEBS 视频工时</h1>
        {state === 'working' && <p>正在用阿米巴令牌登录并按产品建计时项目…</p>}
        {state === 'ok' && (
          <>
            <p style={{ color: '#15803d' }}>✓ 接入成功</p>
            <p className="hint">{msg}</p>
            <a href="/" style={btn}>进入工时工作台</a>
          </>
        )}
        {state === 'error' && (
          <>
            <p style={{ color: '#dc2626' }}>✗ 接入失败</p>
            <p className="hint">{msg}</p>
            <a href="/" style={btn}>仍然进入工作台</a>
          </>
        )}
      </div>
    </div>
  )
}

const wrap = { minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }
const box = { maxWidth: 440 }
const btn = { display: 'inline-block', marginTop: 12, padding: '8px 16px', background: '#3b82f6', color: '#fff', borderRadius: 6, textDecoration: 'none' }
