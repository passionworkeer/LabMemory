## 1. LLM 直答通道

- [x] 1.1 `app/services/llm.py`：新增 `SMALLTALK_SYSTEM_PROMPT`（简短友好、禁止实验数据/结论、禁止引用编号、引导知识提问）。
- [x] 1.2 `app/services/llm.py`：新增 `chat_direct(question, intent) -> (text, mode)`；LLM 可用走 API，异常/不可用降级为 `_direct_fallback(intent)` 固定模板（greeting/thanks/goodbye/meta 四类文案）。

## 1.5 空补全修复（pre-existing 缺陷）

- [x] 1.6 `app/config.py`：新增 `DEEPSEEK_MAX_TOKENS`（默认 4000）、`DEEPSEEK_DIRECT_MAX_TOKENS`（默认 500）；`.env.example` 同步。
- [x] 1.7 `app/services/llm.py`：`_chat_via_api`/`_direct_via_api` 改用配置化预算；`_post_chat` 检测空 content（含 finish_reason=length）并抛出，上层降级模板，保证回答不落空。

## 2. RAG 意图门控

- [x] 2.1 `app/services/rag.py`：新增 `_classify_intent(question) -> str`，归一化（小写、压缩空白、剥离尾部标点与语气词）后整体完全匹配寒暄短语表，返回 `greeting`/`thanks`/`goodbye`/`meta`/`knowledge`；混合内容（寒暄+知识）必须落入 `knowledge`。
- [x] 2.2 `app/services/rag.py:ask`：流程调整为 空问题校验 → 会话解析 → 意图门控；非 `knowledge` 意图走 `_direct_answer` 组装并 `_finalize` 落库返回，跳过 `ensure_index_ready` 及全部检索阶段；`knowledge` 意图管线零变化。
- [x] 2.3 直答响应：`refused=false`、`citations=[]`；`retrieval_details` 含 `retrieval_skipped=true`、`intent`、`elapsed_sec`；`retrieval_scope` 含 `identity`/`intent`/`retrieval_skipped`；`model_info` 含 `embedding_mode='skipped'`、真实 `chat_mode`/`chat_model`、`intent`。

## 3. 前端适配

- [x] 3.1 `frontend/src/types.ts`：`QARetrievalDetails` 新增 `retrieval_skipped?: boolean`、`intent?: string`；`QAModelInfo` 新增 `intent?: string`。
- [x] 3.2 `frontend/src/pages/TrustedQA.tsx`：右侧面板在 `retrieval_skipped=true` 时展示「意图识别 → 本轮无需检索，直接作答」状态行与耗时；否则保持现有六阶段展示。
- [x] 3.3 等待提示「检索中...」改为「思考中...」；降级警告卡在直答轮不展示。

## 4. 测试

- [x] 4.1 `tests/test_hardening_smoke.py`：新增寒暄用例（「你好」「谢谢」）断言 200、`refused=false`、`retrieval_details.retrieval_skipped=true`、`citations=[]`、消息落库。
- [x] 4.2 新增 fail-safe 用例：「你好，Compound-A 温度参数」等混合内容断言**不**跳过检索（`retrieval_skipped` 缺省/false）。
- [x] 4.3 既有 `test_qa_degrades_without_vector_not_503` 保持通过（向后兼容）。

## 5. 验证与归档

- [x] 5.1 后端 import 自检：`cd labmemory-platform && python -c "from app.main import app"`。
- [x] 5.2 `pytest tests/` 全量通过。
- [x] 5.3 前端 `npx tsc --noEmit` 与 `npm run build` 通过。
- [x] 5.4 启动后端冒烟：寒暄直答无检索字段、知识问题正常检索。
- [x] 5.5 归档：增量合入 `openspec/specs/decision-qa/spec.md`，change 移入 `archive/`。
