## 1. 规格基线核对（无实现改动，验证现有代码与规格一致）

- [ ] 1.1 核对 `app/api/brief.py` 行为与 `experiment-brief/spec.md` 各场景一致（访问权限、当前主张、上一轮结果、失败边界聚合、当前目标、响应结构）
- [ ] 1.2 核对 `app/api/qa.py` 行为与 `decision-qa/spec.md` 各场景一致（权限前置过滤、状态过滤、关键词匹配排序、带出处引用、拒答、答案结构）

## 2. 校验与归档

- [ ] 2.1 运行 `openspec validate --all`，确认本 change 与全部源真相规格通过
- [ ] 2.2 运行 `openspec archive add-experiment-brief-and-decision-qa-specs --yes` 归档，增量规格合并入 `openspec/specs/`
