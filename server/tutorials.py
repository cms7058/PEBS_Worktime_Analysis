"""教程知识库：分步操作引导的唯一数据源.

前端 Tour 组件按 selector 在真实页面上高亮元素并显示说明（data-tour 属性
锚点，比 CSS 类稳定）；智能体通过 show_tutorial 工具触发播放，并能用
steps 文本回答"怎么操作"类问题。文案中英双语，跟随界面语言。
"""
from __future__ import annotations

T = dict   # 简写：{"zh": ..., "en": ...}

TUTORIALS: list[dict] = [
    {
        "id": "create_process",
        "title": T(zh="创建一个新工序", en="Create a new process"),
        "summary": T(
            zh="从工序库新建工序：填名称、用模板配置起步，创建后进入工作台细调。",
            en="Create a process from the library: name it, start from the template config, then fine-tune in the Workbench.",
        ),
        "steps": [
            {"tab": "library", "selector": "[data-tour=new-process]",
             "title": T(zh="新建工序", en="New Process"),
             "body": T(zh="点击这里展开新建表单。工序 = 一个工位作业的配置包（区域 + 工步规则）。",
                       en="Click to open the creation form. A process is the config package for one station (regions + step rules).")},
            {"tab": "library", "selector": "[data-tour=new-process-form]",
             "title": T(zh="填写基本信息", en="Fill in the basics"),
             "body": T(zh="填名称和描述；配置 YAML 先用模板即可，下一步去工作台可视化调整，不用手写。",
                       en="Enter a name and description; keep the template YAML for now — you will adjust it visually in the Workbench, no hand-editing needed.")},
            {"tab": "workbench", "selector": "[data-tour=roi-canvas]",
             "title": T(zh="到配置工作台画区域", en="Draw regions in the Workbench"),
             "body": T(zh="创建后会自动跳到这里：在视频帧上按住拖拽画出取料区、放置区等关键区域。",
                       en="After creating you land here: drag on the video frame to draw key regions such as the picking and placing areas.")},
        ],
    },
    {
        "id": "configure_workbench",
        "title": T(zh="配置区域与工步规则", en="Configure regions & step rules"),
        "summary": T(
            zh="在工作台画 ROI、编辑工步序列（起止事件、超时、MODAPTS 标准工时）。",
            en="Draw ROIs and edit the step sequence (start/end events, timeout, MODAPTS standard time) in the Workbench.",
        ),
        "steps": [
            {"tab": "workbench", "selector": "[data-tour=roi-canvas]",
             "title": T(zh="画区域（ROI）", en="Draw regions (ROI)"),
             "body": T(zh="按住拖拽即可新增区域，自动命名后可在下方列表改名。先选一帧手不遮挡工位的画面（拖动时间滑杆）。",
                       en="Drag to add a region; rename it in the list below. Use the time slider to pick a frame where hands do not occlude the station.")},
            {"tab": "workbench", "selector": "[data-tour=step-editor]",
             "title": T(zh="编辑工步", en="Edit work steps"),
             "body": T(zh="每个工步 = 起始事件 + 结束事件（如「任意手进入料盒区」到「同一只手离开」）。全部工步按顺序完成记为一个循环，循环时长就是单件工时。",
                       en="Each step = a start event + an end event (e.g. any hand enters the bin until the same hand leaves). Completing all steps in order = one cycle; cycle duration is the unit work time.")},
            {"tab": "workbench", "selector": "[data-tour=step-editor]",
             "title": T(zh="标准工时（可选）", en="Standard time (optional)"),
             "body": T(zh="给工步选 MODAPTS 序列（如 M4 G3 = 大臂伸入 + 复杂抓取），系统实时算出理论秒数，之后统计页会自动给出实测 vs 标准的效率比。",
                       en="Assign a MODAPTS sequence (e.g. M4 G3 = arm reach + complex grasp); the theoretical seconds compute live, and Statistics will show measured-vs-standard efficiency.")},
            {"tab": "workbench", "selector": "[data-tour=save-config]",
             "title": T(zh="保存配置", en="Save the config"),
             "body": T(zh="改完记得保存。需要直接编辑 YAML 的高级场景，点旁边的「高级」按钮。",
                       en="Remember to save. For advanced cases, edit the raw YAML via the Advanced button next to it.")},
        ],
    },
    {
        "id": "upload_batch",
        "title": T(zh="上传视频并分析", en="Upload a video & analyze"),
        "summary": T(
            zh="上传采集批次：选视频、选感知后端（pose/hands）、可先上传后画 ROI 再分析。",
            en="Upload a batch: choose the video and perception backend (pose/hands); you can upload first, draw ROIs, then analyze.",
        ),
        "steps": [
            {"tab": "batches", "selector": "[data-tour=upload-form]",
             "title": T(zh="上传视频", en="Upload a video"),
             "body": T(zh="选择固定机位拍摄的作业视频。要求：机位固定、光线正常、能看清手部动作。",
                       en="Pick a fixed-camera video of the operation. Requirements: fixed camera, decent lighting, hands clearly visible.")},
            {"tab": "batches", "selector": "[data-tour=backend-select]",
             "title": T(zh="选感知后端", en="Choose the backend"),
             "body": T(zh="画面能看到上半身选 pose；近景只拍到手选 hands。选错会导致检出率低、循环识别不全。",
                       en="Upper body visible → pose; close-up hands only → hands. The wrong choice causes low detection and missed cycles.")},
            {"tab": "batches", "selector": "[data-tour=autostart-select]",
             "title": T(zh="立即分析 or 先画 ROI", en="Analyze now or draw ROI first"),
             "body": T(zh="新工序第一段视频建议选「仅上传」：先去工作台对着画面画好区域，再回来点「开始分析」。",
                       en="For the first video of a new process choose Upload only: draw regions in the Workbench first, then come back and click Start analysis.")},
            {"tab": "batches", "selector": "[data-tour=batch-list]",
             "title": T(zh="查看结果", en="View results"),
             "body": T(zh="分析完成后这里显示循环数和节拍中位数；点「循环明细」能看每个循环的工步分解与异常原因。",
                       en="When done, cycle count and median cycle time appear here; Cycle details shows each cycle's step breakdown and anomalies.")},
        ],
    },
    {
        "id": "read_statistics",
        "title": T(zh="解读统计看板", en="Read the Statistics dashboard"),
        "summary": T(
            zh="看懂中位数/置信区间/分布诊断，以及实测 vs MODAPTS 标准工时的效率比。",
            en="Understand median/CI/distribution diagnostics and the measured-vs-MODAPTS efficiency ratio.",
        ),
        "steps": [
            {"tab": "stats", "selector": "[data-tour=stats-overview]",
             "title": T(zh="数据概览", en="Overview"),
             "body": T(zh="只有 complete（完整）循环进入统计；incomplete/anomalous 单独计数，保证没有样本被悄悄丢掉。",
                       en="Only complete cycles enter the statistics; incomplete/anomalous ones are counted separately so nothing is silently dropped.")},
            {"tab": "stats", "selector": "[data-tour=cycle-dist]",
             "title": T(zh="工时分布", en="Time distribution"),
             "body": T(zh="工时数据右偏是常态，所以看中位数而不是平均值；95% 置信区间越窄数据越可信；下方会自动提示双峰（两种作业方法）或长尾（偶发等待）。",
                       en="Work-time data is usually right-skewed, so read the median, not the mean; a narrower 95% CI means more reliable data. Bimodal (two work methods) or long-tail (occasional waits) warnings appear automatically.")},
            {"tab": "stats", "selector": "[data-tour=efficiency-table]",
             "title": T(zh="效率比", en="Efficiency ratio"),
             "body": T(zh="效率比 = 标准工时 ÷ 实测中位数。注意实测含手进出区域的路径时间，会略低于 100%，关注趋势而非个位百分比。",
                       en="Efficiency = standard time ÷ measured median. Measured times include hand travel in/out of regions, so slightly below 100% is normal — watch trends, not single points.")},
        ],
    },
    {
        "id": "setup_model",
        "title": T(zh="配置智能体模型", en="Set up the assistant model"),
        "summary": T(
            zh="在助手面板添加任意 Anthropic 兼容接口的大模型（官方 Claude、MiniMax 等）。",
            en="Add any Anthropic-compatible LLM (official Claude, MiniMax, etc.) in the assistant panel.",
        ),
        "steps": [
            {"tab": None, "selector": "[data-tour=assistant-settings]",
             "title": T(zh="打开模型设置", en="Open model settings"),
             "body": T(zh="点击 ⚙ 展开模型设置。密钥只存在本机数据库，不会上传。",
                       en="Click ⚙ to open model settings. API keys are stored only in the local database.")},
            {"tab": None, "selector": "[data-tour=assistant-settings]",
             "title": T(zh="填写并测试", en="Fill in & test"),
             "body": T(zh="填名称、Base URL（官方 Claude 留空）、模型名和 API Key，保存后点「测试」验证连通，再点「启用」切换使用。",
                       en="Enter name, Base URL (empty for official Claude), model and API key; save, click Test to verify, then Activate to switch.")},
        ],
    },
]


def list_tutorials(lang: str = "zh") -> list[dict]:
    return [{"id": tu["id"], "title": tu["title"][lang],
             "summary": tu["summary"][lang]} for tu in TUTORIALS]


def get_tutorial(tutorial_id: str, lang: str = "zh") -> dict | None:
    for tu in TUTORIALS:
        if tu["id"] == tutorial_id:
            return {
                "id": tu["id"], "title": tu["title"][lang],
                "summary": tu["summary"][lang],
                "steps": [{"tab": s["tab"], "selector": s["selector"],
                           "title": s["title"][lang], "body": s["body"][lang]}
                          for s in tu["steps"]],
            }
    return None
