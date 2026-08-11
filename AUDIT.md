# LabMemory 对抗审查报告与 Tier 2 路线图

> 本文件记录对整个项目的**对抗性 + 第一性原理审查**结论：已修缺陷（Tier 1，见归档 change `2026-08-11-fix-adversarial-audit-tier1`）与**待补缺失功能**（Tier 2，需产品规则定义才能非臆测实现）。
> 整合运行全貌见 [`INTEGRATION.md`](./INTEGRATION.md)；本文件聚焦「宣称 vs 真实」的落差。

---

## 1. 审查方法与范围

三维度并行对抗审查（platform 正确性/安全、第一性原理/规格一致性、orchestrator/跨侧接线），累计发现 ~8 P0 + ~21 P1 + ~15 P2。分两类：
- **Tier 1（有界缺陷，已修）**：安全/越权、迁移列错位、编排器 real 模式契约对齐、幂等 TOCTOU、审计未过静默 success 等 ~28 条，全部走 OpenSpec change 修复并归档。
- **Tier 2（缺失功能，待补）**：核心卖点中只在 spec/PRD 存在、代码未实现或被竞态/AI 越权击穿的部分，需产品规则定义后另起 change。

## 2. 已修（Tier 1）摘要

- **平台安全**：默认密钥启动告警、CORS 白名单（禁 `*`+credentials）、跨实验越权读过滤（meetings/tasks/control-tower）、reset-demo 限 admin、publish 强制成员校验、API key 常量时间比较。
- **平台正确性（含 B 计划引入的 3 bug）**：`tasks_new` 迁移显式列名（修列错位）、`_actor_for` 不回退 admin、`card_callback` approve 不回退 running/completed、任务状态守卫、版本门 current=None 判 blocked。
- **编排器 real 模式契约对齐（P0）**：pipeline 编译前 `POST /api/v1/meetings` 注册会议、注入 `experiment_id`、`source_package_id==meeting_id`。
- **编排器可靠性（P0）**：幂等 `O_CREAT|O_EXCL` 原子占位、card_handler 不静默 success（显式 needs_confirmation/blocked 分支）、forward 成功后立即 mark、Aily 无条件强制候选边界、RUN_MODE mock 限 localhost、`"approve"` 统一、retry 按 HTTP code 分类。
- **小修**：空 event_id 幂等兜底、get_candidate 失败不建空壳任务。
- 验证：平台 e2e 17 步 + pytest、跨侧 cross_side 5/5、编排器 test_integration 22/22，全绿。

---

## 3. Tier 2：缺失功能路线图（需产品规则定义）

以下每条是**第一性原理层面的根本缺口**——README/PRD/spec 宣称的能力在代码层未实现或被绕过。补全需先定义产品规则（门规则/判定逻辑/关键词表/策略），再走 OpenSpec change。按优先级：

### T2-1（P0）：候选发布前的「六道质量闸门」校验
- **当前**：`_run_checks`（`app/api/tasks.py`）只是**任务执行前**的 5 项审计（版本/证据/审批/资源/失败边界），且 `confirm_review` / `card_callback approve` 直接 `_build_claim` 生成 current 主张，**候选→主张路径零闸门**。spec `trust-rules` 要求对象/参数/证据/范围/状态/责任六道。
- **第一性原理违背**：未过闸门的候选可直接变生效主张，整个「可信发布」层落空。
- **所需产品输入**：六道门每道的具体判定规则（对象门=类型合法？参数门=数值/单位齐全？证据门=有锚点？范围门=scope 完整？状态门=不冲突？责任门=有责任人？）。
- **建议 change**：`add-six-gate-candidate-publish-check`。

### T2-2（P1）：6 类冲突检测
- **当前**：仅 `_run_checks.version_unit`（任务引用旧主张）这一种版本对比；数值/范围/语义/证据/责任冲突完全无实现。README 宣称「冲突检测 F1=0.89」缺代码支撑。
- **所需产品输入**：每类冲突的判定逻辑（数值冲突=同参数不同值？语义冲突=关键词反义？证据冲突=同锚点不同结论？）。
- **建议 change**：`add-conflict-detection-module`。

### T2-3（P1）：证据失效降级
- **当前**：证据锚点入库后永不复验；spec `decision-inbox` 要求证据链接失效时降级主张可信、停止推荐、通知责任人。
- **所需产品输入**：证据可达性校验策略（URL 探活？飞书文档权限？周期？）+ 降级后 `knowledge_status` 取值。
- **建议 change**：`add-evidence-validity-degradation`。

### T2-4（P1）：三值留痕重构
- **当前**：原始（`Meeting.raw_payload`+transcript）、AI（`Candidate.candidates`）两值保留；人工值仅 `MeetingReview.modifications` 自由 dict（会议级、非逐候选、无修改原因）。spec `trust-rules`/`decision-inbox` 要求「任何人工修改 MUST 记录修改人与原因」。
- **所需产品输入**：人工值结构（`[{candidate_id, field, old, new, reason, user}]`？）+ 前端编辑器联动。
- **建议 change**：`restructure-three-value-provenance`。

### T2-5（P1）：参数 vs 主张版本模型
- **当前**：以**实验为粒度**整体 supersede 主张（`Claim.status=current` 全局唯一），version 实验级 `vN+1`。改一个催化剂会把未变的温度参数整体升版本、旧温度主张也被 supersede。spec `trust-rules` 要求「同适用范围同参数仅一个生效版本」。
- **所需产品输入**：版本链维度 `(experiment_id, parameter_name, scope)` 的精确定义与迁移。
- **建议 change**：`refactor-parameter-versioning-per-scope`。

