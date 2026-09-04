"""UUAP 飞书免登 + 自动注册 + 管理员用户管理 测试。

覆盖：
1. 登录页初始化（mock 模式）
2. 新用户飞书登录自动注册（默认 viewer 最低权限）
3. 同一飞书用户重复登录不重复注册
4. viewer 默认不可见任何实验；不能做业务操作
5. 管理员用户列表 / 角色调整 / 可见实验范围增删
6. 非 admin 访问用户管理被拒；admin 不能自降级
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    """TestClient + in-memory SQLite + 演示数据（与 test_e2e 同构）。"""
    from app.db.base import Base
    from app.db.session import engine
    from app.main import app

    Base.metadata.create_all(bind=engine)
    from scripts.seed_demo import main as seed_main
    seed_main()
    return TestClient(app)


def test_feishu_authorize_init(client: TestClient):
    r = client.get("/api/auth/feishu/authorize")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "mock"
    assert d["mock_enabled"] is True
    assert d["password_login_enabled"] is True


def test_auto_register_viewer(client: TestClient):
    r = client.post(
        "/api/auth/feishu/mock-login",
        json={"user_key": "zhangsan", "display_name": "张三"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["global_role"] == "viewer"          # 默认最低权限
    assert d["user"]["source"] == "feishu_auto"          # 自动注册
    assert d["user"]["username"].startswith("fs_")
    token = d["access_token"]

    # 同一飞书用户重复登录 -> 复用同一账号，不重复注册
    r2 = client.post("/api/auth/feishu/mock-login", json={"user_key": "zhangsan"})
    assert r2.status_code == 200
    assert r2.json()["user"]["id"] == d["user"]["id"]

    # viewer 无成员关系 -> 默认不可见任何实验
    assert client.get("/api/passports", headers=_h(token)).json() == []

    # viewer 不能执行业务操作（复核被 require_member 拦截）
    r3 = client.post(
        "/api/meetings/meet_demo_65c/review",
        headers=_h(token),
        json={"decision": "confirmed", "modifications": {}},
    )
    assert r3.status_code == 403


def test_admin_user_management(client: TestClient):
    admin_token = client.post(
        "/api/auth/login", json={"username": "admin", "password": "123456"}
    ).json()["access_token"]
    AH = _h(admin_token)

    users = client.get("/api/admin/users", headers=AH).json()
    fs_user = next(u for u in users if u["source"] == "feishu_auto")
    uid = fs_user["id"]

    # 非 admin 访问用户管理 -> 403
    viewer_token = client.post(
        "/api/auth/feishu/mock-login", json={"user_key": "lisi"}
    ).json()["access_token"]
    assert client.get("/api/admin/users", headers=_h(viewer_token)).status_code == 403

    # 提权 viewer -> executor
    r = client.patch(f"/api/admin/users/{uid}", headers=AH, json={"global_role": "executor"})
    assert r.status_code == 200
    assert r.json()["global_role"] == "executor"

    # 添加实验成员 -> 可见范围扩大
    r = client.post(
        f"/api/admin/users/{uid}/members",
        headers=AH,
        json={"experiment_id": "EXP-DEMO-001", "role": "viewer"},
    )
    assert r.status_code == 200
    assert r.json()["experiment_count"] == 1
    assert r.json()["members"][0]["experiment_id"] == "EXP-DEMO-001"

    # admin 不能移除自己的管理员角色（避免锁死）
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    r = client.patch(f"/api/admin/users/{admin_id}", headers=AH, json={"global_role": "viewer"})
    assert r.status_code == 403

    # 移除成员 -> 范围收回
    r = client.delete(f"/api/admin/users/{uid}/members/EXP-DEMO-001", headers=AH)
    assert r.status_code == 200
    assert r.json()["experiment_count"] == 0
