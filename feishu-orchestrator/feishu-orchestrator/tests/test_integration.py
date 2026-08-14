"""
集成测试：验证完整链路
测试范围：事件驱动 → Aily 编译 → 平台提交 → 卡片回调 → 任务创建
"""
import sys
import os
import json
import time
import hashlib
import subprocess
import tempfile
from pathlib import Path
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.event_router import event_router
from core.state_machine import state_machine, MeetingState
from core.pipeline_orchestrator import pipeline_orchestrator
from core.card_handler import card_handler
from core.platform_client import platform_client
from core.webhook_server import (
    WebhookHandler,
    verify_signature,
    SIGNATURE_MAX_AGE_SECONDS,
)
from adapters.minutes_adapter import minutes_adapter
from adapters.aily_adapter import aily_adapter
from adapters.im_card_adapter import im_card_adapter
from adapters.base_adapter import base_adapter
from adapters.docs_adapter import docs_adapter
from adapters.task_adapter import task_adapter
from adapters import task_adapter as task_module
from reliability.integration_log import integration_log
from reliability.idempotency import idempotency_guard
from reliability.retry_engine import RetryEngine, RetryableError


class TestEventDrivenFlow(unittest.TestCase):
    """事件驱动流程测试"""

    def setUp(self):
        """测试前重置状态"""
        # 重置平台 mock 状态
        platform_client._mock_candidates = {}

    def test_meeting_ended_event(self):
        """测试会议结束事件"""
        event = {
            "type": "meeting.ended_v1",
            "event_id": "test_evt_meeting_001",
            "meeting_id": "test_meeting_001",
            "title": "测试会议",
        }

        result = event_router.handle_event(event)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["next_state"], "waiting_minutes")

        # 验证状态机
        state = state_machine.get_state("meeting:test_meeting_001")
        self.assertIsNotNone(state)
        self.assertEqual(state["state"], "waiting_minutes")

    def test_minutes_generated_event(self):
        """测试妙记生成事件"""
        # 先发会议结束事件
        event_router.handle_event({
            "type": "meeting.ended_v1",
            "event_id": "test_evt_meeting_002",
            "meeting_id": "test_meeting_002",
        })

        # 再发妙记生成事件
        event = {
            "type": "minutes.minute.generated_v1",
            "event_id": "test_evt_minutes_002",
            "minute_token": "test_minutes_002",
            "meeting_id": "test_meeting_002",
        }

        result = event_router.handle_event(event)

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["next_state"], "minutes_ready")

        # 验证状态机
        state = state_machine.get_state("meeting:test_meeting_002")
        self.assertEqual(state["state"], "minutes_ready")

    def test_event_idempotency(self):
        """测试事件幂等性"""
        event = {
            "type": "meeting.ended_v1",
            "event_id": "test_evt_idempotent",
            "meeting_id": "test_meeting_idempotent",
        }

        # 第一次处理
        result1 = event_router.handle_event(event)
        # 第二次处理（重复事件）
        result2 = event_router.handle_event(event)

        # 第一次应该是 accepted，第二次应该是 duplicate（幂等）
        self.assertEqual(result1["status"], "accepted")
        self.assertEqual(result2["status"], "duplicate")


class TestAilyCompiler(unittest.TestCase):
    """Aily 编译测试"""

    def test_compile_from_minutes(self):
        """测试从妙记编译"""
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_compile"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)

        candidate_package = aily_adapter.compile(meeting_package)

        # 验证输出结构
        self.assertIn("candidates", candidate_package)
        self.assertIn("risks", candidate_package)
        self.assertIn("action_items", candidate_package)
        self.assertIn("compiled_at", candidate_package)

        # 验证候选决策不为空
        self.assertGreater(len(candidate_package["candidates"]), 0)

        # 验证每个候选决策的字段
        for cand in candidate_package["candidates"]:
            self.assertIn("candidate_id", cand)
            self.assertIn("type", cand)
            self.assertIn("title", cand)
            self.assertIn("confidence", cand)
            self.assertIn("status", cand)

    def test_compile_from_text(self):
        """测试从纯文本编译"""
        text = """
        今天的会议决定采用方案B来优化实验流程。
        我们将把反应温度从20度调整到30度，预计转化率会提升20%。
        但是需要注意，温度升高可能会增加副反应的风险。
        张三负责下周三之前完成小试，李四负责检测数据。
        """

        meeting_package = {
            "schema_version": "1.0",
            "source": "manual_upload",
            "source_object_id": "test_text_001",
            "title": "测试会议",
            "content": {
                "transcript": [{"speaker": "张三", "text": text}],
                "chapters": [],
            },
        }

        candidate_package = aily_adapter.compile(meeting_package)

        # 应该能识别出决策
        decisions = [c for c in candidate_package["candidates"] if c["type"] == "decision"]
        self.assertGreater(len(decisions), 0)

        # 应该能识别出参数变更
        param_changes = [c for c in candidate_package["candidates"] if c["type"] == "parameter_change"]
        self.assertGreater(len(param_changes), 0)

        # 应该能识别出风险
        self.assertGreater(len(candidate_package["risks"]), 0)

        # 应该能识别出行动项
        self.assertGreater(len(candidate_package["action_items"]), 0)


