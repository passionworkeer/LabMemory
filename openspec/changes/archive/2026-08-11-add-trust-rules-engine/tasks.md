# Tasks: 可信规则引擎

## M1 - OpenSpec
- [x] 创建 change `add-trust-rules-engine`（proposal + trust-rules spec 增量 + tasks）
- [x] `openspec validate add-trust-rules-engine` 通过

## M2 - 规则引擎
- [x] `app/services/trust_rules.py`：`run_six_gates` + `detect_conflicts` + `SEMANTIC_HEDGE_KEYWORDS`
- [x] Claim 状态取值扩展 current/superseded/pending_supplement/pending_validation（文档化，无迁移）

## M3 - 接入发布路径
- [x] `app/api/meetings.py:confirm_review`：_build_claim 后跑闸门+冲突；未过则 claim 置 pending_*，不生成任务草稿
- [x] `app/api/integration.py:card_callback` approve：同样接入
- [x] 响应携带闸门/冲突报告

## M4 - 问答与护照隔离
- [x] `app/api/qa.py`：仅 current 主张作答
- [x] 护照 current_claim 仅取 current

## M5 - 验证与归档
- [x] 平台 e2e + cross_side + pytest 全绿（seed「暂定」候选变待验证，更新断言）
- [x] `openspec validate --all` + archive
