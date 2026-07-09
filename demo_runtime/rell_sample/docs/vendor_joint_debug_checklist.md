# Vendor Joint Debug Checklist

本文用于与机器人厂商或中试中心进行第一次联调前的技术交底。

## 一、对方需要提供

1. 机器人 SDK、ROS 接口或控制服务说明。
2. 末端执行器可执行动作列表。
3. 传感器列表及数据频率。
4. 急停、暂停、恢复和人工确认机制。
5. 坐标系定义与标定方式。
6. 可用于倒水演示的容器、杯子和安全测试环境。

## 二、我方提供

1. P016 Runtime Core。
2. Robot Adapter 合约。
3. SimulatedRobotAdapter 样例。
4. VendorRobotAdapterStub 接入占位类。
5. 最小 API 与演示页面。
6. 一键验收脚本。

## 三、一天内目标

1. 跑通 Adapter 合约校验。
2. 读取一条真实或仿真状态数据。
3. 将真实状态映射为 `spout_to_cup_distance` 或 `tilt_angle`。
4. 在页面日志中看到 `state_update` 来自厂商 Adapter。

## 四、一周内目标

1. 跑通 `align` 与 `tilting` 两个阶段。
2. 建立至少一个物理观测通道。
3. 建立一个数字估计通道。
4. 形成一次端到端倒水演示或等价低风险动作演示。

## 五、边界声明

1. 第一轮联调不要求机器人自主学习新动作。
2. 第一轮联调不要求完整流体仿真。
3. 第一轮联调不要求复杂 VLA 或世界模型推理。
4. 第一轮联调重点验证 Runtime 与 Adapter 边界，以及连续状态变量到阶段跃迁的闭环。

## 六、验收命令

```powershell
python .\demo_runtime\rell_sample\validate_adapter_contract.py
python .\demo_runtime\rell_sample\run_all_checks.py
```