class TestPlatformIntegration(unittest.TestCase):
    """平台对接测试"""

    def setUp(self):
        """测试前重置状态"""
        platform_client._mock_candidates = {}

    def test_submit_candidates(self):
        """测试提交候选决策"""
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_submit"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)
        candidate_package = aily_adapter.compile(meeting_package)

        result = platform_client.submit_candidates(candidate_package)

        self.assertEqual(result["status"], "submitted")
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), len(candidate_package["candidates"]))

    def test_card_callback_approved(self):
        """测试卡片回调（通过）"""
        # 先提交
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_callback"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)
        candidate_package = aily_adapter.compile(meeting_package)
        platform_client.submit_candidates(candidate_package)

        first_candidate = candidate_package["candidates"][0]

        # 模拟通过回调
        callback_data = {
            "token": "test_callback_approved",
            "action": {
                "value": {
                    "action_type": "approve",
                    "candidate_id": first_candidate["candidate_id"],
                }
            }
        }

        result = platform_client.forward_card_callback(callback_data)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["action_audit"], "pass")

        # 验证候选状态已更新
        candidate = platform_client.get_candidate(first_candidate["candidate_id"])
        self.assertEqual(candidate["status"], "approved")

    def test_update_task_status(self):
        """测试更新任务状态"""
        # 先提交并批准
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_task"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)
        candidate_package = aily_adapter.compile(meeting_package)
        platform_client.submit_candidates(candidate_package)

        first_candidate = candidate_package["candidates"][0]
        candidate_id = first_candidate["candidate_id"]
        task_guid = "task_test_12345"

        # 更新任务状态
        result = platform_client.update_task_status(candidate_id, task_guid, "success")

        self.assertEqual(result["status"], "ok")

        # 验证候选详情中包含任务信息
        candidate = platform_client.get_candidate(candidate_id)
        self.assertEqual(candidate["task_guid"], task_guid)
        self.assertEqual(candidate["task_status"], "success")
        self.assertEqual(candidate["status"], "completed")


class TestCardHandler(unittest.TestCase):
    """卡片回调处理测试"""

    def setUp(self):
        """测试前重置状态"""
        platform_client._mock_candidates = {}

    def test_approved_creates_task(self):
        """测试通过后自动创建任务"""
        # 先提交候选
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_card_handler"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)
        candidate_package = aily_adapter.compile(meeting_package)
        platform_client.submit_candidates(candidate_package)

        first_candidate = candidate_package["candidates"][0]

        # 模拟卡片回调
        callback_data = {
            "token": "test_card_handler_001",
            "open_id": "test_user",
            "action": {
                "value": {
                    "action_type": "approve",
                    "candidate_id": first_candidate["candidate_id"],
                }
            }
        }

        result = card_handler.handle_callback(callback_data)

        # 验证平台返回通过
        self.assertEqual(result["status"], "approved")

        # 验证任务已创建
        candidate = platform_client.get_candidate(first_candidate["candidate_id"])
        self.assertIsNotNone(candidate.get("task_guid"))
        self.assertEqual(candidate["status"], "completed")

    def test_callback_idempotency(self):
        """测试卡片回调幂等性"""
        # 先提交候选
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_card_idem"
        detail = minutes_adapter.get_by_url(minutes_url)
        meeting_package = minutes_adapter.to_meeting_package(detail)
        candidate_package = aily_adapter.compile(meeting_package)
        platform_client.submit_candidates(candidate_package)

        first_candidate = candidate_package["candidates"][0]

        callback_data = {
            "token": "test_card_idem_001",
            "action": {
                "value": {
                    "action_type": "approve",
                    "candidate_id": first_candidate["candidate_id"],
                }
            }
        }

        # 第一次处理
        result1 = card_handler.handle_callback(callback_data)
        # 第二次处理（重复回调）
        result2 = card_handler.handle_callback(callback_data)

        # 第一次应该是 approved，第二次应该是 duplicate（幂等）
        self.assertEqual(result1["status"], "approved")
        self.assertEqual(result2["status"], "duplicate")


