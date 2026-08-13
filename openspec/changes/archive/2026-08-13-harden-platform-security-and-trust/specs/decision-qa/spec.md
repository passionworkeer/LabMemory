## MODIFIED Requirements

### Requirement: 应用启动初始化
系统 SHALL 在应用启动时加载 sqlite-vec 扩展、确保 `vec_chunks` 与 `chunks_fts` 虚拟表存在、并在 `embedding_chunks` 为空但 DB 含可索引数据时自动触发 `reindex_all`。建表 SHALL 独立处理两类虚拟表：`chunks_fts`（FTS5，SQLite 内置）MUST 始终建成功；`vec_chunks`（vec0，依赖 sqlite-vec 扩展）建表失败时系统 SHALL 不影响 `chunks_fts` 的创建。启动失败 MUST NOT 阻止应用启动。`vec_chunks` 不可用时，`POST /api/qa/ask` SHALL 降级为仅 BM25 + 关系扩展 + 重排（跳过向量召回）并返回结果（而非 503），且在 `retrieval_details.vector_available` 标注 `false`；仅当 `chunks_fts` 也不可用时才拒答。

#### Scenario: 首次启动自动建表与建索引
- GIVEN 全新 SQLite 库，无 `embedding_chunks` / `vec_chunks` / `chunks_fts`
- WHEN 应用首次启动
- THEN 系统 SHALL 创建上述三张表，若 DB 已含 Claim/Result 数据则触发 `reindex_all`，`embedding_chunks` 非空

#### Scenario: sqlite-vec 扩展加载失败降级
- GIVEN sqlite-vec 扩展无法加载（如未安装）
- WHEN 用户调用 `POST /api/qa/ask`
- THEN 系统 SHALL 完成 BM25 召回 + 关系扩展 + 重排并返回答案（而非 503），`retrieval_details.vector_available=false`、`vector_hits=0`，前端可据此展示「向量检索不可用，已降级为关键词检索」提示

## ADDED Requirements

### Requirement: 关系扩展的证据关联键
系统 SHALL 在混合检索的「关系扩展」阶段，以**字符串** `meeting_id`（`Meeting.meeting_id`）关联 claim 的支持证据片段（evidence 切片 `ref_id` 形如 `{meeting_id}#seg{idx}`）；MUST NOT 用整数外键（`Claim.meeting_id` 指向 `Meeting.id`）直接拼接 ref_id，否则 SHALL 不命中任何证据切片、关系扩展静默失效。

#### Scenario: claim 命中后带入其会议证据
- GIVEN 主张 C003 命中向量/BM25 召回，其所属会议 M004 的逐字稿已被索引为 `evidence:M004#seg0..7`
- WHEN 关系扩展处理 C003
- THEN 系统 SHALL 经 `Meeting` 将 C003 的整数 meeting FK 解析为字符串 `meeting_id`，至少把一条 `evidence:M004#seg{idx}` 合并入候选集
