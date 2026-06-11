import pytest

from pmts import modapts, registry
from pmts.base import calc_standard_time, parse_token


def test_parse_token_variants():
    assert parse_token("M4") == ("M4", 1)
    assert parse_token("2*M4") == ("M4", 2)
    assert parse_token("m4*3") == ("M4", 3)
    with pytest.raises(ValueError):
        parse_token("4M*")


def test_modapts_calc():
    # 经典例：大臂取件放到面前 M4 G1 M4 P0 = 9 MOD = 1.161s
    r = calc_standard_time(modapts.table(), ["M4", "G1", "M4", "P0"])
    assert r["basic_seconds"] == pytest.approx(9 * 0.129, abs=1e-4)
    assert r["standard_seconds"] == r["basic_seconds"]


def test_allowance_applied():
    r = calc_standard_time(modapts.table(), ["M4", "G1"], allowance=0.15)
    assert r["standard_seconds"] == pytest.approx(r["basic_seconds"] * 1.15, abs=1e-4)
    with pytest.raises(ValueError):
        calc_standard_time(modapts.table(), ["M4"], allowance=1.5)


def test_unknown_element():
    with pytest.raises(KeyError):
        calc_standard_time(modapts.table(), ["M4", "Z9"])


CSV_TMU = """code,tmu,description
R40B,15.6,伸手40cm到大致位置
G1A,2.0,简单抓取
M40B,18.2,移动40cm到大致位置
P1SE,5.6,简单定位
"""


def test_import_csv_card_tmu(tmp_path):
    from server import db as dbmod
    conn = dbmod.connect(tmp_path / "t.db")
    table = registry.parse_csv_card("mtm-demo", "MTM 演示卡", CSV_TMU)
    registry.save_table(conn, table)

    loaded = registry.resolve(conn, "imported:mtm-demo")
    assert loaded.lookup("R40B").seconds == pytest.approx(15.6 * 0.036, abs=1e-4)

    r = calc_standard_time(loaded, ["R40B", "G1A", "M40B", "P1SE"])
    assert r["basic_seconds"] == pytest.approx(41.4 * 0.036, abs=1e-3)

    methods = registry.list_methods(conn)
    names = {m["name"] for m in methods}
    assert "modapts" in names and "imported:mtm-demo" in names
    conn.close()


def test_import_csv_requires_value_column():
    with pytest.raises(ValueError):
        registry.parse_csv_card("bad", "bad", "code,foo\nM1,1\n")


def test_efficiency_comparison(tmp_path):
    from pipeline.rules import StepRule, EventMatcher
    from server import db as dbmod
    from server.efficiency import process_efficiency

    conn = dbmod.connect(tmp_path / "t.db")
    rules = [
        StepRule("pick", EventMatcher("roi_enter", "a"), EventMatcher("roi_exit", "a"),
                 standard={"method": "modapts",
                           "sequence": ["M4", "G3", "M4"], "allowance": 0.1}),
        StepRule("place", EventMatcher("roi_enter", "b"), EventMatcher("roi_exit", "b"),
                 standard={"seconds": 0.5}),
    ]
    cycles = [
        {"duration": 2.0, "status": "complete",
         "steps": [{"step": "pick", "duration": 1.2},
                   {"step": "place", "duration": 0.6}]}
        for _ in range(10)
    ]
    r = process_efficiency(conn, rules, cycles)
    pick = r["steps"][0]
    # M4+G3+M4 = 11 MOD = 1.419s × 1.1 = 1.561s；实测 1.2s → 效率 > 1
    assert pick["standard_seconds"] == pytest.approx(1.561, abs=0.01)
    assert pick["efficiency"] > 1
    place = r["steps"][1]
    assert place["source"] == "direct"
    assert place["gap_seconds"] == pytest.approx(0.1, abs=1e-6)
    assert r["cycle_standard_seconds"] == pytest.approx(2.061, abs=0.01)
    assert r["cycle_efficiency"] == pytest.approx(2.061 / 2.0, abs=0.01)
    conn.close()
