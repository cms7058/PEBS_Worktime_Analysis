"""PEBS 工时分析平台 API（阶段 3）.

run:  .venv/bin/uvicorn server.app:app --port 8000
docs: http://localhost:8000/docs

Resources: 工序 processes (config packages) -> 批次 batches (uploaded videos
analyzed against a process) -> cycles (detected work cycles). Statistics are
computed on demand from cycle rows.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form,
                     HTTPException, Request, UploadFile)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pmts import registry as pmts_registry
from pmts.base import calc_standard_time

from . import analysis, auth, db, efficiency, stats

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"

app = FastAPI(title="PEBS AI Worktime", version="0.6.0")

# 开发期前端跑在 Vite dev server（默认 5173），需要跨域访问 API
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@app.on_event("startup")
def _bootstrap_auth():
    conn = db.connect()
    try: auth.init(conn)
    finally: conn.close()


# 鉴权中间件：未携带有效令牌的 API 请求返回 401。
# 静态资源 / OPTIONS 预检 / 登录端点放行。测试可通过环境变量绕过。
_API_PREFIXES = ("/processes", "/batches", "/pmts", "/llm", "/chat", "/users")
_AUTH_DISABLED = os.environ.get("PEBS_DISABLE_AUTH") == "1"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _AUTH_DISABLED or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    # 登录端点开放；/auth/me 和 /auth/logout 仍需令牌
    if path == "/auth/login":
        return await call_next(request)
    if not path.startswith(_API_PREFIXES) and not path.startswith("/auth/"):
        return await call_next(request)   # 静态资源由 StaticFiles 处理
    # 支持 ?token=  query 参数（用于 <img src> 之类无法加 header 的场景）
    token = (request.headers.get("authorization", "").removeprefix("Bearer ").strip()
             or request.query_params.get("token", ""))
    conn = db.connect()
    try:
        user = auth.check_token(conn, token)
    finally:
        conn.close()
    if user is None:
        return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
    request.state.user = user
    return await call_next(request)


# -- 鉴权与用户管理 ----------------------------------------------------------

def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "未登录")
    return user


def require_admin(request: Request) -> dict:
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login_endpoint(body: LoginIn, conn=Depends(get_db)):
    result = auth.login(conn, body.username, body.password)
    if result is None:
        raise HTTPException(401, "用户名或密码错误")
    return result


@app.post("/auth/logout")
def logout_endpoint(request: Request, conn=Depends(get_db)):
    token = (request.headers.get("authorization", "").removeprefix("Bearer ").strip()
             or request.query_params.get("token", ""))
    auth.logout(conn, token)
    return {"ok": True}


@app.get("/auth/me")
def me_endpoint(user=Depends(current_user)):
    return user


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordIn(BaseModel):
    password: str


class RoleIn(BaseModel):
    role: str


@app.get("/users")
def users_list(conn=Depends(get_db), _=Depends(require_admin)):
    return auth.list_users(conn)


@app.post("/users", status_code=201)
def users_create(body: UserCreateIn, conn=Depends(get_db),
                 _=Depends(require_admin)):
    try:
        return auth.create_user(conn, body.username, body.password, body.role)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "用户名已存在")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.put("/users/{user_id}/password")
def users_set_password(user_id: int, body: PasswordIn,
                       user=Depends(current_user), conn=Depends(get_db)):
    # 用户改自己的密码或管理员改任何人
    if user["role"] != "admin" and user["id"] != user_id:
        raise HTTPException(403, "无权修改他人密码")
    if auth.get_user(conn, user_id) is None:
        raise HTTPException(404, "用户不存在")
    auth.set_password(conn, user_id, body.password)
    return {"ok": True}


@app.put("/users/{user_id}/role")
def users_set_role(user_id: int, body: RoleIn, conn=Depends(get_db),
                   admin=Depends(require_admin)):
    if auth.get_user(conn, user_id) is None:
        raise HTTPException(404, "用户不存在")
    if admin["id"] == user_id:
        raise HTTPException(400, "不能修改自己的角色")
    try: auth.set_role(conn, user_id, body.role)
    except ValueError as e: raise HTTPException(422, str(e))
    return {"ok": True}


@app.delete("/users/{user_id}", status_code=204)
def users_delete(user_id: int, conn=Depends(get_db),
                 admin=Depends(require_admin)):
    if admin["id"] == user_id:
        raise HTTPException(400, "不能删除自己")
    if not auth.delete_user(conn, user_id):
        raise HTTPException(404, "用户不存在")


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# -- processes ----------------------------------------------------------------

class ProcessIn(BaseModel):
    name: str
    description: str = ""
    config_yaml: str


class ProcessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_yaml: Optional[str] = None


@app.post("/processes", status_code=201)
def create_process(body: ProcessIn, conn=Depends(get_db)):
    analysis.validate_config_yaml(body.config_yaml)
    try:
        return db.create_process(conn, body.name, body.description, body.config_yaml)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"process name already exists: {body.name!r}")


@app.get("/processes")
def list_processes(conn=Depends(get_db)):
    return db.list_processes(conn)


def _get_process_or_404(conn, process_id: int) -> dict:
    p = db.get_process(conn, process_id)
    if p is None:
        raise HTTPException(404, f"process {process_id} not found")
    return p


@app.get("/processes/{process_id}")
def get_process(process_id: int, conn=Depends(get_db)):
    return _get_process_or_404(conn, process_id)


@app.put("/processes/{process_id}")
def update_process(process_id: int, body: ProcessUpdate, conn=Depends(get_db)):
    _get_process_or_404(conn, process_id)
    if body.config_yaml is not None:
        analysis.validate_config_yaml(body.config_yaml)
    try:
        return db.update_process(conn, process_id, **body.model_dump())
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"process name already exists: {body.name!r}")


@app.delete("/processes/{process_id}", status_code=204)
def delete_process(process_id: int, conn=Depends(get_db)):
    if not db.delete_process(conn, process_id):
        raise HTTPException(404, f"process {process_id} not found")


class CloneIn(BaseModel):
    name: str
    description: Optional[str] = None


@app.post("/processes/{process_id}/clone", status_code=201)
def clone_process(process_id: int, body: CloneIn, conn=Depends(get_db)):
    """复制工序配置包：相似产线快速适配的入口."""
    src = _get_process_or_404(conn, process_id)
    try:
        return db.create_process(
            conn, body.name,
            body.description if body.description is not None else src["description"],
            src["config_yaml"],
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"process name already exists: {body.name!r}")


# -- batches (video upload + analysis) -----------------------------------------

@app.post("/processes/{process_id}/batches", status_code=201)
async def create_batch(
    process_id: int,
    background: BackgroundTasks,
    video: UploadFile = File(...),
    label: str = Form(""),
    backend: str = Form("pose"),
    sample_fps: float = Form(10.0),
    autostart: bool = Form(True),
    conn=Depends(get_db),
):
    """上传视频建批次。autostart=false 时只上传不分析（先在工作台画 ROI，
    确认配置后再 POST /batches/{id}/run）."""
    _get_process_or_404(conn, process_id)
    if backend not in ("pose", "hands"):
        raise HTTPException(422, "backend must be 'pose' or 'hands'")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    batch = db.create_batch(conn, process_id, video_path="", label=label,
                            backend=backend, sample_fps=sample_fps)
    dest = UPLOAD_DIR / f"batch_{batch['id']}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    conn.execute("UPDATE batches SET video_path = ? WHERE id = ?",
                 (str(dest), batch["id"]))
    conn.commit()
    if autostart:
        background.add_task(analysis.run_batch, batch["id"])
    return db.get_batch(conn, batch["id"])


@app.post("/batches/{batch_id}/run")
def run_batch(batch_id: int, background: BackgroundTasks, conn=Depends(get_db)):
    """启动（或失败后重跑）批次分析."""
    batch = _get_batch_or_404(conn, batch_id)
    if batch["status"] == "running":
        raise HTTPException(409, "batch is already running")
    background.add_task(analysis.run_batch, batch_id)
    db.set_batch_status(conn, batch_id, "pending")
    return db.get_batch(conn, batch_id)


@app.get("/batches/{batch_id}/frame")
def batch_frame(batch_id: int, t: float = 2.0, conn=Depends(get_db)):
    """抽取批次视频在 t 秒处的帧（JPEG），供前端 ROI 画布作底图."""
    import cv2
    from fastapi.responses import Response

    batch = _get_batch_or_404(conn, batch_id)
    cap = cv2.VideoCapture(batch["video_path"])
    cap.set(cv2.CAP_PROP_POS_MSEC, max(t, 0) * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(422, f"no frame at t={t}s")
    h, w = frame.shape[:2]
    if max(h, w) > 1280:   # ROI 用归一化坐标，底图缩小不影响精度
        scale = 1280 / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return Response(content=buf.tobytes(), media_type="image/jpeg")


def _get_batch_or_404(conn, batch_id: int) -> dict:
    b = db.get_batch(conn, batch_id)
    if b is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    return b


@app.get("/batches/{batch_id}")
def get_batch(batch_id: int, conn=Depends(get_db)):
    return _get_batch_or_404(conn, batch_id)


@app.get("/processes/{process_id}/batches")
def list_batches(process_id: int, conn=Depends(get_db)):
    _get_process_or_404(conn, process_id)
    return db.list_batches(conn, process_id)


@app.get("/batches/{batch_id}/cycles")
def batch_cycles(batch_id: int, status: Optional[str] = None, conn=Depends(get_db)):
    _get_batch_or_404(conn, batch_id)
    return db.list_cycles(conn, batch_id=batch_id, status=status)


# -- statistics (阶段 4) --------------------------------------------------------

@app.get("/processes/{process_id}/cycles")
def process_cycles(process_id: int, status: Optional[str] = None, conn=Depends(get_db)):
    """该工序所有历史批次的循环明细."""
    _get_process_or_404(conn, process_id)
    return db.list_cycles(conn, process_id=process_id, status=status)


@app.get("/processes/{process_id}/statistics")
def process_statistics(process_id: int, batch_id: Optional[int] = None,
                       conn=Depends(get_db)):
    """工序级统计：中位数/分位数、bootstrap 置信区间、正态/对数正态检验、
    偏度/双峰诊断；batch_id 可选，限定单批次."""
    _get_process_or_404(conn, process_id)
    cycles = db.list_cycles(conn, process_id=process_id, batch_id=batch_id)
    return stats.process_statistics(cycles)


# -- PMTS 测量方法（阶段 5） -----------------------------------------------------

@app.get("/pmts/methods")
def list_pmts_methods(conn=Depends(get_db)):
    """可选测量方法：内置 MODAPTS + 已导入的数据卡."""
    return pmts_registry.list_methods(conn)


@app.get("/pmts/methods/{method:path}/elements")
def pmts_elements(method: str, conn=Depends(get_db)):
    try:
        table = pmts_registry.resolve(conn, method)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"name": table.name, "display_name": table.display_name,
            "unit_note": table.unit_note,
            "elements": [{"code": e.code, "seconds": e.seconds,
                          "description": e.description}
                         for e in table.elements.values()]}


class CalcIn(BaseModel):
    method: str = "modapts"
    sequence: list[str]
    allowance: float = 0.0


@app.post("/pmts/calc")
def pmts_calc(body: CalcIn, conn=Depends(get_db)):
    """动作序列 -> 标准工时（含逐要素分解）."""
    try:
        table = pmts_registry.resolve(conn, body.method)
        return calc_standard_time(table, body.sequence, body.allowance)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/pmts/tables", status_code=201)
async def import_pmts_table(
    name: str = Form(...),
    display_name: str = Form(""),
    unit_note: str = Form(""),
    card: UploadFile = File(...),
    conn=Depends(get_db),
):
    """导入数据卡（CSV：code + seconds/tmu/mod [+ description]）。
    MTM/MOST 官方数据卡有版权，请导入企业自有授权资料或自定义标准."""
    text = (await card.read()).decode("utf-8-sig")
    table = pmts_registry.parse_csv_card(
        name, display_name or name, text, unit_note)
    pmts_registry.save_table(conn, table)
    return {"name": table.name, "element_count": len(table.elements)}


@app.get("/processes/{process_id}/efficiency")
def process_efficiency(process_id: int, batch_id: Optional[int] = None,
                       conn=Depends(get_db)):
    """实测工时 vs 标准工时（PMTS）对比：各工步与循环级效率比、改善空间.
    工步需在工序配置 steps[].standard 中定义标准（动作序列或直接秒数）."""
    process = _get_process_or_404(conn, process_id)
    cfg = analysis.validate_config_yaml(process["config_yaml"])
    cycles = db.list_cycles(conn, process_id=process_id, batch_id=batch_id)
    try:
        return efficiency.process_efficiency(conn, cfg.steps, cycles)
    except KeyError as e:
        raise HTTPException(422, str(e))


# -- 教程 -----------------------------------------------------------------------

from . import tutorials as tutorials_mod  # noqa: E402


@app.get("/tutorials")
def tutorials_list(lang: str = "zh"):
    return tutorials_mod.list_tutorials(lang if lang in ("zh", "en") else "zh")


@app.get("/tutorials/{tutorial_id}")
def tutorial_get(tutorial_id: str, lang: str = "zh"):
    tu = tutorials_mod.get_tutorial(tutorial_id, lang if lang in ("zh", "en") else "zh")
    if tu is None:
        raise HTTPException(404, f"tutorial {tutorial_id!r} not found")
    return tu


# -- 智能体：模型配置与对话 ------------------------------------------------------------

from . import llm  # noqa: E402


class LLMConfigIn(BaseModel):
    name: str
    model: str
    api_key: str
    base_url: str = ""


@app.get("/llm/configs")
def list_llm_configs(conn=Depends(get_db)):
    """模型配置列表（api_key 掩码返回）."""
    return llm.list_configs(conn)


@app.post("/llm/configs", status_code=201)
def save_llm_config(body: LLMConfigIn, conn=Depends(get_db)):
    """新增模型配置；name 已存在则覆盖。首个配置自动启用."""
    return llm.save_config(conn, body.name, body.model, body.api_key,
                           body.base_url)


@app.delete("/llm/configs/{config_id}", status_code=204)
def delete_llm_config(config_id: int, conn=Depends(get_db)):
    if not llm.delete_config(conn, config_id):
        raise HTTPException(404, f"config {config_id} not found")


@app.post("/llm/configs/{config_id}/activate")
def activate_llm_config(config_id: int, conn=Depends(get_db)):
    result = llm.activate(conn, config_id)
    if result is None:
        raise HTTPException(404, f"config {config_id} not found")
    return result


@app.post("/llm/configs/{config_id}/test")
def test_llm_config(config_id: int, conn=Depends(get_db)):
    """对该配置做一次最小真实调用验证连通性."""
    cfg = next((dict(r) for r in conn.execute(
        "SELECT * FROM llm_configs WHERE id = ?", (config_id,)).fetchall()),
        None)
    if cfg is None:
        raise HTTPException(404, f"config {config_id} not found")
    return llm.test_config(cfg)


class ChatIn(BaseModel):
    messages: list   # Anthropic 消息格式的历史（前端原样回传以保持多轮上下文）
    context: Optional[dict] = None   # 页面上下文：tab/tab_label/process_id/process_name


@app.post("/chat")
def chat(body: ChatIn, conn=Depends(get_db)):
    """智能体对话：用当前启用的模型配置跑一轮（含工具循环），
    嵌入式助手通过 context 感知用户当前页面与选中工序."""
    cfg = llm.get_active(conn)
    if cfg is None:
        raise HTTPException(422, "尚未配置模型：请先在助手面板的「模型设置」里添加并启用")
    if not body.messages:
        raise HTTPException(422, "messages 不能为空")
    try:
        return llm.run_chat(cfg, body.messages, context=body.context)
    except Exception as e:
        raise HTTPException(502, f"模型调用失败 {type(e).__name__}: {str(e)[:300]}")


# -- 前端静态文件（生产模式：web/ 下 npm run build 后由本服务直接托管） ----------------

_DIST = Path(__file__).parent.parent / "web" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
