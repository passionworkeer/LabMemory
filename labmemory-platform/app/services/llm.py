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


SYSTEM_PROMPT = """你是 LabMemory 晶研智流平台的可信知识问答助手。基于提供的实验决策上下文回答用户问题。

强制规则：
1. 只能基于 <context> 中给出的信息回答，不得编造或引用上下文之外的实验数据。
2. 每条结论 MUST 在句末标注引用编号，格式 [C1]、[C2] 等，对应 <context> 中的编号。
3. 引用编号 MUST 与上下文中的编号严格对应，不得虚构编号。
4. 若上下文不足以回答问题，输出 `REFUSED: <具体原因>`，并简要说明需补充什么信息（实验编号/参数名/适用范围/证据类型）。
5. 回答用中文，简洁专业，避免冗长。涉及具体数值时必须给出单位。
6. 若上下文中含「待验证」「未验证」状态的主张，在引用时显式提示「该结论尚未经实验结果验证」。
7. 不要复述上下文原文，用自然语言归纳。
"""


class LLMService:
    def __init__(self) -> None:
        self._model = settings.DEEPSEEK_CHAT_MODEL
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

    def chat(self, question: str, context_chunks: list[dict]) -> tuple[str, ChatMode]:
        """生成回答。

        context_chunks: [{ref: 'C1', text: '...', type: 'claim', metadata: {...}}, ...]
        返回 (answer_text, mode)。
        """
        if not self._enabled or not self._client:
            return self._template_answer(question, context_chunks), "template-fallback"
        try:
            return self._chat_via_api(question, context_chunks), "deepseek-chat"
        except Exception:
            return self._template_answer(question, context_chunks), "template-fallback"

    def _chat_via_api(self, question: str, context_chunks: list[dict]) -> str:
        context_text = self._format_context(context_chunks)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"<context>\n{context_text}\n</context>\n\n<question>\n{question}\n</question>\n\n请基于 context 回答 question，按规则标注引用编号。若证据不足，输出 REFUSED: 原因。",
            },
        ]
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 800,
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
        return data["choices"][0]["message"]["content"].strip()

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

    def _template_answer(self, question: str, context_chunks: list[dict]) -> str:
        """模板式降级回答：拼接 top chunk 的结构化字段。"""
        if not context_chunks:
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
