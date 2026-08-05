#!/usr/bin/env python3
"""
Phase 3 单元测试
测试 BaseAdapter、DocsAdapter、Mock Server 等新增功能
"""
import sys
import os
import unittest
import json

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from adapters.base_adapter import base_adapter
from adapters.docs_adapter import docs_adapter
from mock.mock_server import mock_state, MockPlatformState


class TestBaseAdapter(unittest.TestCase):
    """测试多维表格适配器"""

    def setUp(self):
        """每个测试前重置"""
        base_adapter._mock_records.clear()

    def test_add_record(self):
        """测试添加记录"""
        candidate = {
            "candidate_id": "cand_test_001",
            "type": "decision",
            "title": "测试决策",
            "description": "测试描述",
            "confidence": 0.9,
            "status": "pending_review",
        }

        record_id = base_adapter.add_record(candidate, "测试会议")

        self.assertTrue(record_id.startswith("rec_"))
        self.assertEqual(len(base_adapter._mock_records), 1)

        record = base_adapter.get_record(record_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["候选ID"], "cand_test_001")
        self.assertEqual(record["标题"], "测试决策")
        self.assertEqual(record["状态"], "pending_review")
        self.assertIn("🟢", record["类型"])  # 决策类型标签

    def test_update_record(self):
        """测试更新记录"""
        candidate = {
            "candidate_id": "cand_test_002",
            "type": "risk",
            "title": "测试风险",
            "confidence": 0.7,
            "status": "pending_review",
        }

        record_id = base_adapter.add_record(candidate)

        # 更新状态
        result = base_adapter.update_status(record_id, "approved")
        self.assertTrue(result)

        record = base_adapter.get_record(record_id)
        self.assertEqual(record["状态"], "approved")

    def test_update_task_url(self):
        """测试更新任务链接"""
        candidate = {
            "candidate_id": "cand_test_003",
            "type": "action_item",
            "title": "测试行动项",
            "confidence": 0.85,
            "status": "pending_review",
        }

        record_id = base_adapter.add_record(candidate)

        result = base_adapter.update_task_url(record_id, "task_123")
        self.assertTrue(result)

        record = base_adapter.get_record(record_id)
        self.assertIn("task_123", record["任务链接"])

    def test_batch_add(self):
        """测试批量添加"""
        candidates = [
            {"candidate_id": "cand_batch_001", "type": "decision", "title": "批量1", "confidence": 0.9, "status": "pending_review"},
            {"candidate_id": "cand_batch_002", "type": "risk", "title": "批量2", "confidence": 0.7, "status": "pending_review"},
            {"candidate_id": "cand_batch_003", "type": "action_item", "title": "批量3", "confidence": 0.8, "status": "approved"},
        ]

        record_ids = base_adapter.batch_add_records(candidates, "批量测试会议")
        self.assertEqual(len(record_ids), 3)
        self.assertEqual(len(base_adapter._mock_records), 3)

    def test_list_records(self):
        """测试查询记录列表"""
        candidates = [
            {"candidate_id": "cand_list_001", "type": "decision", "title": "列表1", "confidence": 0.9, "status": "pending_review"},
            {"candidate_id": "cand_list_002", "type": "risk", "title": "列表2", "confidence": 0.7, "status": "approved"},
            {"candidate_id": "cand_list_003", "type": "action_item", "title": "列表3", "confidence": 0.8, "status": "pending_review"},
        ]

        base_adapter.batch_add_records(candidates)

        # 查询所有
        all_records = base_adapter.list_records()
        self.assertEqual(len(all_records), 3)

        # 按状态筛选
        pending = base_adapter.list_records(status="pending_review")
        self.assertEqual(len(pending), 2)

        approved = base_adapter.list_records(status="approved")
        self.assertEqual(len(approved), 1)

        # 限制数量
        limited = base_adapter.list_records(limit=2)
        self.assertEqual(len(limited), 2)

    def test_type_labels(self):
        """测试类型标签映射"""
        test_cases = [
            ("decision", "🟢"),
            ("conclusion", "🔵"),
            ("risk", "🟠"),
            ("action_item", "🟡"),
            ("question", "❓"),
            ("parameter_change", "📊"),
        ]

        for cand_type, expected_label in test_cases:
            candidate = {
                "candidate_id": f"cand_type_{cand_type}",
                "type": cand_type,
                "title": f"测试{cand_type}",
                "confidence": 0.8,
                "status": "pending_review",
            }

            record_id = base_adapter.add_record(candidate)
            record = base_adapter.get_record(record_id)
            self.assertIn(expected_label, record["类型"])


