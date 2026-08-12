## MODIFIED Requirements

### Requirement: CLI 缺失与授权缺失的可诊断失败
当 `lark-cli` 未安装、未绑定配置、未完成身份授权、返回非零状态或输出不符合响应契约时，系统 MUST 以明确原因失败并记录 `failed` 集成日志，MUST NOT 静默退回 Mock 数据、空列表、空对象或空资源 ID。

真实调用成功时，任务创建 MUST 返回非空 `task_guid`，Base 记录创建 MUST 返回非空 `record_id`，文档发布 MUST 返回非空 `doc_token`；缺少必要标识时系统 MUST 判定响应无效并失败。

#### Scenario: CLI 未安装
- GIVEN Real 模式且执行环境不存在 `lark-cli`
- WHEN 系统发起飞书调用
- THEN 系统 SHALL 报告 CLI 未安装并记录失败集成日志，MUST NOT 返回 Mock 数据

#### Scenario: CLI 授权失败
- GIVEN Real 模式且 CLI 已安装但 bot 或 user 身份未完成授权
- WHEN 系统发起对应调用
- THEN 系统 SHALL 报告所需身份授权缺失并记录失败，MUST NOT 转换为空结果

#### Scenario: 成功响应缺少资源 ID
- GIVEN CLI 返回成功状态但任务、记录或文档响应缺少必填资源 ID
- WHEN 系统解析响应
- THEN 系统 SHALL 判定响应契约无效并失败，MUST NOT 记录为成功

#### Scenario: 未完成 user 授权
- GIVEN Real 模式下需要以 user 身份读取资源但未执行 `lark-cli auth login`
- WHEN 系统发起调用
- THEN 系统 SHALL 判定失败并在错误信息中指出需要完成 CLI 授权，MUST NOT 返回模拟数据冒充真实结果

#### Scenario: 查询资源确实为空
- GIVEN CLI 返回成功状态且查询结果合法但没有匹配资源
- WHEN 系统解析响应
- THEN 系统 SHALL 返回明确的空查询结果；该结果 MUST 与 CLI 执行失败可区分