class TestReliability(unittest.TestCase):
    """可靠性测试"""

    def test_idempotency_guard(self):
        """测试幂等守卫"""
        key = "test_idempotency_key_001"

        # 第一次检查应该返回 None
        result1 = idempotency_guard.check(key)
        self.assertIsNone(result1)

        # 标记为已处理
        idempotency_guard.mark(key, {"status": "processed"})

        # 第二次检查应该返回之前的结果
        result2 = idempotency_guard.check(key)
        self.assertIsNotNone(result2)
        self.assertEqual(result2["status"], "processed")

    def test_integration_log(self):
        """测试集成日志"""
        # 记录一条日志
        integration_log.log(
            direction="outbound",
            interface="test.interface",
            input_data={"test": "input"},
            output_data={"test": "output"},
            status="success",
            duration_ms=100,
            request_id="test_req_001",
        )

        # 查询日志
        logs = integration_log.get_logs(interface="test.interface", limit=10)

        # 应该能查到刚才记录的日志
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0]["interface"], "test.interface")
        self.assertEqual(logs[0]["status"], "success")

    def test_state_machine_transitions(self):
        """测试状态机流转"""
        object_id = "test_state_machine_001"

        # 初始状态
        state_machine.set_state(object_id, MeetingState.WAITING_MINUTES)

        # 正常流转
        result = state_machine.transition(
            object_id,
            from_state=MeetingState.WAITING_MINUTES,
            to_state=MeetingState.MINUTES_READY,
        )
        self.assertTrue(result)

        state = state_machine.get_state(object_id)
        self.assertEqual(state["state"], "minutes_ready")

        # 错误流转（前置状态不对）
        result = state_machine.transition(
            object_id,
            from_state=MeetingState.WAITING_MINUTES,  # 不对，当前是 minutes_ready
            to_state=MeetingState.COMPILING,
        )
        self.assertFalse(result)  # 应该失败

        # 状态应该不变
        state = state_machine.get_state(object_id)
        self.assertEqual(state["state"], "minutes_ready")


class TestPipelineOrchestrator(unittest.TestCase):
    """主编排器测试"""

    def setUp(self):
        """测试前重置状态"""
        platform_client._mock_candidates = {}

    def test_run_from_minutes_url(self):
        """测试从妙记链接运行完整流程"""
        minutes_url = "https://bytedance.larkoffice.com/minutes/test_pipeline"

        result = pipeline_orchestrator.run_from_minutes_url(
            minutes_url=minutes_url,
            reviewer_id="test_reviewer",
        )

        self.assertIn("status", result)
        self.assertEqual(result["status"], "submitted")
        self.assertIn("candidate_count", result)
        self.assertGreater(result["candidate_count"], 0)
        self.assertTrue(result.get("review_cards_sent"))

    def test_run_from_text(self):
        """测试从文本运行完整流程"""
        text = """
        会议决定：采用新方案，把温度调整到25度。
        风险：可能会有副作用。
        行动项：小王负责验证。
        """

        result = pipeline_orchestrator.run_from_text(
            text=text,
            title="测试会议",
            reviewer_id="test_reviewer",
        )

        self.assertIn("status", result)
        self.assertEqual(result["status"], "submitted")
        self.assertGreater(result["candidate_count"], 0)
        self.assertTrue(result.get("review_cards_sent"))


