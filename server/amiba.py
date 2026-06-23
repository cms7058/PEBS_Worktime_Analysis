"""阿米巴对接：把视频工时工具按「平台令牌 + 产品」接入阿米巴动态智能体系统.

与 BOM 等子工具同款三段式：
  1. 接入(register)：阿米巴生成连接器令牌(amk_)后把浏览器跳到本工具 /register，
     工具存下 amiba_endpoint + connector_token，并回 hello 上报能力。
  2. 平台登录(launch)：用户从阿米巴产品页打开工作台，带 平台令牌(apk_) + 产品 跳到
     /amiba/launch；工具调阿米巴 /api/platform-auth/verify 核验，建立本工具会话，
     按产品建/绑工序项目。
  3. 回填(report)：工序分析出实测工时 / 工时负荷率 / PMTS 标准对比后，用连接器令牌
     回传到阿米巴 /api/ingest/manhours，进入该产品 toolData 与 5M1E 画像（man 维度）。
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from . import analysis, auth, db, efficiency, stats

TOOL_ID = "worktime"
CAPABILITIES = ["工步切分", "循环工时", "工时负荷率", "PMTS 标准工时对比", "异常识别"]
LABOR_RATE = float(os.environ.get("WORKTIME_LABOR_RATE", "60"))  # ¥/h 默认工价
SCOPES = ["工步切分与 ROI 标定", "视频采集与分析", "循环工时统计", "工时负荷率核算", "PMTS 标准对比"]

# 新建产品工序时的占位配置（与前端 ProcessLibrary 模板一致，保证通过校验）。
# 用户接入后在「配置工作台」按实际产线画 ROI / 调工步即可。
_DEFAULT_CONFIG_YAML = """process: amiba_product
keypoints: [left_wrist, right_wrist]

rois:
  - name: parts_bin
    rect: [0.05, 0.35, 0.30, 0.75]
  - name: fixture
    rect: [0.45, 0.40, 0.75, 0.85]

