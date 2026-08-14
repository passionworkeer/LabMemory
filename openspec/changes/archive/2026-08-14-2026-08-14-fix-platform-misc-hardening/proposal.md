# Proposal: fix-platform-misc-hardening（平台杂项加固第三轮）

## Why

对抗审查第三轮的平台侧杂项发现：① PI 可见性口径分裂——`deps.visible_experiment_ids` 只给 admin 全局可见，但 RAG/brief/passport 给任何 PI 全局读（水平越权读取面）；② 审计证据门是 OR 语义与注释/设计不符（结合 scope 常丢失，仅凭 parameters 即过「证据与范围」门）；③ 结果冻结判定不校验值非空（`{"温度": null}` 也算覆盖）；④ 登录无失败限速（配合演示弱口令放大风险）；⑤ 生产环境 `/docs`、`/redoc` 公开暴露。

## What Changes

1. **PI 可见性统一**：`rag._user_experiments`、`brief`、`passport` 的「PI/admin 全局可见」统一收窄为 admin 全局可见 + PI 按 ExperimentMember/项目归属可见（与 `deps.visible_experiment_ids` 同一口径）。
2. **审计证据门 AND 语义**：`_run_checks` 中 scope 与 parameters 均需非空（对齐注释），缺失判 needs_confirmation。
3. **冻结判定校验非空**：实际参数键覆盖且值非空才算覆盖，含 null/空串 → frozen。
4. **登录失败限速**：每用户名+IP 5 次失败后 15 分钟锁定（进程内计数，够 demo/受控试点）。
5. **生产关闭交互文档**：`APP_ENV=production` 时不注册 `/docs`、`/redoc`、`/openapi.json`。

## Impact

- 代码：`app/services/rag.py`、`app/api/brief.py`、`app/api/passport.py`、`app/api/tasks.py`、`app/api/results.py`（或 tasks 提交处）、`app/api/auth.py`、`app/main.py`
- 规格：platform-permissions、action-audit、result-backflow、runtime-configuration
- 风险：中低——PI 全局读收窄可能影响现有 PI 演示流程；种子数据中 pi 即 PROJ-DEMO-001 所有者且为成员，行为不变。
