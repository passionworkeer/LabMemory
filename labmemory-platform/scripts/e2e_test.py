"""端到端测试：模拟飞书 MeetingPackage + CandidatePackage 推送，并走完整链路。

可独立运行（启动服务后）：
    conda run -n labmemory python -m scripts.e2e_test

也可作为 pytest 的内核（被 tests/test_e2e.py 复用）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx


BASE_URL = "http://127.0.0.1:8081"


def _platform_api_key() -> str:
    """与被测服务同源取密钥：优先 app.config.settings（读 .env / 环境变量），
    兜底 dev 默认值——生产环境已轮换密钥后硬编码默认值会被 403 拒绝。"""
    try:
        from app.config import settings

        return settings.PLATFORM_API_KEY
    except Exception:
        return "dev-platform-api-key-please-rotate"


PLATFORM_API_KEY = _platform_api_key()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers_platform() -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {PLATFORM_API_KEY}"}


def _headers_user(token: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def login(client, username: str, password: str = "123456") -> str:
    """client 可以是 httpx.Client 或 fastapi TestClient。"""
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def push_meeting(client, experiment_id: str, meeting_id: str) -> dict:
    """模拟飞书 MeetingPackage。"""
    payload = {
        "schema_version": "1.0.0",
        "source": "feishu_minutes",
        "source_object_id": f"minute_{meeting_id}",
        "meeting_id": meeting_id,
        "title": f"Compound-A 复验讨论（{meeting_id}）",
        "start_time": _now_iso(),
        "end_time": _now_iso(),
        "organizer": "陈博士",
        "participants": ["陈博士", "王工程师", "李实验员"],
        "content": {
            "transcript": [
                {"speaker": "陈博士", "start_offset_sec": 10, "end_offset_sec": 18, "text": "复现实验确认 70 度收率更高"},
                {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 30, "text": "建议温度参数从 80 调整为 70"},
                {"speaker": "李实验员", "start_offset_sec": 35, "end_offset_sec": 45, "text": "副产物从 4 升到 9 需要关注"},
            ],
            "summary": "讨论 Compound-A 温度参数从 80℃ 调整为 70℃",
            "action_items": ["更新温度参数", "关注副产物边界"],
        },
        "source_url": f"https://example.feishu.cn/minutes/{meeting_id}",
        "captured_at": _now_iso(),
        "metadata": {"experiment_id": experiment_id, "project_id": "PROJ-DEMO-001"},
    }
    r = client.post("/api/v1/meetings", json=payload, headers=_headers_platform())
    r.raise_for_status()
    return r.json()


def push_candidate(client, meeting_id: str) -> dict:
    """模拟 Aily CandidatePackage。"""
    payload = {
        "schema_version": "1.0.0",
        "source_package_id": meeting_id,
        "aily_skill_version": "skill-v1.2.0",
        "model_version": "qwen-max-2026-07",
        "prompt_version": "v3",
        "candidates": [
            {
                "candidate_id": f"cand_{meeting_id}_1",
                "type": "parameter_change",
                "title": "温度参数调整 80℃ -> 70℃",
                "description": "复现实验显示 70℃ 收率优于 80℃",
                "experiment_ref": "EXP-DEMO-001",
                "scope": {"material": "Compound-A", "catalyst": "B"},
                "parameters": [
                    {"name": "temperature", "value": "70", "unit": "℃"},
                    {"name": "concentration", "value": "0.20", "unit": "mol/L"},
                    {"name": "time", "value": "2", "unit": "h"},
                ],
                "confidence": 0.92,
                "evidence": [
                    {"speaker": "陈博士", "text": "复现实验确认 70 度收率更高", "start_offset_sec": 10, "end_offset_sec": 18},
                    {"speaker": "王工程师", "text": "建议温度参数从 80 调整为 70", "start_offset_sec": 20, "end_offset_sec": 30},
                ],
                "status": "pending_review",
                "needs_review": True,
            },
            {
                "candidate_id": f"cand_{meeting_id}_2",
                "type": "risk",
                "title": "副产物边界风险",
                "description": "升温可能使副产物升高",
                "confidence": 0.7,
                "evidence": [{"speaker": "李实验员", "text": "副产物从 4 升到 9 需要关注"}],
                "status": "candidate",
            },
        ],
        "risks": [{"title": "副产物边界", "severity": "medium"}],
        "action_items": [],
        "open_questions": [],
        "compiled_at": _now_iso(),
    }
    r = client.post("/api/v1/candidates", json=payload, headers=_headers_platform())
    r.raise_for_status()
    return r.json()


def run_e2e(
    base_url: str = BASE_URL,
    transport_client: Any | None = None,
) -> dict:
    """跑完整链路。

    transport_client：可选的 HTTP 客户端（httpx.Client 或 fastapi.TestClient）。
    若为 None 则新建 httpx.Client 连接真实服务。
    """
    result: dict[str, Any] = {"steps": [], "ok": False}
    owns_client = transport_client is None
    client = transport_client or httpx.Client(base_url=base_url, timeout=30.0)
    try:
        # 1. 健康检查
        h = client.get("/health")
        h.raise_for_status()
        result["steps"].append({"step": "health", "status": h.json()["status"]})

        # 2. 三角色登录
        pi_token = login(client, "pi")
        lead_token = login(client, "lead")
        executor_token = login(client, "executor")
        result["steps"].append({
            "step": "login",
            "pi": bool(pi_token), "lead": bool(lead_token), "executor": bool(executor_token),
        })

        meeting_id = f"meet_{uuid.uuid4().hex[:12]}"
        experiment_id = "EXP-DEMO-001"

        # 3. 推送会议 + 候选（模拟飞书侧）
        m = push_meeting(client, experiment_id, meeting_id)
        c = push_candidate(client, meeting_id)
        result["steps"].append({
            "step": "ingest",
            "meeting_created": m.get("created"),
            "candidate_created": c.get("created"),
        })

        # 4. 复核：执行人修改后确认（把 concentration 改为 0.25）
        mods = {
            "parameters": [
                {"name": "temperature", "value": "70", "unit": "℃"},
                {"name": "concentration", "value": "0.25", "unit": "mol/L"},
                {"name": "time", "value": "2", "unit": "h"},
            ],
            "scope": {"material": "Compound-A", "catalyst": "B"},
        }
        r = client.post(
            f"/api/meetings/{meeting_id}/review",
            json={"decision": "confirmed", "modifications": mods, "notes": "浓度由 0.20 调整为 0.25"},
            headers=_headers_user(executor_token),
        )
        r.raise_for_status()
        chain = r.json()
        assert chain["review"]["decision"] == "confirmed"
        assert chain["claim"], "确认后应生成主张"
        assert chain["task"], "确认后应生成任务草稿"
        task_id = chain["task"]["task_id"]
        result["steps"].append({
            "step": "review.confirm",
            "claim_id": chain["claim"]["claim_id"],
            "task_id": task_id,
        })

        # 5. 行动审计（PI 触发）-> 首次审计返回 needs_confirmation（审批+资源未就绪）
        r = client.post(f"/api/tasks/{task_id}/audit", headers=_headers_user(pi_token))
        r.raise_for_status()
        audit = r.json()
        assert audit["status"] == "needs_confirmation", f"首次审计应需确认：{audit}"
        result["steps"].append({"step": "audit.first", "status": audit["status"]})

        # 5a. PI 审批通过
        r = client.post(
            f"/api/tasks/{task_id}/approve",
            json={"note": "方案已评审，可执行"},
            headers=_headers_user(pi_token),
        )
        r.raise_for_status()
        assert r.json()["approval_status"] == "approved"
        result["steps"].append({"step": "task.approve", "approval_status": "approved"})

        # 5b. 执行人补充资源
        r = client.put(
            f"/api/tasks/{task_id}/resources",
            json={
                "materials": [{"name": "Compound-A", "amount": "500g"}],
                "equipment": [{"name": "反应釜A", "status": "可用"}],
                "assignee_username": "executor",
                "note": "物料设备已就位",
            },
            headers=_headers_user(executor_token),
        )
        r.raise_for_status()
        assert r.json()["resource_status"] == "ready"
        result["steps"].append({"step": "task.resources", "resource_status": "ready"})

        # 5b.2 确认知晓历史失败边界（seed 数据含 65℃ 未解决失败边界）
        r = client.post(
            f"/api/tasks/{task_id}/ack-failure-boundary",
            headers=_headers_user(executor_token),
        )
        r.raise_for_status()
        assert r.json()["failure_boundary_ack"] is True
        result["steps"].append({"step": "task.ack_failure_boundary", "acked": True})

        # 5c. 重新审计 -> passed
        r = client.post(f"/api/tasks/{task_id}/audit", headers=_headers_user(pi_token))
        r.raise_for_status()
        audit = r.json()
        assert audit["status"] == "passed", f"补充后审计应通过：{audit}"
        result["steps"].append({"step": "audit", "status": audit["status"]})

        # 6. 启动任务（执行人启动）
        r = client.post(
            f"/api/tasks/{task_id}/start",
            json={"assignee_username": "executor"},
            headers=_headers_user(executor_token),
        )
        r.raise_for_status()
        assert r.json()["status"] == "running"
        result["steps"].append({"step": "task.start", "status": "running"})

        # 7. 提交结果（执行人提交，提交即完成任务，无需单独标记完成）
        r = client.post(
            f"/api/tasks/{task_id}/results",
            json={
                "actual_params": {"temperature": "70", "concentration": "0.25", "time": "2"},
                "metrics": {"conversion": "78%", "byproduct": "9%"},
                "notes": "升温后转化率提升但副产物升高",
            },
            headers=_headers_user(executor_token),
        )
        r.raise_for_status()
        result_id = r.json()["result_id"]
        assert r.json()["status"] == "submitted"
        result["steps"].append({"step": "result.submit", "result_id": result_id})

        # 9. 发布知识（PI 发布，更新主张状态为 partially_supported）
        r = client.post(
            f"/api/results/{result_id}/publish",
            json={"knowledge_status": "partially_supported", "notes": "支持升温正向但副产物边界需关注"},
            headers=_headers_user(pi_token),
        )
        r.raise_for_status()
        assert r.json()["status"] == "published"
        result["steps"].append({"step": "result.publish", "knowledge_status": "partially_supported"})

        # 10. 实验护照：验证完整链路
        r = client.get(f"/api/experiments/{experiment_id}/passport", headers=_headers_user(pi_token))
        r.raise_for_status()
        passport = r.json()
        assert any(m["meeting_id"] == meeting_id for m in passport["meetings"]), "护照应包含本次会议"
        assert passport["current_claim"], "护照应有当前主张"
        assert passport["current_claim"]["knowledge_status"] == "partially_supported"
        assert passport["timeline"], "护照应有时间线"
        result["steps"].append({
            "step": "passport",
            "meetings": len(passport["meetings"]),
            "timeline_events": len(passport["timeline"]),
            "current_claim_status": passport["current_claim"]["status"],
            "current_claim_knowledge_status": passport["current_claim"]["knowledge_status"],
        })

        # 11. 权限校验：执行人尝试发布知识应被拒（403 或 409 已发布）
        try:
            r = client.post(
                f"/api/results/{result_id}/publish",
                json={"knowledge_status": "supported"},
                headers=_headers_user(executor_token),
            )
            permission_blocked = r.status_code in (403, 409)
        except Exception:
            permission_blocked = True
        result["steps"].append({"step": "permission.executor_cannot_publish", "blocked": permission_blocked})

        # 12. 第二次会议：验证旧主张被 superseded
        meeting_id_2 = f"meet_{uuid.uuid4().hex[:12]}"
        push_meeting(client, experiment_id, meeting_id_2)
        push_candidate(client, meeting_id_2)
        r = client.post(
            f"/api/meetings/{meeting_id_2}/review",
            json={"decision": "confirmed", "modifications": {
                # 温度值变更（70→72）：验证经复核确认的值变更走 supersede+升版，
                # 而非被数值冲突冻结（change refine-numeric-conflict-supersede）
                "parameters": [
                    {"name": "temperature", "value": "72", "unit": "℃"},
                    {"name": "concentration", "value": "0.25", "unit": "mol/L"},
                    {"name": "time", "value": "2", "unit": "h"},
                ],
                "scope": {"material": "Compound-A", "catalyst": "B"},
            }},
            headers=_headers_user(lead_token),
        )
        r.raise_for_status()
        chain2 = r.json()
        assert chain2["claim"]["status"] == "current", (
            f"值变更应经复核确认 supersede 为 current，而非被数值冲突冻结：{chain2['claim']}"
        )
        result["steps"].append({
            "step": "second_meeting",
            "new_claim_id": chain2["claim"]["claim_id"],
            "new_claim_status": chain2["claim"]["status"],
            "replaces": chain2["claim"]["replaces_claim_id"],
        })

        # 重新加载护照验证链路
        r = client.get(f"/api/experiments/{experiment_id}/passport", headers=_headers_user(pi_token))
        r.raise_for_status()
        passport2 = r.json()
        assert len(passport2["meetings"]) >= 2, "护照应包含两次会议"
        result["steps"].append({
            "step": "passport_after_second",
            "meetings": len(passport2["meetings"]),
            "current_claim_status": passport2["current_claim"]["status"],
            "current_claim_knowledge_status": passport2["current_claim"]["knowledge_status"],
        })

        # 13. 仅 PI 可访问实验管理
        r = client.get("/api/experiments", headers=_headers_user(executor_token))
        pi_only_ok = r.status_code == 403
        result["steps"].append({"step": "permission.pi_only_experiments", "blocked": pi_only_ok})

        result["ok"] = True
    finally:
        if owns_client:
            client.close()
    return result


def main() -> None:
    print(f"开始 E2E 测试，目标：{BASE_URL}")
    result = run_e2e()
    for s in result["steps"]:
        print(f"  ✓ {s['step']}: {json.dumps({k: v for k, v in s.items() if k != 'step'}, ensure_ascii=False)}")
    print(f"\n{'✓' if result['ok'] else '✗'} E2E 测试{'通过' if result['ok'] else '失败'}")


if __name__ == "__main__":
    main()