### T2-6（P1）：语义分类栅栏
- **当前**：`_build_claim` 直接采信 Aily 的 `type`/`title`；种子数据 `"温度 80℃ 暂定"` 即 `parameter_change`，复核确认就变 current 主张。spec `decision-inbox` 要求「可以试试/建议/可能/暂定 MUST NOT 成为当前有效参数」。
- **所需产品输入**：暂定/建议关键词表 + 命中后状态（`待验证` 不可发布 current？）。
- **建议 change**：`add-semantic-classification-fence`。

### T2-7（P1）：非二元知识状态 5 态补全
- **当前**：`ResultPublishIn.knowledge_status: Literal["supported","partially_supported","refuted"]`（3 态），缺 `replaced`（替代）与 `insufficient_evidence`（证据不足）。spec `result-backflow` 要求 5 态。
- **所需产品输入**：`replaced`/`insufficient_evidence` 的触发条件与下游影响（问答检索是否排除？）。
- **建议 change**：`extend-knowledge-status-to-five-states`。

### T2-8（P1）：spec-代码路径/权限系统性对齐
- **当前**：多个 spec 引用 `/web/tasks/...`、`/web/control-tower`、`app/services/permissions.py`、命名权限 `operate_action_audit` 等，代码实际是 `/api/...` + 角色依赖。根因：归档的 `2026-08-09-extend-action-audit-permissions` 设想的服务型架构未落地。
- **所需产品输入**：二选一——改 spec 对齐 `/api/` 现状，还是补 services 层 + 命名权限。
- **建议 change**：`reconcile-spec-paths-with-code`。

### T2-9（P2）：告警卡片接线 + pipeline 诚实 status
- **当前**：`im_card_adapter.send_alert_card` 无调用方；retry 耗尽只静默置 FAILED；pipeline 返回 `status:"success"+completed_at`（实际是 SUBMITTED/REVIEWING）。
- **建议 change**：`wire-alert-card-and-honest-pipeline-status`。

### T2-10（P2）：real 路径确定性规则
- **当前**：`_extract_experiment_ref` + 数值范围 + 版本校验只在 `_mock_compile` 调用；real Aily 输出直接采信。
- **建议 change**：`apply-deterministic-rules-in-real-aily-path`。

---

## 4. 已知延后项（Tier 1 中评估为可接受/dev 工具/边界）

- **D7 standalone `mock_server.py` 字段形状**：读扁平字段、返回 `{data:cand}` 包装，与真平台嵌套契约不一致。它是 dev-only 联调工具（非生产路径，cross_side_check 用真平台验证）。修法：宽化为同时接受嵌套+扁平，或废弃改用 in-process mock。低优先。
- **E1 meeting.ended/minutes 乱序死状态**：minutes 先到、meeting.ended 后到会留 `WAITING_MINUTES` 死状态。属边界事件乱序，生产用飞书事件序号可缓解。中优先，可并入 T2 相关 change。
- **E3 `url_verification` 在验签前回显 challenge**：飞书事件订阅的标准握手流程（challenge 需在验签前回显以完成订阅注册），属设计行为，非漏洞。
- **多 worker 分布式幂等**：本次 D1 用单进程原子文件锁消除主要 TOCTOU；多 worker 部署需 DB 唯一约束或分布式锁（T2 级）。

---

## 5. 核心卖点实现度（一句话总评）

**真实现**：版本不覆盖（`replaces_claim_id`+superseded）、阻断不建飞书任务（双条件+状态守卫）、审计三态结论、JWT+API key 鉴权（含安全加固）、跨侧正向联动（合规化打通）、幂等原子化。

**Tier 2 已实现（2026-08-11，4 个 OpenSpec change 归档）**：
- 六道闸门（候选→主张发布前 `app/services/trust_rules.py`，PRD §10.1）— `add-trust-rules-engine`
- 语义栅栏（可以试试/建议/可能/暂定 不生效，PRD line 854）— 同上
- 冲突检测（数值冲突冻结 + 闸门/审计复用覆盖 6 类，PRD §10.5）— 同上
- 知识状态 5 态（+replaced/insufficient_evidence，PRD §10.6）— `add-knowledge-five-states-and-evidence-degradation`
- 证据失效降级（结构化校验 + 问答排除 + 发布守卫，PRD §13.1）— 同上
- 三值留痕（reason 字段 + 修改人/原因入审计，PRD line 297）— `add-three-value-and-per-param-version`
- 参数级版本模型（按参数维度跟踪版本，未变参数继承不升版，PRD §10.3）— 同上
- pipeline 诚实 status（submitted）+ 失败告警卡片接线 — `add-alert-realrules-specalign`
- real Aily 路径确定性校验（experiment_ref 格式，real/mock 共用）— 同上
- spec-代码路径对齐说明（`/api/` 为准）— 同上

**仍有的诚实边界**：
- 真实 URL 证据可达性探活（需飞书文档权限，demo 用占位 URL，本次为结构化校验）。
- 多 worker 分布式幂等（本次单进程原子文件锁；DB 唯一约束为生产增强）。
- 真飞书实时联调（需真 FEISHU 凭证）。
- spec 中 `/web/...` 路径的逐条改写未做（已用对齐说明声明以 `/api/` 为准）。

> 8 个核心卖点已从「PPT/缩水」转为代码实现，规则源自 PRD §10/§13/line 854。剩余边界为外部凭证/生产增强，非产品逻辑缺口。
