## 背景

`add-qa-session-history` 后，QA 已有会话级持久化与多轮历史拼接，但存在用户反馈的"上下文丢失"现象。根因有三：(1) 历史窗口硬截断、超限即丢；(2) 每轮必跑 RAG 检索，指代消解类追问被无关切片污染；(3) 意图与压缩状态不可见。本设计引入双 agent + 滚动摘要，让上下文窗口结构稳定、token 可控、意图清晰。

## 1. 上下文窗口结构

回答 agent 收到的 messages 数组（按顺序）：

```
1. system                                    ← SYSTEM_PROMPT，不变
2. system: <history_summary>...</history_summary>   ← 仅当 session.summary 非空
3..(2+2N)   历史消息对 (user/assistant 交替)         ← 最近 QA_HISTORY_TURNS 轮 = 2N 条
2+2N+1      user: <context>...</context>\n<question>...</question>   ← intent=rag
            或 user: <question>...</question>                          ← intent=chat
```

**关键不变量**：
- `[Cx]` 引用编号仅在第 (2+2N+1) 条本轮 user 消息的 `<context>` 内有效；历史轮与摘要中的 `[Cx]` MUST NOT 复用。
- 摘要作为独立 system 消息，明确告诉 LLM "仅用于消解指代与延续上下文，不得引用编号"。

## 2. 意图识别 agent

### 2.1 调用时机

`rag.ask` 解析会话后、检索前。输入：`question`（本轮问题）+ `recent_history`（最近 2-4 条历史消息，仅 user 角色，轻量）。

### 2.2 system prompt

```
你是 LabMemory 可信问答的意图识别 agent。判断用户本轮问题是否需要触发 RAG 检索可信知识库（实验主张/结果/证据/失败边界/参数版本）。

输出严格 JSON：{"intent": "rag" | "chat", "reason": "<≤20字中文理由>"}

判断准则：
- 需要查询具体实验数据、参数、知识状态、证据、失败边界、参数版本 → "rag"
- 普通寒暄、致谢、闲聊、关于 agent 自身能力、用户明确说"不用查/直接回答" → "chat"
- 指代消解型追问（"它/这个/刚才那个再展开"）：
  * 若问题只需复述/重组上文已有信息 → "chat"
  * 若问题需要新数据或更细粒度证据 → "rag"
- 一律输出 JSON，不得输出任何 JSON 之外的内容。
- 模糊时倾向 "rag"（宁检索勿漏）。
```

### 2.3 解析与降级

- 用 `json.loads` 严格解析；解析失败、字段缺失、值越界 → 默认 `("rag", "parse_failed")`。
- LLM 不可用（`not _enabled` 或网络异常）→ 默认 `("rag", "fallback")`。
- 默认 rag 的理由：当不确定时宁可走检索，最坏情况只是多花一次检索延迟，但避免漏掉可信证据。

### 2.4 chat 分支影响

`intent == "chat"` 时：
- 跳过 BM25/向量/关系扩展/重排，`context_chunks=[]`。
- `retrieval_details={"skipped_by_intent": true, "intent": "chat", "intent_reason": "..."}`，前端透明可见。
- 不跳过权限前置过滤？— 实际上 chat 路径连权限都不需要（不检索），但保留 `_user_experiments(db, user)` 调用记录在 `retrieval_details.permission_filtered_experiments`，便于审计"该用户在这个时间点有多少可见实验"。

## 3. 历史滚动摘要 agent

### 3.1 触发条件

`_maybe_summarize(db, session)` 在每轮 ask 持久化后调用：

```
total_messages = count(qa_messages where session_id == session.id)
fresh_keep     = QA_HISTORY_TURNS * 2     # 最近 N 轮 = 2N 条消息
should_summarized_count = max(0, total_messages - fresh_keep)
already_summarized_to   = session.summary_cursor or 0   # message id 边界
```

设 `oldest_fresh_id = 第 (total - fresh_keep + 1) 条消息的 id`。
- 若 `oldest_fresh_id > already_summarized_to`：存在需要折叠的消息区间 `[already_summarized_to + 1, oldest_fresh_id - 1]`。
- 取该区间内全部消息（必须 user/assistant pair 对齐，未对齐时少取最后一条）。
- 调 `summarize_history(session.summary, pair_messages) -> new_summary`。
- 若 `new_summary` 非空（LLM 成功）：更新 `session.summary = new_summary[:QA_SUMMARY_MAX_CHARS]`、`session.summary_cursor = pair_messages[-1].id`。
- 若 `new_summary` 为空（LLM 失败）：**不推进 cursor**，下次再试；当前轮的多余消息暂以"超出窗口"形式被丢弃（与现状一致，不引入新风险）。

### 3.2 对齐到 pair

