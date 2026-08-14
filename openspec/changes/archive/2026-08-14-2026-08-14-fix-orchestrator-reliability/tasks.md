## 1. 失败状态 key

- [x] 1.1 `pipeline_orchestrator.run_from_minutes_url`：try 之前解析 source_id（minutes 解析成功后），except 分支优先用真实 source_id 写 FAILED。

## 2. 幂等原子化

- [x] 2.1 `event_router.handle_event`：`is_processed` 检查改为 `acquire()` 抢占；异常 `release()`；成功 `mark()`。
- [x] 2.2 `pipeline_orchestrator.run_from_minutes_url/run_from_text`：同样改 acquire/release/mark。

## 3. 状态原子写

- [x] 3.1 `state_machine.set_state`：临时文件 + `os.replace`。

## 4. mock 加固与请求上限

- [x] 4.1 `webhook_server`：mock 模式拒绝携带 X-Forwarded-For 的请求。
- [x] 4.2 webhook handler：Content-Length > 1MB 返回 413。

## 5. 测试与验证

- [x] 5.1 `tests/test_integration.py` 全绿（38 项）；`scripts/health_check.py` 通过。
- [ ] 5.2 `openspec validate` 通过后归档。
