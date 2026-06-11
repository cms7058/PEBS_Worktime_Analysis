# PEBS AI Worktime — 视频工时/工步采集分析系统

通过固定机位视频分析人工作业的工步切分与工时统计。**用户自定义规则，无需训练模型**：
预训练姿态模型提取原子事实（关键点轨迹），用户用 ROI + 工步状态机定义语义。

## 架构（当前为阶段 1-2：核心管线）

```
视频 ──► 感知层 perception.py ──► 关键点流 (JSONL)
              MediaPipe Tasks API，双后端：pose（人体可见）/ hands（近景只见手），
              归一化坐标，含置信分
         ──► 事件层 events.py ──► 原子事件流 (roi_enter / roi_exit)
              迟滞去抖：连续 N 帧确认进入/离开，吸收关键点抖动与跟踪丢失
         ──► 规则引擎 rules.py ──► 工步切分 + 循环工时 + 异常
              用户 YAML 定义工步状态机（起止事件 + 时限），异常显式记录
         ──► summarize() ──► 工时统计摘要
```

## 快速开始

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 姿态模型（约 5.5MB）：
curl -sL -o models/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

# 分析视频（10fps 采样）；近景手部视角加 --backend hands（需 hand_landmarker.task 模型）
.venv/bin/python -m pipeline.run <视频文件> configs/example_process.yaml --fps 10

# 预览 ROI 配置是否套准画面（--pose 同时叠加关键点检测结果）
.venv/bin/python -m pipeline.preview <视频文件> configs/example_process.yaml --t 3 --pose

# 用已保存的关键点流跳过感知层（开发/调试）
.venv/bin/python -m pipeline.run <stream.jsonl> configs/example_process.yaml --keypoints

# 测试
.venv/bin/python -m pytest tests/ -q

# 启动数据平台 API（交互文档在 http://localhost:8000/docs）
.venv/bin/uvicorn server.app:app --port 8000
```

## Web 界面

```bash
# 生产模式：构建后由 FastAPI 直接托管，打开 http://localhost:8000
cd web && npm install && npm run build && cd ..
.venv/bin/uvicorn server.app:app --port 8000

# 开发模式：Vite 热更新（API 自动代理到 8000）
cd web && npm run dev   # http://localhost:5173
```

四个页面：**工序库**（建/复制/删工序）→ **配置工作台**（视频帧上拖拽画 ROI，
双向同步 YAML）→ **批次分析**（上传视频，可选"仅上传先画 ROI"，循环明细）→
**统计看板**（分位数/置信区间/直方图/分布诊断 + PMTS 效率对比）。

## API 全流程示例

```bash
# 1. 创建工序（配置包 = ROI + 工步规则 YAML）
curl -X POST localhost:8000/processes -H 'Content-Type: application/json' \
  -d '{"name": "取石入杯", "config_yaml": "<YAML 内容>"}'
# 2. 上传视频开始分析（后台任务）
curl -X POST localhost:8000/processes/1/batches \
  -F video=@视频.MOV -F backend=hands -F sample_fps=10 -F label=批次1
# 3. 轮询批次状态与摘要
curl localhost:8000/batches/1
# 4. 循环明细 / 工序级统计（含中位数、95% 置信区间、分布诊断、直方图数据）
curl localhost:8000/batches/1/cycles
curl localhost:8000/processes/1/statistics
# 工序配置可复制（相似产线快速适配）
curl -X POST localhost:8000/processes/1/clone -d '{"name": "取石入杯-线2"}' \
  -H 'Content-Type: application/json'
```

输出到 `data/outputs/`：`*.events.jsonl`（事件流）、`*.cycles.jsonl`（循环明细）、
`*.summary.json`（工时摘要：循环数、中位工时、各工步中位耗时、异常计数）。

## 工序配置示例

见 [configs/example_process.yaml](configs/example_process.yaml)：定义 ROI（归一化矩形）
和工步序列（每步 = 起始事件 + 结束事件 + 最大时限）。`keypoint: same` 表示结束事件
须与起始事件为同一只手。

## 路线图

- [x] 阶段 1：感知管线（MediaPipe Pose/Hands → 关键点流）
- [x] 阶段 2：事件层 + 规则引擎（工步切分、循环工时、异常标记）
- [x] 阶段 3：工序库与数据平台（FastAPI + SQLite，多工序/多批次管理）
- [x] 阶段 4：统计分析服务（中位数、bootstrap 置信区间、正态/对数正态、偏度/双峰诊断；SPC 控制图待做）
- [x] 阶段 5：PMTS 测量方法模块（MODAPTS 内置 / MTM、MOST 等数据卡导入，工步配置 standard 块自选方法；实测 vs 标准效率对比接口）
- [x] 阶段 6：前端（React + Vite：工序库、ROI 画布工作台、批次分析、统计看板）
- [x] 阶段 7：智能体层（Claude tool use，11 个工具覆盖全流程）

## 智能体使用

**嵌入式助手**：智能体以右侧常驻面板嵌入每个功能页（可收起为悬浮球），
自动感知当前页面与选中工序，每页有专属快捷操作——工序库页帮起草配置、
工作台页检查 ROI/规则并可直接修改（页面数据自动刷新）、批次页解释异常循环、
统计页解读分布与效率比。

**模型可由用户自行配置**：助手面板「⚙ 模型设置」里添加任意 Anthropic 兼容接口的
模型（官方 Claude、MiniMax 等），填 Base URL / 模型名 / API Key，可"测试连接"并
选择启用；密钥仅存本机数据库，接口返回一律掩码。已验证 MiniMax-M2.7
（国内站 `https://api.minimaxi.com/anthropic`，注意 `.io` 国际站与国内 key 不互通）。

- **终端对话**：`.venv/bin/python -m agent.chat`（与 Web 共用启用的模型配置；
  无配置时回退 `ANTHROPIC_API_KEY` 环境变量 + 官方 Claude）

对话示例：「我有一段装配视频在 data/videos/xx.MOV，帮我配置工序并分析」——
智能体会调用 preview_roi 看画面、起草配置 YAML、与你确认后建工序、跑分析、解读统计。
工具清单见 [agent/tools.py](agent/tools.py)。官方 Claude 端点自动启用自适应思考与
prompt 缓存；第三方兼容端点走最小参数集（server/llm.py 自动判断）。