class TestDocsAdapter(unittest.TestCase):
    """测试云文档适配器"""

    def setUp(self):
        """每个测试前重置"""
        docs_adapter._mock_docs.clear()

    def test_publish_success_case(self):
        """测试发布成功案例"""
        candidate = {
            "candidate_id": "cand_docs_001",
            "type": "decision",
            "title": "测试决策",
            "description": "测试描述",
            "confidence": 0.92,
            "status": "approved",
            "experiment_ref": "EXP-2026-001",
        }

        result = docs_adapter.publish_success_case(candidate, "测试会议")

        self.assertIn("doc_token", result)
        self.assertIn("url", result)
        self.assertIn("title", result)
        self.assertTrue(result["doc_token"].startswith("doc_"))
        self.assertIn("成功案例", result["title"])

        # 检查文档是否保存
        doc = docs_adapter.get_doc(result["doc_token"])
        self.assertIsNotNone(doc)
        self.assertEqual(doc["doc_type"], "success")

    def test_publish_failure_case(self):
        """测试发布失败边界案例"""
        candidate = {
            "candidate_id": "cand_docs_002",
            "type": "risk",
            "title": "测试风险",
            "description": "风险描述",
            "confidence": 0.6,
            "status": "blocked",
        }

        result = docs_adapter.publish_failure_case(candidate, "测试会议")
        self.assertIn("失败边界", result["title"])

        doc = docs_adapter.get_doc(result["doc_token"])
        self.assertEqual(doc["doc_type"], "failure")

    def test_publish_pending_case(self):
        """测试发布待验证案例"""
        candidate = {
            "candidate_id": "cand_docs_003",
            "type": "conclusion",
            "title": "测试结论",
            "description": "结论描述",
            "confidence": 0.75,
            "status": "pending_review",
        }

        result = docs_adapter.publish_pending_case(candidate, "测试会议")
        self.assertIn("待验证", result["title"])

        doc = docs_adapter.get_doc(result["doc_token"])
        self.assertEqual(doc["doc_type"], "pending")

    def test_doc_content(self):
        """测试文档内容生成"""
        candidate = {
            "candidate_id": "cand_docs_004",
            "type": "decision",
            "title": "内容测试决策",
            "description": "这是一个测试决策的描述",
            "confidence": 0.9,
            "experiment_ref": "EXP-TEST-001",
            "parameters": [
                {"name": "温度", "old_value": "20", "new_value": "25", "unit": "℃"},
            ],
            "evidence": [
                {"speaker": "张三", "text": "我建议调整温度"},
            ],
        }

        result = docs_adapter.publish_success_case(candidate, "内容测试会议")
        doc = docs_adapter.get_doc(result["doc_token"])

        content = doc["content"]
        self.assertIn("内容测试决策", content)
        self.assertIn("EXP-TEST-001", content)
        self.assertIn("参数变更", content)
        self.assertIn("温度", content)
        self.assertIn("证据", content)
        self.assertIn("张三", content)

    def test_list_docs(self):
        """测试查询文档列表"""
        candidates = [
            {"candidate_id": "cand_list_001", "type": "decision", "title": "文档1", "confidence": 0.9},
            {"candidate_id": "cand_list_002", "type": "risk", "title": "文档2", "confidence": 0.7},
            {"candidate_id": "cand_list_003", "type": "conclusion", "title": "文档3", "confidence": 0.8},
        ]

        docs_adapter.publish_success_case(candidates[0])
        docs_adapter.publish_failure_case(candidates[1])
        docs_adapter.publish_success_case(candidates[2])

        all_docs = docs_adapter.list_docs()
        self.assertEqual(len(all_docs), 3)

        success_docs = docs_adapter.list_docs(doc_type="success")
        self.assertEqual(len(success_docs), 2)

        failure_docs = docs_adapter.list_docs(doc_type="failure")
        self.assertEqual(len(failure_docs), 1)


