# Design: 平台加固（对抗审查第二轮）

记录几个非显然的技术决策，便于归档后回溯。

## D1. 并发串行化为什么用「线程锁 + 行锁」而非唯一约束

最初设想在 `Claim` 上加 `(experiment_id) WHERE status='current'` 的部分唯一索引。**否决**：trust-rules 明确允许同一实验在**不同参数/不同 scope** 下各持有一条 current（例如「温度 70℃」current 与「催化剂 0.8eq」current 并存），仅禁止「同 scope 同参数名的多个 current」。current 主张的 scope 与参数名位于 `parameter_version` JSON 内、且一条主张可含多个参数，无法落到单列唯一约束。因此唯一性只能由业务逻辑在写路径保证，并发安全靠**串行化临界区**而非约束兜底。

威胁模型：uvicorn 默认把**同步**路由派发到线程池（`--limit-concurrency`/anyio threadpool，默认 40 线程），即使单 worker 也能并行处理两个 `confirm_review`。SQLite 单写者模型只串行化 commit，串行化不了「读旧 current→决策→写新 current」的读后写间隙——两个事务都读到旧 current、各自 supersede + 新建，commit 后留下两条 current。

实现：`app/db/locking.py` 提供 `lock_experiment_for_write(db, experiment_id)` 上下文管理器：
- 进程内：按 `experiment_id` 取一把 `threading.Lock`，覆盖从「读旧 current」到「事务 commit」整段（调用方在 `with` 块内完成 supersede + 新建 claim + commit）。
- 跨进程（Postgres）：`SELECT ... FOR UPDATE` 锁实验行，使另一进程的同实验发布阻塞到本事务提交。
- SQLite 多进程部署天然单写者，不在本 change 覆盖范围（README 已声明生产建议 Postgres）。

锁粒度为实验级，不同实验的发布互不阻塞；同实验的发布串行，符合「同实验同 scope 同参数仅一个 current」的不变量而无须全局锁。

## D2. 冻结判定方向：覆盖而非子集

现状 `frozen = bool(planned_keys and not actual_keys.issubset(planned_keys))`：实际只要出现任何计划外 key 就冻。语义错误——执行人在计划参数外多记一项观测（如 pH、备注）是正常的科研行为，不应冻结果。

result-backflow「结果版本校验」的本意是「结果与任务参数不匹配才冻」。当前结果模型没有独立的「参数版本」字段可逐字比对，故采用可落地的代理：**实际参数键集必须覆盖全部计划参数名且非空**，否则视为参数不匹配→冻。改为 `frozen = bool(planned_keys) and not planned_keys.issubset(actual_keys)`（计划非空且实际未全覆盖→冻）；额外 key 不触发。

## D3. 默认密钥：APP_ENV 门控而非全局硬失败

tier1 与 `platform-permissions` 规格都**刻意**把默认密钥定为「warn 不 crash」以保留 dev/test 可运行性。全局硬失败会翻转该决策、破坏 `npm run dev`/本地起服务。但生产以弱密钥运行确是真实风险。折中：新增 `APP_ENV`（默认 `development`），仅当 `APP_ENV=production` 且密钥为默认值时 `model_validator` 抛错拒绝启动；其余环境维持 warn。这是对既有规格的 MODIFY（而非推翻），既堵生产弱密钥又不伤开发。

## D4. QA 降级：拆分建表，复用既有可选向量召回

`rag.ask` 内部 step 4 本就把向量召回写成 `if vec.vec_available(db)`，唯一硬 503 来自 `qa.py` 入口的早退检查；真正的拦路虎是 `ensure_vec_tables` 把 vec0 与 FTS5 放同一 try——扩展不可用时 FTS 表也不建，BM25 无表可用。拆成两个独立 try（FTS5 是 SQLite 内置，恒可建；vec0 仍可能失败）后，FTS 索引与 BM25 召回在无 sqlite-vec 时仍工作。`indexer._upsert_chunk` 早已对 vec/fts 写入包 try/except，无需再改。移除 `qa.py` 503 后，QA 返回 BM25 结果并在 `retrieval_details.vector_available=false` 透传降级态。

## D5. 前端不在规格域内

OpenSpec 规格域（§6）均为后端领域，无前端规格。本轮前端改动是崩溃防护/异常态处理（ErrorBoundary、401 跳转、空态/加载态），不改变业务语义，作为 bugfix 处理，不新增规格，仅记入 tasks。

## D6. 不在本次范围

- 唯一索引化 current 不变量（见 D1，不可行）。
- 多进程 SQLite 并发（生产建议 Postgres）。
- 第一轮 AUDIT.md 记的 Tier 2 功能路线图（六闸门/冲突检测等缺失功能），与本轮「修缺陷」目标不同。