steps:
  - name: pick
    start: {event: roi_enter, roi: parts_bin, keypoint: any}
    end:   {event: roi_exit,  roi: parts_bin, keypoint: same}
    max_duration: 5.0
  - name: place
    start: {event: roi_enter, roi: fixture, keypoint: any}
    end:   {event: roi_exit,  roi: fixture, keypoint: same}
    max_duration: 8.0
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS amiba_config (
    enterprise_id   TEXT PRIMARY KEY,
    amiba_endpoint  TEXT NOT NULL,
    connector_token TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'worktime',
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS amiba_bindings (
    process_id    INTEGER PRIMARY KEY REFERENCES processes(id) ON DELETE CASCADE,
    enterprise_id TEXT NOT NULL,
    product_id    TEXT NOT NULL,
    part_no       TEXT NOT NULL DEFAULT '',
    product_name  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_amiba_bindings_product ON amiba_bindings(product_id);
CREATE TABLE IF NOT EXISTS amiba_projects (
    id              TEXT PRIMARY KEY,
    enterprise_id   TEXT NOT NULL,
    enterprise_name TEXT,
    product_id      TEXT NOT NULL,
    part_no         TEXT,
    product_name    TEXT,
    amiba_endpoint  TEXT NOT NULL,
    connector_token TEXT,
    labor_rate      REAL NOT NULL DEFAULT 60,
    created_by      TEXT,
    started_at      INTEGER NOT NULL,
    submitted_at    INTEGER,
    status          TEXT NOT NULL DEFAULT 'active',
    report_json     TEXT
);
CREATE TABLE IF NOT EXISTS amiba_tasks (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL,
    assignee_username TEXT NOT NULL,
    assignee_display  TEXT,
    scope             TEXT,
    status            TEXT NOT NULL DEFAULT 'todo',
    active_seconds    INTEGER NOT NULL DEFAULT 0,
    running_since     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_amiba_tasks_project ON amiba_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_amiba_projects_product ON amiba_projects(product_id);
"""


def init(conn) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- 接入配置 ------------------------------------------------------------------

def save_config(conn, enterprise_id: str, amiba_endpoint: str,
                connector_token: str, source: str = TOOL_ID) -> dict:
    init(conn)
    conn.execute(
        "INSERT INTO amiba_config (enterprise_id, amiba_endpoint, connector_token, source, updated_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(enterprise_id) DO UPDATE SET"
        "   amiba_endpoint=excluded.amiba_endpoint,"
        "   connector_token=excluded.connector_token,"
        "   source=excluded.source,"
        "   updated_at=excluded.updated_at",
        (enterprise_id, amiba_endpoint.rstrip("/"), connector_token, source, _now()),
    )
    conn.commit()
    return get_config(conn, enterprise_id)


def get_config(conn, enterprise_id: str) -> Optional[dict]:
    init(conn)
    row = conn.execute(
        "SELECT * FROM amiba_config WHERE enterprise_id = ?", (enterprise_id,)
    ).fetchone()
    return dict(row) if row else None


# -- 产品 <-> 工序绑定 ---------------------------------------------------------

def get_binding(conn, process_id: int) -> Optional[dict]:
    init(conn)
    row = conn.execute(
        "SELECT * FROM amiba_bindings WHERE process_id = ?", (process_id,)
    ).fetchone()
    return dict(row) if row else None


def find_binding_by_product(conn, product_id: str) -> Optional[dict]:
    init(conn)
    row = conn.execute(
        "SELECT * FROM amiba_bindings WHERE product_id = ?", (product_id,)
    ).fetchone()
    return dict(row) if row else None


def ensure_process_for_product(conn, enterprise_id: str, product_id: str,
                               part_no: str, product_name: str) -> dict:
    """按产品找/建工序项目：已绑定则复用，否则新建一个占位工序并绑定。"""
    existing = find_binding_by_product(conn, product_id)
    if existing:
        p = db.get_process(conn, existing["process_id"])
        if p:
            return p
        # 绑定残留但工序已删，清理后重建
        conn.execute("DELETE FROM amiba_bindings WHERE product_id = ?", (product_id,))
        conn.commit()

    label = product_name or part_no or product_id
    base = f"{label}（{part_no}）" if part_no and part_no != label else label
    name = base
    # processes.name 唯一：冲突时追加短后缀
    for suffix in ("", f" · {product_id[-4:]}", f" · {secrets.token_hex(2)}"):
        try:
            p = db.create_process(
                conn, name + suffix,
                description=f"阿米巴产品 {label}（{part_no}）的实测工时项目",
                config_yaml=_DEFAULT_CONFIG_YAML,
            )
            break
        except Exception:  # sqlite3.IntegrityError: name 冲突
            continue
    else:
        raise RuntimeError("无法为产品创建工序（名称冲突）")

    conn.execute(
        "INSERT INTO amiba_bindings (process_id, enterprise_id, product_id, part_no, product_name, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (p["id"], enterprise_id, product_id, part_no, product_name, _now()),
    )
    conn.commit()
    return p


# -- 会话：把阿米巴用户映射成本工具用户 ----------------------------------------

def ensure_user(conn, username: str) -> dict:
    auth.init(conn)
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row:
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    # 平台令牌已是凭证，这里只需占位密码（本工具不再单独登录该账号）
    u = auth.create_user(conn, username, secrets.token_urlsafe(24), role="user")
    return u


def mint_session(conn, user_id: int) -> str:
    auth.init(conn)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(timespec="seconds"),
         (now + timedelta(days=auth.SESSION_TTL_DAYS)).isoformat(timespec="seconds")),
    )
    conn.commit()
    return token


# -- 出站调用阿米巴 ------------------------------------------------------------

def hello(config: dict, inbound_url: str = "") -> None:
    """启动/接入时上报能力，点亮阿米巴诊断界面的「已注册」。失败不阻断接入。"""
    try:
        httpx.post(
            f"{config['amiba_endpoint']}/api/connectors/hello",
            headers={"Authorization": f"Bearer {config['connector_token']}"},
            json={"version": "0.6.0", "capabilities": CAPABILITIES, "inboundUrl": inbound_url},
            timeout=8.0,
        )
    except Exception:
        pass


def verify_platform_login(amiba_endpoint: str, username: str, platform_token: str,
                          tool: str = TOOL_ID) -> dict:
    """调阿米巴 /api/platform-auth/verify 核验平台令牌。返回核验结果（valid/...）。"""
    try:
        r = httpx.post(
            f"{amiba_endpoint.rstrip('/')}/api/platform-auth/verify",
            json={"username": username, "token": platform_token, "tool": tool},
            timeout=10.0,
        )
        return r.json()
    except Exception as e:  # 网络/解析失败
        return {"valid": False, "reason": f"无法连接阿米巴平台：{e}"}


def report(conn, process_id: int) -> dict:
    """把该工序的实测工时 / 工时负荷率 / PMTS 标准对比回填到阿米巴对应产品。"""
    binding = get_binding(conn, process_id)
    if not binding:
        raise ValueError("该工序未绑定阿米巴产品")
    config = get_config(conn, binding["enterprise_id"])
    if not config:
        raise ValueError("本企业尚未完成阿米巴接入（缺连接器令牌）")

    process = db.get_process(conn, process_id)
    cycles = db.list_cycles(conn, process_id=process_id)
    complete = [c for c in cycles if c["status"] == "complete" and c.get("duration")]
    total_seconds = sum(c["duration"] for c in complete)
    man_hours = round(total_seconds / 3600.0, 3)

    metrics: list[dict] = []
    summary = f"{len(complete)} 个完整循环"
    if complete:
        st = stats.process_statistics(cycles)
        median = st["cycle_time"].get("median")
        if median:
            metrics.append({"label": "实测循环工时", "value": round(median, 2), "unit": "s"})
            summary += f" · 实测中位 {round(median, 2)}s"
        # 工时负荷率 / PMTS 标准对比（需工序配置了 standard）
        try:
            cfg = analysis.validate_config_yaml(process["config_yaml"])
            eff = efficiency.process_efficiency(conn, cfg.steps, cycles)
            if eff.get("cycle_efficiency") is not None:
                metrics.append({"label": "工时负荷率", "value": round(eff["cycle_efficiency"] * 100, 1), "unit": "%"})
            if eff.get("cycle_standard_seconds") is not None:
                metrics.append({"label": "PMTS标准工时", "value": round(eff["cycle_standard_seconds"], 2), "unit": "s"})
        except Exception:
            pass
    else:
        summary = "尚无完整循环数据"

    payload = {
        "productId": binding["product_id"],
        "manHours": man_hours,
        "summary": summary,
        "metrics": metrics,
    }
    r = httpx.post(
        f"{config['amiba_endpoint']}/api/ingest/manhours",
        headers={"Authorization": f"Bearer {config['connector_token']}"},
        json=payload,
        timeout=12.0,
    )
    ok = r.status_code in (200, 201)
    return {"ok": ok, "status": r.status_code, "sent": payload,
            "response": (r.json() if ok else r.text)}


# -- 计时项目（按产品：任务计时 + 提交回传工时，APS/Lean 同款）--------------------

def _now_sec() -> int:
    return int(time.time())


def _task_elapsed(t: dict) -> int:
    return t["active_seconds"] + (max(0, _now_sec() - t["running_since"]) if t["running_since"] else 0)


def project_dict(conn, p: dict) -> dict:
    tasks = [dict(r) for r in conn.execute(
        "SELECT * FROM amiba_tasks WHERE project_id = ?", (p["id"],)).fetchall()]
    total = sum(_task_elapsed(t) for t in tasks)
    return {
        "id": p["id"], "enterpriseId": p["enterprise_id"], "enterpriseName": p["enterprise_name"],
        "productId": p["product_id"], "partNo": p["part_no"], "productName": p["product_name"],
        "laborRate": p["labor_rate"], "startedAt": p["started_at"], "submittedAt": p["submitted_at"],
        "status": p["status"], "totalSeconds": total,
        "manHours": round(total / 3600, 2), "laborCost": round(total / 3600 * p["labor_rate"], 2),
        "report": (__import__("json").loads(p["report_json"]) if p["report_json"] else None),
        "tasks": [{
            "id": t["id"], "assigneeUsername": t["assignee_username"], "assigneeDisplay": t["assignee_display"],
            "scope": t["scope"], "status": t["status"], "running": t["running_since"] is not None,
            "elapsedSeconds": _task_elapsed(t),
        } for t in tasks],
    }


def get_project(conn, project_id: str) -> Optional[dict]:
    init(conn)
    row = conn.execute("SELECT * FROM amiba_projects WHERE id = ?", (project_id,)).fetchone()
    return project_dict(conn, dict(row)) if row else None


def ensure_project(conn, enterprise_id: str, enterprise_name: str, product_id: str,
                   part_no: str, product_name: str, amiba_endpoint: str,
                   connector_token: str, created_by: str,
                   team: Optional[list] = None) -> dict:
    """按产品找/建计时项目：已有进行中的则复用；否则新建并（单人）自动开始计时。"""
    init(conn)
    existing = conn.execute(
        "SELECT * FROM amiba_projects WHERE product_id = ? AND status = 'active'"
        " ORDER BY started_at DESC LIMIT 1", (product_id,)).fetchone()
    if existing:
        return project_dict(conn, dict(existing))

    members = team or [{"username": created_by or "me"}]
    solo = len(members) == 1  # 单人（从接入直接进工具）：进入即自动开始计时
    pid = "wt_proj_" + secrets.token_hex(5)
    conn.execute(
        "INSERT INTO amiba_projects (id, enterprise_id, enterprise_name, product_id, part_no, product_name,"
        " amiba_endpoint, connector_token, labor_rate, created_by, started_at, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (pid, enterprise_id, enterprise_name, product_id, part_no, product_name,
         amiba_endpoint.rstrip("/"), connector_token, LABOR_RATE, created_by, _now_sec()),
    )
    for i, m in enumerate(members):
        conn.execute(
            "INSERT INTO amiba_tasks (id, project_id, assignee_username, assignee_display, scope, status,"
            " active_seconds, running_since) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            ("task_" + secrets.token_hex(4), pid, m["username"], m.get("displayName") or m["username"],
             SCOPES[i % len(SCOPES)] if len(members) > 1 else "整体工时实测",
             "doing" if solo else "todo", _now_sec() if solo else None),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM amiba_projects WHERE id = ?", (pid,)).fetchone()
    return project_dict(conn, dict(row))


def task_action(conn, project_id: str, task_id: str, action: str) -> Optional[dict]:
    init(conn)
    p = conn.execute("SELECT * FROM amiba_projects WHERE id = ?", (project_id,)).fetchone()
    if not p:
        return None
    t = conn.execute("SELECT * FROM amiba_tasks WHERE id = ? AND project_id = ?",
                     (task_id, project_id)).fetchone()
    if not t:
        raise ValueError("任务不存在")
    t = dict(t)
    if action == "start":
        if not t["running_since"]:
            conn.execute("UPDATE amiba_tasks SET running_since = ?, status = 'doing' WHERE id = ?",
                         (_now_sec(), task_id))
    elif action == "stop":
        if t["running_since"]:
            conn.execute("UPDATE amiba_tasks SET active_seconds = ?, running_since = NULL WHERE id = ?",
                         (_task_elapsed(t), task_id))
    elif action == "done":
        conn.execute("UPDATE amiba_tasks SET active_seconds = ?, running_since = NULL, status = 'done' WHERE id = ?",
                     (_task_elapsed(t), task_id))
    else:
        raise ValueError("未知操作")
    conn.commit()
    return project_dict(conn, dict(p))


def submit_project(conn, project_id: str) -> Optional[dict]:
    init(conn)
    p = conn.execute("SELECT * FROM amiba_projects WHERE id = ?", (project_id,)).fetchone()
    if not p:
        return None
    p = dict(p)
    if p["status"] == "submitted":
        return project_dict(conn, p)

    tasks = [dict(r) for r in conn.execute(
        "SELECT * FROM amiba_tasks WHERE project_id = ?", (project_id,)).fetchall()]
    members, total = [], 0
    for t in tasks:
        secs = _task_elapsed(t)
        conn.execute("UPDATE amiba_tasks SET active_seconds = ?, running_since = NULL WHERE id = ?",
                     (secs, t["id"]))
        total += secs
        members.append({"username": t["assignee_username"], "seconds": secs})
    man_hours = round(total / 3600, 2)
    labor_cost = round(man_hours * p["labor_rate"], 2)

    report_ok, report_err = False, None
    if p["amiba_endpoint"] and p["connector_token"] and p["product_id"]:
        try:
            r = httpx.post(
                f"{p['amiba_endpoint'].rstrip('/')}/api/ingest/manhours",
                headers={"Authorization": f"Bearer {p['connector_token']}"},
                json={"productId": p["product_id"], "manHours": man_hours, "laborCost": labor_cost,
                      "members": members,
                      "summary": f"实测作业工时 {man_hours}h · 人工成本 ¥{round(labor_cost)}"},
                timeout=12.0,
            )
            report_ok = r.status_code in (200, 201)
            if not report_ok:
                report_err = f"HTTP {r.status_code}"
        except Exception as e:
            report_err = str(e)
    else:
        report_err = "缺少连接器令牌/产品，未回传"

    import json as _json
    report = {"ok": report_ok, "error": report_err, "manHours": man_hours, "laborCost": labor_cost}
    conn.execute("UPDATE amiba_projects SET status = 'submitted', submitted_at = ?, report_json = ? WHERE id = ?",
                 (_now_sec(), _json.dumps(report, ensure_ascii=False), project_id))
    conn.commit()
    row = conn.execute("SELECT * FROM amiba_projects WHERE id = ?", (project_id,)).fetchone()
    return project_dict(conn, dict(row))
