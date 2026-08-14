## ADDED Requirements

### Requirement: 状态与版本过滤的索引时效

检索候选集的 claim 切片状态 MUST 与主张生命周期同步：主张被 supersede 时，其检索切片 SHALL 同步标记 superseded（不得继续以 current 参与召回）；主张 knowledge_status 变为 refuted/replaced/insufficient_evidence 时，其切片 SHALL 同步刷新并因状态过滤被排除。

#### Scenario: 替代后旧版本不参与召回

- GIVEN 实验 E 主张 C1（80℃）已索引为 current，新复核发布 C2（70℃）替代 C1
- WHEN 用户提问「当前推荐温度」
- THEN 检索候选集 SHALL 含 C2 的切片且不含 C1 的切片

### Requirement: 拒答轮模型信息诚实

已执行嵌入/检索的拒答轮（score 低于阈值、检索未命中等），`model_info` SHALL 反映本轮实际使用的嵌入与生成模式，不得固定回退为 hash-fallback/template-fallback。

#### Scenario: 阈值拒答的真实模式

- GIVEN 本轮以真实向量嵌入执行检索，因 top_score 低于阈值拒答
- THEN model_info.embedding_mode SHALL 为本轮实际嵌入模式，而非 hash-fallback
