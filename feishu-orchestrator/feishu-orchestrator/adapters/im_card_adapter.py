"""
交互卡片适配器 - IMCardAdapter
负责发送飞书交互卡片和处理回调
"""
import json
import subprocess
from typing import Optional, List

from core.config import Config
from core.utils import now_iso, generate_id
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


class IMCardAdapter:
    """交互卡片适配器"""

    def __init__(self):
        self.mock_mode = Config.is_mock_mode()
        self.app_token = Config.FEISHU_TENANT_ACCESS_TOKEN

    @with_retry(interface_name="im.send_card")
    def send_review_card(
        self,
        receive_id: str,
        candidate: dict,
        meeting_title: str,
        source_url: str = "",
    ) -> str:
        """
        发送待复核卡片
        :param receive_id: 接收人 ID（open_id / user_id / email）
        :param candidate: 候选决策
        :param meeting_title: 会议标题
        :param source_url: 来源链接
        :return: 消息 ID
        """
        card = self._build_review_card(candidate, meeting_title, source_url)

        integration_log.log(
            direction="outbound",
            interface="im.send_review_card",
            input_data={
                "receive_id": receive_id,
                "candidate_id": candidate.get("candidate_id"),
                "candidate_title": candidate.get("title"),
            },
            status="start"
        )

        try:
            if self.mock_mode:
                message_id = generate_id("msg")
            else:
                message_id = self._real_send_card(receive_id, card)

            integration_log.log(
                direction="outbound",
                interface="im.send_review_card",
                input_data={"receive_id": receive_id, "candidate_id": candidate.get("candidate_id")},
                output_data={"message_id": message_id},
                status="success"
            )
            return message_id

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="im.send_review_card",
                input_data={"receive_id": receive_id, "candidate_id": candidate.get("candidate_id")},
                error=str(e),
                status="failed"
            )
            raise

    def send_approved_card(
        self,
        receive_id: str,
        candidate: dict,
        task_url: str = "",
    ) -> str:
        """发送已批准卡片"""
        card = self._build_approved_card(candidate, task_url)

        if self.mock_mode:
            return generate_id("msg")
        return self._real_send_card(receive_id, card)

    def send_blocked_card(
        self,
        receive_id: str,
        candidate: dict,
        reason: str = "",
    ) -> str:
        """发送已阻断卡片"""
        card = self._build_blocked_card(candidate, reason)

        if self.mock_mode:
            return generate_id("msg")
        return self._real_send_card(receive_id, card)

    def send_alert_card(
        self,
        receive_id: str,
        title: str,
        error: str,
        retry_action: Optional[dict] = None,
    ) -> str:
        """发送异常告警卡片"""
        card = self._build_alert_card(title, error, retry_action)

        if self.mock_mode:
            return generate_id("msg")
        return self._real_send_card(receive_id, card)

    def update_card(self, message_id: str, card: dict):
        """更新卡片内容"""
        if self.mock_mode:
            return
        # 真实模式调用更新接口
        self._real_update_card(message_id, card)

    # ==================== 卡片构建 ====================

    def _build_review_card(self, candidate: dict, meeting_title: str, source_url: str) -> dict:
        """构建待复核卡片"""
        candidate_id = candidate.get("candidate_id", "")
        title = candidate.get("title", "未命名候选")
        description = candidate.get("description", "")
        cand_type = candidate.get("type", "conclusion")
        confidence = candidate.get("confidence", 0)
        experiment_ref = candidate.get("experiment_ref", "")
        parameters = candidate.get("parameters", [])
        evidence = candidate.get("evidence", [])

        # 类型标签
        type_labels = {
            "decision": "🟢 决策",
            "conclusion": "🔵 结论",
            "risk": "🟠 风险",
            "action_item": "🟡 行动项",
            "question": "❓ 疑问",
            "parameter_change": "📊 参数变更",
        }
        type_label = type_labels.get(cand_type, cand_type)

        # 参数展示
        params_text = ""
        if parameters:
            params_text = "\n".join([
                f"  • {p.get('name', '')}: {p.get('value', '')} {p.get('unit', '')}"
                for p in parameters
            ])

        # 证据展示（只取第一条）
        evidence_text = ""
        if evidence:
            ev = evidence[0]
            evidence_text = f"{ev.get('speaker', '')}: {ev.get('text', '')[:80]}..."

        # 置信度显示
        confidence_pct = int(confidence * 100)
        confidence_label = f"{confidence_pct}%"

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{type_label}** | 置信度：{confidence_label}"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**来源会议**：{meeting_title}"
                }
            },
            {
                "tag": "hr"
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": description[:200] + ("..." if len(description) > 200 else "")
                }
            },
        ]

        if experiment_ref:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**关联实验**：{experiment_ref}"
                }
            })

        if params_text:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**参数变更**：\n{params_text}"
                }
            })

        if evidence_text:
            elements.extend([
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**证据**：\n{evidence_text}"
                    }
                }
            ])

        # 按钮
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✅ 确认"
                        },
                        "type": "primary",
                        "value": {
                            "action_type": "approve",
                            "candidate_id": candidate_id,
                        }
                    },
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "✏️ 修正"
                        },
                        "type": "default",
                        "value": {
                            "action_type": "revise",
                            "candidate_id": candidate_id,
                        }
                    },
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "❌ 驳回"
                        },
                        "type": "danger",
                        "value": {
                            "action_type": "reject",
                            "candidate_id": candidate_id,
                        }
                    },
                ]
            }
        ])

        if source_url:
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "📄 查看完整复核台"
                        },
                        "type": "default",
                        "url": source_url,
                    }
                ]
            })

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🔍 待复核：新的候选决策"
                },
                "template": "blue"
            },
            "elements": elements
        }

        return card

    def _build_approved_card(self, candidate: dict, task_url: str = "") -> dict:
        """构建已批准卡片"""
        title = candidate.get("title", "未命名候选")

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": "该候选已通过复核，将创建对应任务。"
                }
            },
        ]

        if task_url:
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "📋 打开任务"
                        },
                        "type": "primary",
                        "url": task_url,
                    }
                ]
            })

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "✅ 已批准"
                },
                "template": "green"
            },
            "elements": elements
        }

        return card

    def _build_blocked_card(self, candidate: dict, reason: str = "") -> dict:
        """构建已阻断卡片"""
        title = candidate.get("title", "未命名候选")

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**"
                }
            },
        ]

        if reason:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"阻断原因：{reason}"
                }
            })

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🚫 已阻断"
                },
                "template": "red"
            },
            "elements": elements
        }

        return card

    def _build_alert_card(self, title: str, error: str, retry_action: Optional[dict] = None) -> dict:
        """构建异常告警卡片"""
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": error
                }
            },
        ]

        if retry_action:
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "🔄 重试"
                        },
                        "type": "primary",
                        "value": retry_action,
                    }
                ]
            })

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"⚠️ {title}"
                },
                "template": "orange"
            },
            "elements": elements
        }

        return card

    # ==================== 真实实现 ====================

    def _real_send_card(self, receive_id: str, card: dict) -> str:
        """真实发送卡片（使用 lark-cli）"""
        try:
            cmd = [
                "lark-cli", "im", "+send-card",
                "--receive-id", receive_id,
                "--card", json.dumps(card, ensure_ascii=False),
            ]

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
            return data.get("message_id", "")

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI")
        except subprocess.TimeoutExpired:
            raise Exception("发送卡片超时")
        except json.JSONDecodeError:
            raise Exception("解析发送结果失败")

    def _real_update_card(self, message_id: str, card: dict):
        """真实更新卡片"""
        try:
            cmd = [
                "lark-cli", "im", "+update-card",
                "--message-id", message_id,
                "--card", json.dumps(card, ensure_ascii=False),
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
            raise Exception("更新卡片超时")


# 单例
im_card_adapter = IMCardAdapter()