class TestMockPlatform(unittest.TestCase):
    """测试 Mock 平台状态管理"""

    def setUp(self):
        """每个测试前重置"""
        mock_state.reset()

    def test_submit_candidates(self):
        """测试提交候选"""
        package = {
            "schema_version": "1.0",
            "candidates": [
                {"candidate_id": "cand_mock_001", "type": "decision", "title": "测试1", "confidence": 0.9},
                {"candidate_id": "cand_mock_002", "type": "risk", "title": "测试2", "confidence": 0.7},
            ]
        }

        result = mock_state.submit_candidates(package)

        self.assertIn("submission_id", result)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(len(mock_state.candidates), 2)
        self.assertEqual(len(mock_state.submissions), 1)

        # 检查初始状态
        cand = mock_state.get_candidate("cand_mock_001")
        self.assertEqual(cand["status"], "pending_review")

    def test_card_callback_approved(self):
        """测试卡片回调 - 通过"""
        # 先提交
        mock_state.submit_candidates({
            "candidates": [
                {"candidate_id": "cand_cb_001", "type": "decision", "title": "测试"},
            ]
        })

        # 回调通过
        result = mock_state.handle_card_callback({
            "candidate_id": "cand_cb_001",
            "action_type": "approved",
        })

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["action_audit"], "pass")

        cand = mock_state.get_candidate("cand_cb_001")
        self.assertEqual(cand["status"], "approved")

    def test_card_callback_rejected(self):
        """测试卡片回调 - 驳回"""
        mock_state.submit_candidates({
            "candidates": [
                {"candidate_id": "cand_cb_002", "type": "decision", "title": "测试"},
            ]
        })

        result = mock_state.handle_card_callback({
            "candidate_id": "cand_cb_002",
            "action_type": "rejected",
        })

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["action_audit"], "reject")

    def test_card_callback_blocked(self):
        """测试卡片回调 - 阻断"""
        mock_state.submit_candidates({
            "candidates": [
                {"candidate_id": "cand_cb_003", "type": "risk", "title": "测试"},
            ]
        })

        result = mock_state.handle_card_callback({
            "candidate_id": "cand_cb_003",
            "action_type": "blocked",
        })

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["action_audit"], "block")

    def test_update_task_status(self):
        """测试更新任务状态"""
        mock_state.submit_candidates({
            "candidates": [
                {"candidate_id": "cand_task_001", "type": "action_item", "title": "测试"},
            ]
        })

        result = mock_state.update_task_status(
            candidate_id="cand_task_001",
            task_guid="task_12345",
            status="created",
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(mock_state.task_updates), 1)

        cand = mock_state.get_candidate("cand_task_001")
        self.assertEqual(cand["task_guid"], "task_12345")
        self.assertEqual(cand["task_status"], "created")

    def test_state_summary(self):
        """测试状态摘要"""
        # 提交一些候选
        mock_state.submit_candidates({
            "candidates": [
                {"candidate_id": "cand_sum_001", "type": "decision", "title": "测试1"},
                {"candidate_id": "cand_sum_002", "type": "risk", "title": "测试2"},
                {"candidate_id": "cand_sum_003", "type": "action_item", "title": "测试3"},
            ]
        })

        # 更新一些状态
        mock_state.handle_card_callback({"candidate_id": "cand_sum_001", "action_type": "approved"})
        mock_state.handle_card_callback({"candidate_id": "cand_sum_002", "action_type": "rejected"})

        summary = mock_state.get_state_summary()

        self.assertEqual(summary["total_candidates"], 3)
        self.assertEqual(summary["total_submissions"], 1)
        self.assertEqual(summary["total_callbacks"], 2)
        self.assertEqual(summary["status_counts"]["approved"], 1)
        self.assertEqual(summary["status_counts"]["rejected"], 1)
        self.assertEqual(summary["status_counts"]["pending_review"], 1)

    def test_reset(self):
        """测试重置状态"""
        mock_state.submit_candidates({
            "candidates": [{"candidate_id": "cand_reset_001", "title": "测试"}],
        })

        self.assertEqual(len(mock_state.candidates), 1)

        mock_state.reset()

        self.assertEqual(len(mock_state.candidates), 0)
        self.assertEqual(len(mock_state.submissions), 0)
        self.assertEqual(len(mock_state.callbacks), 0)
        self.assertEqual(len(mock_state.task_updates), 0)

    def test_action_type_normalization(self):
        """测试 action_type 规范化"""
        mock_state.submit_candidates({
            "candidates": [{"candidate_id": "cand_norm_001", "title": "测试"}],
        })

        # 各种写法都应该识别为 approved
        test_cases = [
            ("approve", "approved"),
            ("approved", "approved"),
            ("confirm", "approved"),
            ("pass", "approved"),
            ("APPROVE", "approved"),  # 大小写不敏感
        ]

        for action_type, expected_status in test_cases:
            mock_state.reset()
            mock_state.submit_candidates({
                "candidates": [{"candidate_id": "cand_norm_001", "title": "测试"}],
            })

            result = mock_state.handle_card_callback({
                "candidate_id": "cand_norm_001",
                "action_type": action_type,
            })

            self.assertEqual(result["status"], expected_status, f"action_type={action_type} 应该返回 {expected_status}")


def run_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("  Phase 3 单元测试")
    print("="*60)
    print()

    # 确保目录存在
    Config.ensure_dirs()

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestBaseAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestDocsAdapter))
    suite.addTests(loader.loadTestsFromTestCase(TestMockPlatform))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 统计
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    failed = len(result.failures) + len(result.errors)

    print()
    print("="*60)
    print(f"  测试结果: {passed}/{total} 通过, {failed} 失败")
    print("="*60)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
