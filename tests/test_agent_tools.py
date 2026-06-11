"""智能体工具层测试（不调用 Claude API，纯本地）."""
import json
import pathlib

import pytest

from agent import tools
from server import db as dbmod

CONFIG_YAML = (pathlib.Path(__file__).parent.parent
               / "configs" / "example_process.yaml").read_text()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "agent_test.db")


def call(_tool, **kwargs):
    output, is_error = tools.execute_tool(_tool, kwargs)
    return json.loads(output) if not is_error else output, is_error


def test_tool_definitions_match_functions():
    defined = {t["name"] for t in tools.TOOL_DEFINITIONS}
    implemented = set(tools.TOOL_FUNCTIONS)
    assert defined == implemented


def test_process_roundtrip():
    created, err = call("create_process", name="测试工序",
                        config_yaml=CONFIG_YAML, description="d")
    assert not err
    listed, _ = call("list_processes")
    assert listed[0]["name"] == "测试工序"
    cfg, _ = call("get_process_config", process_id=created["id"])
    assert "parts_bin" in cfg["config_yaml"]


def test_invalid_config_returns_error():
    output, is_error = call("create_process", name="bad",
                            config_yaml="rois: []\nsteps: []")
    assert is_error
    assert "config" in output


def test_calc_standard_time_tool():
    result, err = call("calc_standard_time", sequence=["M4", "G1", "M4", "P0"])
    assert not err
    assert result["basic_seconds"] == pytest.approx(9 * 0.129, abs=1e-3)


def test_list_pmts_methods_tool():
    result, err = call("list_pmts_methods")
    assert not err
    assert any(m["name"] == "modapts" for m in result)


def test_unknown_tool_is_error():
    output, is_error = tools.execute_tool("nope", {})
    assert is_error


def test_statistics_on_empty_process():
    created, _ = call("create_process", name="p2", config_yaml=CONFIG_YAML)
    result, err = call("query_statistics", process_id=created["id"])
    assert not err
    assert result["cycle_time"]["n"] == 0
