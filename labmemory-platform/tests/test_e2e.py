"""端到端测试。

启动一个 TestClient 跑完整链路，验证：
1. 三角色都能登录、操作复核 / 审计 / 启动 / 提交结果
2. 仅 PI/Lead 可发布知识（执行人被拦截）
3. 仅 PI 可访问实验管理
4. 一个会议最终形成一个任务，确认后生成主张（含参数版本）
5. 多次会议：新主张 supersede 旧主张
6. 实验护照按会议 ID 组织数据链，按实验 ID 组织时间线
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """启动 TestClient，初始化 in-memory SQLite + 演示数据。"""
    from app.db.base import Base
    from app.db.session import engine
    from app.main import app

    Base.metadata.create_all(bind=engine)
    from scripts.seed_demo import main as seed_main
    seed_main()
    return TestClient(app)


def test_e2e_full_chain(client):
    """完整端到端：从飞书推会议到结果发布知识 + 护照验证。"""
    from scripts.e2e_test import run_e2e
    result = run_e2e(base_url="http://testserver", transport_client=client)
    assert result["ok"], f"E2E 失败：{result['steps']}"

    steps = {s["step"]: s for s in result["steps"]}
    assert steps["review.confirm"]["claim_id"], "应生成主张"
    assert steps["audit"]["status"] == "passed"
    assert steps["passport"]["current_claim_knowledge_status"] == "partially_supported"
    assert steps["permission.executor_cannot_publish"]["blocked"] is True
    assert steps["second_meeting"]["replaces"] is not None, "新主张应 supersede 旧主张"
    assert steps["passport_after_second"]["meetings"] >= 2
