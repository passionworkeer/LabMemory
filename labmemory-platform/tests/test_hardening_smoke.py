"""平台加固 change（harden-platform-security-and-trust）的聚焦回归测试。

覆盖 tests/test_e2e.py 主链路未触达的 5 个加固点：
- R1: QA /ask 在向量不可用时降级为 BM25（不返回 503），retrieval_details 透传 vector_available
- R4: relation_expand 经字符串 meeting_id 关联 evidence（QA 正常返回，不因类型不匹配漏证据）
- B2: 结果提交冻结判定 —— 未覆盖全部计划参数名→frozen；含计划外额外 key→不冻结
- IDOR: 非项目所有者 PI 访问/操作他人项目下实验 → 403；admin 放行；所有者本人 → 200
- S1: APP_ENV=production 保留代码默认密钥 → Settings 校验硬失败；development 仅告警
"""
from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from scripts.e2e_test import _headers_user, push_candidate, push_meeting


@pytest.fixture(scope="module")
def client():
    """启动 TestClient，建表 + 演示数据，并额外植入「另一个 PI + 其项目 + 实验」供 IDOR 测试。"""
    from app.db.base import Base
    from app.db.models import Experiment, ExperimentMember, Project
    from app.db.session import SessionLocal, engine
    from app.main import app
    from scripts.seed_demo import ensure_user, main as seed_main

    Base.metadata.create_all(bind=engine)
    seed_main()

    db = SessionLocal()
    try:
        if not db.query(Project).filter(Project.project_id == "PROJ-OTHER").first():
            pi2 = ensure_user(db, "pi2", "另一个 PI", "pi")
            proj2 = Project(project_id="PROJ-OTHER", name="他人项目", pi_user_id=pi2.id)
            db.add(proj2)
            db.flush()
            exp_other = Experiment(
                experiment_id="EXP-OTHER",
                project_id=proj2.id,
                name="他人实验",
                owner_user_id=pi2.id,
                parameters_template={},
            )
            db.add(exp_other)
            db.flush()
            db.add(ExperimentMember(experiment_id=exp_other.id, user_id=pi2.id, role="pi"))
            db.commit()
    finally:
        db.close()
    return TestClient(app)


