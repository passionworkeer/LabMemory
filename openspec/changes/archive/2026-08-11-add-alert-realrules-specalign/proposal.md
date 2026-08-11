# Proposal: 规格路径对齐 + 告警卡片接线 + real 路径确定性规则

## Why

AUDIT T2-8/T2-9/T2-10：
- 多个 spec 引用 `/web/...` 路径 + `app/services/permissions.py` + 命名权限，代码实际是 `/api/...` + 角色依赖（归档的 `2026-08-09` change 设想的服务型架构未落地）。
- `im_card_adapter.send_alert_card` 无调用方；retry 耗尽只静默置 FAILED；pipeline 返回 `status:"success"+completed_at`（实际是 SUBMITTED/REVIEWING）。
- `_extract_experiment_ref` + 数值范围 + 版本校验只在 `_mock_compile` 调用，real Aily 输出直接采信。

## What Changes

- **T2-9**：`pipeline_orchestrator` 返回 `status:"submitted"`（去 completed_at，如实反映已提交待复核）；失败时调 `im_card_adapter.send_alert_card`（若配置 reviewer）。
- **T2-10**：`adapters/aily_adapter.py` real 编译路径同样过 `_extract_experiment_ref` + 参数数值范围校验（从 `_mock_compile` 抽公共校验，real/mock 共用）。
- **T2-8**：在受影响 spec（action-audit/platform-permissions/control-tower/experiment-passport）Purpose 段补一条 ADDED 说明：实现路径为 `/api/...`、权限为角色依赖（admin/pi/lead/executor + ExperimentMember），`/web/...` 为未落地的前瞻设计。避免规格误导。

## Impact

- spec：ADDED 路径对齐说明（分散到既有领域 Purpose 或集中一处）。
- 代码：`pipeline_orchestrator.py`（status+告警）、`aily_adapter.py`（real 校验）。
- 回归：编排器 test_integration 22/22、平台全量绿。
