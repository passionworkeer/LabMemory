## 1. PI 可见性统一

- [x] 1.1 `rag._user_experiments`：改为 admin 全局 + 成员/项目归属（复用 `deps.visible_experiment_ids` 口径）。
- [x] 1.2 `brief.py`、`passport.py` 同口径修正。
- [x] 1.3 回归：他项目 PI 问答不可见他人实验（沿用 IDOR 测试思路）。

## 2. 审计证据门

- [x] 2.1 `tasks.py:_run_checks`：scope 与 parameters 均需非空，缺失判 blocked（与 action-audit 规格一致，已在 trust-core round3 change 中实现）。

## 3. 冻结判定非空

- [x] 3.1 结果提交覆盖判定：键存在且值非空；含 null/空串 → frozen。

## 4. 登录限速

- [x] 4.1 `auth.py`：用户名+IP 失败计数，5 次锁 15 分钟，锁定返回 429。

## 5. 生产关文档

- [x] 5.1 `main.py`：APP_ENV=production 时不注册 docs/redoc/openapi.json。

## 6. 测试与验证

- [x] 6.1 新增回归：限速 429、空值冻结、证据门 needs_confirmation（限速/空值冻结已入 test_hardening_smoke；证据门随 trust-core round3 实现并覆盖）。
- [ ] 6.2 `pytest tests/ -q` + e2e 全绿；`openspec validate` 通过后归档。
