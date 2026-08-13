# Tasks: 平台 → 飞书编排器反向联动

## M1 - OpenSpec change

- [x] 创建 change `add-platform-feishu-reverse-linkage`（proposal + design + platform-outbound spec 增量 + tasks）
- [x] 校验 spec 增量格式（`### Requirement:` + `#### Scenario:`，SHALL/MUST 措辞）

## M2 - 编排器侧：动作处理器

- [x] 新增 `feishu-orchestrator/feishu-orchestrator/core/platform_action_handler.py`
- [x] 实现 `handle_action(request)`：必填字段校验 + 幂等（check/acquire/mark/release）+ 分派
- [x] 实现 `_dispatch`：send_card / create_task（含回写）/ publish_doc / notify / update_base
- [x] 集成日志（inbound 平台动作，成功/失败/幂等命中）

## M3 - 编排器侧：/webhook/platform 端点

- [x] `webhook_server.py` `do_POST` 新增 `/webhook/platform` 分支
- [x] 新增 `_handle_platform_action`（读体 + 鉴权 + 调 handler + 返回）
- [x] 新增 `_verify_platform_key`（mock 限 localhost；real 校验 Bearer {PLATFORM_API_KEY}）
- [x] 启动横幅补充端点说明

## M4 - 平台侧：出站客户端

- [x] 新增 `labmemory-platform/app/services/feishu_client.py`
- [x] `send_feishu_action(...)` 组装契约体 + mock 跳过 / real urllib POST + 非阻断错误处理
- [x] 辅助 `candidate_dict_from_candidates(candidates_list)` 挑 parameter_change（否则第一个）返回扁平候选

## M5 - 平台侧：四个触发点

- [x] `app/api/meetings.py:receive_candidate`：新候选待复核 → `send_card`（≤3，try/except）
- [x] `app/api/tasks.py:start_task`：任务 running → `create_task`（try/except）
- [x] `app/api/tasks.py:run_audit`：结论 blocked → `notify`（try/except）
- [x] `app/api/results.py:publish_result`：发布后 → `publish_doc`（knowledge_status→doc_type，try/except）

## M6 - 验证脚本与回归

- [x] 新增 `labmemory-platform/scripts/reverse_linkage_check.py`（直打编排器 /webhook/platform + 平台业务触发点断言，7/7）
- [x] 平台 `pytest tests/ -q` 全绿（回归守护）—— 本会话实测 7/7 通过
- [x] 编排器 `python tests/test_integration.py` 回归（据实更正：套件已增至 38 项；清空 `data/idempotency` + `data/state` 运行时残留后干净态 37 通过 / 0 失败 / 1 error；唯一 error 为 `TestProductionReliability.test_minutes_detail_uses_isolated_output_dir`，依赖妙记 CLI 拉逐字稿，属 `production-reliability-hardening` 范畴、与本 change 无关；原 tasks 所写「22/22」为套件增长前的旧书签。另：编排器测试套件存在预先存在的运行时状态泄漏弱点——幂等/状态持久化到 `data/` 未在用例间清理，导致重复运行出现 ~6 个 `'duplicate'` 假失败，非本次引入，建议另起 change 修测试隔离）

## M7 - 归档与交付

- [x] `openspec validate add-platform-feishu-reverse-linkage` 通过（本会话实测 valid）
- [x] 更新 `INTEGRATION.md` §6.4 反向联动状态为「已实现（mock 级通路）」+ 触发点说明
- [x] 更新 `feishu-orchestrator/README.md`（新增 `/webhook/platform` 端点行）与 `labmemory-platform/README.md`（反向联动小节）
- [x] `openspec archive add-platform-feishu-reverse-linkage --yes`（已归档为 `2026-08-13-add-platform-feishu-reverse-linkage`，源真相 `openspec/specs/platform-outbound/spec.md` 生成 +7 需求）
- [x] `git add` + 中文 commit
