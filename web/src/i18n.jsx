import { createContext, useContext, useState } from 'react'

// 轻量 i18n：以中文原文为 key，缺词条时回退中文（便于发现漏翻）。
// 默认英文，切换持久化到 localStorage。
const DICT = {
  // 通用
  'PEBS 工时分析': 'PEBS Work-Time Analytics',
  '工序库': 'Processes',
  '配置工作台': 'Workbench',
  '批次分析': 'Batches',
  '统计看板': 'Statistics',
  '（暂无工序）': '(no processes)',
  '用户管理': 'User Management',
  '注销': 'Sign out',
  '管理员': 'Admin',
  '普通用户': 'User',
  '（点击关闭）': ' (click to dismiss)',
  '加载工序失败': 'Failed to load processes',
  '拖动调整助手面板宽度': 'Drag to resize assistant panel',
  '关闭': 'Close',
  '取消': 'Cancel',
  '确定': 'OK',
  '删除': 'Delete',
  '删': 'Del',
  '复制': 'Clone',
  '配置': 'Configure',
  '批次': 'Batches',
  '名称': 'Name',
  '描述': 'Description',
  '状态': 'Status',
  '角色': 'Role',
  '秒': 's',
  '加载中…': 'Loading…',
  '请先选择工序': 'Select a process first',

  // 登录
  '视频工时/工步采集分析系统': 'Video-based work-time & step analysis system',
  '用户名': 'Username',
  '密码': 'Password',
  '登录': 'Sign in',
  '登录中…': 'Signing in…',
  '请输入用户名和密码': 'Please enter username and password',
  '首次部署默认管理员 admin / admin123，登录后请在「用户管理」修改密码。':
    'Default admin account: admin / admin123. Please change the password in User Management after first sign-in.',

  // 用户管理
  '新增用户': 'Add User',
  '初始密码': 'Initial password',
  '新增': 'Add',
  '创建时间': 'Created',
  '（你）': ' (you)',
  '改密': 'Password',
  '降为用户': 'Demote to user',
  '升为管理员': 'Promote to admin',
  '确认删除？': 'Confirm delete?',
  '再点一次确认': 'Click again to confirm',
  '新密码（≥4位）': 'New password (≥4 chars)',
  '密码已更新': 'Password updated',
  '用户已创建': 'User created',
  '用户名和密码必填': 'Username and password are required',
  '密码至少 4 位': 'Password must be at least 4 characters',
  '新增失败': 'Create failed',
  '改密失败': 'Password change failed',
  '改角色失败': 'Role change failed',
  '删除失败': 'Delete failed',

  // 工序库
  '+ 新建工序': '+ New Process',
  '收起': 'Collapse',
  '更新时间': 'Updated',
  '配置 YAML（ROI 坐标可先用模板值，建完后到「配置工作台」对着画面拖框调整）':
    'Config YAML (use template ROI values first, then adjust by dragging on the Workbench)',
  '创建并进入工作台': 'Create & open Workbench',
  '创建中…': 'Creating…',
  '请填写工序名称': 'Please enter a process name',
  '创建失败': 'Create failed',
  '复制失败': 'Clone failed',
  '新工序名称': 'New process name',
  '-副本': '-copy',
  '还没有工序，点「+ 新建工序」开始': 'No processes yet — click "+ New Process" to start',

  // 工作台
  '区域（ROI）—': 'Regions (ROI) —',
  '底图加载中…': 'Loading frame…',
  '先到「批次分析」上传一段视频（可选不立即分析）':
    'Upload a video in Batches first (analysis can be deferred)',
  '（无视频，先上传批次）': '(no video — upload a batch first)',
  '在画面上按住拖拽即可新增区域；先选一帧手不遮挡工位的画面再画框。':
    'Drag on the frame to add a region; pick a frame where hands do not occlude the station.',
  '请先在工序库创建或选择一个工序': 'Create or select a process in Processes first',
  '工序配置': 'Process Config',
  '（未保存）': '(unsaved)',
  'YAML 解析失败': 'YAML parse error',
  '（请在高级视图修复）': ' (fix it in the advanced view)',
  '工序标识': 'Process ID',
  '跟踪关键点（近景手部视角选食指尖，能看到上半身选手腕）':
    'Tracked keypoints (close-up hands: index tips; upper body visible: wrists)',
  '左手腕': 'Left wrist', '右手腕': 'Right wrist',
  '左食指尖': 'Left index tip', '右食指尖': 'Right index tip',
  '工步序列': 'Work Steps',
  '按顺序执行，全部完成记为一个循环': 'Executed in order; completing all steps = one cycle',
  '+ 添加工步': '+ Add Step',
  '工步': 'Step',
  '保存配置': 'Save Config',
  '保存中…': 'Saving…',
  '高级：查看/编辑 YAML': 'Advanced: view/edit YAML',
  '收起 YAML': 'Hide YAML',
  '至少需要一个工步': 'At least one step is required',
  'YAML 语法错误': 'YAML syntax error',
  '加载配置失败': 'Failed to load config',
  '加载批次失败': 'Failed to load batches',
  '保存失败': 'Save failed',
  '区域': 'Region',
  '开始': 'Start',
  '结束': 'End',
  '任意手': 'Any hand',
  '与起始同一只手': 'Same hand as start',
  '进入区域': 'enters region',
  '离开区域': 'leaves region',
  '（选择区域）': '(select region)',
  '超时上限': 'Timeout',
  '不限': 'none',
  '秒（超过记异常）': 's (exceeding is flagged)',
  '标准工时': 'Standard time',
  '不设置': 'Not set',
  'MODAPTS 序列': 'MODAPTS sequence',
  '直接给秒数': 'Direct seconds',
  '宽放': 'Allowance',
  '如 M4 G3 M4 P2': 'e.g. M4 G3 M4 P2',
  '常用：M1手指 M2手腕 M3小臂 M4大臂 M5伸臂 / G1简单抓 G3复杂抓 / P0放下 P2对准放 P5精确放':
    'Common: M1 finger, M2 wrist, M3 forearm, M4 arm, M5 extended arm / G1 simple grasp, G3 complex / P0 put, P2 aligned, P5 precise',

  // 批次
  '上传采集批次 —': 'Upload Batch —',
  '视频文件': 'Video file',
  '批次标签（班次/日期）': 'Batch label (shift/date)',
  '感知后端': 'Perception backend',
  'pose（可见上半身）': 'pose (upper body visible)',
  'hands（近景手部）': 'hands (close-up hands)',
  '采样 fps': 'Sample fps',
  '上传后': 'After upload',
  '立即分析': 'Analyze now',
  '仅上传（先画 ROI）': 'Upload only (draw ROI first)',
  '上传': 'Upload',
  '上传中…': 'Uploading…',
  '请选择视频文件': 'Please choose a video file',
  '上传失败': 'Upload failed',
  '批次列表': 'Batch List',
  '暂无批次': 'No batches yet',
  '标签': 'Label',
  '后端': 'Backend',
  '循环数': 'Cycles',
  '节拍中位': 'Median CT',
  '异常': 'Anomalies',
  '开始分析': 'Start analysis',
  '循环明细': 'Cycle details',
  '启动失败': 'Start failed',
  '起止 (s)': 'Start–End (s)',
  '时长': 'Duration',
  '工步分解': 'Step breakdown',

  // 统计
  '数据概览 —': 'Overview —',
  '该工序还没有分析数据': 'No analysis data for this process yet',
  '统计只纳入 complete 循环；其余状态单独计数，确保无样本被静默丢弃。':
    'Only complete cycles enter the statistics; other statuses are counted separately so nothing is silently dropped.',
  '循环工时分布': 'Cycle Time Distribution',
  '工步：': 'Step: ',
  '中位数': 'Median',
  '95% 置信区间': '95% CI',
  '变异系数': 'CV',
  '有效循环': 'Valid cycles',
  '样本不足，无直方图': 'Not enough samples for a histogram',
  '实测 vs 标准工时（PMTS）': 'Measured vs Standard Time (PMTS)',
  '实测中位': 'Measured median',
  '方法': 'Method',
  '效率比': 'Efficiency',
  '改善空间': 'Gap',
  '未定义': 'Not defined',
  '循环合计': 'Cycle total',
  '实测工步耗时包含手进出 ROI 的路径段，会系统性略长于纯操作理论值； 循环级差值还含工步间移动时间。对比应关注趋势而非个位百分比。':
    'Measured step times include hand travel into/out of ROIs and run slightly longer than pure-motion theory; cycle-level gaps also include inter-step travel. Focus on trends, not single percentage points.',
  '分布右偏，近似对数正态（工时数据的典型形态）':
    'Right-skewed, approximately log-normal (typical for work-time data)',
  '未通过正态/对数正态检验，建议检查异常样本':
    'Failed normal/log-normal tests — check for anomalous samples',
  '疑似双峰：可能存在两种作业方法或人员熟练度差异':
    'Suspected bimodal: possibly two work methods or skill-level differences',
  '右侧长尾明显：存在偶发等待或异常慢循环':
    'Pronounced right tail: occasional waits or abnormally slow cycles',

  // 助手
  '智能助手': 'AI Assistant',
  '未配置模型': 'No model configured',
  '模型设置（Anthropic 兼容接口；密钥仅存本机）':
    'Model settings (Anthropic-compatible API; keys stored locally only)',
  '名称（如 MiniMax）': 'Name (e.g. MiniMax)',
  'Base URL（官方 Claude 留空）': 'Base URL (leave empty for official Claude)',
  '模型名（如 MiniMax-M2.7）': 'Model (e.g. MiniMax-M2.7)',
  '保存模型配置': 'Save Model Config',
  '启用中': 'Active',
  '启用': 'Activate',
  '测试': 'Test',
  '名称、模型、API Key 必填': 'Name, model and API key are required',
  '发送': 'Send',
  '清空': 'Clear',
  '思考中…（涉及视频分析时可能需要较久）': 'Thinking… (video analysis may take a while)',
  '（出错了：': '(Error: ',
  '打开智能助手': 'Open AI assistant',
  '（失败）': ' (failed)',
  '我了解你当前在「': 'I know you are on the "',
  '」页': '" page',
  '，选中工序「': ', with process "',
  '」': '"',
  '。 可以直接提问，或点下面的快捷操作：': '. Ask anything, or use a quick action below:',
  '在': 'Ask the assistant on ',
  '页向助手提问…': '…',

  // 助手快捷提问（发送给模型的文本也跟随语言）
  '我想新建一个工序，帮我起草配置': 'I want to create a new process — draft the config for me',
  '解释一下工序配置 YAML 的写法': 'Explain how the process config YAML works',
  '检查当前工序的 ROI 和工步规则是否合理': 'Review whether the current ROIs and step rules are reasonable',
  '帮各工步加上 MODAPTS 标准工时': 'Add MODAPTS standard times to each step',
  '最近一个批次的异常循环是什么原因？': 'What caused the anomalous cycles in the latest batch?',
  '我的视频该用 pose 还是 hands 后端？': 'Should my video use the pose or hands backend?',
  '解读当前工序的统计结果': 'Interpret the current process statistics',
  '效率比偏低，可能的原因和改善方向？': 'Efficiency is low — likely causes and improvements?',
}

const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('pebs_lang') || 'en')
  const toggle = () => {
    const next = lang === 'en' ? 'zh' : 'en'
    setLang(next)
    localStorage.setItem('pebs_lang', next)
  }
  const t = (zh) => (lang === 'zh' ? zh : (DICT[zh] ?? zh))
  return (
    <I18nContext.Provider value={{ lang, toggle, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export const useI18n = () => useContext(I18nContext)
