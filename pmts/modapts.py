"""内置 MODAPTS（模特法）基础动作表.

收录的是已在教科书与公开文献中广泛发表的基础要素值（1 MOD = 0.129 秒，
要素代号中的数字即 MOD 值）。完整的官方数据卡及认证培训材料由国际 MODAPTS
协会持有，企业如需官方版本请通过数据卡导入功能使用自有授权资料。
"""
from __future__ import annotations

from .base import Element, ElementTable

MOD_SECONDS = 0.129

# code -> (MOD 值, 描述)
_ELEMENTS = {
    # 移动动作（以参与的身体部位分级）
    "M1": (1, "手指动作"),
    "M2": (2, "手腕动作"),
    "M3": (3, "小臂动作"),
    "M4": (4, "大臂动作"),
    "M5": (5, "伸直手臂/肩部动作"),
    "M7": (7, "躯干参与的极限伸够"),
    # 终结动作：抓取
    "G0": (0, "触碰（无抓取）"),
    "G1": (1, "简单抓取"),
    "G3": (3, "复杂抓取（小件/混堆/需挑选）"),
    # 终结动作：放置
    "P0": (0, "简单放下（无对准）"),
    "P2": (2, "需注意的放置（一次对准）"),
    "P5": (5, "精确放置（多次对准/配合）"),
    # 辅助动作
    "L1": (1, "负重附加（每约 4kg 双手/2kg 单手）"),
    "E2": (2, "眼睛动作（注视/移视）"),
    "D3": (3, "判断决策"),
    "R2": (2, "换抓/调整握持"),
    "A4": (4, "施压"),
    "C4": (4, "摇转（每圈）"),
    "F3": (3, "脚踏动作"),
    "W5": (5, "行走（每步）"),
    "B17": (17, "弯腰并直起"),
    "S30": (30, "坐下并站起"),
}


def table() -> ElementTable:
    return ElementTable(
        name="modapts",
        display_name="MODAPTS 模特法（内置基础表）",
        unit_note=f"1 MOD = {MOD_SECONDS}s；要素代号中的数字即 MOD 值",
        elements={code: Element(code, round(mod * MOD_SECONDS, 4), desc)
                  for code, (mod, desc) in _ELEMENTS.items()},
    )
