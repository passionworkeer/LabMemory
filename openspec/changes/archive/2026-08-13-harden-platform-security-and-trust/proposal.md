# Proposal: 平台加固——并发可信不变量、降级与越权收口（对抗审查第二轮）

## Why

第一轮对抗审查（`fix-adversarial-audit-tier1`，已归档）之后，对 labmemory-platform 做了第二轮深度审查，发现一批第一轮未覆盖的真实缺陷：可信规则的核心不变量在并发下会被打破、QA 降级路径仍以硬 503 暴露给用户、实验管理接口存在横向越权、RAG 关系扩展因类型不匹配而静默失效、前端在异常态会白屏。本 change 以最小改动修复这批缺陷，使已归档规格中「同 scope 同参数仅一个 current」「证据失效降级」「项目成员关系」等不变量在实现层真正成立，而非仅停留在规格文字里。

## What Changes

**并发可信不变量（B1）**：主张发布（`confirm_review` 与 `/api/v1/card/callback` 的 approve 路径）的 supersede 临界区改为按实验串行化。uvicorn 把同步路由跑在线程池（默认 40 线程），存在并发 confirm 同一实验的现实可能；当前 check-then-act（读旧 current → 置 superseded → 写新 current）会让两个并发发布各自基于陈旧读取创建新 current，破坏「MUST NOT 同时保留两条 current」不变量。新增按实验的写锁（进程内线程锁；Postgres 下叠加 `SELECT...FOR UPDATE`），覆盖「读旧 current 至事务提交」整段。锁粒度为实验级，不阻塞不同实验的并发发布。

**冻结判定修正（B2）**：`submit_result` 当前以「实际参数 key 是计划参数 key 的子集」作为不冻结条件——这会在执行人多记一个计划外参数（如额外记录 pH）时误冻。改为「实际参数必须覆盖全部计划参数名且非空」才不冻结，与 result-backflow「结果版本校验」语义一致；额外观测不构成版本不匹配。

**默认密钥生产硬失败（S1）**：当前默认密钥仅 warn（tier1 刻意保留 dev/test 可运行性，且 `platform-permissions` 规格明确「MUST NOT 因默认值直接拒绝启动」）。直接全局改硬失败会翻转该刻意决策并破坏本地开发。改为新增 `APP_ENV`：当 `APP_ENV=production` 且 `JWT_SECRET`/`PLATFORM_API_KEY` 任一为默认值时启动硬失败；其余环境（默认 development）保持 warn。既堵住生产弱密钥，又不破坏 dev/test。

**实验管理越权收口（IDOR）**：`get_experiment`/`add_member` 此前**无 user 参数**（仅 router 层 `require_pi`），任意 PI 可读/改他人项目的实验；`create_experiment` 不校验项目属主，PI 可在他人的项目下建实验。补齐「仅项目所有者 PI（或 admin）可操作该项目下实验」的属主校验，对齐 `platform-permissions`「项目成员关系」。

**QA 优雅降级（R1）**：sqlite-vec 不可用时 `/api/qa/ask` 当前返 503。根因是 `ensure_vec_tables` 把 `vec_chunks`（vec0，依赖扩展）与 `chunks_fts`（FTS5，SQLite 内置）放在同一 try——扩展加载失败时连 FTS 表都不建，BM25 也用不了。拆分后 FTS5 始终可用，QA 降级为 BM25+关系扩展+重排（`rag.ask` 内部本已把向量召回写成可选）并在 `retrieval_details` 标注 `vector_available=false`、返回结果而非 503。

**关系扩展类型修正（R4）**：`rag._relation_expand` 用 `claim.meeting_id`（**整数** FK）去匹配 evidence `ref_id`（`"{字符串 meeting_id}#seg{idx}"`，见 indexer），`.like(f"{int}#%")` 永不命中，导致 claim 的支持证据片段无法被关系扩展带入候选集。改为经 Meeting 取字符串 `meeting_id` 匹配。

**前端健壮性（P0，崩溃防护）**：全局 `ErrorBoundary` 防单页渲染异常白屏；API 层 401（非登录接口本身）自动清 token 跳登录；`ResultBackflow` 改用 `apiListMeetings()` 并处理任务未命中（不再无限 Loading）；`Layout` 在 `user` 未就绪时显示加载态而非返回 null。前端无对应后端规格域，作为崩溃防护类 bugfix 处理，不新增规格。

## Impact

- 规格增量：MODIFY `trust-rules`（新增并发串行化不变量）、`result-backflow`（冻结判定收敛为「实际覆盖计划且非空」）、`decision-qa`（vec 不可用降级为 BM25 而非 503；关系扩展 join key 用字符串 meeting_id）、`platform-permissions`（默认密钥生产硬失败；实验管理操作限项目所有者）。
- 后端改动：`app/config.py`（`APP_ENV` + 生产硬失败）、`app/db/vec.py`（拆分建表）、`app/api/qa.py`（移除 503）、`app/services/rag.py`（`_relation_expand` 字符串 meeting_id + `vector_available` 透传）、`app/api/results.py`（冻结判定）、`app/api/meetings.py`（confirm_review 加锁）、`app/api/integration.py`（卡片 approve 加锁）、`app/api/experiments.py`（属主校验），新增 `app/db/locking.py`（按实验写锁）。
- 前端改动：`frontend/src/main.tsx`（挂 ErrorBoundary）、`api.ts`（401 跳登录）、`pages/ResultBackflow.tsx`（改用 apiListMeetings + 未命中处理）、`components/Layout.tsx`（`!user` 加载态），新增 `components/ErrorBoundary.tsx`。
- 回归守护：重置演示数据后冒烟可信问答（含降级）、结果提交（覆盖/缺失计划参数两种）、实验管理越权拒绝；前端 `npm run build` 通过。
