"""智能体工具层：把平台能力封装成 Claude tool use 的工具.

设计原则（与整体架构一致）：确定性计算全部在平台代码完成，LLM 只负责
调用工具和解读结果。每个工具直接调用 DAL/管线，不经过 HTTP，便于离线
测试；返回值必须 JSON 可序列化。
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable

from pipeline.events import EventDetector
from pipeline.perception import analyze_video as run_perception
from pipeline.rules import ProcessConfig, RuleEngine, summarize
from pmts import registry as pmts_registry
from pmts.base import calc_standard_time as pmts_calc
from server import db, efficiency, stats, tutorials
from server.analysis import validate_config_yaml

PROJECT_ROOT = Path(__file__).parent.parent


def _conn():
    return db.connect()


# -- tool implementations -------------------------------------------------------

def list_processes() -> list[dict]:
    conn = _conn()
    try:
        return [{k: p[k] for k in ("id", "name", "description", "created_at")}
                for p in db.list_processes(conn)]
    finally:
        conn.close()


def get_process_config(process_id: int) -> dict:
    conn = _conn()
    try:
        p = db.get_process(conn, process_id)
        if p is None:
            raise ValueError(f"工序 {process_id} 不存在")
        return {"id": p["id"], "name": p["name"], "config_yaml": p["config_yaml"]}
    finally:
        conn.close()


def create_process(name: str, config_yaml: str, description: str = "") -> dict:
    validate_config_yaml(config_yaml)
    conn = _conn()
    try:
        p = db.create_process(conn, name, description, config_yaml)
        return {"id": p["id"], "name": p["name"]}
    finally:
        conn.close()


def update_process_config(process_id: int, config_yaml: str) -> dict:
    validate_config_yaml(config_yaml)
    conn = _conn()
    try:
        if db.get_process(conn, process_id) is None:
            raise ValueError(f"工序 {process_id} 不存在")
        db.update_process(conn, process_id, config_yaml=config_yaml)
        return {"id": process_id, "updated": True}
    finally:
        conn.close()


def analyze_video(process_id: int, video_path: str, backend: str = "pose",
                  sample_fps: float = 10.0, label: str = "") -> dict:
    """同步跑完整分析管线并入库，返回批次摘要。视频较长时耗时几十秒."""
    if not Path(video_path).exists():
        raise ValueError(f"视频文件不存在: {video_path}")
    conn = _conn()
    try:
        process = db.get_process(conn, process_id)
        if process is None:
            raise ValueError(f"工序 {process_id} 不存在")
        cfg = validate_config_yaml(process["config_yaml"])
        batch = db.create_batch(conn, process_id, video_path, label,
                                backend, sample_fps)
        db.set_batch_status(conn, batch["id"], "running")
        try:
            frames = run_perception(video_path, sample_fps=sample_fps,
                                    backend=backend)
            detector = EventDetector(rois=cfg.rois, keypoints=cfg.keypoints)
            events = sorted(detector.process(frames),
                            key=lambda e: (e.t, e.frame_idx))
            cycles = RuleEngine(cfg).run(iter(events))
            db.insert_cycles(conn, batch["id"],
                             [dataclasses.asdict(c) for c in cycles])
            report = summarize(cycles)
            db.set_batch_status(conn, batch["id"], "done", summary=report)
            return {"batch_id": batch["id"], "summary": report}
        except Exception as e:
            db.set_batch_status(conn, batch["id"], "failed",
                                error=f"{type(e).__name__}: {e}")
            raise
    finally:
        conn.close()


def get_cycles(process_id: int, batch_id: int | None = None,
               status: str | None = None) -> list[dict]:
    conn = _conn()
    try:
        rows = db.list_cycles(conn, process_id=process_id,
                              batch_id=batch_id, status=status)
        return [{k: c[k] for k in ("batch_id", "cycle_idx", "t_start", "t_end",
                                   "duration", "status", "steps", "anomalies")}
                for c in rows]
    finally:
        conn.close()


def query_statistics(process_id: int, batch_id: int | None = None) -> dict:
    conn = _conn()
    try:
        cycles = db.list_cycles(conn, process_id=process_id, batch_id=batch_id)
        return stats.process_statistics(cycles)
    finally:
        conn.close()


def compare_efficiency(process_id: int, batch_id: int | None = None) -> dict:
    conn = _conn()
    try:
        process = db.get_process(conn, process_id)
        if process is None:
            raise ValueError(f"工序 {process_id} 不存在")
        cfg = validate_config_yaml(process["config_yaml"])
        cycles = db.list_cycles(conn, process_id=process_id, batch_id=batch_id)
        return efficiency.process_efficiency(conn, cfg.steps, cycles)
    finally:
        conn.close()


def list_pmts_methods() -> list[dict]:
    conn = _conn()
    try:
        return pmts_registry.list_methods(conn)
    finally:
        conn.close()


def calc_standard_time(sequence: list[str], method: str = "modapts",
                       allowance: float = 0.0) -> dict:
    conn = _conn()
    try:
        table = pmts_registry.resolve(conn, method)
        return pmts_calc(table, sequence, allowance)
    finally:
        conn.close()


def preview_roi(video_path: str, t: float = 3.0,
                process_id: int | None = None, backend: str = "pose") -> dict:
    """抽取视频帧并叠加 ROI（如指定工序）与关键点检测，写出预览图。
    返回图片路径，提示用户打开查看以确认 ROI 是否套准."""
    import cv2
    if not Path(video_path).exists():
        raise ValueError(f"视频文件不存在: {video_path}")
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"无法读取 t={t}s 处的帧")
    h, w = frame.shape[:2]

    rois_drawn = []
    if process_id is not None:
        cfg_info = get_process_config(process_id)
        cfg = validate_config_yaml(cfg_info["config_yaml"])
        colors = [(0, 200, 0), (0, 140, 255), (255, 120, 0), (180, 0, 220)]
        for i, roi in enumerate(cfg.rois):
            x1, y1, x2, y2 = roi.rect
            c = colors[i % len(colors)]
            cv2.rectangle(frame, (int(x1 * w), int(y1 * h)),
                          (int(x2 * w), int(y2 * h)), c, 2)
            cv2.putText(frame, roi.name, (int(x1 * w) + 4, int(y1 * h) + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2)
            rois_drawn.append(roi.name)

    detected = []
    for fp in run_perception(video_path, sample_fps=None, backend=backend):
        if fp.t >= t:
            for name, (x, y, conf) in fp.keypoints.items():
                cv2.circle(frame, (int(x * w), int(y * h)), 6, (0, 0, 255), -1)
                detected.append({"keypoint": name, "x": round(x, 3),
                                 "y": round(y, 3), "confidence": conf})
            break

    out = str(Path(video_path).with_suffix("")) + f".preview_t{t:g}.jpg"
    cv2.imwrite(out, frame)
    return {"image_path": out, "frame_size": [w, h], "t": t,
            "rois_drawn": rois_drawn, "keypoints_detected": detected}


def list_tutorials(lang: str = "zh") -> list[dict]:
    return tutorials.list_tutorials(lang)


def show_tutorial(tutorial_id: str, lang: str = "zh") -> dict:
    """返回教程内容；前端检测到本工具调用成功后会自动播放交互式引导
    （在页面上高亮对应按钮/区域并分步说明）."""
    tu = tutorials.get_tutorial(tutorial_id, lang)
    if tu is None:
        raise ValueError(f"教程不存在: {tutorial_id}，可用教程见 list_tutorials")
    return tu


# -- tool registry --------------------------------------------------------------

TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    f.__name__: f for f in [
        list_processes, get_process_config, create_process,
        update_process_config, analyze_video, get_cycles, query_statistics,
        compare_efficiency, list_pmts_methods, calc_standard_time, preview_roi,
        list_tutorials, show_tutorial,
    ]
}

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_processes",
        "description": "列出工序库中的所有工序（配置包）。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_process_config",
        "description": "查看某个工序的完整配置 YAML（ROI、工步规则、标准工时定义）。",
        "input_schema": {
            "type": "object",
            "properties": {"process_id": {"type": "integer"}},
            "required": ["process_id"],
        },
    },
    {
        "name": "create_process",
        "description": ("创建新工序。config_yaml 必须包含 process、rois（归一化矩形"
                        " [x1,y1,x2,y2]）、steps（每步 start/end 事件 + 可选"
                        " max_duration 和 standard 标准工时块）。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "config_yaml": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "config_yaml"],
        },
    },
    {
        "name": "update_process_config",
        "description": "更新工序的配置 YAML（调整 ROI、规则或标准工时定义后使用）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {"type": "integer"},
                "config_yaml": {"type": "string"},
            },
            "required": ["process_id", "config_yaml"],
        },
    },
    {
        "name": "analyze_video",
        "description": ("对视频按指定工序的规则跑完整分析（感知→事件→工步切分），"
                        "结果入库并返回摘要。backend：画面能看到上半身用 pose，"
                        "近景只见手用 hands。同步执行，视频长时需等待。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {"type": "integer"},
                "video_path": {"type": "string", "description": "视频文件绝对路径"},
                "backend": {"type": "string", "enum": ["pose", "hands"]},
                "sample_fps": {"type": "number"},
                "label": {"type": "string", "description": "批次标签，如班次/日期"},
            },
            "required": ["process_id", "video_path"],
        },
    },
    {
        "name": "get_cycles",
        "description": "查询循环明细（每个循环的起止时间、各工步耗时、异常记录）。用于解释某个时段为何异常。",
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {"type": "integer"},
                "batch_id": {"type": "integer"},
                "status": {"type": "string",
                           "enum": ["complete", "incomplete", "anomalous"]},
            },
            "required": ["process_id"],
        },
    },
    {
        "name": "query_statistics",
        "description": ("工序历史数据统计：中位数/分位数、bootstrap 95% 置信区间、"
                        "正态与对数正态检验、偏度、双峰诊断、直方图。"
                        "不传 batch_id 则统计全部历史批次。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {"type": "integer"},
                "batch_id": {"type": "integer"},
            },
            "required": ["process_id"],
        },
    },
    {
        "name": "compare_efficiency",
        "description": ("实测工时 vs PMTS 标准工时对比：各工步与循环级效率比、"
                        "改善空间秒数。需工序配置中定义了 standard 块。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {"type": "integer"},
                "batch_id": {"type": "integer"},
            },
            "required": ["process_id"],
        },
    },
    {
        "name": "list_pmts_methods",
        "description": "列出可用的预定时间标准（PMTS）测量方法：内置 MODAPTS 及已导入的数据卡。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calc_standard_time",
        "description": ("用 PMTS 方法计算动作序列的标准工时。例如 MODAPTS："
                        "['M4','G1','M4','P2'] 表示大臂伸出+简单抓取+大臂移动+"
                        "注意放置。支持倍数记号 '2*M4'。返回逐要素分解。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {"type": "array", "items": {"type": "string"}},
                "method": {"type": "string",
                           "description": "modapts 或 imported:<表名>"},
                "allowance": {"type": "number",
                              "description": "宽放率，如 0.15 表示 15%"},
            },
            "required": ["sequence"],
        },
    },
    {
        "name": "preview_roi",
        "description": ("抽取视频某时刻的帧，叠加工序 ROI 框和关键点检测结果，"
                        "生成预览图。用于配置 ROI 前查看画面布局、确认关键点能否"
                        "检出、检查 ROI 是否套准。返回检出的关键点坐标（归一化），"
                        "可据此推算 ROI 坐标。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string"},
                "t": {"type": "number", "description": "时间点（秒）"},
                "process_id": {"type": "integer",
                               "description": "可选，叠加该工序的 ROI"},
                "backend": {"type": "string", "enum": ["pose", "hands"]},
            },
            "required": ["video_path"],
        },
    },
]


TOOL_DEFINITIONS.extend([
    {
        "name": "list_tutorials",
        "description": "列出可用的交互式操作教程（创建工序、配置工作台、上传分析、解读统计、配置模型）。",
        "input_schema": {
            "type": "object",
            "properties": {"lang": {"type": "string", "enum": ["zh", "en"]}},
        },
    },
    {
        "name": "show_tutorial",
        "description": ("播放交互式操作教程：调用后前端会在真实页面上分步高亮对应"
                        "按钮/区域并显示说明。用户问「怎么操作/怎么用/教我」类问题时"
                        "优先调用本工具，并在回复里简述要点。lang 跟随用户界面语言。"),
        "input_schema": {
            "type": "object",
            "properties": {
                "tutorial_id": {"type": "string",
                                "enum": ["create_process", "configure_workbench",
                                         "upload_batch", "read_statistics",
                                         "setup_model"]},
                "lang": {"type": "string", "enum": ["zh", "en"]},
            },
            "required": ["tutorial_id"],
        },
    },
])


def execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """执行工具，返回 (JSON 结果, is_error)."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"未知工具: {name}", True
    try:
        result = fn(**tool_input)
        return json.dumps(result, ensure_ascii=False, default=str), False
    except Exception as e:
        return f"{type(e).__name__}: {e}", True
