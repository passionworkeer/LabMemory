"""
多维表格适配器 - BaseAdapter
负责将候选决策同步到多维表格，作为协作投影和批量查看台账
定位：协作投影、批量查看、演示台账，不作为正式审批源
"""
import json
import subprocess
from typing import Optional, List, Dict

from core.config import Config
from core.utils import now_iso, generate_id
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


class BaseAdapter:
    """多维表格适配器"""

    def __init__(self):
        self.app_token = Config.BASE_APP_TOKEN
        self.table_id = Config.BASE_TABLE_ID
        self.mock_mode = Config.is_mock_mode()
        # Mock 模式下的内存数据
        self._mock_records = {}  # record_id -> record data

    @with_retry(interface_name="base.add_record")
    def add_record(self, candidate: dict, meeting_title: str = "") -> str:
        """
        添加一条候选记录到多维表格
        :param candidate: 候选决策数据
        :param meeting_title: 来源会议标题
        :return: 记录 ID
        """
        integration_log.log(
            direction="outbound",
            interface="base.add_record",
            input_data={
                "candidate_id": candidate.get("candidate_id"),
                "type": candidate.get("type"),
                "title": candidate.get("title"),
            },
            status="start"
        )

        try:
            if self.mock_mode:
                record_id = self._mock_add_record(candidate, meeting_title)
            else:
                record_id = self._real_add_record(candidate, meeting_title)

            integration_log.log(
                direction="outbound",
                interface="base.add_record",
                input_data={"candidate_id": candidate.get("candidate_id")},
                output_data={"record_id": record_id},
                status="success"
            )
            return record_id

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="base.add_record",
                input_data={"candidate_id": candidate.get("candidate_id")},
                error=str(e),
                status="failed"
            )
            raise

    @with_retry(interface_name="base.update_record")
    def update_record(self, record_id: str, fields: dict) -> bool:
        """
        更新多维表格记录
        :param record_id: 记录 ID
        :param fields: 要更新的字段
        :return: 是否成功
        """
        integration_log.log(
            direction="outbound",
            interface="base.update_record",
            input_data={"record_id": record_id, "fields": list(fields.keys())},
            status="start"
        )

        try:
            if self.mock_mode:
                result = self._mock_update_record(record_id, fields)
            else:
                result = self._real_update_record(record_id, fields)

            integration_log.log(
                direction="outbound",
                interface="base.update_record",
                input_data={"record_id": record_id},
                output_data={"success": result},
                status="success"
            )
            return result

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="base.update_record",
                input_data={"record_id": record_id},
                error=str(e),
                status="failed"
            )
            raise

    @with_retry(interface_name="base.batch_add")
    def batch_add_records(self, candidates: List[dict], meeting_title: str = "") -> List[str]:
        """
        批量添加候选记录
        :param candidates: 候选决策列表
        :param meeting_title: 来源会议标题
        :return: 记录 ID 列表
        """
        integration_log.log(
            direction="outbound",
            interface="base.batch_add",
            input_data={"count": len(candidates)},
            status="start"
        )

        try:
            record_ids = []
            for cand in candidates:
                record_id = self.add_record(cand, meeting_title)
                record_ids.append(record_id)

            integration_log.log(
                direction="outbound",
                interface="base.batch_add",
                input_data={"count": len(candidates)},
                output_data={"record_count": len(record_ids)},
                status="success"
            )
            return record_ids

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="base.batch_add",
                input_data={"count": len(candidates)},
                error=str(e),
                status="failed"
            )
            raise

    def update_status(self, record_id: str, status: str) -> bool:
        """更新记录状态"""
        return self.update_record(record_id, {"状态": status, "更新时间": now_iso()})

    def update_task_url(self, record_id: str, task_guid: str) -> bool:
        """更新任务链接"""
        task_url = f"https://bytedance.larkoffice.com/task/{task_guid}"
        return self.update_record(record_id, {"任务链接": task_url, "更新时间": now_iso()})

    def get_record(self, record_id: str) -> Optional[dict]:
        """获取记录详情"""
        if self.mock_mode:
            return self._mock_records.get(record_id)
        return self._real_get_record(record_id)

    def list_records(self, status: Optional[str] = None, limit: int = 100) -> List[dict]:
        """
        查询记录列表
        :param status: 按状态筛选
        :param limit: 最大数量
        :return: 记录列表
        """
        if self.mock_mode:
            records = list(self._mock_records.values())
            if status:
                records = [r for r in records if r.get("状态") == status]
            return records[:limit]
        return self._real_list_records(status, limit)

    # ==================== Mock 实现 ====================

    def _mock_add_record(self, candidate: dict, meeting_title: str = "") -> str:
        """Mock 添加记录"""
        record_id = generate_id("rec")

        # 类型标签映射
        type_labels = {
            "decision": "🟢 决策",
            "conclusion": "🔵 结论",
            "risk": "🟠 风险",
            "action_item": "🟡 行动项",
            "question": "❓ 疑问",
            "parameter_change": "📊 参数变更",
        }

        record = {
            "record_id": record_id,
            "候选ID": candidate.get("candidate_id"),
            "类型": type_labels.get(candidate.get("type"), candidate.get("type", "")),
            "标题": candidate.get("title", ""),
            "描述": candidate.get("description", "")[:200],  # 截断
            "来源会议": meeting_title,
            "置信度": f"{int(candidate.get('confidence', 0) * 100)}%",
            "状态": candidate.get("status", "pending_review"),
            "关联实验": candidate.get("experiment_ref", ""),
            "任务链接": "",
            "平台详情": f"https://labmemory.example.com/review/{candidate.get('candidate_id', '')}",
            "创建时间": now_iso(),
            "更新时间": now_iso(),
        }

        self._mock_records[record_id] = record
        return record_id

    def _mock_update_record(self, record_id: str, fields: dict) -> bool:
        """Mock 更新记录"""
        if record_id not in self._mock_records:
            return False

        self._mock_records[record_id].update(fields)
        self._mock_records[record_id]["更新时间"] = now_iso()
        return True

    # ==================== 真实实现 ====================

    def _real_add_record(self, candidate: dict, meeting_title: str = "") -> str:
        """真实添加记录到多维表格"""
        # 构建字段
        type_labels = {
            "decision": "🟢 决策",
            "conclusion": "🔵 结论",
            "risk": "🟠 风险",
            "action_item": "🟡 行动项",
            "question": "❓ 疑问",
            "parameter_change": "📊 参数变更",
        }

        fields = {
            "候选ID": candidate.get("candidate_id"),
            "类型": type_labels.get(candidate.get("type"), candidate.get("type", "")),
            "标题": candidate.get("title", ""),
            "描述": candidate.get("description", "")[:200],
            "来源会议": meeting_title,
            "置信度": f"{int(candidate.get('confidence', 0) * 100)}%",
            "状态": candidate.get("status", "pending_review"),
            "关联实验": candidate.get("experiment_ref", ""),
            "平台详情": f"https://labmemory.example.com/review/{candidate.get('candidate_id', '')}",
            "创建时间": now_iso(),
            "更新时间": now_iso(),
        }

        # 使用 lark-cli base +create-record
        cmd = [
            "lark-cli", "base", "+create-record",
            "--app-token", self.app_token,
            "--table-id", self.table_id,
            "--fields", json.dumps(fields, ensure_ascii=False),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr}")

            output = json.loads(result.stdout)
            return output.get("data", {}).get("record", {}).get("record_id", "")
        except json.JSONDecodeError:
            raise Exception(f"解析输出失败: {result.stdout}")

    def _real_update_record(self, record_id: str, fields: dict) -> bool:
        """真实更新记录"""
        cmd = [
            "lark-cli", "base", "+update-record",
            "--app-token", self.app_token,
            "--table-id", self.table_id,
            "--record-id", record_id,
            "--fields", json.dumps(fields, ensure_ascii=False),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return False

    def _real_get_record(self, record_id: str) -> Optional[dict]:
        """真实获取记录"""
        cmd = [
            "lark-cli", "base", "+get-record",
            "--app-token", self.app_token,
            "--table-id", self.table_id,
            "--record-id", record_id,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            output = json.loads(result.stdout)
            return output.get("data", {}).get("record", {})
        except Exception:
            return None

    def _real_list_records(self, status: Optional[str] = None, limit: int = 100) -> List[dict]:
        """真实查询记录列表"""
        cmd = [
            "lark-cli", "base", "+list-records",
            "--app-token", self.app_token,
            "--table-id", self.table_id,
            "--limit", str(limit),
        ]

        if status:
            filter_str = f'CurrentValue.[状态] = "{status}"'
            cmd.extend(["--filter", filter_str])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return []
            output = json.loads(result.stdout)
            return output.get("data", {}).get("items", [])
        except Exception:
            return []


# 单例
base_adapter = BaseAdapter()
