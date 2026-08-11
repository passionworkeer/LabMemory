# Tasks: 知识 5 态 + 证据失效降级

- [x] 创建 change `add-knowledge-five-states-and-evidence-degradation`
- [x] `openspec validate` 通过
- [x] `app/schemas.py`：ResultPublishIn.knowledge_status 扩展 5 态（+replaced/insufficient_evidence）
- [x] `app/services/evidence.py`：validate_evidence(claim) 结构化校验
- [x] `app/api/qa.py`：排除证据失效 current 主张
- [x] `app/api/results.py`：发布时若证据失效提示 insufficient_evidence
- [x] 平台 e2e + pytest + cross_side 全绿；validate --all + archive
