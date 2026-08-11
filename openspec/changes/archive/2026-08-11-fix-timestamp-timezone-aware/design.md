## Context

平台后端在 8 个文件共 20 处使用 `datetime.utcnow()` 写入时间戳：`app/db/base.py`（TimestampMixin 默认值，2 处 callable 引用）、`app/main.py`（中间件计时，3 处）、`app/api/results.py`（published_at）、`app/api/tasks.py`（audited_at、approved_at 共 3 处）、`app/api/meetings.py`（reviewed_at、effective_at 共 2 处）、`app/api/admin.py`（compiled_at、now 共 3 处）、`app/api/control_tower.py`（24h cutoff）、`scripts/seed_demo.py`（演示数据种子，6 处）。该方法返回 naive datetime（UTC 值但无 `tzinfo`），Pydantic 序列化为不带 `+00:00` 后缀的 ISO 字符串，前端 `new Date()` 按 ES 规范解析为本地时间，导致展示比实际早 8 小时。

**关键发现**：仅替换 `datetime.utcnow()` 为 `datetime.now(timezone.utc)` 不足以解决问题--SQLAlchemy SQLite 后端在存储 aware datetime 时会剥离 `tzinfo`，读回时变为 naive datetime，Pydantic 序列化仍不带时区后缀。实测 `DateTime` 与 `DateTime(timezone=True)` 在 SQLite 下行为一致，均剥离 tzinfo。因此必须在序列化层补兜底。

## Goals / Non-Goals

**Goals:**
- 所有 API 响应中的 datetime 字段带 UTC 时区后缀（`+00:00` 或 `Z`），前端 `new Date()` 正确转本地时区显示
- 修正 `control_tower.py` 24h 截止计算的 8h 偏移 bug
- 保持前端代码零改动（`new Date().toLocaleString()` 已正确处理带时区 ISO 字符串）
- 历史数据同样正确显示（序列化层兜底覆盖 naive datetime）

**Non-Goals:**
- 不修改 DB 列类型（SQLAlchemy `DateTime` 在 SQLite 下无论是否 `timezone=True` 都剥离 tzinfo，改列类型无收益）
- 不回填 DB 中的历史 datetime 字符串（序列化层兜底已让历史数据正确显示，无需写迁移脚本）
- 不引入时区配置项（统一以 UTC 存储、序列化、传输；前端按浏览器时区显示）
- 不改前端时间格式化逻辑

## Decisions

### 决策 1：源头用 `datetime.now(timezone.utc)` 替换 `datetime.utcnow()`

**选择**：`datetime.now(timezone.utc)`（timezone-aware UTC）
**理由**：
- `datetime.utcnow()` 在 Python 3.12+ 已 deprecated，`datetime.now(timezone.utc)` 是官方推荐替代
- UTC 是后端存储与计算的事实标准，避免跨时区部署时数据混乱
- 即使序列化层有兜底，源头仍应产生 aware datetime，保证语义正确（如 `control_tower.py` 的 24h cutoff 计算需要 aware datetime 才能正确做时间算术）
**备选方案**：
- `datetime.now()`（naive 本地时间）：依赖服务器时区配置，跨时区部署会出错
- `datetime.now(timezone(timedelta(hours=8)))`（CST-aware）：硬编码时区，不适合多时区团队

### 决策 2：不修改 DB 列类型

**选择**：保持 `DateTime`（不带 `timezone=True`）
**理由**：
- 实测 SQLAlchemy SQLite 后端在存储 aware datetime 时**剥离 tzinfo**，无论列类型是否带 `timezone=True`，存储字符串均无时区后缀
- 改 `DateTime(timezone=True)` 无实际收益，且增加 DDL 变更
- 时区问题在序列化层兜底解决（见决策 3）
**备选方案**：改 `DateTime(timezone=True)` -- 实测无效，增加迁移工作量

### 决策 3：在 Pydantic 序列化层补兜底（关键决策）

**选择**：新增 `LabMemoryBase(BaseModel)` 基类，用 `@field_serializer('*', check_fields=False)` 把 naive datetime 升级为 UTC-aware（`replace(tzinfo=timezone.utc)`），所有响应 schema 继承该基类
**理由**：
- SQLAlchemy SQLite 后端剥离 tzinfo，仅改源头 `datetime.now(timezone.utc)` 不足以让 API 响应带时区后缀
- 序列化层兜底同时覆盖**新数据**（源头已是 aware，serializer 不改变）与**历史数据**（naive 被升级为 UTC），无需回填 DB
- `field_serializer('*', check_fields=False)` 对非 datetime 字段透传，无副作用
- 集中在 `LabMemoryBase` 一处实现，33 个 schema 类只需改继承，无需逐字段加 `Annotated[datetime, ...]`
**备选方案**：
- 自定义 SQLAlchemy `TypeDecorator` 在存储层保留时区字符串 -- 改动量大，需替换所有 `DateTime` 列定义
- 给每个 datetime 字段用 `Annotated[datetime, PlainSerializer(...)]` -- 逐字段改动，维护成本高
- 不做兜底，仅依赖源头 `datetime.now(timezone.utc)` -- 实测无效，SQLAlchemy 剥离 tzinfo

### 决策 4：不回填历史 DB 数据

**选择**：不写迁移脚本修改 DB 中的历史 datetime 字符串
**理由**：
- 序列化层兜底（决策 3）已让历史 naive datetime 在 API 响应中被升级为 UTC-aware，前端展示正确
- DB 中存量 naive 字符串保持原样，无回填风险
- 用户明确要求不回填
**备选方案**：写迁移脚本给所有 datetime 字段加 8 小时 -- 风险高、无必要（序列化层已解决）

## Risks / Trade-offs

- **[API 响应格式 BREAKING]** ISO 字符串新增 `Z` 后缀（等价 `+00:00`） -> 前端 `new Date()` 已正确处理带时区字符串，无需改动；外部调用方若用严格正则解析需适配（当前无外部调用方）
- **[序列化层隐式行为]** naive datetime 被静默升级为 UTC -> 通过 `LabMemoryBase` 集中实现且有文档注释，调试时可从基类追溯；若未来有"本地时间"语义的 naive datetime 需求，需在子类覆盖 serializer
- **[DB 与 API 不一致]** DB 存 naive 字符串、API 返回带 `Z` 后缀 -> 可接受，DB 是内部存储、API 是对外契约；若直接查 DB 做分析需注意 naive 即 UTC 的约定

## Migration Plan

1. 替换 8 个文件共 20 处 `datetime.utcnow()` / `datetime.utcnow` 为 `datetime.now(timezone.utc)` / `lambda: datetime.now(timezone.utc)`：
   - `app/db/base.py`（2 处 callable 引用 -> lambda）
   - `app/main.py`（3 处）
   - `app/api/results.py`、`app/api/tasks.py`（3 处）、`app/api/meetings.py`（2 处）、`app/api/admin.py`（3 处）、`app/api/control_tower.py`
   - `scripts/seed_demo.py`（6 处）
   - 各文件 `from datetime import ...` 同步补 `timezone`
2. `app/schemas.py` 新增 `LabMemoryBase(BaseModel)` 基类含 `@field_serializer('*', check_fields=False)` 兜底，33 个 schema 类继承改为 `LabMemoryBase`
3. 验证：后端重启 + 抓取 `/api/meetings`、`/api/experiments/{id}/passport` 响应确认 datetime 字段带 `Z` 后缀；`npx tsc --noEmit` + `npm run build` 通过；`openspec validate` 通过
4. 回滚策略：`git revert` 即可，无 DB schema 变更、无数据迁移

## Open Questions
无。
