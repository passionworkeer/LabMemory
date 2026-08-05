# Tasks: retro-spec-feishu-orchestrator

## 1. 规格核对（实现已存在，逐条确认规格与代码一致）

- [x] 1.1 核对 `meeting-ingest` 规格与 `core/webhook_server.py`、`core/event_router.py`、`adapters/minutes_adapter.py` 一致（端点、三类事件、幂等键格式）
- [x] 1.2 核对 `decision-compiler` 规格与 `adapters/aily_adapter.py`、`core/pipeline_orchestrator.py` 一致（技能调用、候选包字段、Aily 只产候选）
- [x] 1.3 核对 `feishu-actions` 规格与 `core/card_handler.py`、`adapters/{task,im_card,base,docs}_adapter.py` 一致（三值分流、任务回写、看板与文档回流）
- [x] 1.4 核对 `orchestration-reliability` 规格与 `core/state_machine.py`、`reliability/*.py`、`core/config.py` 一致（9 状态、7 天 TTL、退避参数、脱敏字段、`RUN_MODE`）

## 2. 契约收敛（代码变更）

- [x] 2.1 在 `contracts/feishu-action-request.schema.json` 中把 `schema_version`、`action_id`、`idempotency_key`、`actor_user_id` 加入 `required`；原 `request_id`（注释为「请求 ID（幂等）」）更名为语义明确的 `idempotency_key`
- [~] 2.2 更新构造 `FeishuActionRequest` 的调用方与 Mock 样例 —— **N/A**：核对确认该契约在代码中零引用，平台向编排器下发动作的入向通路尚不存在（实际链路是卡片回调 → 编排器转发平台 → 编排器执行动作），无调用方可改
- [x] 2.3 `schema_version` 默认值升至 `1.1.0`，版本升级原因记录于 `proposal.md` 与 `design.md`

## 3. 验签落地（代码变更，安全缺口）

- [x] 3.1 实现 `core/webhook_server.py:verify_signature()`：`sha256(timestamp + nonce + encrypt_key + raw_body)` 十六进制摘要 + `hmac.compare_digest` 常量时间比较 + 300 秒时间窗；读取 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` / `X-Lark-Signature`
      - **修正**：原桩函数 docstring 写的是 `HMAC-SHA256(secret, timestamp + nonce + body)`，与飞书实际算法不符（飞书为拼接后单次 sha256、hex 摘要，密钥作为拼接项而非 HMAC key）。照桩补完会导致 real 模式拒绝所有真实飞书请求，故以飞书规范为准并同步修正规格与 docstring
- [x] 3.2 在 `/webhook/event` 与 `/webhook/card` 接入 `_verify_request()`：`RUN_MODE=real` 验签失败返回 401、记录失败集成日志且不进入事件路由；密钥为空一律判失败
- [x] 3.3 `RUN_MODE=mock` 下跳过验签，启动日志显式提示「验签已跳过」；real 模式缺密钥时提示「所有请求将被拒绝」

## 4. 测试

- [x] 4.1 新增 `TestWebhookSignature`（`tests/test_integration.py`）：正确签名通过、错误签名拒绝、请求体篡改拒绝、密钥为空拒绝、超时间窗拒绝、非法时间戳拒绝、mock 模式跳过，共 7 例
- [~] 4.2 `FeishuActionRequest` 必填字段校验用例 —— **N/A**：仓库内无 JSON Schema 校验代码，且该契约无调用通路（见 2.2）。为尚不存在的入向通路写校验器与测试属于为假想需求做设计；待平台侧真正启用该通路时另走 change 落校验
- [x] 4.3 `python tests/test_integration.py` 22/22 通过；`python tests/test_phase3.py` 19/19 通过
- [x] 4.4 `python scripts/health_check.py` 11/11 通过；`python scripts/demo_end_to_end.py` 主链路无回归（WAITING_MINUTES → … → COMPLETED）

## 5. 归档

- [x] 5.1 `openspec validate retro-spec-feishu-orchestrator --strict` 通过
- [x] 5.2 更新 `feishu-orchestrator/README.md`，指向 `openspec/specs/` 中新增的 4 个领域规格
- [x] 5.3 `openspec archive retro-spec-feishu-orchestrator --yes`（归档为 `2026-08-05-retro-spec-feishu-orchestrator`；源真相新增 4 个领域 + contracts 更新，共 +26 / ~5）

## 遗留（未纳入本 change，需另开提案）

- `openspec/specs/trust-rules/spec.md` 校验不通过：「任务状态机」与「三值留痕」两条需求缺少 `#### Scenario:` 块。属既有源真相缺陷，修复需单独走 change（未在飞书侧提案里夹带平台侧规格变更）。
- 归档时修正了 `openspec/specs/contracts/spec.md` 中 `FeishuActionRequest` 需求的标题层级（`####` → `###`）。原为 h4，导致解析器把它并入 `CandidatePackage` 需求，archive 判定会丢弃场景而中止。属纯格式修复，未改动任何语义文本。
- `DEPLOYMENT.md` 声称「无外部 pip 依赖（仅标准库）」，但 `core/config.py` 导入了 `dotenv`。属文档与实现不符，需修文档或去掉该依赖。
- Windows 控制台默认 cp1252 编码下，测试与脚本的中文输出会抛 `UnicodeEncodeError`（需 `PYTHONIOENCODING=utf-8`）。属既有问题，与本次变更无关。
