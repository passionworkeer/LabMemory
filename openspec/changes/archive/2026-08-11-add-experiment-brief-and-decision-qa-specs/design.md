## Context

见 proposal.md - Why：brief 与 qa 两端点已在 `labmemory-platform/app/api/brief.py`、`app/api/qa.py` 实现并上线运行，本次仅为缺失的领域建立源真相规格基线。实现细节（路由、查询、schema）已存在，无需重新设计。

## Goals / Non-Goals

**Goals:**
- 让 `openspec/specs/experiment-brief/` 与 `openspec/specs/decision-qa/` 精确描述现有行为，供后续变更对照。

**Non-Goals:**
- 不改动 brief.py / qa.py 的任何实现或接口契约。
- 不引入向量检索、LLM 生成等新能力（现状为关键词检索）。

## Decisions

- **规格即现状基线**：两条需求的措辞与场景严格对齐现有代码行为（权限角色 `admin`/`pi`、`current` 状态过滤、引用上限 3 结果 + 2 证据、`refused` 语义），避免"规格写未来、实现是过去"的漂移。
- **领域独立成册而非并入既有领域**：`experiment-brief` 与 `decision-qa` 语义与 `experiment-passport`（历史时间线）、`decision-inbox`（收件箱）不同，独立建册便于各自演进。

## Risks / Trade-offs

- 规格先于实现的改进（如向量检索）会改变 `decision-qa` 行为 → 届时走新 change 修订规格，本基线作为对照锚点。
- 场景未穷尽所有边界（如 `qa` 关键词切分对中文的局限） → 属实现细节，不构成规格缺口，留待后续按需补充。
