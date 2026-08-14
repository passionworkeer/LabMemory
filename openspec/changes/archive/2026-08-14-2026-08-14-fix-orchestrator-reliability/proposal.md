# Proposal: fix-orchestrator-reliability（编排器可靠性第三轮）

## Why

对抗审查发现编排器 4 处可靠性缺陷：① pipeline 失败时 `source_id = minutes_url` 把 FAILED 状态写错 key，`get_status` 永远显示陈旧进行中状态；② 主链路（event_router/pipeline）幂等仍是 check-then-mark 非原子，原子 `acquire()` 只用于 platform_action_handler/base_adapter，依赖单线程 HTTPServer 才不重入；③ 状态文件 `open(path,"w")` 直写非原子，崩溃半写静默丢失全部状态与历史；④ mock 模式只比对 client_address，反代/容器部署下 peer 恒为 127.0.0.1 → 验签全旁路；webhook 无请求体大小上限。

## What Changes

1. **失败状态正确 key**：`run_from_minutes_url` 在 try 之前解析 source_id，except 分支用真实 source_id（解析失败才回退 URL）写 FAILED。
2. **幂等原子化**：`event_router.handle_event` 与 pipeline 主链路改用 `acquire()` 抢占 + 异常 `release()` + 成功 `mark()`，消除 TOCTOU。
3. **状态文件原子写**：`state_machine.set_state` 改为临时文件 + `os.replace` 原子替换。
4. **mock 模式加固**：RUN_MODE=mock 下拒绝携带 `X-Forwarded-For` 的请求（反代旁路封堵）；webhook 请求体上限 1MB。

## Impact

- 代码：`core/pipeline_orchestrator.py`、`core/event_router.py`、`core/state_machine.py`、`core/webhook_server.py`
- 规格：orchestration-reliability
- 风险：低——行为仅在崩溃窗口/并发/反代场景下变正确，正常路径不变。
