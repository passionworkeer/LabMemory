# platform-permissions Specification Delta

## ADDED Requirements

### Requirement: 实现路径与权限模型对齐说明
系统 SHALL 以 `/api/...` 为 API 路径基线（如 `/api/meetings`、`/api/tasks/{id}`、`/api/control-tower`、`/api/experiments/{id}/passport`），权限 MUST 通过角色依赖（`admin`/`pi`/`lead`/`executor`）+ `ExperimentMember` 成员关系强制。早期规格中出现的 `/web/...` 路径与命名权限为未落地的前瞻设计；以本对齐说明为准，`/web/...` MUST NOT 作为实现契约。

#### Scenario: 路径以 /api 为准
- GIVEN 任意客户端访问平台
- WHEN 调用任务审计/控制塔/护照等接口
- THEN 命中路径 SHALL 为 `/api/...`（非 `/web/...`），权限由角色 + 成员关系判定
