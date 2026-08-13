# Tasks: 平台加固（对抗审查第二轮）

## M1 - OpenSpec change
- [x] 创建 change `harden-platform-security-and-trust`（proposal + design + 4 领域 spec 增量 + tasks）
- [x] `openspec validate harden-platform-security-and-trust` 通过

## M2 - 并发可信不变量（B1）
- [x] 新增 `app/db/locking.py`：`lock_experiment_for_write(db, experiment_id)` 上下文管理器（per-experiment `threading.Lock` + Postgres `SELECT...FOR UPDATE`）
- [x] `app/api/meetings.py` `confirm_review`：在 `_build_claim`（supersede 临界区）至 `db.commit()` 整段套 `lock_experiment_for_write`
- [x] `app/api/integration.py` 卡片 approve：同样套锁覆盖 `_build_claim` 至 commit

## M3 - 冻结判定修正（B2）
- [x] `app/api/results.py` `submit_result`：冻结条件改为「计划参数非空且实际未全覆盖」`frozen = bool(planned_keys) and not planned_keys.issubset(actual_keys)`

## M4 - 默认密钥生产硬失败（S1）
- [x] `app/config.py`：新增 `APP_ENV: str = "development"`；`_warn_default_secrets` 改为 production+默认值→抛错，其余→warn

## M5 - 实验管理越权收口（IDOR）
- [x] `app/api/experiments.py`：`create_experiment`/`get_experiment`/`add_member` 补 `user` 参数 + `Project.pi_user_id == user.id or admin` 属主校验，否则 403

## M6 - QA 优雅降级（R1）
- [x] `app/db/vec.py` `ensure_vec_tables`：拆为两个独立 try——FTS5 恒建；vec0 失败不影响 FTS
- [x] `app/api/qa.py`：移除 `vec_available` 为假时的 503 早退，交由 `rag.ask` 降级
- [x] `app/services/rag.py` `ask`：`retrieval_details` 增加 `vector_available` 透传降级态

## M7 - 关系扩展类型修正（R4）
- [x] `app/services/rag.py` `_relation_expand`：经 `db.get(Meeting, claim.meeting_id)` 取字符串 `meeting_id` 匹配 evidence `ref_id`

## M8 - 前端健壮性（P0）
- [x] 新增 `frontend/src/components/ErrorBoundary.tsx`（class 组件 + 降级 UI）
- [x] `frontend/src/main.tsx`：用 `ErrorBoundary` 包裹 `<App/>`
- [x] `frontend/src/api.ts` `request`：401（非 `/api/auth/*`）自动 `clearToken` + 跳 `/login`
- [x] `frontend/src/pages/ResultBackflow.tsx` `load`：改用 `apiListMeetings()`，任务未命中时 `setErr` 而非无限 Loading
- [x] `frontend/src/components/Layout.tsx`：`!user` 显示加载态而非 `return null`

## M9 - 验证与归档
- [x] 重置演示数据（`--db-only`），冒烟：QA 提问、结果提交（覆盖/缺失两种）、实验管理越权拒绝
- [x] `npm run build` 通过
- [x] 逐项核对实现与 spec 增量一致
- [x] `openspec archive harden-platform-security-and-trust --yes`
- [x] 中文 conventional-commit 提交 + push
