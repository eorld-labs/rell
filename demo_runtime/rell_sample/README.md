# RELL Sample Stage Zero

本目录是 RELL 样品从 0 到 1 的阶段零交付物。阶段零只冻结数据结构、接口边界和 Mock 剧本，不实现完整 Runtime。

## 当前范围

- 单过程倒水样品：`align -> tilting -> maintain_flow -> return`。
- 规则映射式意图输入，不做通用语义检索。
- 异步 Robot Adapter 合约，不接真实机器人。
- Mock 时间轴驱动连续状态变量和事实观测结果。
- 双通道验真：物理液位观测与数字流速积分估计。
- 冲突时降级到人工确认，不做自动传感器融合。

## 关键文件

- `data/pour_water_process_instance.json`：倒水过程模板经偶然绑定后的运行实例。
- `data/mock_timeline_success.json`：成功闭环剧本。
- `data/mock_timeline_no_flow.json`：无水流失败剧本。
- `data/mock_timeline_channel_conflict.json`：双通道冲突剧本。
- `docs/adapter_contract.md`：Runtime 与 Robot Adapter 的异步边界。
- `docs/admission_rules.md`：第一阶段“会不会做”的最小准入规则。
- `docs/schema_change_protocol.md`：Schema 受控变更协议。

## 校验

```powershell
python .\demo_runtime\rell_sample\validate_stage_zero.py
```

通过标准：

- `schemas/` 与 `demo_runtime/rell_sample/data/` 下全部 JSON 可按 UTF-8 解析。
- 倒水过程实例包含四个阶段与最小能力词汇表。
- Mock 时间轴均以当前阶段 `stage_started` 为相对时间零点。
- 成功剧本包含两个通道均成立的 `cup_has_water` 判断。
- 冲突剧本包含两个通道相反的 `cup_has_water` 判断。
- 无水流剧本包含失败事件。

## 边界说明

Mock 时间轴是剧本 DSL，不是 Runtime 队列中的正式事件。MockRobotAdapter 读取时间轴后，应按 Runtime 当前阶段启动时间展开为带 `event_id`、`sequence`、`timestamp`、`process_instance_id`、`stage_id` 和 `event_type` 的 `RuntimeEvent`。

第一阶段不实现多动作过程链、不实现根因诊断、不实现自动模板学习、不实现真实视觉识别或流体仿真。

## 运行 Runtime 样品

```powershell
python .\demo_runtime\rell_sample\run_runtime_sample.py
```

该脚本运行三条纯软件路径：

- `success`：两个观测通道均确认 `cup_has_water` 成立，四阶段完成。
- `no_flow`：倾斜到位但无水流，触发失败标签并进入人工确认。
- `channel_conflict`：物理液位通道成立、数字流速积分通道不成立，进入人工确认。

输出写入：

```text
demo_runtime/output/rell_sample
```

运行结果校验：

```powershell
python .\demo_runtime\rell_sample\validate_runtime_sample.py
```

## 运行最小 API

```powershell
python .\demo_runtime\rell_sample\api_server.py
```

默认地址：

```text
http://127.0.0.1:8876
```

演示页面：

```text
http://127.0.0.1:8876/
```

外部 API：

- `POST /process/admit`
- `POST /process/run`
- `GET /audit/{task_id}`

API 逻辑校验：

```powershell
python .\demo_runtime\rell_sample\validate_api_sample.py
```

## 一键验收

```powershell
python .\demo_runtime\rell_sample\run_all_checks.py
```

该脚本会依次运行阶段零校验、Runtime 样品校验、API 函数校验和本地 HTTP 冒烟测试。
