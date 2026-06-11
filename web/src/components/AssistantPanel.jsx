import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import RichMessage from './RichMessage.jsx'
import { useI18n } from '../i18n.jsx'

// 各页面的快捷提问：让助手"嵌入"当前模块的工作流
const QUICK_PROMPTS = {
  library: [
    '我想新建一个工序，帮我起草配置',
    '解释一下工序配置 YAML 的写法',
  ],
  workbench: [
    '检查当前工序的 ROI 和工步规则是否合理',
    '帮各工步加上 MODAPTS 标准工时',
  ],
  batches: [
    '最近一个批次的异常循环是什么原因？',
    '我的视频该用 pose 还是 hands 后端？',
  ],
  stats: [
    '解读当前工序的统计结果',
    '效率比偏低，可能的原因和改善方向？',
  ],
}

// 调用了这些工具说明数据被改写，需要刷新页面数据
const WRITE_TOOLS = new Set(['create_process', 'update_process_config', 'analyze_video'])

export default function AssistantPanel({ tab, tabLabel, process, width = 360, onDataChanged, setError }) {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [configs, setConfigs] = useState([])
  const [form, setForm] = useState({ name: '', base_url: '', model: '', api_key: '' })
  const [testResult, setTestResult] = useState({})

  const [history, setHistory] = useState([])
  const [apiMessages, setApiMessages] = useState([])
  const [input, setInput] = useState('')
  const [chatting, setChatting] = useState(false)
  const bottomRef = useRef(null)

  const reloadConfigs = () => api.llmConfigs().then(setConfigs).catch((e) => setError(e.message))
  useEffect(() => { reloadConfigs() }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [history, chatting])

  const active = configs.find((c) => c.is_active)

  const send = async (text) => {
    text = (text ?? input).trim()
    if (!text || chatting) return
    setInput('')
    setHistory((h) => [...h, { role: 'user', text }])
    const nextMessages = [...apiMessages, { role: 'user', content: text }]
    setChatting(true)
    try {
      const context = {
        tab, tab_label: tabLabel, lang,
        process_id: process?.id, process_name: process?.name,
      }
      const r = await api.chat(nextMessages, context)
      setApiMessages(r.messages)
      setHistory((h) => [...h, { role: 'assistant', text: r.reply, tools: r.tool_calls }])
      if (r.tool_calls?.some((t) => WRITE_TOOLS.has(t.tool) && !t.is_error)) {
        onDataChanged?.()   // 助手改了数据，刷新当前页面
      }
    } catch (e) {
      setHistory((h) => [...h, { role: 'assistant', text: `${t('（出错了：')}${e.message}）` }])
    } finally { setChatting(false) }
  }

  const saveConfig = async () => {
    if (!form.name || !form.model || !form.api_key) return setError(t('名称、模型、API Key 必填'))
    try {
      await api.saveLlmConfig(form)
      setForm({ name: '', base_url: '', model: '', api_key: '' })
      reloadConfigs()
    } catch (e) { setError(`${t('保存失败')}: ${e.message}`) }
  }

  const test = async (id) => {
    setTestResult((r) => ({ ...r, [id]: { pending: true } }))
    try {
      const result = await api.testLlmConfig(id)
      setTestResult((r) => ({ ...r, [id]: result }))
    } catch (e) { setTestResult((r) => ({ ...r, [id]: { ok: false, error: e.message } })) }
  }

  if (!open) {
    return (
      <button className="assistant-fab" onClick={() => setOpen(true)} title={t('打开智能助手')}>🤖</button>
    )
  }

  return (
    <aside className="assistant" style={{ width }}>
      <div className="assistant-head">
        <b>🤖 {t('智能助手')}</b>
        <span className="hint" style={{ flex: 1, marginLeft: 8 }}>
          {active ? active.name : t('未配置模型')}
        </span>
        <button className="ghost" style={{ padding: '2px 8px' }}
                onClick={() => setShowSettings(!showSettings)}>⚙</button>
        <button className="ghost" style={{ padding: '2px 8px' }}
                onClick={() => setOpen(false)}>✕</button>
      </div>

      {showSettings && (
        <div className="assistant-settings">
          <div className="hint" style={{ marginBottom: 6 }}>{t('模型设置（Anthropic 兼容接口；密钥仅存本机）')}</div>
          {configs.map((c) => (
            <div key={c.id} style={{ fontSize: 12, marginBottom: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
              <b>{c.name}</b>
              <span className="hint" style={{ flex: 1 }}>{c.model}</span>
              {c.is_active ? <span className="status complete">{t('启用中')}</span>
                : <button className="ghost" style={{ padding: '1px 6px' }}
                          onClick={() => api.activateLlmConfig(c.id).then(reloadConfigs)}>{t('启用')}</button>}
              <button className="ghost" style={{ padding: '1px 6px' }} onClick={() => test(c.id)}>
                {testResult[c.id]?.pending ? '…' : t('测试')}
              </button>
              <button className="ghost danger" style={{ padding: '1px 6px' }}
                      onClick={() => api.deleteLlmConfig(c.id).then(reloadConfigs)}>{t('删')}</button>
              {testResult[c.id] && !testResult[c.id].pending && (
                <span style={{ color: testResult[c.id].ok ? '#15803d' : '#dc2626' }}>
                  {testResult[c.id].ok ? '✓' : '✗'}
                </span>
              )}
            </div>
          ))}
          <input type="text" placeholder={t('名称（如 MiniMax）')} value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ marginBottom: 4 }} />
          <input type="text" placeholder={t('Base URL（官方 Claude 留空）')} value={form.base_url}
                 onChange={(e) => setForm({ ...form, base_url: e.target.value })} style={{ marginBottom: 4 }} />
          <input type="text" placeholder={t('模型名（如 MiniMax-M2.7）')} value={form.model}
                 onChange={(e) => setForm({ ...form, model: e.target.value })} style={{ marginBottom: 4 }} />
          <input type="text" placeholder="API Key" value={form.api_key}
                 onChange={(e) => setForm({ ...form, api_key: e.target.value })} style={{ marginBottom: 6 }} />
          <button className="primary" style={{ width: '100%' }} onClick={saveConfig}>{t('保存模型配置')}</button>
        </div>
      )}

      <div className="assistant-body">
        {history.length === 0 && (
          <div className="hint" style={{ marginBottom: 10 }}>
            {t('我了解你当前在「')}{tabLabel}{t('」页')}
            {process ? `${t('，选中工序「')}${process.name}${t('」')}` : ''}
            {t('。 可以直接提问，或点下面的快捷操作：')}
          </div>
        )}
        {history.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            <div className={`bubble ${m.role}`}>
              {m.tools?.length > 0 && (
                <div className="hint" style={{ marginBottom: 4 }}>
                  {m.tools.map((tc, j) => <div key={j}>🔧 {tc.tool}{tc.is_error ? t('（失败）') : ''}</div>)}
                </div>
              )}
              {m.role === 'assistant' ? <RichMessage text={m.text} /> : m.text}
            </div>
          </div>
        ))}
        {chatting && <div className="hint">{t('思考中…（涉及视频分析时可能需要较久）')}</div>}
        <div ref={bottomRef} />
      </div>

      <div className="assistant-quick">
        {(QUICK_PROMPTS[tab] ?? []).map((q) => (
          <button key={q} className="ghost" onClick={() => send(t(q))} disabled={chatting}>{t(q)}</button>
        ))}
      </div>
      <div className="assistant-input">
        <input type="text" value={input} placeholder={`${t('在')}${tabLabel}${t('页向助手提问…')}`}
               onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && send()} />
        <button className="primary" disabled={chatting} onClick={() => send()}>{t('发送')}</button>
        {history.length > 0 && (
          <button className="ghost" onClick={() => { setHistory([]); setApiMessages([]) }}>{t('清空')}</button>
        )}
      </div>
    </aside>
  )
}