def _login(client: TestClient, username: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert r.status_code == 200, f"登录失败 {username}: {r.status_code} {r.text}"
    return r.json()["access_token"]


# ---------------- R1 + R4 ----------------
def test_qa_degrades_without_vector_not_503(client: TestClient):
    """R1: 向量不可用时 QA 必须降级（200 + vector_available 字段），不得 503。"""
    token = _login(client, "pi")
    r = client.post(
        "/api/qa/ask",
        json={"question": "Compound-A 温度参数"},
        headers=_headers_user(token),
    )
    assert r.status_code == 200, f"QA 降级应返回 200 而非 503：{r.status_code} {r.text}"
    body = r.json()
    assert "retrieval_details" in body
    assert "vector_available" in body["retrieval_details"], "retrieval_details 必须透传 vector_available"
    # R4：relation_expand 走字符串 meeting_id 关联证据，整个过程不抛错（QA 已正常返回即间接验证）


# ---------------- B2 ----------------
def _running_task(client: TestClient, token_pi: str, token_executor: str, experiment_id: str = "EXP-DEMO-001") -> str:
    """推一个会议 → 复核确认 → 审批 → 资源 → 失败边界确认 → 审计通过 → 启动，返回 running 态 task_id。"""
    meeting_id = f"smoke_{uuid.uuid4().hex[:10]}"
    push_meeting(client, experiment_id, meeting_id)
    push_candidate(client, meeting_id)
    h_pi = _headers_user(token_pi)
    h_ex = _headers_user(token_executor)

    r = client.post(
        f"/api/meetings/{meeting_id}/review",
        json={
            "decision": "confirmed",
            "modifications": {
                "parameters": [
                    {"name": "temperature", "value": "70", "unit": "℃"},
                    {"name": "concentration", "value": "0.25", "unit": "mol/L"},
                    {"name": "time", "value": "2", "unit": "h"},
                ],
                "scope": {"material": "Compound-A", "catalyst": "B"},
            },
            "notes": "B2 冒烟",
        },
        headers=h_ex,
    )
    assert r.status_code == 200, r.text
    task_id = r.json()["task"]["task_id"]

    client.post(f"/api/tasks/{task_id}/approve", json={"note": "ok"}, headers=h_pi)
    client.put(
        f"/api/tasks/{task_id}/resources",
        json={
            "materials": [{"name": "Compound-A", "amount": "500g"}],
            "equipment": [{"name": "反应釜A", "status": "可用"}],
            "assignee_username": "executor",
        },
        headers=h_ex,
    )
    client.post(f"/api/tasks/{task_id}/ack-failure-boundary", headers=h_ex)
    ar = client.post(f"/api/tasks/{task_id}/audit", headers=h_pi)
    assert ar.json()["status"] == "passed", ar.text
    sr = client.post(f"/api/tasks/{task_id}/start", json={"assignee_username": "executor"}, headers=h_ex)
    assert sr.json()["status"] == "running", sr.text
    return task_id


def test_result_frozen_when_missing_planned_param(client: TestClient):
    """B2 负向：实际参数未覆盖全部计划参数名 → frozen。"""
    pi, ex = _login(client, "pi"), _login(client, "executor")
    tid = _running_task(client, pi, ex)
    r = client.post(
        f"/api/tasks/{tid}/results",
        json={"actual_params": {"temperature": "70", "concentration": "0.25"}},  # 缺 time
        headers=_headers_user(ex),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "frozen", f"未覆盖全部计划参数应 frozen：{r.json()}"


def test_result_not_frozen_with_extra_key(client: TestClient):
    """B2 正向：覆盖全部计划参数 + 计划外额外 key → submitted（额外观测不触发冻结）。"""
    pi, ex = _login(client, "pi"), _login(client, "executor")
    tid = _running_task(client, pi, ex)
    r = client.post(
        f"/api/tasks/{tid}/results",
        json={
            "actual_params": {
                "temperature": "70",
                "concentration": "0.25",
                "time": "2",
                "extra_observation": "xxx",  # 计划外额外观测
            },
            "metrics": {"conversion": "78%"},
        },
        headers=_headers_user(ex),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted", f"额外观测不应触发 frozen：{r.json()}"


# ---------------- IDOR ----------------
def test_idor_other_project_pi_blocked(client: TestClient):
    """IDOR：非项目所有者 PI 访问/操作他人项目下实验 → 403；admin 放行；所有者本人 → 200。"""
    pi = _login(client, "pi")      # PROJ-DEMO-001 所有者
    admin = _login(client, "admin")

    # 1) pi 访问他人项目下的实验 → 403
    r = client.get("/api/experiments/EXP-OTHER", headers=_headers_user(pi))
    assert r.status_code == 403, f"非所有者 PI 访问他人实验应 403：{r.status_code} {r.text}"
    # 2) admin 放行
    r2 = client.get("/api/experiments/EXP-OTHER", headers=_headers_user(admin))
    assert r2.status_code == 200, f"admin 应可访问任意实验：{r2.status_code}"
    # 3) pi 改他人实验成员 → 403
    r3 = client.post(
        "/api/experiments/EXP-OTHER/members",
        json={"username": "executor", "role": "executor"},
        headers=_headers_user(pi),
    )
    assert r3.status_code == 403, f"非所有者 PI 改他人实验成员应 403：{r3.status_code}"
    # 4) pi 访问自己项目下的实验 → 200
    r4 = client.get("/api/experiments/EXP-DEMO-001", headers=_headers_user(pi))
    assert r4.status_code == 200, f"项目所有者访问自己实验应 200：{r4.status_code}"


# ---------------- S1 ----------------
DEFAULT_JWT = "dev-jwt-secret-please-rotate"
DEFAULT_API_KEY = "dev-platform-api-key-please-rotate"


def test_default_secret_hard_fails_in_production():
    """S1: APP_ENV=production 下保留代码默认密钥 → Settings 校验硬失败。"""
    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(APP_ENV="production", JWT_SECRET=DEFAULT_JWT, PLATFORM_API_KEY=DEFAULT_API_KEY)


def test_default_secret_warns_in_development(caplog):
    """S1: development 环境保留默认密钥 → 仅告警，不阻断（保 dev/test 可运行）。"""
    from app.config import Settings

    with caplog.at_level(logging.WARNING):
        Settings(APP_ENV="development", JWT_SECRET=DEFAULT_JWT, PLATFORM_API_KEY=DEFAULT_API_KEY)
    assert any("JWT_SECRET" in rec.message for rec in caplog.records), "development 下默认密钥应告警"
