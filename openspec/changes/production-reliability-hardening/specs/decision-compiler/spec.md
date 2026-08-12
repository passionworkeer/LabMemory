## MODIFIED Requirements

### Requirement: 编译失败处理
Aily 调用失败、返回结构不符合契约、返回无法解析的内容或返回候选字段类型不合法时，系统 MUST NOT 提交平台；SHALL 将编排状态置为 `failed`、记录失败集成日志，并保留 `MeetingPackage` 以便重放。空候选结果只有在响应结构合法且业务明确允许无候选时才能视为成功，解析失败 MUST NOT 降级为空候选包。

#### Scenario: Aily 返回非法结构
- GIVEN Aily 返回缺少 `candidates` 字段或无法解析为 JSON 的响应
- WHEN 系统校验编译结果
- THEN 系统 SHALL 判定编译失败、不调用平台提交接口，并支持按 `source_id` 重放

#### Scenario: Aily 返回类型错误
- GIVEN Aily 返回的 `candidates` 不是合法数组或候选缺少契约必填字段
- WHEN 系统校验编译结果
- THEN 系统 SHALL 记录结构错误并终止流程，MUST NOT 把响应转换为空候选成功返回

#### Scenario: 合法空候选
- GIVEN Aily 返回符合契约的空候选数组并附带合法编译元数据
- WHEN 系统校验编译结果
- THEN 系统 SHALL 按业务规则处理为空结果，并与解析失败状态明确区分