class TestWebhookSignature(unittest.TestCase):
    """Webhook 验签测试"""

    ENCRYPT_KEY = "test_encrypt_key"

    def _sign(self, timestamp, nonce, body, encrypt_key=None):
        key = self.ENCRYPT_KEY if encrypt_key is None else encrypt_key
        sha256 = hashlib.sha256()
        sha256.update(f"{timestamp}{nonce}{key}".encode("utf-8") + body)
        return sha256.hexdigest()

    def test_valid_signature(self):
        """正确签名应通过"""
        timestamp = str(int(time.time()))
        nonce, body = "nonce_001", b'{"type":"event"}'
        signature = self._sign(timestamp, nonce, body)

        self.assertTrue(
            verify_signature(self.ENCRYPT_KEY, body, timestamp, nonce, signature)
        )

    def test_invalid_signature(self):
        """错误签名应拒绝"""
        timestamp = str(int(time.time()))
        self.assertFalse(
            verify_signature(
                self.ENCRYPT_KEY, b'{"type":"event"}', timestamp, "nonce_001", "deadbeef"
            )
        )

    def test_tampered_body(self):
        """签名有效但请求体被篡改应拒绝"""
        timestamp = str(int(time.time()))
        nonce = "nonce_001"
        signature = self._sign(timestamp, nonce, b'{"amount":1}')

        self.assertFalse(
            verify_signature(self.ENCRYPT_KEY, b'{"amount":999}', timestamp, nonce, signature)
        )

    def test_missing_encrypt_key(self):
        """密钥为空应拒绝（空密钥会使签名退化为可伪造的固定哈希）"""
        timestamp = str(int(time.time()))
        nonce, body = "nonce_001", b'{"type":"event"}'
        signature = self._sign(timestamp, nonce, body, encrypt_key="")

        self.assertFalse(verify_signature("", body, timestamp, nonce, signature))

    def test_expired_timestamp(self):
        """超出时间窗的请求应拒绝（防重放）"""
        timestamp = str(int(time.time()) - SIGNATURE_MAX_AGE_SECONDS - 60)
        nonce, body = "nonce_001", b'{"type":"event"}'
        signature = self._sign(timestamp, nonce, body)

        self.assertFalse(
            verify_signature(self.ENCRYPT_KEY, body, timestamp, nonce, signature)
        )

    def test_malformed_timestamp(self):
        """非法时间戳应拒绝"""
        nonce, body = "nonce_001", b'{"type":"event"}'
        self.assertFalse(
            verify_signature(self.ENCRYPT_KEY, body, "not-a-timestamp", nonce, "x")
        )

    def test_mock_mode_skips_verification(self):
        """mock 模式下跳过验签（但限 localhost，防未设 RUN_MODE=real 暴露）"""
        original = Config.RUN_MODE
        Config.RUN_MODE = "mock"
        try:
            handler = WebhookHandler.__new__(WebhookHandler)
            handler._send_json = lambda *a, **kw: None  # 裸 handler 无 requestline，stub 发送
            handler.headers = {}
            handler.client_address = ("127.0.0.1", 0)
            self.assertTrue(handler._verify_request(b"{}", "webhook.event"))
            # 携带 X-Forwarded-For 的代理转发请求即使来自 localhost 也拒绝
            handler.headers = {"X-Forwarded-For": "203.0.113.7"}
            self.assertFalse(handler._verify_request(b"{}", "webhook.event"))
            # 非本地来源即使 mock 模式也拒绝
            handler.headers = {}
            handler.client_address = ("10.0.0.5", 0)
            self.assertFalse(handler._verify_request(b"{}", "webhook.event"))
        finally:
            Config.RUN_MODE = original


