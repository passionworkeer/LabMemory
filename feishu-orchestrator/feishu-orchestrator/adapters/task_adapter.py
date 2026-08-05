"""
飞书任务适配器 - TaskAdapter
负责创建和管理飞书任务
"""
import json
import subprocess
from typing import Optional, List

from core.config import Config
from core.utils import now_iso, generate_id
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


class TaskAdapter:
    """飞书任务适配器"""

    def __init__(self):
        self.mock_mode = Config.is_mock_mode()
        self.app_token = Config.FEISHU_TENANT_ACCESS_TOKEN

    @with_retry(interface_name="task.create")
    def create_from_candidate(self, candidate: dict, meeting_title: str = "", source_url: str = "") -> str:
        """
        从候选决策创建飞书任务
        :param candidate: 候选决策
        :param meeting_title: 来源会议标题
        :param source_url: 来源链接
        :return: 任务 GUID
        """
        title = candidate.get("title", "未命名任务")
        description = candidate.get("description", "")
        assignee = candidate.get("assignee", "")
        due_date = candidate.get("due_date")

        # 构建任务描述
        full_description = self._build_task_description(candidate, meeting_title, source_url)

        integration_log.log(
            direction="outbound",
            interface="task.create_from_candidate",
            input_data={
                "candidate_id": candidate.get("candidate_id"),
                "title": title,
                "assignee": assignee,
            },
            status="start"
        )

        try:
            if self.mock_mode:
                task_guid = generate_id("task")
            else:
                task_guid = self._real_create_task(
                    summary=title,
                    description=full_description,
                    assignee=assignee,
                    due_date=due_date,
                )

            integration_log.log(
                direction="outbound",
                interface="task.create_from_candidate",
                input_data={"candidate_id": candidate.get("candidate_id"), "title": title},
                output_data={"task_guid": task_guid},
                status="success"
            )
            return task_guid

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="task.create_from_candidate",
                input_data={"candidate_id": candidate.get("candidate_id"), "title": title},
                error=str(e),
                status="failed"
            )
            raise

    def get_task(self, task_guid: str) -> dict:
        """获取任务详情"""
        if self.mock_mode:
            return {
                "task_guid": task_guid,
                "summary": "示例任务",
                "status": "not_started",
            }
        return self._real_get_task(task_guid)

    def update_task_status(self, task_guid: str, status: str):
        """更新任务状态"""
        if self.mock_mode:
            return
        self._real_update_task_status(task_guid, status)

    def _build_task_description(self, candidate: dict, meeting_title: str, source_url: str) -> str:
        """构建任务描述"""
        description = candidate.get("description", "")
        experiment_ref = candidate.get("experiment_ref", "")
        parameters = candidate.get("parameters", [])
        evidence = candidate.get("evidence", [])

        lines = []

        lines.append(f"**来源会议**：{meeting_title}")
        if source_url:
            lines.append(f"**来源链接**：{source_url}")

        lines.append("")
        lines.append("**任务详情**：")
        lines.append(description)

        if experiment_ref:
            lines.append("")
            lines.append(f"**关联实验**：{experiment_ref}")

        if parameters:
            lines.append("")
            lines.append("**相关参数**：")
            for p in parameters:
                lines.append(f"  - {p.get('name', '')}: {p.get('value', '')} {p.get('unit', '')}")

        if evidence:
            lines.append("")
            lines.append("**证据**：")
            for i, ev in enumerate(evidence[:3]):  # 最多3条
                speaker = ev.get("speaker", "")
                text = ev.get("text", "")
                lines.append(f"  {i+1}. {speaker}: {text[:100]}...")

        lines.append("")
        lines.append("---")
        lines.append(f"*由 LabMemory 飞书编排系统自动创建*")
        lines.append(f"*候选 ID: {candidate.get('candidate_id', '')}*")

        return "\n".join(lines)

    # ==================== 真实实现 ====================

    def _real_create_task(
        self,
        summary: str,
        description: str = "",
        assignee: str = "",
        due_date: Optional[str] = None,
        followers: Optional[List[str]] = None,
    ) -> str:
        """真实创建飞书任务（使用 lark-cli）"""
        try:
            cmd = [
                "lark-cli", "task", "+create",
                "--summary", summary,
                "--description", description,
            ]

            if assignee:
                cmd.extend(["--assignee", assignee])

            if due_date:
                cmd.extend(["--due-date", due_date])

            if followers:
                cmd.extend(["--followers", ",".join(followers)])

            if self.app_token:
                cmd.extend(["--tenant-access-token", self.app_token])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr}")

            data = json.loads(result.stdout)
            return data.get("task_guid", data.get("guid", ""))

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI")
        except subprocess.TimeoutExpired:
            raise Exception("创建任务超时")
        except json.JSONDecodeError:
            raise Exception("解析创建任务结果失败")

    def _real_get_task(self, task_guid: str) -> dict:
        """真实获取任务详情"""
        try:
            cmd = [
                "lark-cli", "task", "+get",
                "--task-guid", task_guid,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr}")

            return json.loads(result.stdout)

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI")
        except subprocess.TimeoutExpired:
            raise Exception("获取任务超时")
        except json.JSONDecodeError:
            raise Exception("解析任务详情失败")

    def _real_update_task_status(self, task_guid: str, status: str):
        """真实更新任务状态"""
        try:
            cmd = [
                "lark-cli", "task", "+update",
                "--task-guid", task_guid,
                "--status", status,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr}")

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI")
        except subprocess.TimeoutExpired:
            raise Exception("更新任务超时")


# 单例
task_adapter = TaskAdapter()
