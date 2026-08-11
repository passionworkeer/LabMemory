## Why

平台后端统一使用 `datetime.utcnow()` 写入时间戳，该方法返回**无时区标记的 UTC 时间**（naive datetime）。Pydantic 序列化时生成不带 `+00:00` 后缀的 ISO 字符串，前端 JavaScript `new Date()` 按 ES 规范将无时区 ISO 字符串解析为**本地时间**，导致所有展示时间比服务器本地时间（Asia/Shanghai +0800）早 8 小时。服务器系统时间本身正确，问题在序列化链路缺时区信息。同时 `control_tower.py` 的"近 24h 发布"截止计算也因此偏移 8 小时（实际窗口为 32h），属于逻辑 bug。

## What Changes

- 后端所有 `datetime.utcnow()` 调用替换为 `datetime.now(timezone.utc)`（timezone-aware UTC），涉及 8 个文件、20 处调用（含 `scripts/seed_demo.py` 演示数据种子）。
- `TimestampMixin`（`app/db/base.py`）的 `created_at`/`updated_at` 默认值同步切换为 `lambda: datetime.now(timezone.utc)`。
- `control_tower.py` 的 24h 截止计算同步修正，cutoff 不再偏移 8 小时。
- **Pydantic 序列化层兜底**：新增 `LabMemoryBase(BaseModel)` 基类，用 `@field_serializer('*', check_fields=False)` 把 naive datetime 升级为 UTC-aware，33 个响应 schema 继承该基类。实测 SQLAlchemy SQLite 后端存储 aware datetime 时会剥离 `tzinfo`，仅改源头不够，必须在序列化层补兜底。
- **历史数据无需回填即正确显示**：序列化层兜底覆盖存量 naive datetime，API 响应中所有 datetime 字段（含历史数据）均带 `Z`（UTC）后缀，前端按本地时区正确显示。
- **BREAKING**：API 响应中所有由后端生成的 datetime 字段（如 `created_at`、`reviewed_at`、`audited_at`、`approved_at`、`published_at`、`effective_at`、`captured_at`、`compiled_at`、`last_activity_at`、timeline `timestamp` 等）的 ISO 字符串格式从 `YYYY-MM-DDTHH:MM:SS.ffffff` 变为 `YYYY-MM-DDTHH:MM:SS.ffffffZ`（或 `+00:00`）。前端 `new Date()` 解析逻辑无需改动。

## Capabilities

### New Capabilities
<!-- 无新增能力，仅修正现有时间戳序列化行为 -->

### Modified Capabilities
- `platform-audit-trail`: 新增"时间戳时区规范"需求--所有 AuditEvent 与 API 响应中的 datetime 字段 SHALL 以 timezone-aware UTC 写入并序列化带 `+00:00` 后缀，保证前端按本地时区正确显示。

## Impact

- **代码**：`app/db/base.py`、`app/main.py`、`app/api/results.py`、`app/api/tasks.py`、`app/api/meetings.py`、`app/api/admin.py`、`app/api/control_tower.py`、`scripts/seed_demo.py` 共 8 个文件、20 处 `datetime.utcnow` 调用；`app/schemas.py` 新增 `LabMemoryBase` 基类 + 33 个 schema 类改继承。
- **API**：响应中所有 datetime 字段新增 `Z`（UTC）后缀。前端 `new Date().toLocaleString()` 调用无需改动。
- **数据**：历史 naive datetime 无需回填，序列化层兜底自动升级为 UTC-aware；DB 存储格式不变。
- **依赖**：无新增依赖；`datetime.timezone`、`pydantic.field_serializer` 均为标准库/已引入库。
- **逻辑 bug 修复**：`control_tower.py` 的"近 24h 发布"截止计算同步修正。
