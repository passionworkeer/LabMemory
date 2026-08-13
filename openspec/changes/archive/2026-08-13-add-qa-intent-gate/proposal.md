## Why

可信知识问答当前对**每一次**用户输入都无差别执行完整 RAG 检索管线（权限过滤 → 状态过滤 → BM25 召回 → 向量嵌入 API → 向量召回 → 关系扩展 → 重排 → LLM 生成）。问题：

- **成本浪费**：「你好」「谢谢」「再见」这类寒暄/元问题也会触发 Qwen 嵌入 API 与 DeepSeek 生成 API 调用，并伴随多轮 DB 查询。
- **体验受损**：寒暄输入经检索后 top score 必然低于 `RAG_MIN_SCORE`，用户收到的是「检索到的证据与问题相关度不足」的系统拒答——对一句问候回答"拒答"，明显不合理。
- **指标污染**：寒暄轮次混入 `retrieval_details` 各阶段统计，检索面板展示一堆无意义的 0。

目标：**只有在必要的时候才进行检索**——寒暄/感谢/告别/助手能力询问等无需知识库的输入直接友好作答；拿不准的输入一律回退到完整检索管线（fail-safe 向检索倾斜，宁可多检索、不可漏检索）。

## What Changes

### 后端

- **新增意图门控** `app/services/rag.py`：
  - `_classify_intent(question) -> str`：确定性规则分类器，返回 `greeting` / `thanks` / `goodbye` / `meta` / `knowledge`。归一化（小写、压缩空白、剥离尾部标点与语气词）后**整体完全匹配**寒暄短语表才判定为非知识意图；含任何实验编号/参数/疑问内容的混合输入必然落入 `knowledge`。
  - `ask()` 流程调整：空问题校验 → 会话解析（照旧持久化所有轮次）→ **意图门控**：非 `knowledge` 意图直接生成作答并落库返回，**跳过** `ensure_index_ready`、权限过滤、状态过滤、BM25、嵌入与向量召回、关系扩展、重排；`knowledge` 意图走既有管线，零行为变化。
- **扩展对话服务** `app/services/llm.py`：新增 `chat_direct(question, intent) -> (text, mode)` 与 `SMALLTALK_SYSTEM_PROMPT`。LLM 可用时生成简短寒暄回复（禁止提及任何实验数据/结论、禁止输出引用编号、引导用户提知识问题）；不可用或异常时降级为按意图分类的固定模板文案。
- **响应标记**：直答路径 `refused=false`、`citations=[]`；`retrieval_details` 透传 `retrieval_skipped=true` 与 `intent`；`model_info` 标记 `embedding_mode='skipped'`（未执行嵌入）、`chat_mode` 如实反映 LLM/模板。
- **顺带修复（pre-existing 缺陷）**：推理型模型（deepseek-v4-flash）的 `reasoning_tokens` 计入 `completion_tokens`，原写死的 `max_tokens=800` 在长 context 下被 reasoning 耗尽，返回空 content（`finish_reason=length`），用户看到空气泡。修复：生成预算配置化（`DEEPSEEK_MAX_TOKENS` 默认 4000 / `DEEPSEEK_DIRECT_MAX_TOKENS` 默认 500），且空补全（含 length 截断）一律视为失败并降级到模板回答，保证任何情况下回答非空。

### 前端

- **`frontend/src/types.ts`**：`QARetrievalDetails` 新增 `retrieval_skipped?: boolean`、`intent?: string`；`QAModelInfo` 新增 `intent?: string`。
- **`frontend/src/pages/TrustedQA.tsx`**：
  - 右侧「检索阶段」面板：当本轮 `retrieval_skipped=true` 时展示「意图识别 → 本轮无需检索，直接作答」的明确状态，而非一列无意义的 0。
  - 等待提示由「检索中...」改为「思考中...」（发送前无法预知本轮是否检索）。
  - 降级警告卡仅在真正执行检索的轮次判定（直答轮不误报降级）。

### 规格基线

- **MODIFIED** `openspec/specs/decision-qa/spec.md`：
  - 「检索过程透明」补充 `retrieval_skipped` / `intent` 透传字段。
- **ADDED** `openspec/specs/decision-qa/spec.md`：
  - 新增「检索意图门控」需求（确定性规则分类、直答跳过全部检索阶段、混合内容 fail-safe 走检索、直答轮照常持久化、拒答契约不受影响）。

## Capabilities

### Modified Capabilities
- `decision-qa`：检索管线入口新增意图门控——寒暄/元问题直接作答，仅知识型问题触发混合检索。检索管线本体、权限前置过滤、拒答契约、降级路径、会话生命周期全部保持不变。

## Impact

- 代码：`labmemory-platform/app/services/rag.py`（门控 + 直答组装）、`app/services/llm.py`（`chat_direct` + 模板）、`frontend/src/pages/TrustedQA.tsx`、`frontend/src/types.ts`。**不动**：混合检索各阶段、索引器、引用后处理、会话持久化结构。
- API：`POST /api/qa/ask` 请求/响应结构完全向后兼容，仅 `retrieval_details`/`model_info` 新增可选字段。
- 数据：无 schema 变更；直答轮仍以 user+assistant 两条 `QAMessage` 落库。
- 依赖：无新增依赖。
- 安全/信任：门控只跳过检索，不放宽权限；直答 prompt 禁止输出实验数据与引用编号；混合内容一律走检索，无信息泄漏面。
