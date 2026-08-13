# Proposal: 修复妙记逐字稿 --output-dir 与读取路径不一致

## Why

`meeting-ingest` 规格已要求「逐字稿落盘读取」使用"按妙记标识隔离的**稳定** `--output-dir`"并"从预期目录读取逐字稿"（`openspec/specs/meeting-ingest/spec.md`「逐字稿落盘读取」）。但 `production-reliability-hardening` change 落地的实现违反了该规格，导致集成测试 `test_minutes_detail_uses_isolated_output_dir` 持续 error——本地 main HEAD 与服务器部署环境均为 37/38（`INTEGRATION.md §6.4` 已记录"与本 change 无关"，本 change 专门修它）。

根因（`feishu-orchestrator/feishu-orchestrator/adapters/minutes_adapter.py`）：

1. `_real_get_detail`（L332-339）落盘目录用 `Config.DATA_DIR / "minutes" / token`（绝对、可被运维/测试稳定覆盖），但传给 lark-cli 的 `--output-dir` 却用**硬编码相对路径** `Path("data") / "minutes" / token`（L334），两者不一致——`--output-dir` 依赖进程工作目录（cwd），违反"稳定"要求。
2. `_read_transcript_file`（L421-423）对非绝对路径再拼 `Config.DATA_DIR / "minutes" / path`。当 lark-cli 按 `--output-dir` 返回 `data/minutes/<token>/transcript.txt`（相对 cwd）时，拼接结果变成 `DATA_DIR/minutes/data/minutes/<token>/transcript.txt`，**路径前缀重复**，文件找不到 → "逐字稿缺失"。

两处路径约定脱节，是"写入用相对 cwd、读取用 DATA_DIR"的 design mismatch。

## What Changes

- **修改** `minutes_adapter.py` `_real_get_detail`：`cli_output_dir` 复用基于 `Config.DATA_DIR` 的落盘目录 `output_dir`（即 `cli_output_dir = output_dir`），使 lark-cli 的 `--output-dir`、落盘目录、`_read_transcript_file` 查找目录三者一致，且不再依赖 cwd。
- **不修改** `_read_transcript_file` 逻辑：`Config.DATA_DIR` 为绝对路径（`PROJECT_ROOT / "data"`），改动后 lark-cli 返回的 `transcript_file` 即基于 `Config.DATA_DIR` 的绝对路径，`_read_transcript_file` 现有 `if not path.is_absolute()` 分支自然跳过二次拼接，正确读取（仅补一行注释说明约定）。
- **修改** `tests/test_integration.py` `test_minutes_detail_uses_isolated_output_dir`：把 `--output-dir` 断言迁移到 `Config.DATA_DIR` 被设为临时目录的 `try` 块内，断言 `--output-dir == Config.DATA_DIR / "minutes" / minute_test`（稳定隔离路径），取代原先与实现矛盾、且在 `finally` 恢复 DATA_DIR 后才执行的相对字面量断言。
- **不修改** 契约 `contracts/`、其它适配器、平台侧、前端、六道闸门。

## Impact

- 1 个 spec 领域增量（`meeting-ingest`，MODIFIED「逐字稿落盘读取」Requirement：明确 `--output-dir` 基于 `Config.DATA_DIR` 的稳定路径 + 写入/读取路径一致性 Scenario）。
- 编排器改动：`adapters/minutes_adapter.py`（1 行 + 注释）、`tests/test_integration.py`（1 个测试的断言位置与期望值）。
- 编排器集成测试 38/38 全绿（消除既有 1 个 error）。
- 生产正确性：妙记逐字稿落盘/读取不再依赖 cwd，`Config.DATA_DIR` 可被稳定覆盖（部署/测试隔离）。
