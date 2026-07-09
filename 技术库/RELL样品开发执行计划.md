# RELL 样品开发执行计划

依据文件：`技术库/RELL样品落地0到1计划.md`

## 一、开发目标

第一阶段只做一个可运行的单过程倒水样品，证明 P016 Runtime 的最小闭环：

```text
规则输入
-> 模板选择
-> 准入判断
-> 偶然绑定
-> 事件驱动阶段推进
-> 双通道因果验真
-> 最终成立状态回流
-> 恢复/人工确认/停止
-> execution_trace 与 audit_summary
```

第一阶段不做：

- 多动作过程链。
- 通用编排引擎。
- 真实流体仿真。
- 真实视觉识别。
- 机器人底层执行模型。
- 自动技能泛化。
- 复杂前端或 3D 演示。
- 完整来源链、代理权预算和多主体治理。

## 二、阶段零：接口与数据冻结

周期：3 至 5 天。

阶段零不写业务 Runtime，只冻结接口、Schema 和 Mock 数据。

### 2.1 必交付物

1. `schemas/process_template.schema.json`
2. `schemas/occasional_binding.schema.json`
3. `schemas/fact_observation.schema.json`
4. `schemas/runtime_event.schema.json`
5. `schemas/stage_runtime_state.schema.json`
6. `schemas/execution_trace.schema.json`
7. `schemas/audit_summary.schema.json`
8. `demo_runtime/rell_sample/data/pour_water_task_intent.json`
9. `demo_runtime/rell_sample/data/pour_water_process_instance.json`
10. `demo_runtime/rell_sample/data/mock_timeline_success.json`
11. `demo_runtime/rell_sample/data/mock_timeline_no_flow.json`
12. `demo_runtime/rell_sample/data/mock_timeline_channel_conflict.json`
13. `demo_runtime/rell_sample/docs/adapter_contract.md`
14. `demo_runtime/rell_sample/docs/admission_rules.md`
15. `schemas/executor_profile.schema.json`

### 2.2 阶段零硬门槛

必须通过以下检查后才能进入阶段一：

1. 倒水任务完整 Mock JSON 能串通最小数据流。
2. 双通道 Mock 信号定义完成，并至少包含一个冲突配置。
3. 所有 JSON 示例通过 Schema 校验。
4. Robot Adapter 最小能力词汇表完成。
5. Robot Adapter 能上报最小执行体能力画像，用于承接 P008 主体物理约束和后续空间可进入性准入。
6. Runtime Event 结构包含 `event_id`、`sequence`、`timestamp`、`process_instance_id`、`stage_id`。
7. Schema 版本号采用 major/minor 规则。

## 三、阶段一：纯软件 Runtime 样品

周期：1 至 2 周。

### 3.1 模块拆分

#### 3.1.1 Runtime Core

建议文件：

- `demo_runtime/rell_sample/runtime/core.py`
- `demo_runtime/rell_sample/runtime/event_queue.py`
- `demo_runtime/rell_sample/runtime/state_machine.py`

职责：

- 串行消费 Event Queue。
- 管理 `stage_runtime_state`。
- 判断阶段跃迁条件。
- 处理 `awaiting_human_confirmation`。
- 处理恢复次数和停止条件。
- 生成 `execution_trace`。

验收：

- 不使用阻塞式死循环作为主逻辑。
- 所有状态写入都通过单线程事件消费完成。
- 人工等待期间暂停非必要事件消费，并从最新快照恢复。

#### 3.1.2 MockRobotAdapter

建议文件：

- `demo_runtime/rell_sample/adapters/base.py`
- `demo_runtime/rell_sample/adapters/mock_robot.py`
- `demo_runtime/rell_sample/adapters/timeline_loader.py`

职责：

- 按 Timeline JSON 回放事件。
- 支持成功、无水流、通道冲突、传感器 unknown。
- 支持 `pause_streams()`、`resume_streams()`、`get_latest_snapshot()`。
- 支持 `stop(reason, callback)`。

验收：

- Mock 不硬编码复杂物理逻辑。
- `time_ms` 以当前阶段 `stage_started` 为相对零点。
- 能跑通至少三条时间轴：成功、无水流、通道冲突。

#### 3.1.3 Process Template Runner

建议文件：

- `demo_runtime/rell_sample/runtime/process_runner.py`
- `demo_runtime/rell_sample/runtime/transition_guard.py`

职责：

- 加载过程模板。
- 定位当前阶段。
- 读取绑定阈值。
- 基于连续状态变量与阈值比较判断跃迁。

验收：

- Adapter 不判断阶段跃迁。
- `align -> tilt -> maintain_flow -> return` 可完整推进。
- 至少一个阶段跃迁依赖事实验真结果。

#### 3.1.4 Occasional Binding Resolver

建议文件：

- `demo_runtime/rell_sample/runtime/binding_resolver.py`

职责：

- 校验对象、传感器、阈值、确认窗口、偏好参数。
- 生成 `process_instance`。
- 输出缺失绑定项。

验收：

- 家庭 A 绑定可执行。
- 未知容器绑定失败，并输出不可执行原因。

