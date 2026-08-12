"""
多维表格适配器 - BaseAdapter
负责将候选决策同步到多维表格，作为协作投影和批量查看台账
定位：协作投影、批量查看、演示台账，不作为正式审批源
"""
import json
import subprocess
from typing import Optional, List, Dict

from core.config import Config
from core.utils import now_iso, generate_id, safe_get
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry
from reliability.idempotency import idempotency_guard


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
                candidate_id = cand.get("candidate_id", "")
                recovery_key = f"base_record:{candidate_id}" if candidate_id else ""
                previous = idempotency_guard.check(recovery_key) if recovery_key else None
                if previous and previous.get("record_id"):
                    record_ids.append(previous["record_id"])
                    continue
                if recovery_key and not idempotency_guard.acquire(recovery_key):
                    raise RuntimeError(f"候选 {candidate_id} 的 Base 写入正在处理中")
                try:
                    record_id = self.add_record(cand, meeting_title)
                    record_ids.append(record_id)
                    if recovery_key:
                        idempotency_guard.mark(recovery_key, {"record_id": record_id})
                except Exception:
                    if recovery_key:
                        idempotency_guard.release(recovery_key)
                    raise

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

    @with_retry(interface_name="base.get_record")
    def get_record(self, record_id: str) -> Optional[dict]:
        """获取记录详情"""
        if self.mock_mode:
            return self._mock_records.get(record_id)
        return self._real_get_record(record_id)

    @with_retry(interface_name="base.list_records")
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

        # lark-cli base +record-batch-create：字段通过 --json 的 create_records 传入
        cmd = [
            "lark-cli", "base", "+record-batch-create",
            "--base-token", self.app_token,
            "--table-id", self.table_id,
            "--json", json.dumps({"create_records": [fields]}, ensure_ascii=False),
            "--as", "bot",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=30
            )
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")

            output = json.loads(result.stdout)
            records = safe_get(output, "data", "records", default=[]) or []
            record_id = records[0].get("record_id", "") if records else ""
            if not record_id:
                raise ValueError("多维表格创建响应缺少 record_id")
            return record_id
        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except json.JSONDecodeError:
            raise Exception(f"解析输出失败: {result.stdout}")

    def _real_update_record(self, record_id: str, fields: dict) -> bool:
        """真实更新记录（lark-cli base +record-batch-update）"""
        cmd = [
            "lark-cli", "base", "+record-batch-update",
            "--base-token", self.app_token,
            "--table-id", self.table_id,
            "--json", json.dumps({"update_records": {record_id: fields}}, ensure_ascii=False),
            "--as", "bot",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=30
            )
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")
            return True
        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except subprocess.TimeoutExpired:
            raise Exception("更新多维表格记录超时")

    def _real_get_record(self, record_id: str) -> Optional[dict]:
        """真实获取记录（lark-cli base +record-get）"""
        cmd = [
            "lark-cli", "base", "+record-get",
            "--base-token", self.app_token,
            "--table-id", self.table_id,
            "--record-id", record_id,
            "--format", "json",
            "--as", "bot",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=30
            )
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")
            output = json.loads(result.stdout)
            records = safe_get(output, "data", "records", default=[]) or []
            return records[0] if records else None
        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except subprocess.TimeoutExpired:
            raise Exception("获取多维表格记录超时")

    def _real_list_records(self, status: Optional[str] = None, limit: int = 100) -> List[dict]:
        """真实查询记录列表（lark-cli base +record-list）"""
        cmd = [
            "lark-cli", "base", "+record-list",
            "--base-token", self.app_token,
            "--table-id", self.table_id,
            "--limit", str(limit),
            "--format", "json",
            "--as", "bot",
        ]

        if status:
            filter_json = {
                "conjunction": "and",
                "conditions": [
                    {"field_name": "状态", "operator": "is", "value": [status]}
                ],
            }
            cmd.extend(["--filter-json", json.dumps(filter_json, ensure_ascii=False)])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=30
            )
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")
            output = json.loads(result.stdout)
            return safe_get(output, "data", "records", default=None) or safe_get(
                output, "data", "items", default=[]
            )
        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except subprocess.TimeoutExpired:
            raise Exception("查询多维表格记录超时")


# 单例
base_adapter = BaseAdapter()
