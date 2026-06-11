// 轻量 API 客户端：自动注入 Bearer 令牌；401 时清空令牌并通知 App 回登录页
let onUnauthorized = null
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

const TOKEN_KEY = 'pebs_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY)

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...options, headers })
  if (res.status === 401) {
    setToken('')
    onUnauthorized?.()
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* 非 JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return null
  return res.json()
}

const json = (method, body) => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

// <img src> 不能加 Authorization header，用 ?token= 传递（中间件已支持）
const withToken = (url) => {
  const t = getToken()
  return t ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(t)}` : url
}

export const api = {
  // 鉴权
  login: (username, password) =>
    request('/auth/login', json('POST', { username, password })),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/auth/me'),

  // 用户管理（管理员）
  listUsers: () => request('/users'),
  createUser: (body) => request('/users', json('POST', body)),
  setUserPassword: (id, password) =>
    request(`/users/${id}/password`, json('PUT', { password })),
  setUserRole: (id, role) =>
    request(`/users/${id}/role`, json('PUT', { role })),
  deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),

  // 工序
  listProcesses: () => request('/processes'),
  getProcess: (id) => request(`/processes/${id}`),
  createProcess: (body) => request('/processes', json('POST', body)),
  updateProcess: (id, body) => request(`/processes/${id}`, json('PUT', body)),
  deleteProcess: (id) => request(`/processes/${id}`, { method: 'DELETE' }),
  cloneProcess: (id, name) => request(`/processes/${id}/clone`, json('POST', { name })),

  // 批次
  listBatches: (pid) => request(`/processes/${pid}/batches`),
  getBatch: (id) => request(`/batches/${id}`),
  uploadBatch: (pid, formData) =>
    request(`/processes/${pid}/batches`, { method: 'POST', body: formData }),
  runBatch: (id) => request(`/batches/${id}/run`, { method: 'POST' }),
  batchCycles: (id) => request(`/batches/${id}/cycles`),
  frameUrl: (batchId, t) => withToken(`/batches/${batchId}/frame?t=${t}`),

  // 统计/PMTS
  statistics: (pid, batchId) =>
    request(`/processes/${pid}/statistics${batchId ? `?batch_id=${batchId}` : ''}`),
  efficiency: (pid) => request(`/processes/${pid}/efficiency`),
  pmtsMethods: () => request('/pmts/methods'),
  pmtsCalc: (sequence, method = 'modapts', allowance = 0) =>
    request('/pmts/calc', json('POST', { sequence, method, allowance })),

  // 教程
  listTutorials: (lang) => request(`/tutorials?lang=${lang}`),
  getTutorial: (id, lang) => request(`/tutorials/${id}?lang=${lang}`),

  // 智能体
  llmConfigs: () => request('/llm/configs'),
  saveLlmConfig: (body) => request('/llm/configs', json('POST', body)),
  deleteLlmConfig: (id) => request(`/llm/configs/${id}`, { method: 'DELETE' }),
  activateLlmConfig: (id) => request(`/llm/configs/${id}/activate`, { method: 'POST' }),
  testLlmConfig: (id) => request(`/llm/configs/${id}/test`, { method: 'POST' }),
  chat: (messages, context) => request('/chat', json('POST', { messages, context })),
}