#### 3.1.5 Fact Verifier

建议文件：

- `demo_runtime/rell_sample/runtime/fact_verifier.py`
- `demo_runtime/rell_sample/runtime/arbitration.py`

职责：

- 读取两个 Mock 通道。
- 形成通道判断。
- 输出 `established`、`not_established`、`conflicted`、`unknown`。
- 处理确认窗口、超时和冲突降级。

验收：

- 通道一：模拟液位高度。
- 通道二：流速积分与倾角估计。
- 冲突时不自动融合，直接请求人工确认。
- unknown 不无限等待。

#### 3.1.6 Admission Checker

建议文件：

- `demo_runtime/rell_sample/runtime/admission.py`

职责：

- 执行规则映射。
- 检查模板存在。
- 检查绑定完整。
- 检查 Adapter 能力词汇表。
- 检查观测通道可用。

验收：

- “倒水 / 倒一杯水 / 给客人倒水”映射到 `pour_water`。
- 未知任务进入不会做路径。
- 缺绑定进入不会做路径。

#### 3.1.7 Audit And Trace

建议文件：

- `demo_runtime/rell_sample/runtime/trace.py`
- `demo_runtime/rell_sample/runtime/audit.py`

职责：

- 写入事件流水。
- 写入阶段跃迁。
- 写入事实验真结果。
- 写入人工确认和恢复。
- 生成审计摘要。
- 生成可人工审核的技能包草案。

验收：

- `stage_runtime_state` 是当前快照。
- `execution_trace` 是追加日志。
- 审计摘要展示双通道输入、判断、冲突和最终状态。

#### 3.1.8 Minimal API

建议文件：

- `demo_runtime/rell_sample/api.py`

第一阶段外部 API：

- `POST /process/admit`
- `POST /process/run`
- `GET /audit/{task_id}`

调试接口：

- `GET /process/status/{task_id}`
- `POST /process/events/{task_id}`

验收：

- 外部 API 文档只承诺 3 个正式接口。
- status/events 标注为调试接口。
- `POST /process/run` 返回 `task_id`，不阻塞等完整过程结束。

## 四、演示场景

阶段一必须跑通四个演示。

### 4.1 成功路径

输入：

```text
给客人倒一杯水
```

预期：

- 命中 `pour_water`。
- 使用家庭 A 绑定。
- 阶段推进完成。
- 双通道一致。
- `cup_has_water = established`。
- 输出审计摘要。

### 4.2 缺绑定不会做

输入：

```text
用未知容器倒水
```

预期：

- 找到模板。
- 缺少对象或阈值绑定。
- 输出不可执行原因。
- 不进入 Runtime 执行。

### 4.3 无水流恢复

输入：

```text
故障配置：no_flow
```

预期：

- 倾斜阶段达到阈值。
- 水流未成立。
- 写入预设失败标签。
- 达到恢复边界后请求人工确认或停止。

### 4.4 双通道冲突

输入：

```text
故障配置：channel_conflict
```

预期：

- 通道一判断有水。
- 通道二判断注入量不足。
- `final_establishment_state = conflicted`。
- Runtime 阻断后续阶段。
- 请求人工确认。

## 五、第一周建议排期

### Day 1

- 确认 Schema 文件列表。
- 确认 Runtime Event 结构。
- 确认 Adapter Contract。
- 确认能力词汇表。

### Day 2

- 完成倒水过程模板 Mock 实例。
- 完成家庭 A 偶然绑定 Mock 实例。
- 完成成功时间轴脚本。

### Day 3

- 完成无水流和通道冲突时间轴脚本。
- 完成 Schema 校验脚本。
- 完成阶段零硬门槛评审。

### Day 4

- 开始 Runtime Event Queue。
- 开始 MockRobotAdapter。
- 开始 stage_runtime_state 快照结构。

### Day 5

- 跑通成功路径的最小命令行 demo。
- 输出第一版 execution_trace。
- 复盘 Schema 是否需要受控变更。

## 六、开发纪律

1. 不允许绕过 Adapter 直接读 Mock 数据。
2. 不允许 Adapter 判断阶段跃迁条件。
3. 不允许 LLM 输出直接进入 Runtime。
4. 不允许新增正式外部 API，除非更新本计划。
5. 不允许让 MockRobotAdapter 变成物理仿真器。
6. 不允许让 `execution_trace` 和 `stage_runtime_state` 互相混用。
7. 不允许在双通道冲突时自动采信单一通道继续执行。
8. 不允许 Schema 偷偷改，必须更新版本号和 Mock JSON。

## 七、完成标准

第一阶段完成时，应能向基金、机器人公司或内部评审展示：

1. 一个本地可运行样品。
2. 一个倒水过程模板。
3. 一套偶然绑定。
4. 三条 Mock 时间轴。
5. 一个事件驱动 Runtime。
6. 一个异步 MockRobotAdapter。
7. 一个事实验真器。
8. 一个不会做准入判断。
9. 一份 execution_trace。
10. 一份 audit_summary。

只要以上十项成立，样品即可进入阶段二：仿真/日志驱动联调。
