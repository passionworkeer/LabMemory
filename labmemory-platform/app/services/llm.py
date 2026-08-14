"""DeepSeek 对话服务（OpenAI 兼容接口）。

无 API key 或 RAG_ENABLE_LLM=false 时降级为模板式回答。
"""
from __future__ import annotations

import json
import re
from typing import Literal

import httpx

from app.config import settings


ChatMode = Literal["deepseek-chat", "template-fallback"]
Intent = Literal["rag", "chat"]


SYSTEM_PROMPT = """你是 LabMemory 晶研智流平台的可信知识问答助手。基于提供的实验决策上下文回答用户问题。

强制规则：
1. 只能基于 <context> 中给出的信息回答，不得编造或引用上下文之外的实验数据。
2. 每条结论 MUST 在句末标注引用编号，格式 [C1]、[C2] 等，对应 <context> 中的编号。
3. 引用编号 MUST 与上下文中的编号严格对应，不得虚构编号，也不得复用上文历史中出现的编号。
4. 若上下文不足以回答问题，输出 `REFUSED: <具体原因>`，并简要说明需补充什么信息（实验编号/参数名/适用范围/证据类型）。
5. 回答用中文，简洁专业，避免冗长。涉及具体数值时必须给出单位。
6. 若上下文中含「待验证」「未验证」状态的主张，在引用时显式提示「该结论尚未经实验结果验证」。
7. 不要复述上下文原文，用自然语言归纳。
8. 当存在 <history> 历史消息或 <history_summary> 摘要时，可结合上文推断「它/这个/那个」等指代；但若指代无法消解或本轮 <context> 仍无相关证据，输出 `REFUSED: <具体原因>`。
9. 当本轮 user 消息不含 <context>（意图为 chat）时，MUST 只基于 <history_summary> 与上文历史回答，不得虚构编号或切片，回答中 MUST NOT 出现 [Cx] 编号。对于「你能做什么/你是谁/你好/谢谢/再见」等关于 agent 自身能力或寒暄的问题，MUST 用中文自然简短回应，不得 REFUSED。仅当用户追问实验事实/数据/参数且上文摘要与历史中确无相关证据时，才输出 `REFUSED: <原因>`。
"""

INTENT_SYSTEM_PROMPT = """你是 LabMemory 可信问答的意图识别 agent。判断用户本轮问题是否需要触发 RAG 检索可信知识库（实验主张/结果/证据/失败边界/参数版本）。

输出严格 JSON，且不得输出 JSON 之外的任何字符：
{"intent": "rag" | "chat", "reason": "<≤20字中文理由>"}

判断准则：
- 需要查询具体实验数据、参数、知识状态、证据、失败边界、参数版本 → "rag"
- 普通寒暄、致谢、闲聊、关于 agent 自身能力、用户明确说"不用查/直接回答" → "chat"
- 指代消解型追问（"它/这个/刚才那个再展开"）：
  * 若问题只需复述/重组上文已有信息 → "chat"
  * 若问题需要新数据或更细粒度证据 → "rag"
- 模糊时倾向 "rag"（宁检索勿漏）。
"""

SUMMARY_SYSTEM_PROMPT = """你是 LabMemory 可信问答的历史摘要 agent。把已有对话历史（可能含上一轮摘要）压缩为不超过 300 字的中文摘要，必须保留：
- 涉及的实验编号、参数版本与具体数值（带单位）、知识状态（supported/refuted/partially_supported）
- 失败边界关键事实（trigger/ruled_out/next_step）
- 已确立的指代对象（如"EXP-001 是当前讨论的实验"、"它指 C003 主张"）
- 用户表达的偏好或约束（如"只看 EXP-002 的数据"）
必须丢弃：寒暄、致谢、过程性措辞、重复内容。
若已有摘要，在其基础上增量更新，不得丢失关键事实。
直接输出摘要正文，不要前后缀、不要 Markdown 标记、不要 JSON。"""


