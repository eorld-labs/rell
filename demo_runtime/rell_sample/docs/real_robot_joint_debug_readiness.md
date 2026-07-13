# 真机联调准备说明

## 当前完成边界

当前工程已经把具身运行时到真机 SDK 之间的通用边界收口为以下链条：

```text
P016/P018 候选阶段目标
  -> 真机安全网关准入
  -> 厂商传输命令
  -> 原始遥测与传感观测
  -> RELL observation_update 候选
  -> P016/P018 因果事实验真
```

安全网关不判断任务是否完成，也不直接提交运行时事实。厂商 SDK 只负责执行动作与返回观测，任务完成仍由既有因果事实和双通道验真机制判断。

## 已实现能力

- `shadow`：只编译和记录命令，不向传输层发送。
- `dry_run`：完成标定与安全边界检查，不向传输层发送。
- `armed`：仅在传输连接、心跳有效、标定可用且人工明确授权时允许发送。
- 心跳超时自动急停并回到 `shadow`。
- 急停锁存必须经人工明确授权重置，重置后仍需重新武装。
- 命令具备 TTL、世界版本、进程实例和幂等标识。
- 超过标定速度或接触力上限的命令在发送前被拒绝。
- 真机遥测统一携带传感器、坐标帧、置信度和世界版本。
- 观测桥只生成候选，不提交物理事实。
- 命令、回执和运行时事件可录制并离线回放。

## 首条真机联调链

```text
observe_target
-> navigate_to_target
-> align_end_effector
-> grasp_target
-> verify_target_in_gripper
-> navigate_to_destination
-> place_target
-> verify_target_supported
```

该链覆盖视觉观测、底盘或本体移动、末端对准、抓取、放置以及两次关键物理验真。接水等流体任务应在这条低风险闭环稳定后再接入。

## 真机到场后必须补充

1. 机器人品牌、型号和 SDK/ROS2 接口。
2. `map -> base_link -> camera -> end_effector` 实测坐标链。
3. 机身包络、可达空间、负载、速度、角速度和接触力上限。
4. 相机、关节、夹爪、力矩等传感器的真实帧和时间戳映射。
5. 厂商急停、取消命令、心跳和状态回执接口。
6. 在围栏或低速工位依次验收 shadow、dry_run、armed 三种模式。

`data/real_robot_calibration_template.json` 中的空值必须由实测填写。只有人工验收后将 `calibration_status` 标为 `hardware_verified`，真实传输才允许进入武装阶段。

## 软件前置验收

```powershell
python demo_runtime\rell_sample\validate_real_robot_readiness.py
```

测试使用 `loopback_only` 传输验证协议。其输出不能作为物理事实，也不会声称向真实硬件发送了命令。

## 联调 API

```text
GET  /real-robot/readiness
GET  /real-robot/session/{session_id}
POST /real-robot/session/start
POST /real-robot/session/heartbeat
POST /real-robot/session/mode
POST /real-robot/session/dispatch
POST /real-robot/session/emergency-stop
POST /real-robot/session/reset-stop
```

`loopback_preflight` 只验证协议。真实厂商传输必须由本地、经过审查的启动代码调用 `register_real_robot_transport_factory()` 注册；HTTP 请求不能动态加载厂商代码。
