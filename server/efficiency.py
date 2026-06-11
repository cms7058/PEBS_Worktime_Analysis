"""实测工时 vs 标准工时（PMTS）对比：效率比与改善空间.

效率比 = 标准工时 / 实测中位工时（>1 快于标准，<1 存在改善空间）。
注意：视频实测的工步耗时包含手进出 ROI 的路径段，系统性略长于纯操作时间，
对比结论应结合 gap_seconds 看趋势而非纠结个位百分比。
"""
from __future__ import annotations

from typing import Optional

from pmts import registry
from pmts.base import calc_standard_time

from . import stats


def step_standard_seconds(conn, standard: dict) -> dict:
    """解析工步配置里的 standard 块 -> {standard_seconds, detail}."""
    if "seconds" in standard:
        return {"standard_seconds": float(standard["seconds"]),
                "source": "direct"}
    table = registry.resolve(conn, standard["method"])
    result = calc_standard_time(table, standard["sequence"],
                                allowance=float(standard.get("allowance", 0)))
    return {"standard_seconds": result["standard_seconds"],
            "source": standard["method"], "detail": result}


def process_efficiency(conn, step_rules: list, cycles: list[dict]) -> dict:
    """对一个工序的全部工步做实测/标准对比.

    step_rules: pipeline.rules.StepRule 列表（带 standard 块）
    cycles: DB 循环行（process_statistics 同款输入）
    """
    measured = stats.process_statistics(cycles)
    steps_out = []
    total_standard: Optional[float] = 0.0
    for rule in step_rules:
        m = measured["step_time"].get(rule.name, {})
        entry: dict = {"step": rule.name,
                       "measured_median": m.get("median"),
                       "measured_n": m.get("n", 0)}
        if rule.standard:
            std = step_standard_seconds(conn, rule.standard)
            entry.update(std)
            if total_standard is not None:
                total_standard += std["standard_seconds"]
            if entry["measured_median"]:
                ratio = std["standard_seconds"] / entry["measured_median"]
                entry["efficiency"] = round(ratio, 3)
                entry["gap_seconds"] = round(
                    entry["measured_median"] - std["standard_seconds"], 3)
        else:
            total_standard = None   # 任一工步缺标准则不出循环级合计
        steps_out.append(entry)

    cycle_median = measured["cycle_time"].get("median")
    out = {"steps": steps_out,
           "cycle_measured_median": cycle_median,
           "cycle_standard_seconds": (round(total_standard, 4)
                                      if total_standard is not None else None)}
    if total_standard and cycle_median:
        out["cycle_efficiency"] = round(total_standard / cycle_median, 3)
        out["cycle_gap_seconds"] = round(cycle_median - total_standard, 3)
    return out
