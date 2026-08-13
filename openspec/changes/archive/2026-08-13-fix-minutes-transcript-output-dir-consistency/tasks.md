# Tasks: 修复妙记逐字稿 --output-dir 与读取路径不一致

## M1 - OpenSpec change

- [ ] 创建 change `fix-minutes-transcript-output-dir-consistency`（proposal + meeting-ingest spec MODIFIED 增量 + tasks）
- [ ] `openspec validate fix-minutes-transcript-output-dir-consistency` 通过

## M2 - 实现：统一 --output-dir 与落盘/读取路径

- [ ] `adapters/minutes_adapter.py` `_real_get_detail`：`cli_output_dir` 复用 `output_dir`（基于 `Config.DATA_DIR / "minutes" / token`），删除硬编码 `Path("data")`
- [ ] `adapters/minutes_adapter.py` `_read_transcript_file`：补注释说明"transcript_file 由 lark-cli 基于 --output-dir 返回，Config.DATA_DIR 为绝对路径时 is_absolute 分支直接采用，不再二次拼接"（不改逻辑）

## M3 - 测试：断言对齐实现与规格

- [ ] `tests/test_integration.py` `test_minutes_detail_uses_isolated_output_dir`：将 `--output-dir` 与 `--as` 断言迁入 `try` 块（DATA_DIR=temp_dir 时），断言 `output_dir == Config.DATA_DIR / "minutes" / minute_test`

## M4 - 回归验证

- [ ] 本地编排器 `python tests/test_integration.py` → 38/38 全绿（清 `data/` 后）
- [ ] 本地编排器 `python scripts/health_check.py` → 11/11
- [ ] 同步改动到部署服务器（<SERVER_IP>）并重测 → 38/38

## M5 - 归档与交付

- [ ] 更新 `INTEGRATION.md §6.4`：标注既有 `test_minutes_detail_uses_isolated_output_dir` error 已由本 change 修复
- [ ] `openspec archive fix-minutes-transcript-output-dir-consistency --yes`
- [ ] `git add` + 中文 commit
