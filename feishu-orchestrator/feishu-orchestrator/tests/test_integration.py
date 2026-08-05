"""
集成测试：验证完整链路
测试范围：事件驱动 → Aily 编译 → 平台提交 → 卡片回调 → 任务创建
"""
import sys
import os
import json
import time
import hashlib
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
from adapters.task_adapter import task_adapter
from reliability.integration_log import integration_log
from reliability.idempotency import idempotency_guard


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
                    "action_type": "approved",
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
                    "action_type": "approved",
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
                    "action_type": "approved",
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
        self.assertEqual(result["status"], "success")
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
        self.assertEqual(result["status"], "success")
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
        """mock 模式下跳过验签"""
        original = Config.RUN_MODE
        Config.RUN_MODE = "mock"
        try:
            handler = WebhookHandler.__new__(WebhookHandler)
            self.assertTrue(handler._verify_request(b"{}", "webhook.event"))
        finally:
            Config.RUN_MODE = original


def run_all_tests():
    """运行所有测试"""
    print()
    print("=" * 70)
    print("  集成测试套件")
    print("=" * 70)
    print()

    # 确保目录存在
    Config.ensure_dirs()

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
