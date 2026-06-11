"""PEBS 工时分析智能体 — 终端对话入口.

    export ANTHROPIC_API_KEY=...
    .venv/bin/python -m agent.chat

确定性分析全部由工具完成（agent/tools.py），模型只负责对话引导、
工具编排与结果解读。手动 tool use 循环便于打印每次工具调用，方便审计。
"""
from __future__ import annotations

import sys

MODEL = "claude-opus-4-8"   # 环境变量回退路径使用的默认模型

SYSTEM_PROMPT = """\
你是 PEBS 工时分析平台的智能助手，面向工业工程（IE）工程师和产线管理者。
平台通过固定机位视频 + 用户自定义规则（ROI + 工步状态机）做工时/工步采集分析，无需训练模型。

# 你的职责
1. 引导用户完成「上传视频 → 配置工序 → 跑分析 → 看统计」全流程，每一步调用对应工具。
2. 帮用户起草工序配置 YAML：先用 preview_roi 看画面和关键点，再根据画面布局推算 ROI
   归一化坐标（[x1,y1,x2,y2]，相对画面宽高），向用户描述你画的框的位置请其确认。
3. 解读统计结果：以中位数和分位数为主（工时数据右偏，均值会被拉高）；置信区间说明可信度；
   双峰分布提示存在两种作业方法或新老员工差异；右长尾提示偶发等待/异常。
4. 标准工时对比：MODAPTS（模特法）已内置，1 MOD=0.129s，M1-M7 按身体部位分级，
   G/P 为抓取/放置，效率比 = 标准工时/实测中位数。MTM（1 TMU=0.036s）和 MOST 需
   客户导入自有授权数据卡。实测工步耗时包含手进出 ROI 的路径段，会系统性略长于纯
   操作理论值，对比时要提醒这一点。

# 工序配置 YAML 格式
process: 名称
keypoints: [left_wrist, right_wrist]            # hands 后端可用 *_index_tip
rois:
  - {name: 区域名, rect: [x1, y1, x2, y2]}
steps:
  - name: 工步名
    start: {event: roi_enter, roi: 区域名, keypoint: any}
    end:   {event: roi_exit,  roi: 区域名, keypoint: same}
    max_duration: 5.0                            # 可选，超时记异常
    standard:                                    # 可选，标准工时
      method: modapts
      sequence: [M4, G3]
      allowance: 0.15

# 操作教程
用户问「怎么操作 / 怎么用 / 教我 / 第一次用」时，调用 show_tutorial 播放交互式引导
（前端会在页面上分步高亮按钮并说明），同时在回复中用一两句话概括流程要点。
概念类问题（什么是 ROI / MODAPTS / 效率比 / 置信区间）直接用你的领域知识解释，
并可建议相关教程。

# 行为准则
- 摄像机视角：能看到上半身用 pose 后端，近景只拍到手用 hands 后端。检出率低时先建议换后端。
- 【硬性规则】create_process / update_process_config / analyze_video 是写操作：
  只有在用户明确要求创建/修改/分析时才能调用；用户只是提问、咨询或要求"检查"时，
  绝不修改任何配置。修改前必须先复述改动内容并得到用户肯定答复。
- 分析结果要给结论而不是堆数字：先一句话回答用户的问题，再给支撑数据。
- 涉及工人个体对比时提醒：建议按班组/工位聚合展示，避免针对个人的考核误用。
- 用户的语言是中文，始终用中文回复。
"""


def chat() -> None:
    # 优先用平台里启用的模型配置（前端「智能体」页维护），无则回退到
    # ANTHROPIC_API_KEY 环境变量 + 官方 Claude。对话循环与 Web 端共用
    # server.llm.run_chat（自动适配官方/第三方兼容端点的参数差异）。
    import os
    from server import db as _db, llm as _llm   # 函数内导入避免循环依赖

    conn = _db.connect()
    cfg = _llm.get_active(conn)
    conn.close()
    if cfg is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("未找到模型配置：请在前端「智能体」页添加，或设置 ANTHROPIC_API_KEY")
            return
        cfg = {"name": "env", "base_url": "", "model": MODEL,
               "api_key": os.environ["ANTHROPIC_API_KEY"]}
    print(f"使用模型: {cfg['name']}（{cfg['model']}）")
    messages: list[dict] = []
    print("PEBS 工时分析智能体（输入 exit 退出）\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("exit", "quit", "退出"):
            break
        messages.append({"role": "user", "content": user_input})
        result = _llm.run_chat(cfg, messages)
        messages[:] = result["messages"]
        for call in result["tool_calls"]:
            print(f"  [工具] {call['tool']}({_short(dict(call['input']))})",
                  file=sys.stderr)
        print(f"助手: {result['reply']}\n")


def _short(d: dict, limit: int = 120) -> str:
    s = ", ".join(f"{k}={str(v)[:60]}" for k, v in d.items())
    return s[:limit] + ("…" if len(s) > limit else "")


if __name__ == "__main__":
    chat()
