# Design: 对抗审查 Tier 1 修复

## 关键决策

### 决策 1：默认密钥告警而非 crash
`JWT_SECRET`/`PLATFORM_API_KEY` 硬编码默认值是真实伪造面，但硬性断言会破坏所有 dev/test（依赖默认值运行）。折中：启动时若为默认值 → 显眼 warning（日志 + 控制台），`INTEGRATION.md` 强调生产必改。`Settings` 加 `@model_validator` 在非 test 环境输出 warning。

### 决策 2：CORS 白名单
`CORS_ORIGINS` 默认 `*` + `allow_credentials=True` 等同任意源携带 Authorization。改默认 `http://localhost:5173,http://localhost:8081`；`app/main.py` 拒绝 `*` 与 credentials 共存（若 `*` 出现则强制降级 `allow_credentials=False` 并 warning）。

### 决策 3：跨实验越权——成员可见域
`GET /api/meetings*`、`GET /api/tasks/{id}`、`/audit/compare`、`control_tower` 当前仅 `get_current_user`。改为：admin/pi 全局可见；lead/executor 仅可见其 `ExperimentMember` 所属实验的对象。复用既有 `ensure_experiment_member`（`deps.py:60`）+ 新增 list 过滤 helper（join `ExperimentMember`）。

### 决策 4：迁移列错位修复
`main.py:_run_migrations` 的 `tasks_new` 重建分支：① `CREATE TABLE tasks_new` 加 `feishu_task_guid VARCHAR(128)` 列；② `INSERT INTO tasks_new(显式 19 列) SELECT 显式 19 列 FROM tasks`（按列名，非位置）。消除 `SELECT *` 在列数不对齐时的错位/崩溃。

### 决策 5：_actor_for 不充当 admin
`integration.py:_actor_for` 当前 open_id 无映射→首个 admin。改为：open_id 有映射→该 user；否则→`None`。`card_callback`/`task/status` 以 `actor_id=None` 落审计，`AuditEvent.reason` 记原始 open_id。审计可追溯但不冒名提权。

### 决策 6：card_callback 不回退状态
approve 命中"复核已 processed"时，取会议最新 task；仅当 `task.status in {draft,needs_confirmation,blocked}` 才跑审计；`running/completed` 直接返当前 `{status, action_audit}`（不回退）。`review.status==pending` 走完整 confirm+audit。幂等：同 token 返上次结论。

### 决策 7：幂等原子化
`idempotency.py` 当前 `is_processed`→业务→`mark` 三步文件操作有 TOCTOU。改为 `mark` 用 `os.open(path, O_CREAT|O_EXCL)` 原子抢锁文件作占位（成功=获得执行权），业务后填结果；`is_processed` 检查文件存在。多 worker 仍需 DB 唯一约束（记入路线图），单进程原子文件锁消除主要竞态。

### 决策 8：card_handler 不再静默 success
当前仅 `approved+pass` 建任务，其余空档静默 log success。改为显式分支：`approved+pass`→建任务；`rejected`→驳回；`blocked`→阻断卡；`needs_confirmation`/`revise`/default→记 needs_confirmation/blocked 状态，不再 log "success"。`pipeline_orchestrator` 返回 `status="submitted"`（非 "success"+completed_at）。

### 决策 9：RUN_MODE mock 限 localhost
保持默认 mock（保 dev/test），但 `webhook_server` 在 mock 模式拒绝非 localhost 来源 + 启动大红 banner warning。生产设 `RUN_MODE=real` 后照常验签。

### 决策 10："approve" 统一
删 `platform_client` 的 `"approved"` 兼容分支；编排器测试/demo/平台夹具统一 `"approve"`（对齐平台 `Literal["approve","revise","reject"]`）。

## 非目标
- Tier 2 功能（六闸门/冲突检测/证据降级/三值重构/版本模型/语义栅栏/spec-代码路径重构）——需产品规则定义，路线图。
- 真飞书凭证联调。
- 多 worker 分布式幂等（DB 唯一约束）——路线图。
