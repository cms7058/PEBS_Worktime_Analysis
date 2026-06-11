"""PMTS（预定动作时间标准）方法的统一抽象.

每种测量方法 = 一张"动作要素表"（code -> 单位时间值）。内置 MODAPTS 基础表；
MTM / MOST / 企业自定义标准通过数据卡导入成同样的结构（完整官方数据卡有版权，
由持有授权的客户自行导入，产品不内置）。

工步的标准工时 = 动作序列各要素时间之和 × (1 + 宽放率)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Element:
    code: str
    seconds: float
    description: str = ""


@dataclass
class ElementTable:
    """一张动作要素表，即一种可选的测量方法."""
    name: str                       # e.g. "modapts", "imported:mtm-uas-厂内版"
    display_name: str
    unit_note: str = ""             # e.g. "1 MOD = 0.129s"
    elements: dict[str, Element] = field(default_factory=dict)

    def lookup(self, code: str) -> Element:
        el = self.elements.get(code.upper())
        if el is None:
            raise KeyError(
                f"unknown element {code!r} in method {self.name!r}; "
                f"available: {', '.join(sorted(self.elements))}")
        return el


# 序列记号支持重复倍数："M4", "2*M4", "M4*2" 均合法
_TOKEN = re.compile(r"^(?:(\d+)\s*\*\s*)?([A-Za-z][A-Za-z0-9_]*)(?:\s*\*\s*(\d+))?$")


def parse_token(token: str) -> tuple[str, int]:
    m = _TOKEN.match(token.strip())
    if not m:
        raise ValueError(f"invalid motion token: {token!r}")
    count = int(m.group(1) or m.group(3) or 1)
    return m.group(2).upper(), count


def calc_standard_time(table: ElementTable, sequence: list[str],
                       allowance: float = 0.0) -> dict:
    """动作序列 -> 标准工时（秒），返回含逐要素分解的明细."""
    if not 0 <= allowance < 1:
        raise ValueError(f"allowance must be in [0, 1), got {allowance}")
    breakdown = []
    basic = 0.0
    for token in sequence:
        code, count = parse_token(token)
        el = table.lookup(code)
        secs = el.seconds * count
        basic += secs
        breakdown.append({
            "code": el.code, "count": count, "seconds": round(secs, 4),
            "description": el.description,
        })
    return {
        "method": table.name,
        "sequence": sequence,
        "basic_seconds": round(basic, 4),
        "allowance": allowance,
        "standard_seconds": round(basic * (1 + allowance), 4),
        "breakdown": breakdown,
    }
