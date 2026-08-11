"""模拟飞书编排器推送会议 + 候选包。

通过 /v1/* 集成接口注入数据，完整走通 feishu-orchestrator → platform 的真实链路，
而不是直接写数据库。这样可以端到端验证复核、审计、结果回流等全流程。

使用方式：
    # 1. 先启动后端服务
    conda run -n labmemory uvicorn app.main:app --port 8081 --reload

    # 2. 推送单条会议 + 候选
    python -m scripts.mock_feishu_push single

    # 3. 推送完整演示场景（3 个会议 + 候选）
    python -m scripts.mock_feishu_push demo

    # 自定义 base url / api key
    python -m scripts.mock_feishu_push demo --base-url http://localhost:8081 --api-key dev-platform-api-key-please-rotate
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from urllib import error, request

from app.config import settings

DEFAULT_BASE_URL = "http://localhost:8081"


def _post(path: str, payload: dict, base_url: str, api_key: str) -> dict:
    """带 x-platform-api-key 鉴权的 POST。"""
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ✗ POST {path} -> {e.code}: {body}", file=sys.stderr)
        raise


# === 演示场景构建 ===

def _now_iso(delta: timedelta | None = None) -> str:
    t = datetime.now(timezone.utc)
    if delta:
        t += delta
    return t.isoformat()


def build_meeting_payload(
    meeting_id: str,
    title: str,
    experiment_id: str,
    transcript: list[dict],
    captured_delta: timedelta | None = None,
    source: str = "feishu_minutes",
) -> dict:
    """构造 MeetingPackage payload（对齐契约 meeting-package.schema.json）。"""
    return {
        "schema_version": "1.0.0",
        "source": source,
        "source_object_id": f"minutes_{meeting_id}",
        "meeting_id": meeting_id,
        "title": title,
        "start_time": _now_iso(captured_delta),
        "end_time": _now_iso(captured_delta + timedelta(minutes=45) if captured_delta else timedelta(minutes=45)),
        "organizer": "陈博士",
        "participants": ["陈博士", "王工程师", "孙研究员"],
        "content": {
            "transcript": transcript,
            "summary": title,
        },
        "source_url": f"https://feishu.example.com/minutes/{meeting_id}",
        "captured_at": _now_iso(captured_delta),
        "metadata": {
            "experiment_id": experiment_id,
            "project_id": "PROJ-DEMO-001",
            "source": "feishu_mock",
        },
    }


def build_candidate_payload(
    source_package_id: str,
    candidates: list[dict],
    risks: list[dict] | None = None,
    open_questions: list[str] | None = None,
) -> dict:
    """构造 CandidatePackage payload（对齐契约 candidate-package.schema.json）。"""
    return {
        "schema_version": "1.0.0",
        "source_package_id": source_package_id,
        "aily_skill_version": "aily-labmemory-v1.0",
        "model_version": "aily-pro-2026-07",
        "prompt_version": "labmemory-decision-v3",
        "candidates": candidates,
        "risks": risks or [],
        "action_items": [],
        "open_questions": open_questions or [],
        "compiled_at": _now_iso(),
        "raw_output": None,
    }


# === 具体场景 ===

def push_single(base_url: str, api_key: str) -> None:
    """推送一条最简单的待复核会议。"""
    mid = f"meet_demo_{int(datetime.now().timestamp())}"
    payload = build_meeting_payload(
        meeting_id=mid,
        title="Demo 测试会议",
        experiment_id="EXP-DEMO-001",
        transcript=[
            {
                "speaker": "张三",
                "start_offset_sec": 0,
                "end_offset_sec": 15,
                "text": "今天讨论一下反应参数是否需要调整",
            },
            {
                "speaker": "李四",
                "start_offset_sec": 20,
                "end_offset_sec": 35,
                "text": "建议温度从 70 调到 75 度，收率可能更好",
            },
        ],
    )
    print(f"→ 推送会议 {mid}")
    result = _post("/api/v1/meetings", payload, base_url, api_key)
    print(f"  ✓ created={result.get('created')}")

    cand = build_candidate_payload(
        source_package_id=mid,
        candidates=[
            {
                "candidate_id": "CDR-demo-001",
                "type": "parameter_change",
                "title": "温度 70→75℃ 调整",
                "description": "提升收率",
                "experiment_ref": "EXP-DEMO-001",
                "parameters": [
                    {"name": "temperature", "value": "75", "unit": "℃"},
                    {"name": "time", "value": "2", "unit": "h"},
                ],
                "confidence": 0.85,
                "evidence": [
                    {"speaker": "李四", "text": "建议温度从 70 调到 75 度，收率可能更好", "start_offset_sec": 20},
                ],
                "status": "pending_review",
                "needs_review": True,
            },
        ],
        open_questions=["75℃ 下副产物是否可控？"],
    )
    print("→ 推送候选包")
    result = _post("/api/v1/candidates", cand, base_url, api_key)
    print(f"  ✓ created={result.get('created')}")
    print()
    print(f"完成！会议 ID: {mid}")
    print(f"  前往「会后复核」可看到这条待复核会议。")


def push_demo_scenarios(base_url: str, api_key: str) -> None:
    """推送完整演示场景：3 个会议，覆盖不同链路状态。

    场景 1 - 历史已完成链（供实验护照展示）
    场景 2 - 80℃ 旧主张（会被场景 3 覆盖，其任务会被审计阻断）
    场景 3 - 70℃ 复现实验（current 主张）
    场景 4 - 待复核会议（催化剂 0.8 eq 复验）
    """
    print("=== 推送演示场景 ===\n")

    # 场景 1：已完成的 65℃ 实验（2 天前）
    print("[1/4] 已完成实验链（65℃，含失败边界卡）")
    m1_id = "meet_demo_completed_65c"
    m1 = build_meeting_payload(
        meeting_id=m1_id,
        title="Compound-A 60→65℃ 升温评审",
        experiment_id="EXP-DEMO-001",
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 10, "end_offset_sec": 18,
             "text": "上一轮 60℃ 转化率只有 63%，建议升到 65℃"},
            {"speaker": "赵负责人", "start_offset_sec": 20, "end_offset_sec": 30,
             "text": "同意，验收看转化率≥75%且副产物≤6%"},
        ],
        captured_delta=timedelta(days=-2),
    )
    _post("/api/v1/meetings", m1, base_url, api_key)
    cand1 = build_candidate_payload(
        source_package_id=m1_id,
        candidates=[{
            "candidate_id": "CDR-65c-001",
            "type": "parameter_change",
            "title": "温度 60→65℃ 升温",
            "description": "提升转化率",
            "experiment_ref": "EXP-DEMO-001",
            "parameters": [
                {"name": "temperature", "value": "65", "unit": "℃"},
                {"name": "time", "value": "2", "unit": "h"},
                {"name": "catalyst", "value": "1.0", "unit": "eq"},
            ],
            "confidence": 0.9,
            "evidence": [
                {"speaker": "陈工", "text": "上一轮 60℃ 转化率只有 63%，建议升到 65℃", "start_offset_sec": 10},
            ],
            "status": "pending_review",
            "needs_review": True,
        }],
    )
    _post("/api/v1/candidates", cand1, base_url, api_key)
    print("  ✓ 推送完成")

    # 场景 2：80℃ 暂定参数（1 天前）
    print("[2/4] 80℃ 暂定参数（后续会被阻断）")
    m2_id = "meet_demo_80c"
    m2 = build_meeting_payload(
        meeting_id=m2_id,
        title="Compound-A 80℃ 暂定参数评审",
        experiment_id="EXP-DEMO-001",
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 5, "end_offset_sec": 15,
             "text": "暂定尝试 80℃ 看看反应极限"},
            {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 25,
             "text": "可以先做一轮预实验"},
        ],
        captured_delta=timedelta(days=-1),
    )
    _post("/api/v1/meetings", m2, base_url, api_key)
    cand2 = build_candidate_payload(
        source_package_id=m2_id,
        candidates=[{
            "candidate_id": "CDR-80c-001",
            "type": "parameter_change",
            "title": "温度 80℃ 暂定",
            "description": "试探反应极限",
            "experiment_ref": "EXP-DEMO-001",
            "parameters": [
                {"name": "temperature", "value": "80", "unit": "℃"},
                {"name": "time", "value": "2", "unit": "h"},
            ],
            "confidence": 0.75,
            "evidence": [
                {"speaker": "陈工", "text": "暂定尝试 80℃ 看看反应极限", "start_offset_sec": 5},
            ],
            "status": "pending_review",
            "needs_review": True,
        }],
        risks=[{"type": "safety", "description": "高温可能导致副反应增加"}],
    )
    _post("/api/v1/candidates", cand2, base_url, api_key)
    print("  ✓ 推送完成")

    # 场景 3：70℃ 复现实验（2 小时前）
    print("[3/4] 70℃ 复现实验（current 主张，将覆盖 80℃）")
    m3_id = "meet_demo_70c"
    m3 = build_meeting_payload(
        meeting_id=m3_id,
        title="Compound-A 70℃ 复现实验评审",
        experiment_id="EXP-DEMO-001",
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 10, "end_offset_sec": 18,
             "text": "复现实验确认 70℃ 收率更高"},
            {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 30,
             "text": "建议温度参数从 80 调整为 70"},
            {"speaker": "孙研究员", "start_offset_sec": 35, "end_offset_sec": 42,
             "text": "浓度也需要确认，0.20 mol/L 比较合适"},
        ],
        captured_delta=timedelta(hours=-2),
    )
    _post("/api/v1/meetings", m3, base_url, api_key)
    cand3 = build_candidate_payload(
        source_package_id=m3_id,
        candidates=[{
            "candidate_id": "CDR-70c-001",
            "type": "parameter_change",
            "title": "温度 70℃ 复现",
            "description": "70℃ 收率优于 80℃",
            "experiment_ref": "EXP-DEMO-001",
            "parameters": [
                {"name": "temperature", "value": "70", "unit": "℃"},
                {"name": "concentration", "value": "0.20", "unit": "mol/L"},
                {"name": "time", "value": "2", "unit": "h"},
            ],
            "confidence": 0.92,
            "evidence": [
                {"speaker": "陈博士", "text": "复现实验确认 70℃ 收率更高", "start_offset_sec": 10},
                {"speaker": "王工程师", "text": "建议温度参数从 80 调整为 70", "start_offset_sec": 20},
            ],
            "status": "pending_review",
            "needs_review": True,
        }],
        open_questions=["浓度是否固定在 0.20 mol/L？"],
    )
    _post("/api/v1/candidates", cand3, base_url, api_key)
    print("  ✓ 推送完成")

    # 场景 4：待复核会议（30 分钟前）
    print("[4/4] 待复核会议（催化剂 0.8 eq 复验）")
    m4_id = "meet_demo_pending_catalyst"
    m4 = build_meeting_payload(
        meeting_id=m4_id,
        title="Compound-A 催化剂 0.8 eq 复验讨论",
        experiment_id="EXP-DEMO-001",
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 10,
             "text": "副产物偏高，下一轮 catalyst 降到 0.8 eq 试试"},
            {"speaker": "李组长", "start_offset_sec": 15, "end_offset_sec": 20,
             "text": "同意，保持温度 70℃ 不变"},
        ],
        captured_delta=timedelta(minutes=-30),
    )
    _post("/api/v1/meetings", m4, base_url, api_key)
    cand4 = build_candidate_payload(
        source_package_id=m4_id,
        candidates=[{
            "candidate_id": "CDR-cat-08-001",
            "type": "parameter_change",
            "title": "催化剂 0.8 eq 复验",
            "description": "降低副产物",
            "experiment_ref": "EXP-DEMO-001",
            "parameters": [
                {"name": "temperature", "value": "70", "unit": "℃"},
                {"name": "catalyst", "value": "0.8", "unit": "eq"},
            ],
            "confidence": 0.82,
            "evidence": [
                {"speaker": "陈工", "text": "副产物偏高，下一轮 catalyst 降到 0.8 eq 试试", "start_offset_sec": 0},
            ],
            "status": "pending_review",
            "needs_review": True,
        }],
        open_questions=["0.8 eq 下收率会不会下降？"],
    )
    _post("/api/v1/candidates", cand4, base_url, api_key)
    print("  ✓ 推送完成")

    print()
    print("=== 全部推送完成 ===")
    print()
    print("当前状态：所有会议均为「待复核」，需要在前端手动确认来推进链路。")
    print("推荐测试路径：")
    print("  1. 确认 65℃ 会议 → 审计通过 → 提交结果 → 发布（含失败边界卡）")
    print("  2. 确认 80℃ 会议 → 生成任务（draft）")
    print("  3. 确认 70℃ 会议 → 生成 current 主张（80℃ 被 supersede）")
    print("  4. 进入 80℃ 任务的行动审计 → 应触发版本阻断 → 一键修正")
    print("  5. 查看催化剂 0.8 eq 待复核会议")


def main() -> None:
    parser = argparse.ArgumentParser(description="模拟飞书编排器推送会议 + 候选包")
    parser.add_argument(
        "mode",
        nargs="?",
        default="demo",
        choices=["single", "demo"],
        help="single=推送单条简单会议；demo=推送完整演示场景（默认）",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="后端服务地址")
    parser.add_argument("--api-key", default=settings.PLATFORM_API_KEY, help="PLATFORM_API_KEY")
    args = parser.parse_args()

    print(f"后端地址: {args.base_url}")
    print(f"推送模式: {args.mode}")
    print()

    try:
        if args.mode == "single":
            push_single(args.base_url, args.api_key)
        else:
            push_demo_scenarios(args.base_url, args.api_key)
    except error.URLError as e:
        print(f"\n✗ 连接失败：{e}", file=sys.stderr)
        print("请先启动后端服务：conda run -n labmemory uvicorn app.main:app --port 8081", file=sys.stderr)
        sys.exit(1)
    except error.HTTPError:
        print("\n✗ 请求失败，请检查上方错误信息", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
