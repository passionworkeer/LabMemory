# trust-rules Specification Delta

## ADDED Requirements

### Requirement: 参数版本按参数维度跟踪
系统 SHALL 在新主张 supersede 旧 current 主张时，按**参数维度**独立跟踪版本（PRD §10.3）：新主张每个参数对比旧 current 同名同范围参数——值相同 SHALL 继承旧版本号（不升版），值变化或新增 SHALL 升版或置 v1。MUST NOT 因某个参数变化而整体升版所有参数、或将未变参数的旧主张 supersede。

#### Scenario: 未变参数继承版本
- GIVEN 旧 current 主张含 temperature=v1（70℃）、catalyst=v1（1.0eq）
- WHEN 新主张在同一 scope 发布 temperature=70℃（未变）、catalyst=0.8eq（变化）
- THEN 新主张 parameter_version 中 temperature SHALL 仍为 v1（继承），catalyst SHALL 为 v2（升版）
