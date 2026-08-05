# Design: feishu-orchestrator 规格回溯与契约收敛

## 领域划分决策

CLAUDE.md 第 6 节建议了 `meeting-ingest` 与 `decision-compiler` 两个飞书侧领域，但实现里还有两块无处安放的行为：飞书**出向动作**（卡片 / 任务 / 多维表格 / 文档）与**编排可靠性**（状态机 / 幂等 / 重试 / 集成日志）。

决策：拆成 4 个领域，而不是塞进 2 个。

- 理由：出向动作与入向接入的触发条件、幂等键、失败语义完全不同；可靠性机制被全部 4 个链路复用，若嵌在某一个领域里，其他领域引用时会产生重复表述。
- 拒绝的替代方案：单个 `feishu-orchestrator` 大领域。会形成 40+ 条需求的巨型 spec，与平台侧按领域拆分的粒度不一致，评审时难以定位。

## 领域边界与平台侧的分工

飞书侧规格**只描述编排与投递事实**，不重复平台侧判断规则：

- 六道闸门、三值留痕的**判定逻辑**属 `trust-rules` / `decision-inbox`；飞书侧只规定「按平台返回的 `status` 与 `action_audit` 分流」。
- 行动前审计的五类检查属 `action-audit`；飞书侧只规定「仅当 `status=approved` 且 `action_audit=pass` 才创建飞书任务」，与 `contracts` 既有约束一致。
- 知识状态判定属 `result-backflow`；飞书侧只规定文档回流的三种落地形态（成功 / 失败 / 待验证）。

## 契约偏离的收敛方向

三处偏离统一**以代码中的 JSON Schema 为准**，反向修规格，而不是改代码去迁就规格。

- 理由：`contracts/*.schema.json` 已被两侧 Mock 并行开发依赖（`tests/test_integration.py`、`mock/sample_aily_output.json`、`data/integration_logs/` 历史记录均按此字段名产出）。改字段名会同时废掉两侧已有的 Mock 与样例数据，而规格文本的收益为零。
- 例外：`FeishuActionRequest` 反向修**代码**。既有 `contracts/spec.md` 要求 `action_id` / `idempotency_key` / `actor_user_id`，实际 schema 只必填 `action_type` / `payload`。这里规格是对的——缺少 `idempotency_key` 会让平台重复请求无法去重，缺少 `actor_user_id` 会让动作无责任人可追溯，属于可信链路的实质缺口。故补 schema 必填字段。

## 验签实现决策

`verify_signature()` 按飞书事件订阅 / 卡片回调的真实规范落地：签名为 `sha256(timestamp + nonce + encrypt_key + raw_body)` 的小写十六进制摘要，请求头取 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` / `X-Lark-Signature`，密钥取 `CARD_CALLBACK_ENCRYPT_KEY`。

- **修正**：原 `core/webhook_server.py` 中的桩函数 docstring 写的是 `HMAC-SHA256(secret, timestamp + nonce + body)`，与飞书实际算法不符（飞书用的是拼接后单次 sha256，密钥作为拼接项而非 HMAC key，且摘要为 hex 而非 base64）。若照桩实现补完，real 模式会拒绝所有真实飞书请求。故以飞书规范为准，同时修正规格与该 docstring。
- 摘要比较使用 `hmac.compare_digest` 常量时间比较，避免计时攻击。
- 附带 300 秒时间窗校验：签名机制本身的目的之一就是防重放，只验摘要不验时间窗等于留着重放缺口。
- `RUN_MODE=mock` 下允许跳过验签，否则本地 demo 与 `tests/` 全部需要构造签名头，成本高于收益。
- `RUN_MODE=real` 下验签失败 MUST 返回 401 且不进入事件路由——这是规格中的强制项，避免「桩函数恒返回 True」再次发生。未配置 `CARD_CALLBACK_ENCRYPT_KEY` 时 MUST 判定失败（空密钥会让签名退化为可伪造的固定哈希），启动时显式告警。

## FeishuActionRequest 的实现现状

核对发现 `contracts/feishu-action-request.schema.json` **在代码中零引用**：平台侧目前不存在向编排器下发动作请求的入向通路（实际链路是卡片回调 → 编排器转发平台 → 编排器执行动作），仓库内也没有任何 JSON Schema 校验代码。

决策：本次只修正契约文件本身（补必填字段、`request_id` 更名为 `idempotency_key`、版本升至 1.1.0），**不新增校验器与对应单测**。

- 理由：为一条尚不存在的调用通路写校验器与测试，属于为假想需求做设计。契约先冻结、待平台侧真正启用该通路时再走 change 落校验。
- 影响：tasks 2.2 与 4.2 无对象可改，标记为 N/A 并写明原因，不做假动作打勾。

