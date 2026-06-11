"""API tests against a temporary database (no video analysis here; the
end-to-end upload flow is exercised against the real server with a real
video — see README 测试 section)."""
import pathlib

import pytest
from fastapi.testclient import TestClient

from server import db as dbmod
from server.app import app, get_db

CONFIG_YAML = (pathlib.Path(__file__).parent.parent
               / "configs" / "example_process.yaml").read_text()


@pytest.fixture()
def client(tmp_path):
    conn = dbmod.connect(tmp_path / "test.db")

    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_process_crud_and_clone(client):
    r = client.post("/processes", json={
        "name": "工序A", "description": "demo", "config_yaml": CONFIG_YAML})
    assert r.status_code == 201
    pid = r.json()["id"]

    assert client.get(f"/processes/{pid}").json()["name"] == "工序A"
    assert len(client.get("/processes").json()) == 1

    r = client.put(f"/processes/{pid}", json={"description": "updated"})
    assert r.json()["description"] == "updated"

    r = client.post(f"/processes/{pid}/clone", json={"name": "工序A-线2"})
    assert r.status_code == 201
    assert r.json()["config_yaml"] == CONFIG_YAML

    assert client.delete(f"/processes/{pid}").status_code == 204
    assert client.get(f"/processes/{pid}").status_code == 404


def test_duplicate_name_rejected(client):
    body = {"name": "dup", "config_yaml": CONFIG_YAML}
    assert client.post("/processes", json=body).status_code == 201
    assert client.post("/processes", json=body).status_code == 409


def test_invalid_config_rejected(client):
    r = client.post("/processes", json={
        "name": "bad", "config_yaml": "process: x\nrois: []\nsteps: []"})
    assert r.status_code == 422
    assert "config" in r.json()["detail"]


def test_statistics_endpoint_on_stored_cycles(client, tmp_path):
    r = client.post("/processes", json={"name": "p", "config_yaml": CONFIG_YAML})
    pid = r.json()["id"]
    # insert a finished batch + cycles directly via the DAL
    conn = next(iter(app.dependency_overrides.values()))().__next__()
    batch = dbmod.create_batch(conn, pid, "x.mp4", "b1", "pose", 10.0)
    dbmod.insert_cycles(conn, batch["id"], [
        {"cycle_idx": i, "t_start": i * 10.0, "t_end": i * 10.0 + 8 + i % 3,
         "duration": 8.0 + i % 3, "status": "complete",
         "steps": [{"step": "pick", "duration": 3.0 + 0.1 * (i % 5)}],
         "anomalies": []}
        for i in range(12)
    ])
    r = client.get(f"/processes/{pid}/statistics")
    assert r.status_code == 200
    body = r.json()
    assert body["cycles_by_status"] == {"complete": 12}
    assert body["cycle_time"]["n"] == 12
    assert body["cycle_time"]["median_ci95"]
    assert body["step_time"]["pick"]["median"] == pytest.approx(3.2, abs=0.2)

    r = client.get(f"/batches/{batch['id']}/cycles")
    assert len(r.json()) == 12
