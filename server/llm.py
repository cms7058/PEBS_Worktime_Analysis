"""大模型配置管理 + 智能体对话服务.

智能体层支持任何 Anthropic 兼容接口的模型（官方 Claude、MiniMax 等），
用户在前端配置 base_url / model / api_key 并选择启用哪个。配置存本地
SQLite（本系统为内网部署形态，密钥不出本机；API 返回时一律掩码）。
"""
from __future__ import annotations

import json
from typing import Optional

import anthropic

from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.chat import SYSTEM_PROMPT

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    api_key TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);
"""


def _mask(key: str) -> str:
    return key[:8] + "…" + key[-4:] if len(key) > 16 else "…"


def _row(r) -> dict:
    d = dict(r)
    d["api_key_masked"] = _mask(d.pop("api_key"))
    d["is_active"] = bool(d["is_active"])
    return d


def list_configs(conn) -> list[dict]:
    conn.executescript(SCHEMA)
    return [_row(r) for r in conn.execute(
        "SELECT * FROM llm_configs ORDER BY id").fetchall()]


def save_config(conn, name: str, model: str, api_key: str,
                base_url: str = "") -> dict:
    """新增或按 name 覆盖；首个配置自动设为启用."""
    conn.executescript(SCHEMA)
    first = conn.execute("SELECT COUNT(*) FROM llm_configs").fetchone()[0] == 0
    conn.execute(
        "INSERT INTO llm_configs (name, base_url, model, api_key, is_active)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(name) DO UPDATE SET base_url=excluded.base_url,"
        " model=excluded.model, api_key=excluded.api_key",
        (name, base_url, model, api_key, 1 if first else 0),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM llm_configs WHERE name = ?",
                       (name,)).fetchone()
    return _row(row)


def delete_config(conn, config_id: int) -> bool:
    conn.executescript(SCHEMA)
    cur = conn.execute("DELETE FROM llm_configs WHERE id = ?", (config_id,))
    conn.commit()
    return cur.rowcount > 0


def activate(conn, config_id: int) -> Optional[dict]:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT 1 FROM llm_configs WHERE id = ?",
                    (config_id,)).fetchone() is None:
        return None
    conn.execute("UPDATE llm_configs SET is_active = 0")
    conn.execute("UPDATE llm_configs SET is_active = 1 WHERE id = ?",
                 (config_id,))
    conn.commit()
    return _row(conn.execute("SELECT * FROM llm_configs WHERE id = ?",
                             (config_id,)).fetchone())


def get_active(conn) -> Optional[dict]:
    """返回含明文 key 的启用配置（仅服务端内部使用，不可直接返回给前端）."""
    conn.executescript(SCHEMA)
    row = conn.execute(
        "SELECT * FROM llm_configs WHERE is_active = 1").fetchone()
    return dict(row) if row else None


def make_client(cfg: dict) -> anthropic.Anthropic:
    kwargs = {"api_key": cfg["api_key"]}
    if cfg.get("base_url"):
        kwargs["base_url"] = cfg["base_url"]
    return anthropic.Anthropic(**kwargs)


def _is_official(cfg: dict) -> bool:
    return not cfg.get("base_url") or "api.anthropic.com" in cfg["base_url"]


def test_config(cfg: dict) -> dict:
    """对配置做一次最小真实调用，验证连通性与凭据."""
    client = make_client(cfg)
    try:
        # 预算给足：推理型模型会先输出 thinking，太小会挤掉正文
        r = client.messages.create(
            model=cfg["model"], max_tokens=512,
            messages=[{"role": "user", "content": "回复「连接正常」四个字"}],
        )
        text = "".join(b.text for b in r.content if b.type == "text")
        return {"ok": True, "reply": text.strip()[:50] or "(空回复)"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


# 各功能页的助手职责：嵌入式智能体根据用户当前所在页面调整引导方式
TAB_GUIDE = """
# 嵌入式助手：按页面工作
你嵌入在平台各功能页的侧边栏，用户消息末尾会附带 [当前上下文]（页面、选中工序等）。
结合上下文主动工作，不要反问用户"你在哪个页面"：
- 工序库页：引导建工序。用户描述作业内容时，帮其起草完整配置 YAML 并调 create_process。
- 配置工作台页：用户正对着视频帧画 ROI。可调 get_process_config 检查当前配置的 ROI
  覆盖、迟滞、max_duration 是否合理；建议为各工步补 standard 标准工时块；修改配置
  用 update_process_config（修改后提醒用户页面已自动刷新）。
- 批次分析页：指导上传参数选择（pose/hands、采样 fps）；批次完成后调 get_cycles
  解释异常循环；失败批次帮助诊断原因。
- 统计看板页：用户正看着统计图表。调 query_statistics / compare_efficiency
  解读分布形态、置信区间和效率比，给出改善建议而不是复述数字。
"""


def _inject_context(messages: list[dict], context: Optional[dict]) -> list[dict]:
    """把前端上报的页面上下文附到最近一条用户消息末尾."""
    if not context:
        return list(messages)
    parts = [f"页面：{context.get('tab_label', context.get('tab', '?'))}"]
    if context.get("process_name"):
        parts.append(f"选中工序：{context['process_name']}"
                     f"(id={context.get('process_id')})")
    if context.get("lang") == "en":
        parts.append("界面语言为英文，请用英文回复（Respond in English）")
    note = f"\n\n[当前上下文] {'；'.join(parts)}"
    messages = [dict(m) for m in messages]
    last = messages[-1]
    if last.get("role") == "user" and isinstance(last.get("content"), str):
        last["content"] = last["content"] + note
    return messages


def run_chat(cfg: dict, messages: list[dict],
             context: Optional[dict] = None,
             max_tool_rounds: int = 15) -> dict:
    """跑一轮智能体对话（含工具循环），返回最终文本、工具调用轨迹和完整消息.

    兼容性处理：thinking/cache_control 等 Anthropic 专有参数只在官方端点
    发送，第三方兼容端点（如 MiniMax）走最小参数集。
    """
    client = make_client(cfg)
    official = _is_official(cfg)
    full_system = SYSTEM_PROMPT + TAB_GUIDE
    system = ([{"type": "text", "text": full_system,
                "cache_control": {"type": "ephemeral"}}]
              if official else full_system)
    extra = {"thinking": {"type": "adaptive"}} if official else {}

    messages = _inject_context(messages, context)
    tool_trace: list[dict] = []
    final_text = ""
    for _ in range(max_tool_rounds):
        response = client.messages.create(
            model=cfg["model"], max_tokens=8192, system=system,
            tools=TOOL_DEFINITIONS, messages=messages, **extra,
        )
        content = [b.model_dump(exclude_none=True) for b in response.content]
        messages.append({"role": "assistant", "content": content})
        final_text = "".join(b.text for b in response.content
                             if b.type == "text")
        if response.stop_reason != "tool_use":
            break
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output, is_error = execute_tool(block.name, dict(block.input))
            tool_trace.append({"tool": block.name, "input": block.input,
                               "is_error": is_error,
                               "output_preview": output[:200]})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": output, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    return {"reply": final_text, "tool_calls": tool_trace,
            "messages": messages}
