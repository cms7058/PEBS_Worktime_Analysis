"""鉴权与用户管理测试（绕过中间件，直接验 auth.py 逻辑 + 端点）."""
import pathlib

import pytest
from fastapi.testclient import TestClient

from server import auth, db as dbmod
from server.app import app, get_db

CONFIG_YAML = (pathlib.Path(__file__).parent.parent
               / "configs" / "example_process.yaml").read_text()


@pytest.fixture()
def client(tmp_path):
    conn = dbmod.connect(tmp_path / "auth.db")
    auth.init(conn)
    app.dependency_overrides[get_db] = lambda: (yield conn)
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_password_hash_roundtrip():
    h = auth.hash_password("mypw")
    assert auth.verify_password("mypw", h)
    assert not auth.verify_password("wrong", h)


def test_login_logout(client):
    # 默认管理员
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin"
    token = body["token"]

    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401

    # 注销
    r = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_user_crud_via_api(client, tmp_path):
    """通过直接调用 auth 模块完成用户管理路径（中间件已禁用）."""
    conn = next(iter(app.dependency_overrides.values()))().__next__()
    user = auth.create_user(conn, "alice", "secret", role="user")
    assert user["username"] == "alice" and user["role"] == "user"
    assert any(u["username"] == "alice" for u in auth.list_users(conn))

    auth.set_password(conn, user["id"], "newpw")
    assert auth.login(conn, "alice", "newpw") is not None
    assert auth.login(conn, "alice", "secret") is None

    auth.set_role(conn, user["id"], "admin")
    assert auth.get_user(conn, user["id"])["role"] == "admin"

    assert auth.delete_user(conn, user["id"]) is True
    assert auth.get_user(conn, user["id"]) is None


def test_check_token_expiry_resilience(client):
    conn = next(iter(app.dependency_overrides.values()))().__next__()
    assert auth.check_token(conn, "") is None
    assert auth.check_token(conn, "nonsense") is None
    session = auth.login(conn, "admin", "admin123")
    assert auth.check_token(conn, session["token"])["username"] == "admin"
