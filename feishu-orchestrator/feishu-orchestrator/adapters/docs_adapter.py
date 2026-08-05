"""
云文档适配器 - DocsAdapter
负责将通过审核的决策、风险、经验等发布为知识文档
触发条件：平台标记为 publishable
"""
import json
import subprocess
from typing import Optional, List, Dict

from core.config import Config
from core.utils import now_iso, generate_id, truncate_text
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


class DocsAdapter:
    """云文档适配器"""

    def __init__(self):
        self.mock_mode = Config.is_mock_mode()
        # Mock 模式下的内存数据
        self._mock_docs = {}  # doc_token -> doc data

    @with_retry(interface_name="docs.publish")
    def publish_knowledge(self, candidate: dict, meeting_title: str = "", doc_type: str = "success") -> dict:
        """
        发布知识文档
        :param candidate: 候选决策数据
        :param meeting_title: 来源会议标题
        :param doc_type: 文档类型：success / failure / pending
        :return: 文档信息 {doc_token, url, title}
        """
        integration_log.log(
            direction="outbound",
            interface="docs.publish",
            input_data={
                "candidate_id": candidate.get("candidate_id"),
                "doc_type": doc_type,
                "title": candidate.get("title"),
            },
            status="start"
        )

        try:
            if self.mock_mode:
                result = self._mock_publish(candidate, meeting_title, doc_type)
            else:
                result = self._real_publish(candidate, meeting_title, doc_type)

            integration_log.log(
                direction="outbound",
                interface="docs.publish",
                input_data={"candidate_id": candidate.get("candidate_id")},
                output_data=result,
                status="success"
            )
            return result

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="docs.publish",
                input_data={"candidate_id": candidate.get("candidate_id")},
                error=str(e),
                status="failed"
            )
            raise

    def publish_success_case(self, candidate: dict, meeting_title: str = "") -> dict:
        """发布成功案例文档"""
        return self.publish_knowledge(candidate, meeting_title, doc_type="success")

    def publish_failure_case(self, candidate: dict, meeting_title: str = "", reason: str = "") -> dict:
        """发布失败边界文档"""
        return self.publish_knowledge(candidate, meeting_title, doc_type="failure")

    def publish_pending_case(self, candidate: dict, meeting_title: str = "") -> dict:
        """发布待验证文档"""
        return self.publish_knowledge(candidate, meeting_title, doc_type="pending")

    def get_doc(self, doc_token: str) -> Optional[dict]:
        """获取文档信息"""
        if self.mock_mode:
            return self._mock_docs.get(doc_token)
        return self._real_get_doc(doc_token)

    def list_docs(self, doc_type: Optional[str] = None, limit: int = 100) -> List[dict]:
        """查询文档列表"""
        if self.mock_mode:
            docs = list(self._mock_docs.values())
            if doc_type:
                docs = [d for d in docs if d.get("doc_type") == doc_type]
            return docs[:limit]
        return self._real_list_docs(doc_type, limit)

    def _build_doc_title(self, candidate: dict, doc_type: str) -> str:
        """构建文档标题"""
        type_prefix = {
            "success": "✅ 成功案例",
            "failure": "❌ 失败边界",
            "pending": "⏳ 待验证",
        }
        prefix = type_prefix.get(doc_type, "📝 知识")
        title = candidate.get("title", "未命名")
        return f"{prefix} | {title}"

    def _build_doc_content(self, candidate: dict, meeting_title: str, doc_type: str) -> str:
        """构建文档内容（Markdown 格式）"""
        type_labels = {
            "decision": "决策",
            "conclusion": "结论",
            "risk": "风险",
            "action_item": "行动项",
            "question": "疑问",
            "parameter_change": "参数变更",
        }

        cand_type = type_labels.get(candidate.get("type"), candidate.get("type", ""))
        confidence = int(candidate.get("confidence", 0) * 100)
        experiment_ref = candidate.get("experiment_ref", "无")
        description = candidate.get("description", "")

        # 参数变更
        parameters = candidate.get("parameters", [])
        params_md = ""
        if parameters:
            params_md = "\n### 参数变更\n\n"
            for p in parameters:
                name = p.get("name", "")
                old_val = p.get("old_value", "")
                new_val = p.get("new_value", "")
                unit = p.get("unit", "")
                params_md += f"- **{name}**: {old_val}{unit} → {new_val}{unit}\n"

        # 证据
        evidence = candidate.get("evidence", [])
        evidence_md = ""
        if evidence:
            evidence_md = "\n### 证据\n\n"
            for i, e in enumerate(evidence[:5], 1):
                speaker = e.get("speaker", "")
                text = e.get("text", "")
                evidence_md += f"{i}. **{speaker}**: {truncate_text(text, 100)}\n"

        # 文档类型说明
        type_notes = {
            "success": "> 🎯 本案例已验证成功，可作为最佳实践参考。",
            "failure": "> ⚠️ 本案例为失败边界，请注意规避类似问题。",
            "pending": "> 🔬 本案例待进一步验证，请谨慎参考。",
        }
        note = type_notes.get(doc_type, "")

        content = f"""# {self._build_doc_title(candidate, doc_type)}

{note}

## 基本信息

| 字段 | 内容 |
|------|------|
| 类型 | {cand_type} |
| 置信度 | {confidence}% |
| 关联实验 | {experiment_ref} |
| 来源会议 | {meeting_title} |
| 发布时间 | {now_iso()} |

## 描述

{description}
{params_md}
{evidence_md}
---

*本文档由 LabMemory 飞书编排系统自动生成*
"""
        return content

    # ==================== Mock 实现 ====================

    def _mock_publish(self, candidate: dict, meeting_title: str, doc_type: str) -> dict:
        """Mock 发布文档"""
        doc_token = generate_id("doc")
        title = self._build_doc_title(candidate, doc_type)
        content = self._build_doc_content(candidate, meeting_title, doc_type)
        url = f"https://bytedance.larkoffice.com/docx/{doc_token}"

        doc = {
            "doc_token": doc_token,
            "title": title,
            "url": url,
            "doc_type": doc_type,
            "candidate_id": candidate.get("candidate_id"),
            "meeting_title": meeting_title,
            "content": content,
            "created_at": now_iso(),
        }

        self._mock_docs[doc_token] = doc
        return {
            "doc_token": doc_token,
            "title": title,
            "url": url,
        }

    # ==================== 真实实现 ====================

    def _real_publish(self, candidate: dict, meeting_title: str, doc_type: str) -> dict:
        """真实发布文档"""
        title = self._build_doc_title(candidate, doc_type)
        content = self._build_doc_content(candidate, meeting_title, doc_type)

        # 使用 lark-cli docx +create
        cmd = [
            "lark-cli", "docx", "+create",
            "--title", title,
            "--content", content,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr}")

            output = json.loads(result.stdout)
            doc_token = output.get("data", {}).get("document", {}).get("document_id", "")
            url = f"https://bytedance.larkoffice.com/docx/{doc_token}"

            return {
                "doc_token": doc_token,
                "title": title,
                "url": url,
            }
        except json.JSONDecodeError:
            raise Exception(f"解析输出失败: {result.stdout}")

    def _real_get_doc(self, doc_token: str) -> Optional[dict]:
        """真实获取文档信息"""
        cmd = [
            "lark-cli", "docx", "+get",
            "--document-id", doc_token,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            output = json.loads(result.stdout)
            return output.get("data", {}).get("document", {})
        except Exception:
            return None

    def _real_list_docs(self, doc_type: Optional[str] = None, limit: int = 100) -> List[dict]:
        """真实查询文档列表（简化实现，实际需要用搜索 API）"""
        # 真实场景下可能需要用云空间搜索或知识库搜索
        return []


# 单例
docs_adapter = DocsAdapter()
