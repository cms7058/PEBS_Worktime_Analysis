"""测量方法注册：内置方法 + 数据库中的导入数据卡.

导入格式（CSV，UTF-8）：列 `code` 必填，时间值列三选一：
    seconds — 直接给秒
    tmu     — MTM 系（1 TMU = 0.036s）
    mod     — MODAPTS 系（1 MOD = 0.129s）
可选列 `description`。导入后方法名为 "imported:<表名>"，与内置方法同等使用。
"""
from __future__ import annotations

import csv
import io
import json

from . import modapts
from .base import Element, ElementTable

TMU_SECONDS = 0.036

_BUILTIN = {"modapts": modapts.table}


def parse_csv_card(name: str, display_name: str, csv_text: str,
                   unit_note: str = "") -> ElementTable:
    reader = csv.DictReader(io.StringIO(csv_text))
    cols = {c.strip().lower() for c in (reader.fieldnames or [])}
    if "code" not in cols:
        raise ValueError("data card needs a 'code' column")
    value_col = next((c for c in ("seconds", "tmu", "mod") if c in cols), None)
    if value_col is None:
        raise ValueError("data card needs one of: seconds / tmu / mod column")
    factor = {"seconds": 1.0, "tmu": TMU_SECONDS, "mod": modapts.MOD_SECONDS}[value_col]

    elements: dict[str, Element] = {}
    for i, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        code = row.get("code", "").upper()
        if not code:
            continue
        try:
            seconds = round(float(row[value_col]) * factor, 4)
        except ValueError:
            raise ValueError(f"line {i}: bad {value_col} value {row[value_col]!r}")
        elements[code] = Element(code, seconds, row.get("description", ""))
    if not elements:
        raise ValueError("data card contains no elements")
    return ElementTable(name=f"imported:{name}", display_name=display_name,
                        unit_note=unit_note or f"imported from {value_col} values",
                        elements=elements)


# -- persistence (uses the platform sqlite connection) -------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS pmts_tables (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    unit_note TEXT NOT NULL DEFAULT '',
    elements_json TEXT NOT NULL
);
"""


def save_table(conn, table: ElementTable) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO pmts_tables (name, display_name, unit_note,"
        " elements_json) VALUES (?, ?, ?, ?)",
        (table.name, table.display_name, table.unit_note,
         json.dumps({c: [e.seconds, e.description]
                     for c, e in table.elements.items()}, ensure_ascii=False)),
    )
    conn.commit()


def _load_imported(conn, name: str) -> ElementTable | None:
    conn.executescript(SCHEMA)
    row = conn.execute(
        "SELECT * FROM pmts_tables WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    elements = {c: Element(c, v[0], v[1])
                for c, v in json.loads(row["elements_json"]).items()}
    return ElementTable(name=row["name"], display_name=row["display_name"],
                        unit_note=row["unit_note"], elements=elements)


def resolve(conn, method: str) -> ElementTable:
    """方法名 -> 要素表。内置名直接给，导入表用 'imported:<名>'."""
    if method in _BUILTIN:
        return _BUILTIN[method]()
    table = _load_imported(conn, method)
    if table is None:
        raise KeyError(f"unknown measurement method: {method!r}; "
                       f"builtin: {sorted(_BUILTIN)}, others: see /pmts/methods")
    return table


def list_methods(conn) -> list[dict]:
    conn.executescript(SCHEMA)
    out = []
    for name, factory in _BUILTIN.items():
        t = factory()
        out.append({"name": name, "display_name": t.display_name,
                    "unit_note": t.unit_note, "builtin": True,
                    "element_count": len(t.elements)})
    for row in conn.execute(
            "SELECT name, display_name, unit_note, elements_json"
            " FROM pmts_tables ORDER BY name").fetchall():
        out.append({"name": row["name"], "display_name": row["display_name"],
                    "unit_note": row["unit_note"], "builtin": False,
                    "element_count": len(json.loads(row["elements_json"]))})
    return out
