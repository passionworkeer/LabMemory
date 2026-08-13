# Tasks: 平台 → 飞书编排器反向联动

## M1 - OpenSpec change

- [ ] 创建 change `add-platform-feishu-reverse-linkage`（proposal + design + platform-outbound spec 增量 + tasks）
- [ ] 校验 spec 增量格式（`### Requirement:` + `#### Scenario:`，SHALL/MUST 措辞）

## M2 - 编排器侧：动作处理器

- [ ] 新增 `feishu-orchestrator/feishu-orchestrator/core/platform_action_handler.py`
- [ ] 实现 `handle_action(request)`：必填字段校验 + 幂等（check/acquire/mark/release）+ 分派
- [ ] 实现 `_dispatch`：send_card / create_task（含回写）/ publish_doc / notify / update_base
- [ ] 集成日志（inbound 平台动作，成功/失败/幂等命中）

## M3 - 编排器侧：/webhook/platform 端点

- [ ] `webhook_server.py` `do_POST` 新增 `/webhook/platform` 分支
- [ ] 新增 `_handle_platform_action`（读体 + 鉴权 + 调 handler + 返回）
- [ ] 新增 `_verify_platform_key`（mock 限 localhost；real 校验 Bearer {PLATFORM_API_KEY}）
- [ ] 启动横幅补充端点说明

## M4 - 平台侧：出站客户端

- [ ] 新增 `labmemory-platform/app/services/feishu_client.py`
- [ ] `send_feishu_action(...)` 组装契约体 + mock 跳过 / real urllib POST + 非阻断错误处理
- [ ] 辅助 `candidate_dict_from_candidates(candidates_list)` 挑 parameter_change（否则第一个）返回扁平候选

## M5 - 平台侧：四个触发点

- [ ] `app/api/meetings.py:receive_candidate`：新候选待复核 → `send_card`（≤3，try/except）
- [ ] `app/api/tasks.py:start_task`：任务 running → `create_task`（try/except）
- [ ] `app/api/tasks.py:run_audit`：结论 blocked → `notify`（try/except）
- [ ] `app/api/results.py:publish_result`：发布后 → `publish_doc`（knowledge_status→doc_type，try/except）

## M6 - 验证脚本与回归

- [ ] 新增 `labmemory-platform/scripts/reverse_linkage_check.py`（直打编排器 /webhook/platform + 平台业务触发点断言）
- [ ] 平台 `pytest tests/ -q` 全绿（回归守护）
- [ ] 编排器 `python tests/test_integration.py` 22/22 回归

## M7 - 归档与交付

- [ ] `openspec validate --all` 全绿（若 CLI 可用；否则人工核对格式）
- [ ] 更新 `INTEGRATION.md` §6.4 反向联动状态为「已实现（mock 级通路）」+ 触发点说明
- [ ] 更新 `feishu-orchestrator/README.md` 与 `labmemory-platform/README.md` 反向联动小节
- [ ] `openspec archive add-platform-feishu-reverse-linkage --yes`（CLI 可用时）
- [ ] `git add` + 中文 commit
