## 1. 后端时间戳写入切换

- [x] 1.1 `app/db/base.py`：`TimestampMixin` 的 `created_at`/`updated_at` 默认值从 `datetime.utcnow` 改为 `lambda: datetime.now(timezone.utc)`，import 补 `timezone`
- [x] 1.2 `app/api/results.py`：`res.published_at = datetime.utcnow()` 改为 `datetime.now(timezone.utc)`，import 补 `timezone`
- [x] 1.3 `app/api/tasks.py`：3 处 `audit.audited_at` / `t.approved_at` 改为 `datetime.now(timezone.utc)`，import 补 `timezone`
- [x] 1.4 `app/api/meetings.py`：`r.reviewed_at` 与 `effective_at` 共 2 处改为 `datetime.now(timezone.utc)`，import 补 `timezone`
- [x] 1.5 `app/api/admin.py`：3 处 `datetime.utcnow()` 改为 `datetime.now(timezone.utc)`，import 已有 `timezone`
- [x] 1.6 `app/api/control_tower.py`：`cutoff = datetime.utcnow() - timedelta(hours=24)` 改为 `datetime.now(timezone.utc) - timedelta(hours=24)`，import 补 `timezone`
- [x] 1.7 `app/main.py`：3 处中间件计时改为 `datetime.now(timezone.utc)`，import 补 `timezone`
- [x] 1.8 `scripts/seed_demo.py`：6 处 `datetime.utcnow()` 改为 `datetime.now(timezone.utc)`，import 补 `timezone`（reset-demo 端点调用此脚本）

## 2. Pydantic 序列化层兜底（关键）

- [x] 2.1 `app/schemas.py` 新增 `LabMemoryBase(BaseModel)` 基类，含 `@field_serializer('*', check_fields=False)` 把 naive datetime 升级为 UTC-aware（`replace(tzinfo=timezone.utc)`）
- [x] 2.2 `app/schemas.py` 33 个 schema 类继承从 `BaseModel` 改为 `LabMemoryBase`

## 3. 验证

- [x] 3.1 后端重启无报错，`/api/meetings` 响应中 `captured_at`/`reviewed_at` 带 `Z` 后缀
- [x] 3.2 `/api/experiments/{id}/passport` 响应中 timeline `timestamp` 与会议链 `captured_at` 带 `Z` 后缀
- [x] 3.3 `/api/control-tower` 的 `published_24h` 计算正确（cutoff 不再偏移 8h）
- [x] 3.4 前端 `npx tsc --noEmit` + `npm run build` 通过（前端代码无改动，确认无回归）
- [x] 3.5 `openspec validate fix-timestamp-timezone-aware` 通过

## 4. 归档

- [ ] 4.1 `openspec archive fix-timestamp-timezone-aware --yes` 合并增量规格回源真相