折叠区间内的消息按 id 升序。若第一条是 assistant（说明上一条 user 已被折叠过），从第二条开始；若最后一条是 user（assistant 还未生成或被截断），少取最后一条。保证折叠的总是完整 user+assistant pair。

### 3.3 system prompt

```
你是 LabMemory 可信问答的历史摘要 agent。把已有对话历史（可能含上一轮摘要）压缩为不超过 300 字的中文摘要，必须保留：
- 涉及的实验编号、参数版本与具体数值（带单位）、知识状态（supported/refuted/...）
- 失败边界关键事实（trigger/ruled_out/next_step）
- 已确立的指代对象（如"EXP-001 是当前讨论的实验"、"它指 C003 主张"）
- 用户表达的偏好或约束（如"只看 EXP-002 的数据"）
必须丢弃：寒暄、致谢、过程性措辞、重复内容。
若已有摘要，在其基础上增量更新，不得丢失关键事实。
直接输出摘要正文，不要前后缀、不要 Markdown 标记。
```

### 3.4 调用频率

平均每 N 轮触发 1 次（N = QA_HISTORY_TURNS）。单次 LLM 调用，与回答 agent 解耦，不影响主路径延迟感知（即便延迟较高也只是后台压缩）。

## 4. 回答 agent 调用组装

`llm.chat_with_history(question, context_chunks, history, summary=None)`：

```python
messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if summary:
    messages.append({"role": "system",
                     "content": f"<history_summary>\n{summary}\n</history_summary>\n仅用于消解指代与延续上下文，不得引用其中编号。"})
for m in history:                       # 已按 user/assistant 对齐
    content = m["content"][:2000] + ("\n[已截断]" if len(m["content"]) > 2000 else "")
    messages.append({"role": m["role"], "content": content})
if context_chunks:                      # intent=rag
    messages.append({"role": "user",
                     "content": f"<context>\n{ctx_text}\n</context>\n\n<question>\n{question}\n</question>\n\n请基于本轮 context 回答 question..."})
else:                                   # intent=chat
    messages.append({"role": "user",
                     "content": f"<question>\n{question}\n</question>\n\n请基于上文 history_summary 与近几轮对话回答 question；不得引用编号。若上下文仍不足，输出 REFUSED: 原因。"})
```

`SYSTEM_PROMPT` 在原 8 条规则上追加：
- 第 9 条：当本轮 user 消息不含 `<context>` 时，MUST 只基于上文摘要与历史回答，不得虚构编号或切片；不足时 REFUSED。

## 5. 持久化与回放

- `QAMessage.intent` 仅在 user 消息上设置；assistant 消息保持 null。
- `QASession.summary` 与 `summary_cursor` 在每次 `_maybe_summarize` 成功后 commit。
- 前端 `GET /api/qa/sessions/{id}` 返回 `summary` 与 `summary_cursor`，TrustedQA 渲染摘要横幅（"已折叠到第 X 条消息，摘要 N 字"）。
- 删除会话时级联清消息（已有 `ON DELETE CASCADE`），summary 随 session 一起删。

## 6. 不引入的东西

- **不引入向量缓存摘要**：摘要只是文本上下文，不入 `embedding_chunks`；查询不会命中摘要。
- **不引入意图缓存**：每轮独立判断，意图可能随上下文变化（"它"在不同轮指向不同实体）。
- **不引入并发压缩**：摘要同步执行（最坏延迟 ~2s，每 N 轮 1 次，可接受）；后续如需异步化再单独 change。
- **不引入意图 agent 的独立路由**：意图分类是 `rag.ask` 内部决策，不暴露 API。
- **不引入摘要编辑 UI**：摘要由 agent 维护，用户不可手改；如未来需要，再单独 change。

## 7. 兼容性与降级矩阵

| 条件 | 意图 agent | 摘要 agent | 回答 agent | 行为 |
|---|---|---|---|---|
| 三 agent 全可用 | rag/chat 分类 | 滚动折叠 | 多轮带摘要+检索 | 设计目标态 |
| 仅回答 agent 可用 | 默认 rag | 跳过（cursor 不动） | 多轮无摘要+检索 | 等价于 add-qa-session-history 终态 |
| 全部不可用 | 默认 rag | 跳过 | 模板回答 | 等价于原始单轮 RAG |
| `QA_ENABLE_INTENT=false` | 总是 rag | 按需触发 | 多轮带摘要+检索 | 关意图、保留摘要 |

向后兼容：现有测试 `test_qa_degrades_without_vector_not_503` 仍能跑——意图 agent 在 LLM 可用时分类为 rag（"Compound-A 温度参数"明显需检索），走原检索路径；若 DeepSeek 不可用，意图默认 rag，仍走原检索路径，行为与升级前一致。