class LLMService:
    def __init__(self) -> None:
        self._model = settings.DEEPSEEK_CHAT_MODEL
        self._intent_model = (settings.QA_INTENT_MODEL or "").strip() or self._model
        self._api_key = settings.DEEPSEEK_API_KEY.strip()
        self._base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self._enabled = settings.RAG_ENABLE_LLM and bool(self._api_key)
        self._client = httpx.Client(timeout=60.0) if self._enabled else None

    @property
    def mode(self) -> ChatMode:
        return "deepseek-chat" if self._enabled else "template-fallback"

    @property
    def model_name(self) -> str:
        return self._model if self._enabled else "template"

    @property
    def intent_model_name(self) -> str:
        return self._intent_model if self._enabled else "template"

    def chat(self, question: str, context_chunks: list[dict]) -> tuple[str, ChatMode]:
        """单轮生成（兼容路径，等价于 chat_with_history(history=[], summary=None)）。"""
        return self.chat_with_history(question, context_chunks, [], None)

    def classify_intent(
        self,
        question: str,
        recent_history: list[dict],
    ) -> tuple[Intent, str]:
        """意图识别 agent。返回 (intent, reason)。

        LLM 不可用、JSON 解析失败或字段越界时默认 ("rag", "fallback") —— 宁检索勿漏。
        """
        if not settings.QA_ENABLE_LLM_INTENT or not self._enabled or not self._client:
            return "rag", "fallback"
        try:
            raw = self._intent_via_api(question, recent_history)
        except Exception:
            return "rag", "fallback"
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return "rag", "parse_failed"
        intent = data.get("intent")
        reason = str(data.get("reason", ""))[:40]
        if intent not in ("rag", "chat"):
            return "rag", "parse_failed"
        return intent, (reason or "ok")  # type: ignore[return-value]

    def _intent_via_api(self, question: str, recent_history: list[dict]) -> str:
        messages: list[dict] = [{"role": "system", "content": INTENT_SYSTEM_PROMPT}]
        if recent_history:
            hist_lines = [
                f"[{m['role']}] {m['content'][:200]}" for m in recent_history[-4:]
            ]
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"<recent_history>\n{chr(10).join(hist_lines)}\n</recent_history>\n\n"
                        f"<question>\n{question}\n</question>\n\n请输出 JSON。"
                    ),
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": f"<question>\n{question}\n</question>\n\n请输出 JSON。",
                }
            )
        return self._post_chat(
            messages,
            model=self._intent_model,
            temperature=0.0,
            max_tokens=120,
        )

    def summarize_history(
        self,
        existing_summary: str | None,
        old_messages: list[dict],
    ) -> str:
        """历史摘要 agent。返回新摘要正文。

        LLM 不可用、异常或输入为空时返回空串 —— 调用方据此跳过推进 cursor，
        本轮多余消息按"超出窗口"形式被丢弃（不引入新风险），下一轮再试。
        """
        if not self._enabled or not self._client or not old_messages:
            return ""
        try:
            return self._summarize_via_api(existing_summary or "", old_messages)
        except Exception:
            return ""

    def _summarize_via_api(self, existing_summary: str, old_messages: list[dict]) -> str:
        messages: list[dict] = [{"role": "system", "content": SUMMARY_SYSTEM_PROMPT}]
        hist_lines = [f"[{m['role']}] {m['content'][:600]}" for m in old_messages]
        user_content = ""
        if existing_summary:
            user_content += f"<previous_summary>\n{existing_summary}\n</previous_summary>\n\n"
        user_content += f"<old_messages>\n{chr(10).join(hist_lines)}\n</old_messages>\n\n请输出新的摘要正文。"
        messages.append({"role": "user", "content": user_content})
        return self._post_chat(
            messages,
            model=self._model,
            temperature=0.2,
            max_tokens=600,
        )

    def chat_with_history(
        self,
        question: str,
        context_chunks: list[dict],
        history: list[dict],
        summary: str | None = None,
    ) -> tuple[str, ChatMode]:
        """回答 agent 多轮生成。上下文窗口结构：

            [system] + [可选 history_summary system] + 历史消息对 + 本轮 user

        本轮 user 消息：context_chunks 非空时含 <context>+<question>；为空时仅 <question>。
        返回 (answer_text, mode)。
        """
        if not self._enabled or not self._client:
            return self._template_answer(question, context_chunks, history), "template-fallback"
        try:
            return self._chat_via_api(question, context_chunks, history, summary), "deepseek-chat"
        except Exception:
            return self._template_answer(question, context_chunks, history), "template-fallback"

    def _chat_via_api(
        self,
        question: str,
        context_chunks: list[dict],
        history: list[dict] | None = None,
        summary: str | None = None,
    ) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"<history_summary>\n{summary}\n</history_summary>\n"
                        "仅用于消解指代与延续上下文，不得引用其中编号。"
                    ),
                }
            )
        if history:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "<history> 以下是本会话之前的问答记录，仅用于消解指代与延续上下文，"
                        "不得引用其中编号：</history>"
                    ),
                }
            )
            for m in history:
                content = m.get("content", "") or ""
                # 单条历史消息超长截断，避免 token 失控
                if len(content) > 2000:
                    content = content[:2000] + "\n[已截断]"
                messages.append({"role": m["role"], "content": content})
            messages.append({"role": "system", "content": "</history>"})
        if context_chunks:
            context_text = self._format_context(context_chunks)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"<context>\n{context_text}\n</context>\n\n"
                        f"<question>\n{question}\n</question>\n\n"
                        "请基于本轮 context 回答 question，按规则标注引用编号。"
                        "若证据不足，输出 REFUSED: 原因。"
                    ),
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"<question>\n{question}\n</question>\n\n"
                        "请基于上文 history_summary 与近几轮对话回答 question；"
                        "不得引用编号。若上下文仍不足，输出 REFUSED: 原因。"
                    ),
                }
            )
        return self._post_chat(
            messages,
            model=self._model,
            temperature=0.2,
            max_tokens=settings.DEEPSEEK_MAX_TOKENS,
        )

    def _post_chat(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 OpenAI 兼容 /chat/completions，返回首条 message 文本。

        推理型模型可能把 max_tokens 全部消耗在 reasoning 上，返回空 content
        （finish_reason=length）。空补全视为失败抛出，由上层降级，保证用户
        永远不会收到空气泡。
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        resp = self._client.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        if not content:
            raise ValueError(f"empty completion (finish_reason={choice.get('finish_reason')})")
        return content

    def _format_context(self, chunks: list[dict]) -> str:
        lines = []
        for c in chunks:
            ref = c["ref"]
            text = c["text"]
            meta = c.get("metadata", {})
            status_hint = ""
            ks = meta.get("knowledge_status")
            if ks == "supported":
                status_hint = " [已验证:支持]"
            elif ks == "partially_supported":
                status_hint = " [已验证:部分支持]"
            elif ks == "refuted":
                status_hint = " [已验证:推翻]"
            elif ks is None and c.get("type") == "claim":
                status_hint = " [待验证]"
            lines.append(f"[{ref}] ({c['type']}){status_hint} {text}")
        return "\n".join(lines)

    def _template_answer(
        self,
        question: str,
        context_chunks: list[dict],
        history: list[dict] | None = None,
    ) -> str:
        """模板式降级回答：拼接 top chunk 的结构化字段。

        history 非空时附加上文最近一轮用户问题作为提示，避免完全退化为单轮
        （模板无法做真正的指代消解，但至少让用户感知系统仍保有上下文）。
        """
        last_user = None
        if history:
            last_user = next((h["content"] for h in reversed(history) if h.get("role") == "user"), None)
        if not context_chunks:
            if last_user:
                return f"检索未命中新的可信证据。结合上文「{last_user[:30]}」，请补充更具体的实验编号或参数名后重试。"
            return "REFUSED: 检索未命中任何可信证据"
        top = context_chunks[0]
        meta = top.get("metadata", {})
        parts = [f"基于检索到的{top['type']} {top['ref']}（{meta.get('title', '')}）："]
        if top["type"] == "claim":
            pv = meta.get("parameter_version", {})
            params = ", ".join(
                f"{p.get('name','')}={p.get('value','')}{p.get('unit','')}"
                for p in pv.get("parameters", [])
            )
            parts.append(f"参数版本 {pv.get('version', '?')}：{params}。")
            ks = meta.get("knowledge_status")
            if ks:
                parts.append(f"知识状态：{ks}。")
            else:
                parts.append("该结论尚未经实验结果验证，仅作参考。")
        elif top["type"] == "result":
            parts.append(f"指标：{json.dumps(meta.get('metrics', {}), ensure_ascii=False)}")
            parts.append(f"知识状态：{meta.get('knowledge_status', '未知')}。")
        parts.append(f"\n引用：[{top['ref']}]")
        for c in context_chunks[1:]:
            parts.append(f"[{c['ref']}]")
        if last_user:
            parts.append(f"\n（注：大模型归纳暂不可用，以上为检索摘要；上文曾讨论「{last_user[:30]}」）")
        return " ".join(parts)


# 引用编号提取：[C1] [C2] 形式
_CITATION_RE = re.compile(r"\[(C\d+)\]")


def extract_citation_refs(answer_text: str) -> list[str]:
    """从 LLM 输出中提取 [C1] [C2] ... 引用编号，按出现顺序去重。"""
    refs: list[str] = []
    seen: set[str] = set()
    for m in _CITATION_RE.finditer(answer_text):
        ref = m.group(1)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def detect_refusal(answer_text: str) -> tuple[bool, str | None]:
    """检测 LLM 是否主动拒答。返回 (is_refused, reason)。"""
    text = answer_text.strip()
    if text.upper().startswith("REFUSED:"):
        reason = text[len("REFUSED:"):].strip()
        # 去掉可能的前后引号
        reason = reason.strip("\"' \n")
        return True, reason
    if text.upper().startswith("REFUSED"):
        return True, None
    return False, None


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
