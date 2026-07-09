# Robot Adapter Contract

本接口是 RELL Runtime 与机器人、仿真或 Mock 数据之间的硬边界。

## 基本原则

1. Adapter 只负责采样、降噪、限频、事件推送和快照返回。
2. Adapter 不判断阶段跃迁条件是否满足。
3. Runtime 基于连续状态变量观测值和偶然绑定阈值判断阶段跃迁。
4. 第一阶段 `MockRobotAdapter` 可空实现背压接口，但必须保留方法形态。

## 最小接口

```python
report_capabilities() -> list[str]
execute_stage_action(stage: dict, context: dict, callback) -> None
subscribe_state_variables(process_instance_id: str, handler) -> None
subscribe_observation_channel(fact_id: str, handler) -> None
pause_streams(process_instance_id: str) -> None
resume_streams(process_instance_id: str) -> None
get_latest_snapshot(process_instance_id: str) -> dict
stop(reason: str, callback=None) -> None
request_human_confirmation(prompt: str, callback) -> None
```

## 最小能力词汇表

- `align_container`
- `tilt_container`
- `hold_pose`
- `return_to_level`
- `observe_tilt_angle`
- `observe_flow_rate`
- `observe_liquid_level`
- `request_human_confirmation`

## 事件要求

每个事件必须包含：

- `event_id`
- `sequence`
- `timestamp`
- `process_instance_id`
- `stage_id`
- `event_type`

Runtime 使用串行事件队列消费事件。等待人工确认时，Runtime 可调用 `pause_streams()`，恢复时调用 `get_latest_snapshot()` 和 `resume_streams()`。
