# Robot Adapter Integration Guide

本文用于指导机器人厂商、仿真平台或中试中心将真实机器人 SDK 接入 RELL 样品 Runtime。

## 一、接入原则

1. Runtime 负责过程模板、阶段跃迁、目标因果事实验真、恢复和审计。
2. Robot Adapter 负责连接机器人 SDK、执行阶段动作、采集传感器数据并推送 RuntimeEvent。
3. Adapter 不判断阶段跃迁条件是否满足。
4. Adapter 不直接决定目标因果事实最终成立状态。
5. 真机接入时优先替换 Adapter，不改 P016 Runtime Core。

## 二、必须实现的方法

```python
report_capabilities() -> list[str]
report_executor_profile() -> dict
execute_stage_action(stage: dict, context: dict, callback=None) -> None
pause_streams(process_instance_id: str) -> None
resume_streams(process_instance_id: str) -> None
get_latest_snapshot(process_instance_id: str) -> dict
stop(reason: str, callback=None) -> None
request_human_confirmation(prompt: str, callback=None) -> None
```

## 三、最小能力词汇表

- `align_container`：将容器壶嘴与杯口对齐。
- `tilt_container`：将容器倾斜到指定角度区间。
- `hold_pose`：保持当前姿态并维持稳定水流。
- `return_to_level`：将容器回正并停止水流。
- `observe_tilt_angle`：输出容器倾角。
- `observe_flow_rate`：输出或估算水流速度。
- `observe_liquid_level`：输出杯中液位或液面间隙。
- `request_human_confirmation`：触发人工确认。

## 四、执行体能力画像

`report_executor_profile()` 用于上报机器人或仿真体的主体约束与本体能力边界。该接口承接 P008 的主体物理约束思路，用于判断不同执行体能否进入空间、可在哪里行动，以及后续是否具备执行某类过程模板的基础条件。

第一阶段只要求提供最小画像，不要求 Adapter 实现复杂 IK、全身规划或自动本体迁移：

| 字段 | 含义 |
|---|---|
| `executor_id` | 执行体标识 |
| `executor_type` | `digital_agent`、`simulated_robot` 或 `real_robot` |
| `body_profile` | 本体类型，例如 `humanoid`、`wheeled_arm`、`mobile_base` |
| `supported_actions` | 能力词汇表 |
| `reachable_workspace` | 可达空间描述或占位 |
| `sensor_frames` | 传感器坐标帧 |
| `end_effector_type` | 末端执行器类型 |
| `payload_limit` | 负载限制 |
| `precision_level` | 执行精度等级 |
| `mobility_constraints` | 转向半径、跨越高度等移动约束 |
| `spatial_entry_constraints` | 主体包络、净空要求等空间进入约束 |

机器人高矮、臂长、腿长、夹爪差异导致的具体运动解算由厂商 SDK、ROS/MoveIt、仿真平台或后续本体适配模块承担。RELL 当前只消费画像，不直接生成底层关节轨迹。

## 五、RuntimeEvent 要求

Adapter 推送给 Runtime 的事件必须包含：

- `schema_version`
- `event_id`
- `sequence`
- `timestamp`
- `process_instance_id`
- `stage_id`
- `event_type`
- `payload`

常用事件：

- `stage_started`
- `state_update`
- `observation_update`
- `failure_event`

## 六、连续状态变量映射

真机 SDK 至少需要映射以下状态：

| RELL 变量 | 来源示例 | 单位 |
|---|---|---|
| `spout_to_cup_distance` | 深度相机、视觉定位、末端位姿计算 | cm |
| `tilt_angle` | 关节编码器、IMU、末端姿态 | degree |
| `water_flow_rate` | 流量传感器、视觉估计、模型估计 | ml_per_second |
| `water_surface_gap` | 深度相机、液位传感器、视觉估计 | cm |

## 七、双通道验真映射

第一阶段倒水样品使用两个通道验证 `cup_has_water`：

1. 物理液位通道：基于深度相机或液位传感器直接观测杯中液位。
2. 数字估计通道：基于水流速度与时间积分估计杯中进水量。

当两个通道均成立时，Runtime 判定目标因果事实成立；当两个通道冲突时，Runtime 阻断后续阶段并请求人工确认。

## 八、真机替换步骤

1. 基于 `adapters/vendor_robot_adapter_stub.py` 新建厂商 Adapter。
2. 在 `connect()` 中连接机器人 SDK、ROS 节点或厂商控制服务。
3. 在 `execute_stage_action()` 中将 `stage_id` 映射为厂商动作命令。
4. 将厂商状态流转换为 RELL 连续状态变量。
5. 将厂商观测结果转换为 `observation_update`。
6. 使用 `validate_adapter_contract.py` 通过接口合约验收。
7. 使用 `run_all_checks.py` 确认未破坏现有 Runtime、API 和页面能力。

## 九、第一轮联调验收标准

1. Adapter 能报告最小能力词汇表。
2. Adapter 能报告最小执行体能力画像。
3. Adapter 能对 `align` 阶段输出 `spout_to_cup_distance`。
4. Adapter 能对 `tilting` 阶段输出 `tilt_angle` 和 `water_flow_rate`。
5. Adapter 能对 `maintain_flow` 阶段输出至少两个 `cup_has_water` 观测通道。
6. Runtime 能在成功路径输出 `completed`。
7. Runtime 能在失败或冲突路径输出 `requires_human_confirmation`。