class TestProductionReliability(unittest.TestCase):
    """真实模式可靠性边界测试"""

    def test_lark_cli_command_uses_platform_default(self):
        original_override = Config.LARK_CLI_COMMAND
        try:
            Config.LARK_CLI_COMMAND = ""
            command = Config.get_lark_cli_command()
            if os.name == "nt":
                self.assertTrue(command.endswith("lark-cli.cmd"))
            else:
                self.assertEqual(command, "lark-cli")
        finally:
            Config.LARK_CLI_COMMAND = original_override


    def test_lark_cli_command_explicit_override(self):
        original_override = Config.LARK_CLI_COMMAND
        try:
            Config.LARK_CLI_COMMAND = "C:/tools/lark-cli-custom.cmd"
            self.assertEqual(Config.get_lark_cli_command(), "C:/tools/lark-cli-custom.cmd")
        finally:
            Config.LARK_CLI_COMMAND = original_override

    def test_retry_engine_retries_explicit_timeout(self):
        attempts = []
        engine = RetryEngine(max_retries=1, base_delay=0, jitter=False)

        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise RetryableError("subprocess timeout")
            return "ok"

        self.assertEqual(engine.execute(operation, interface_name="test.timeout"), "ok")
        self.assertEqual(len(attempts), 2)

    def test_aily_invalid_output_is_not_empty_success(self):
        with self.assertRaises(Exception):
            aily_adapter._extract_json_from_text("not valid json")

    def test_aily_missing_candidates_is_invalid(self):
        with self.assertRaises(Exception):
            aily_adapter._rule_validate({"risks": []})

    def test_retry_engine_recognizes_chinese_timeout(self):
        engine = RetryEngine(max_retries=0, base_delay=0, jitter=False)
        self.assertTrue(engine.is_retryable(Exception("获取任务超时")))

    def test_base_update_cli_failure_is_not_silent(self):
        original = base_adapter.mock_mode
        base_adapter.mock_mode = False
        original_run = __import__("adapters.base_adapter", fromlist=["subprocess"]).subprocess.run
        try:
            def failed_run(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="permission denied")
            __import__("adapters.base_adapter", fromlist=["subprocess"]).subprocess.run = failed_run
            with self.assertRaises(Exception):
                base_adapter._real_update_record("rec_1", {"状态": "approved"})
        finally:
            module = __import__("adapters.base_adapter", fromlist=["subprocess"])
            module.subprocess.run = original_run
            base_adapter.mock_mode = original

    def test_minutes_detail_uses_isolated_output_dir(self):
        module = __import__("adapters.minutes_adapter", fromlist=["subprocess"])
        original_run = module.subprocess.run
        with tempfile.TemporaryDirectory() as temp_dir:
            captured = []
            def successful_detail(cmd, **kwargs):
                captured.append(cmd)
                output_dir = Path(cmd[cmd.index("--output-dir") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                transcript = output_dir / "transcript.txt"
                transcript.write_text("张三: 结论", encoding="utf-8")
                return subprocess.CompletedProcess(
                    cmd, 0,
                    stdout=json.dumps({"data": {"minutes": [{
                        "minute_token": "minute_test",
                        "title": "测试会议",
                        "artifacts": {"transcript_file": str(transcript)},
                    }]}}),
                    stderr="",
                )
            module.subprocess.run = successful_detail
            original_data_dir = Config.DATA_DIR
            Config.DATA_DIR = Path(temp_dir)
            try:
                minutes_adapter._real_get_detail("minute_test")
                # --output-dir 必须基于 Config.DATA_DIR（稳定隔离路径），与逐字稿落盘/读取目录一致
                self.assertIn("--output-dir", captured[0])
                output_dir = Path(captured[0][captured[0].index("--output-dir") + 1])
                self.assertEqual(output_dir, Config.DATA_DIR / "minutes" / "minute_test")
                self.assertEqual(captured[0][captured[0].index("--as") + 1], "user")
            finally:
                Config.DATA_DIR = original_data_dir
        module.subprocess.run = original_run

    def test_docs_publish_requires_document_id(self):
        original_run = __import__("adapters.docs_adapter", fromlist=["subprocess"]).subprocess.run
        try:
            def empty_response(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 0, stdout='{"data": {}}', stderr="")
            __import__("adapters.docs_adapter", fromlist=["subprocess"]).subprocess.run = empty_response
            with self.assertRaises(Exception):
                docs_adapter._real_publish({"title": "x"}, "meeting")
        finally:
            __import__("adapters.docs_adapter", fromlist=["subprocess"]).subprocess.run = original_run


    def test_batch_base_reuses_record_for_same_candidate(self):
        original_mock = base_adapter.mock_mode
        original_add = base_adapter.add_record
        calls = []
        try:
            base_adapter.mock_mode = True
            def fake_add(candidate, meeting_title=""):
                calls.append(candidate["candidate_id"])
                return "rec_existing"
            base_adapter.add_record = fake_add
            candidate = {"candidate_id": "cand_recovery_cross_platform", "title": "测试"}
            first = base_adapter.batch_add_records([candidate])
            second = base_adapter.batch_add_records([candidate])
        finally:
            base_adapter.add_record = original_add
            base_adapter.mock_mode = original_mock
        self.assertEqual(first, ["rec_existing"])
        self.assertEqual(second, ["rec_existing"])
        self.assertEqual(calls, ["cand_recovery_cross_platform"])

    def test_approved_card_cli_failure_is_explicit(self):
        module = __import__("adapters.im_card_adapter", fromlist=["subprocess"])
        original_run = module.subprocess.run
        original_mock = im_card_adapter.mock_mode
        try:
            im_card_adapter.mock_mode = False
            def failed_send(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")
            module.subprocess.run = failed_send
            with self.assertRaises(Exception):
                im_card_adapter.send_approved_card(
                    "ou_reviewer", {"candidate_id": "cand_1", "title": "测试"}
                )
        finally:
            module.subprocess.run = original_run
            im_card_adapter.mock_mode = original_mock


class TestLarkCliCommandMapping(unittest.TestCase):
    """lark-cli 命令映射测试（拦截 subprocess，不发起真实调用）"""

    def test_receiver_flag_user(self):
        """ou_ 前缀 → --user-id"""
        self.assertEqual(
            im_card_adapter._receiver_flag("ou_abc123"), ["--user-id", "ou_abc123"]
        )

    def test_receiver_flag_chat(self):
        """oc_ 前缀 → --chat-id"""
        self.assertEqual(
            im_card_adapter._receiver_flag("oc_abc123"), ["--chat-id", "oc_abc123"]
        )

    def test_receiver_flag_unknown_prefix(self):
        """无法识别的前缀应直接失败，而不是发出错误的调用"""
        with self.assertRaises(Exception):
            im_card_adapter._receiver_flag("unknown_abc")

    def test_task_create_includes_idempotency_key(self):
        module = task_module
        original_run = module.subprocess.run
        captured = []
        try:
            def successful_create(cmd, **kwargs):
                captured.append(cmd)
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=json.dumps({"data": {"task": {"guid": "task_1"}}}), stderr=""
                )
            module.subprocess.run = successful_create
            task_adapter._real_create_task("标题", idempotency_key="cand_1")
        finally:
            module.subprocess.run = original_run
        self.assertIn("--idempotency-key", captured[0])
        self.assertIn("cand_1", captured[0])

    def test_status_dispatch_to_complete_or_reopen(self):
        """完成态 → +complete，其余 → +reopen"""
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        original = task_module.subprocess.run
        task_module.subprocess.run = fake_run
        try:
            task_adapter._real_update_task_status("task_guid_1", "success")
            task_adapter._real_update_task_status("task_guid_1", "pending")
        finally:
            task_module.subprocess.run = original

        self.assertIn("+complete", captured[0])
        self.assertIn("+reopen", captured[1])
        self.assertIn("--task-id", captured[0])


def _reset_file_state():
    """清空幂等/状态机的文件持久化，保证重复运行从干净态开始。

    idempotency_guard / state_machine / base_adapter 去重均落盘到 ``data/idempotency``
    与 ``data/state``（md5 文件名、7 天 TTL）。测试用固定键（如 ``test_evt_meeting_001``），
    若不在套件起点清理，第二次运行首次调用即命中上次残留 → 出现 ``'duplicate'`` 假失败。
    仅清这两个子目录的 ``*.json``，保留 ``integration_logs``（历史）与 ``minutes``（fixture）。
    """
    import glob as _glob
    for sub in ("idempotency", "state"):
        d = Config.DATA_DIR / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in _glob.glob(str(d / "*.json")):
            try:
                os.remove(f)
            except OSError:
                pass


def run_all_tests():
    """运行所有测试"""
    print()
    print("=" * 70)
    print("  集成测试套件")
    print("=" * 70)
    print()

    # 确保目录存在
    Config.ensure_dirs()
    # 清空幂等/状态文件持久化，避免固定键跨运行残留导致 'duplicate' 假失败
    _reset_file_state()

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestEventDrivenFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestAilyCompiler))
    suite.addTests(loader.loadTestsFromTestCase(TestPlatformIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestCardHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestReliability))
    suite.addTests(loader.loadTestsFromTestCase(TestPipelineOrchestrator))
    suite.addTests(loader.loadTestsFromTestCase(TestWebhookSignature))
    suite.addTests(loader.loadTestsFromTestCase(TestProductionReliability))
    suite.addTests(loader.loadTestsFromTestCase(TestLarkCliCommandMapping))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print(f"  测试结果: {result.testsRun} 个测试")
    print(f"  通过: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败: {len(result.failures)}")
    print(f"  错误: {len(result.errors)}")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
