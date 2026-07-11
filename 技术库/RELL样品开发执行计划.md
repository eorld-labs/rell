# RELL 样品开发执行计划

## 当日增补（2026-07-11）：端侧概念内化层落稿与实施拆解

在 P017 主链、统一语义入口、状态问答、边教边动和最小教学闭环已经初步跑通后，当前样品的下一瓶颈已经从“能不能执行”转移为“端侧能不能形成稳定工作语义”。因此，本轮新增端侧概念内化层主线，将高频任务语义、高频状态语义和高频教学语义从云端依赖中剥离，沉到本体侧，形成端脑自己的概念、状态和经验闭环。

这一轮不是为了增加一个新层好看，而是为了固定以下主判断：

1. 直接经验沉在本体侧，构成端脑；
2. 外域经验沉在云脑，作为候选补给；
3. 执行主体的长期主路线不是“大模型直接控制动作”，而是“概念 + 状态 + 经验”交织形成的端侧自行推理；
4. 云脑只增益，不替代端脑主体。

### 增补目标

本轮增补以四个递进版本推进：

1. 第一版：状态概念内化；
2. 第二版：高频动作概念内化；
3. 第三版：教学语言拆层；
4. 第四版：云脑补给桥。

### 第一版：状态概念内化

目标：让执行主体稳定理解并回答高频状态问题，且回答来源只允许来自当前任务期运行时世界状态快照或当前运行上下文。

建议新增或补强文件：

1. `demo_runtime/rell_sample/concept_core/concept_units.py`
2. `demo_runtime/rell_sample/concept_core/query_router.py`
3. `demo_runtime/rell_sample/concept_core/concept_bridge.py`
4. `demo_runtime/rell_sample/data/concept_library.json`
5. `demo_runtime/rell_sample/api_server.py`

本版要完成的事：

1. 固定状态概念词表，至少覆盖“有水/没水”“现在/下一步”“在哪”“拿着什么”“当前偏好”；
2. 把“当前杯子有没有水”“你现在在哪”“你现在在做什么”“下一步做什么”等高频问句映射到统一 `query_type`；
3. 把 `query_type` 映射到任务期运行时世界状态快照槽位，如 `established_facts`、`executor.location_ref`、`current_stage`、`completed_stages`、`active_preferences`；
4. 当当前目标已达成时，稳定输出“等待新的任务指令”，而不是遗留上一步动作名；
5. 所有状态回答都附带来源字段，明确来自 `runtime_world_state_snapshot_only` 或 `runtime_world_state_snapshot_and_current_runtime_context_only`。

验收口径：

1. 高状态类问句命中率稳定；
2. 不依赖大模型也能完成核心状态问答；
3. 回答不从长期经验库和历史日志补推当前真值；
4. 当前动作、下一步和已完成步骤的表达与运行时快照保持一致。

### 第二版：高频动作概念内化

目标：让执行主体对高频动作表达形成稳定概念桥接，而不是每次靠单句硬编码或等待大模型重写。

建议新增或补强文件：

1. `demo_runtime/rell_sample/concept_core/concept_parser.py`
2. `demo_runtime/rell_sample/concept_core/concept_units.py`
3. `demo_runtime/rell_sample/concept_core/concept_bridge.py`
4. `demo_runtime/rell_sample/api_server.py`
5. `demo_runtime/rell_sample/docs/api_contract.md`

本版要完成的事：

1. 为“接一杯水”“倒水”“拿起杯子”“去水源处”“去操作台”“绕开障碍”建立本地动作概念；
2. 允许动作概念桥接到目标因果事实、候选过程链或候选经验，而不是直接下发动作用脚本；
3. 把动作概念解析结果统一落成 `intent_frame` 或 `semantic_request`，继续交给编排层和 P017 可行性主链裁决；
4. 让“任务执行”入口和“语义预览”入口共用同一套概念解析主链。

验收口径：

1. 高频任务短句不依赖云端即可稳定落到目标事实或候选过程链；
2. 概念层只给候选，不直接执行；
3. 复杂、歧义或陌生输入仍可保留 `llm_escalatable` 升级位。

### 第三版：教学语言拆层

目标：让教学输入不再被当作平铺自然语言，而是稳定拆成目标约束、过程约束、可变区间和偏好约束。

建议新增或补强文件：

1. `demo_runtime/rell_sample/concept_core/concept_parser.py`
2. `demo_runtime/rell_sample/concept_core/teaching_frames.py`
3. `demo_runtime/rell_sample/api_server.py`
4. `demo_runtime/rell_sample/docs/api_contract.md`
5. `demo_runtime/rell_sample/validate_api_sample.py`

本版要完成的事：

1. 把“先去拿杯子再接水”“轻一点”“先别做这个”“你可以自己换个顺序但结果要对”一类表达分层结构化；
2. 显式区分教学中的结果导向、过程导向、严格跟随和局部变通授权；
3. 让教学链路稳定回答“我理解了什么”“我缺什么前提”“我现在做到哪一步”“这一步是否发生偏离”；
4. 将偏离后的追认优先写入端侧偏好记忆与审计流，而不是直接写进公共经验库。

验收口径：

1. 单步教学闭环稳定；
2. 缺前提、偏离、恢复和追认都有结构化解释；
3. 自主预算默认仍受 P015 当前偏好与治理层边界约束。

### 第四版：云脑补给桥

目标：在不破坏端脑主体性的前提下，给端侧概念层增加陌生语义和外域经验补给能力。

建议新增或补强文件：

1. `demo_runtime/rell_sample/concept_core/cloud_recall.py`
2. `demo_runtime/rell_sample/concept_core/concept_bridge.py`
3. `demo_runtime/rell_sample/api_server.py`
4. `demo_runtime/rell_sample/docs/api_contract.md`

本版要完成的事：

1. 固定 `CloudRecallPacket` 一类结构，声明端侧概念缺口、当前目标事实和当前运行时摘要；
2. 云端返回结果只允许是候选概念、候选过程链、候选经验或澄清问题；
3. 云脑返回结果必须重新进入端侧概念层、编排层和可行性判断主链，不能绕过本地裁决；
4. 在云脑不可用时，端侧最小状态问答和高频动作链路仍能正常工作。

验收口径：

1. 云脑缺席不使本地最小主链瘫痪；
2. 云脑输出不会直接变成执行控制；
3. 外域经验始终以候选补给而不是本地主体替代的方式进入系统。

### 本轮建议实施顺序

1. 先做第一版，把状态概念主干做稳；
2. 再做第二版，把高频动作概念桥接到目标事实和候选过程链；
3. 再做第三版，把教学语言拆到目标、过程、偏好和局部变通四层；
4. 最后再做第四版，引入云脑补给桥但不改变端脑优先原则。

### 本轮工程纪律

1. 概念层不直接下发执行动作；
2. 状态回答不允许用历史经验替代当前世界状态真值；
3. 云脑不允许绕过编排层和执行层；
4. 概念晋升仍坚持“先经验，后晋升，人工确认再入库”；
5. 所有新接口优先并入现有统一语义入口，不另起一套平行入口。

## 当日增补（2026-07-10）：P014 执行恢复证据补强

本轮补强的目标不是再写一套孤立的补救脚本，而是把 P014 从早期 `run_skill_cocreation.py` 中的静态补救痕迹，升级为 `demo_runtime/rell_sample/` 主链中的动态恢复记录闭环。恢复逻辑现在随执行主链共同发生，并可被查询、审计和复核。

### 增补范围

1. 在 `demo_runtime/rell_sample/api_server.py` 中新增恢复记录主链函数：`load_recovery_library()`、`save_recovery_library()`、`build_recovery_action()`、`build_recovery_outcome_type()`、`persist_recovery_record()`、`attach_recovery_record_to_context()`、`build_recovery_record_for_task()`、`get_recovery_record()` 和 `get_recovery_records_for_task()`。
2. 在 `demo_runtime/rell_sample/data/recovery_record_library.json` 中固定恢复记录持久化载体，使失败、冲突和补救结果不只停留在运行期内存。
3. 将恢复记录接入四类关键阻断路径：步骤前检查阻断、运行时冲突再适配、执行闭环分发中途阻断、普通运行结果非 `completed` 的异常收口。
4. 在 `demo_runtime/rell_sample/docs/api_contract.md` 中补入恢复记录查询接口，形成字段级接口证据。
5. 在 `demo_runtime/rell_sample/validate_api_sample.py` 和 `demo_runtime/rell_sample/run_all_checks.py` 中补入恢复记录查询、库持久化和 HTTP smoke 校验。

### 当前接口补强

1. `GET /recovery/library`：返回恢复记录库摘要与记录列表。
2. `GET /recovery/task/{task_id}`：按任务查询恢复记录，证明恢复动作与任务期快照、执行痕迹和审计链路可关联。
3. `GET /recovery/{recovery_id}`：按恢复记录标识查询单条记录，证明恢复结果具备可复核性。

### 工程证据意义

1. 证明 P014 不再只是“出错后人工补一句说明”，而是“执行偏离/冲突/阻断 -> 形成恢复记录 -> 查询与审计 -> 支持再适配”的主链能力。
2. 证明恢复记录与 `task_id`、运行时世界状态快照、执行回传和审计记录存在结构化关联，可直接作为专利答复和研发留痕材料。
3. 证明 RELL 样品在 P017 迁移主链之外，已经把执行恢复层沉到同一套 API 和校验体系中，避免 P014 证据停留在旧样品。

### 本轮验收命令

```powershell
python demo_runtime\rell_sample\validate_api_sample.py
python demo_runtime\rell_sample\run_all_checks.py
```

预期结果：两条命令均通过，且恢复记录查询接口、恢复库持久化和 HTTP smoke 检查全部通过。

## 当日增补（2026-07-10）：P013 任务语义翻译证据收束

在当前样品中，P013 的实际能力已经存在于统一语义入口、因果求解、显式路线保真、对话教学和边教边动主链中，但此前主要散落在 `validate_api_sample.py` 的综合断言里，不利于后续单独举证。为此，本轮新增独立的 P013 校验脚本和证据输出目录，将任务语义翻译层从“代码里有”收束为“可重复运行、可落盘、可答复”的工程证据包。

### 增补范围

1. 新增 `demo_runtime/rell_sample/validate_p013_task_semantics.py`，固定 P013 的六段证据输出。
2. 新增输出目录 `demo_runtime/output/rell_sample/p013_task_semantics/`，统一落盘 `00_summary.json`、`evidence_index.json` 和六个分段证据文件。
3. 新增 `技术库/P013-任务语义翻译/P013任务语义翻译工程证据说明.md`，把验证命令、输出目录、证据字段和典型审查质疑对应关系写成可直接翻阅的中文说明。
4. 将 `validate_p013_task_semantics.py` 接入 `demo_runtime/rell_sample/run_all_checks.py`，使 P013 与 P014、P017 一样进入一键回归主链。

### 当前证据覆盖点

1. 统一语义入口：证明 `task_execution`、`state_query`、`teaching` 和 `clarification` 四类请求能够落成结构化 `semantic_request`。
2. 目标事实与过程链：证明短句意图和长句意图都能翻译为目标因果事实和可执行过程链，而不是停留在文本标签。
3. 显式路线保真：证明“门旁边 -> 服务位 -> 操作台 -> 水源处”等空间语义路线可保留进入任务计划。
4. 教学与反馈闭环：证明对话教学、边教边动、缺失前提反馈和任务经验沉淀已经形成闭环。
5. LLM 边界：证明统一入口、概念解析和提示词契约共同约束语言模型只做语义理解，不直接下发执行。

### 本轮验收命令

```powershell
python demo_runtime\rell_sample\validate_p013_task_semantics.py
python demo_runtime\rell_sample\run_all_checks.py
```

预期结果：两条命令均通过，并生成 `demo_runtime/output/rell_sample/p013_task_semantics/` 下的证据文件。

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

#### 3.1.8 RuntimeWorldState 与经验不变量契约

建议文件：

- `demo_runtime/rell_sample/runtime/world_state.py`
- `demo_runtime/rell_sample/runtime/invariant_contract.py`

职责：

- 在任务启动时，基于 P010 主体侧空间认知模型生成端侧运行时世界状态快照。
- 在每个过程步骤完成时，依据 P016 的 `requires_facts`、`produces_fact` 和 `destroys_facts` 更新执行体位置、持有物、对象位置和已成立事实。
- 运行时世界状态只作为当前任务工作记忆，生命周期为 `ephemeral_task_memory`，任务结束后不作为长期世界数据库保存。
- 经验库沉淀时，不存绝对坐标、固定关节角或固定执行时长，而存拓扑关系、试探方向与物理约束、事实终止条件。
- 具体机器人如何到达拓扑关系，由 Robot Adapter、机器人 SDK、运动学求解器或厂商控制器在当前本体上实现。

验收：

- `runtime_world_state` 能展示执行体从初始区域到目标区域的变化。
- `pick_up_cup` 后，杯子位置从空间对象位置更新为 `executor_gripper`。
- `fill_cup_at_water_source` 后，`cup_contains_water` 成为已成立事实。
- `experience_library` 中每条经验包含 `invariant_contract`。
- `invariant_contract.forbidden_storage` 明确禁止 `absolute_coordinates`、`robot_specific_joint_angles` 和 `fixed_execution_duration`。
- 所有阶段终止条件以事实成立为边界，例如 `cup_contains_water == established`，而不是固定时长。

架构核实结论：

- P010 负责相对稳定的空间语义底图。
- RuntimeWorldState 负责当前任务期间的状态对齐和工作记忆。
- P012 负责把多条交互经验归纳为可迁移概念和典型经验模式。
- P016 负责阶段跃迁、事实验真和最终成立状态回流。
- 经验库保存可迁移不变量和因果签名，技能包在此基础上加入模板、绑定、验收和审计材料，形成可交付能力。

#### 3.1.9 Minimal API

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
9. 不允许把经验库存成绝对坐标、固定关节角或固定执行时长；经验库只保存可迁移不变量、因果签名和可审核记录。

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

## 八、P017 提交后工程修订

P017 已按“一种跨空间跨本体的真实经验迁移执行方法及系统”提交后，RELL 样品的后续工程补强不再只围绕 P016 Runtime 阶段跃迁，而应把 P017 的迁移适配控制器主链显式做成可运行证据。

### 8.1 今天优先补强的工程主链

1. 增加迁移适配控制器接口：在现有经验记录、当前空间语义数据、本体能力画像和任务期运行时世界状态快照基础上，生成绑定候选以及执行可行性结果。
2. 增加不可执行、部分不可执行和需降级执行的结构化结果：输出不可执行原因、缺失对象、缺失能力、缺失事实前提、建议动作、替代经验候选或教学入口。
3. 增加任务期快照释放可观测字段：为任务期运行时世界状态快照生成快照标识，执行后生成释放令牌、释放状态和审计关联，证明快照不作为长期世界数据库继续参与后续任务。
4. 增加开放执行闭环调用载荷：把通过适配的经验步骤、绑定候选、执行约束和任务期快照标识组织为可发送给 ROS、机器人 SDK、仿真执行器、数字执行体或其他执行闭环的载荷。

### 8.2 计划调整后的最小 API

在原有 `POST /process/admit`、`POST /process/run`、`GET /audit/{task_id}` 基础上，新增或补强以下 API 作为工程证据：

1. `POST /experience/migrate`：接收任务意图或经验记录标识，返回迁移任务标识、任务期快照标识、绑定候选、执行可行性结果、不可执行原因和执行闭环调用载荷。
2. `GET /runtime_world_state/{task_id}`：返回任务期运行时世界状态快照、生命周期状态、释放状态和审计关联。
3. `POST /runtime_world_state/release`：触发任务期快照释放，返回释放令牌、释放状态、释放原因和审计记录标识。

### 8.3 工程验收补充

1. 成功路径应能展示从经验不变量契约到绑定候选、执行可行性结果、执行闭环调用载荷、事实回传和快照释放的完整链路。
2. 不可执行路径应能展示当前空间语义、本体能力画像或任务期事实缺失导致的阻断，不进入底层执行闭环。
3. 部分不可执行或需降级执行路径应能展示可执行步骤集合、不可执行步骤集合、降级动作或人工确认入口。
4. 审计记录应能关联 `migration_task_id`、`runtime_world_state_snapshot_id`、`binding_candidate_id`、`execution_callback_id`、`release_token` 和 `audit_record_id`。

### 8.4 分案工程种子的落实顺序

1. 第一优先级：迁移适配控制器 / SDK / API 接口闭环，直接对应商业形态和取证难点。当前已形成 `POST /experience/migrate`。
2. 第二优先级：任务期快照可观测与释放证明，支撑状态隔离和审计。当前已形成 `GET /runtime_world_state/{task_id}` 与 `POST /runtime_world_state/release`。
3. 第三优先级：不可执行结果到教学入口和经验缺口记录，支撑安全边界和产品闭环。当前已形成 `experience_gap_record` 与 `GET /experience/gap/{gap_record_id}`。
4. 第四优先级：运行时冲突处理与重新适配，复用现有 channel_conflict 场景继续加厚。当前已形成 `POST /runtime_world_state/readapt` 与 `GET /runtime_readaptation/{readaptation_id}`。
5. 第五优先级：执行闭环开放接口、多类型执行器兼容和数字执行体迁移，作为接口文档和 API 载荷持续补强。当前已形成 `POST /execution/dispatch` 与 `GET /execution/dispatch/{dispatch_id}`，支持 `process_template_executor`、`digital_executor`、`simulated_robot`、`ros_controller`、`robot_sdk` 和 `vla_policy` 等执行器类型的统一事实回传。

### 8.5 P017 最小特征闭环证据

为便于后续审查意见答复和工程证据复核，新增 `demo_runtime/rell_sample/validate_p017_minimal_loop.py`，将 P017 的最小特征闭环固定为可重复运行的六段 JSON 证据链。

输出目录：`demo_runtime/output/rell_sample/p017_minimal_loop/`

输出文件：
1. `01_experience_record.json`：经验记录、目标因果事实、过程链、因果签名和经验不变量契约。
2. `02_migration_context.json`：当前空间语义数据、本体能力画像和任务意图。
3. `03_runtime_world_state_snapshot.json`：任务期运行时世界状态快照、生命周期和释放状态。
4. `04_binding_and_feasibility.json`：绑定候选、执行可行性结果和执行闭环调用载荷。
5. `05_execution_fact_feedback.json`：开放执行闭环分发、事实状态回传和任务期快照更新。
6. `06_release_and_audit.json`：快照释放令牌、释放状态和审计记录。

验证命令：`python demo_runtime\rell_sample\validate_p017_minimal_loop.py`

### 8.6 P017 最小闭环展示模式

在 DEMO 首页新增“P017 最小闭环”入口，并新增 `GET /p017/minimal-loop` 接口读取最小闭环证据包。

展示内容：
1. 读取 `evidence_index.json` 中的技术特征、权利要求步骤、关键字段、代码来源和审查答复用途。
2. 读取六个分段证据 JSON，并在页面中按经验记录、迁移上下文、任务期快照、绑定与可行性、执行事实回传、快照释放与审计展示。
3. 每段证据以可展开卡片形式展示核心字段和原始 JSON，便于录屏、截图和内部复核。

接口：`GET /p017/minimal-loop`

## 九、数字执行主体优先的主线备忘

P017 提交后，样品工程的第一主线调整为“数字执行主体先跑通完整技术链条”。这里的数字执行主体不是单纯网页动画，而是当前样品中能够读取任务意图、维护任务期运行时世界状态、执行经验步骤、回传事实结果并形成经验记录的执行主体抽象。网页只是第一阶段最容易观察、取证和迭代的承载形态。

主线顺序如下：

1. 先在网页数字执行主体中跑通“自主判断能不能执行、执行经验步骤、回传因果事实、释放任务期快照”的完整链路。
2. 再实现“边教边动”的教学闭环：用户教一个步骤，数字执行主体执行一个步骤并立即反馈产出事实、销毁事实、缺失前提和当前运行时世界状态；当用户确认成功后，将过程链固化为经验记录。
3. 技能共创台从 0 到 1 的平台化搭建暂时后置，避免过早扩成管理台、市场台或流程台，稀释当前最关键的迁移执行主链。
4. 上述链路跑通后，再切换不同数字空间场景验证跨空间迁移；如果时间允许，再接入本地开源物理引擎或真实机器人接口。
5. 后续所有 DEMO 打磨应优先服务这条主线：数字执行主体如何贯彻 P017 的经验记录、迁移上下文、任务期快照、适配可行性判断、执行闭环事实回传和经验固化，而不是先追求视觉复杂度或泛化平台形态。

### 9.1 边教边动最小 API

1. `POST /teaching/session/start`：启动数字执行主体教学会话，生成任务期运行时世界状态快照。
2. `POST /teaching/session/step`：接收本次教学步骤，校验前提事实；若可执行则更新运行时世界状态并返回事实反馈，若不可执行则返回缺失前提和建议先教学步骤。
3. `POST /teaching/session/finish`：在目标事实已达成或用户确认成功后，将已执行过程链固化为经验记录，并释放任务期快照。
4. `GET /teaching/session/{session_id}`：查询教学会话、过程链、步骤反馈和当前任务期快照。

### 9.2 验收口径

1. 用户输入“到水源处接一杯水”后，可逐步教学“走向操作台、拿起杯子、到水源处、接一杯水”，每一步都有即时事实反馈。
2. 若用户先教“拿起杯子”，系统应反馈缺少 `executor_at_counter` 等前提事实，而不是强行把杯子标记为已抓取。
3. 当 `cup_contains_water` 成立或用户确认成功时，系统应把已执行步骤固化为经验记录，并把来源标记为 `stepwise_teaching_session`。
4. 教学会话结束后应释放任务期快照，返回 `release_token`，防止临时事实污染后续任务。

### 9.3 统一语义路由器

在数字执行主体主线下，后续自然语言入口不再继续按“每类话术单独加接口”的方式扩散，而是统一先进入语义路由器。

1. 语义路由器将输入归入 `state_query`、`task_execution`、`teaching`、`clarification` 或 `unknown`。
2. 轻量、短句、高频输入默认由规则路由处理，复杂、多约束、长句输入预留 `llm_escalatable` 升级位。
3. 无论前端使用规则路由还是后续接入更大模型，输出都应落成统一 `semantic_request` / `intent_frame` 结构，再进入状态查询、任务执行、教学解析或原因说明链路。
4. 状态问答仍坚持只读当前任务期运行时世界状态快照，不回退到长期经验库或执行历史做补充推理。
5. 现在“运行任务”入口也已开始收口到统一语义主链：DEMO 页面先用 `/agent/query` 做语义预览和准入判断，再以 `auto_execute=true` 在同一接口下触发执行，作为后续数字执行主体、教学和大模型升级的共同入口。

### 9.4 LLM 语义边界与概念层补强

在统一语义主链之上，后续大模型接入只承担“长程或陌生任务语义理解”的角色，不参与连续控制、不直接决定执行成功与否，也不允许越过任务期运行时世界状态快照、概念层、经验层和编排层。

1. 新增稳定提示词契约接口 `POST /llm/prompt-contract`，把 `semantic_request`、`intent_translation_preview`、概念层解析摘要、可选的当前任务期快照视图以及输出边界打包，作为后续模型调用层唯一允许的输入边界。
2. 新增概念层公共语义单元库 `GET /concept/library` 与 `demo_runtime/rell_sample/data/concept_library.json`，把“空间目标导航”“可交互对象获取”“可盛装容器”“水源资源区”“液体转移任务”等公共能力从经验层中抬出来，形成稳定复用的中间语义单元。
3. 新增 `POST /concept/resolve`，把自然语言任务解析为概念层候选；该接口只声明可复用概念、运行时绑定状态和回到编排层的边界，不直接下发动作。
4. 概念层遵循“先教经验，后晋升概念”的顺序：优先让示教和运行时事实闭环形成稳定经验，再抽象为概念单元，避免把概念层做成隐藏规划器。
5. 当前世界状态给大模型的任何输入必须来自 `POST /llm/context-view` 暴露的当前任务期运行时世界状态快照；若快照已释放，则不能再把旧快照当作当前世界状态提供给模型。
6. 后续若接入更大模型，仍只允许输出候选语义、候选过程链或澄清内容，且必须先进入 `POST /llm/candidate/validate`，再回到空间语义、本体能力、概念层、经验层和编排层共同判断是否执行。
7. 概念晋升继续坚持人工确认闸门：经验成功形成后自动生成 `concept_promotion_candidates`，只有通过 `POST /concept/candidates/confirm` 做人工确认，才允许把候选写入概念库或补强现有概念。
8. 已确认晋升的概念必须能够反向参与 `POST /concept/resolve` 的概念匹配，证明“经验 -> 概念候选 -> 人确认晋升 -> 后续复用”闭环已经真正生效。
9. DEMO 页面需要直接暴露“查看概念候选”和“确认晋升”入口，避免概念闭环停留在接口层，影响内部演示、录屏和后续教学流程串联。
## 当日增补（2026-07-10）：P011 物理经验内化工程证据收束

当前 `rell_sample` 主链中，P011 的核心能力其实已经存在于经验教学、经验库沉淀、因果签名生成、经验不变量契约生成和后续经验复用推理里，但此前这些证据主要散落在综合校验和接口回归中，不利于单独举证。为此，本轮新增独立的 P011 工程证据包，把“真实教学形成经验 -> 经验库沉淀 -> 后续任务复用经验 -> 明确剥离不可迁移细节”的最小闭环固定下来。

### 增补范围

1. 新增 `demo_runtime/rell_sample/validate_p011_experience_internalization.py`，固定生成 P011 的六段证据输出。
2. 新增输出目录 `demo_runtime/output/rell_sample/p011_experience_internalization/`，统一落盘 `00_summary.json`、`evidence_index.json` 和六个分段证据文件。
3. 新增 `技术库/P011-物理经验内化机制/P011物理经验内化工程证据说明.md`，把验证命令、输出目录、关键字段和典型审查质疑对应关系写成中文说明。
4. 将 `validate_p011_experience_internalization.py` 接入 `demo_runtime/rell_sample/run_all_checks.py`，使 P011 与 P013、P014、P017 一样进入一键回归主链。

### 当前证据覆盖点

1. 经验三元结构：证明经验记录包含 `context`、`action`、`outcome`，并同时保留 `causal_signature` 和 `invariant_contract`。
2. 对话教学入库：证明对话教学能够形成结构化经验记录，并将来源标记为 `dialogue_teaching`。
3. 边教边动反馈：证明系统在缺失前提时返回 `needs_more_teaching` 和 `missing_before_step`，在成功后固化经验并释放任务期快照。
4. 经验复用推理：证明后续任务的因果推理中存在 `source=experience_library` 的推理来源，表明系统优先复用历史经验。
5. 不可迁移字段剥离：证明经验不变量契约明确排除绝对坐标、机器人专用关节角和固定执行时长等字段。

### 本轮验收命令

```powershell
python demo_runtime\rell_sample\validate_p011_experience_internalization.py
python demo_runtime\rell_sample\run_all_checks.py
```

预期结果：两条命令均通过，并生成 `demo_runtime/output/rell_sample/p011_experience_internalization/` 下的证据文件。

## 当日增补（2026-07-10）：P015 人类偏好工程证据收束

当前 `rell_sample` 主链中，P015 的核心能力其实已经存在于偏好记录、运行时快照附着、当前偏好问答和偏好约束可行性判断里，但此前这些证据主要散落在 `validate_api_sample.py` 的综合断言中，不利于单独举证。为此，本轮新增独立的 P015 工程证据包，把“偏好独立存储 -> 当前任务快照加载 -> 运行时偏好问答 -> 新偏好即时附着 -> 偏好约束可行性限定 -> 不改写经验层和概念层”的最小闭环固定下来。

### 增补范围

1. 新增 `demo_runtime/rell_sample/validate_p015_preference_alignment.py`，固定生成 P015 的六段证据输出。
2. 新增输出目录 `demo_runtime/output/rell_sample/p015_preference_alignment/`，统一落盘 `00_summary.json`、`evidence_index.json` 和六个分段证据文件。
3. 新增 `技术库/P015-人类偏好/P015人类偏好工程证据说明.md`，把验证命令、输出目录、关键字段和典型审查质疑对应关系写成中文说明。
4. 将 `validate_p015_preference_alignment.py` 接入 `demo_runtime/rell_sample/run_all_checks.py`，使 P015 与 P011、P013、P014、P017 一样进入一键回归主链。

### 当前证据覆盖点

1. 偏好独立存储：证明偏好记录位于 `preference_record_library.json`，而不是直接写进经验库或概念库。
2. 当前任务快照加载：证明迁移任务创建时，任务期运行时世界状态快照会加载匹配的 `active_preferences`。
3. 运行时偏好问答：证明“当前偏好约束是什么”一类问题只从当前任务期快照读取答案。
4. 新偏好即时附着：证明新增阻断型偏好后，可以即时附着到当前任务，并被同任务查询看到。
5. 偏好约束可行性限定：证明阻断型偏好会把违反偏好的步骤标记为 `partially_inexecutable`，并保留 `human_preference_blocked_step` 原因。
6. 层间边界不改写：证明偏好层的读写不会直接改写经验库或概念库的持久化内容。

### 本轮验收命令

```powershell
python demo_runtime\rell_sample\validate_p015_preference_alignment.py
python demo_runtime\rell_sample\run_all_checks.py
```

预期结果：两条命令均通过，并生成 `demo_runtime/output/rell_sample/p015_preference_alignment/` 下的证据文件。

## 当日增补（2026-07-10）：P014 执行恢复工程证据收束

当前 `rell_sample` 主链中，P014 的核心能力其实已经存在于恢复记录持久化、按任务查询、运行时冲突再适配和执行中途阻断恢复里，但此前这些证据主要散落在 `validate_api_sample.py` 和 HTTP 烟测的综合断言中，不利于单独举证。为此，本轮新增独立的 P014 工程证据包，把“恢复记录独立存储 -> 冲突生成恢复记录 -> 按任务和按标识查询 -> 运行时再适配恢复 -> 执行中途阻断恢复 -> 恢复库持续沉淀”的最小闭环固定下来。

### 增补范围

1. 新增 `demo_runtime/rell_sample/validate_p014_execution_recovery.py`，固定生成 P014 的六段证据输出。
2. 新增输出目录 `demo_runtime/output/rell_sample/p014_execution_recovery/`，统一落盘 `00_summary.json`、`evidence_index.json` 和六个分段证据文件。
3. 新增 `技术库/P014-执行恢复/P014执行恢复工程证据说明.md`，把验证命令、输出目录、关键字段和典型审查质疑对应关系写成中文说明。
4. 将 `validate_p014_execution_recovery.py` 接入 `demo_runtime/rell_sample/run_all_checks.py`，使 P014 与 P011、P013、P015、P017 一样进入一键回归主链。

### 当前证据覆盖点

1. 恢复记录独立存储：证明恢复记录位于 `recovery_record_library.json`，而不是只存在于一次执行返回结果中。
2. 冲突生成恢复记录：证明双通道验真冲突会形成结构化恢复记录，并输出偏离上下文、恢复动作和恢复结果。
3. 查询与审计关联：证明恢复记录既能按 `recovery_id` 查询，也能按 `task_id` 查询，并和审计记录建立关联。
4. 运行时再适配恢复：证明运行时事实冲突会触发 `readaptation`，并生成指向再适配流程的恢复记录。
5. 执行中途阻断恢复：证明执行闭环遇到硬阻断时，会形成步骤级 `readaptation_required` 和恢复记录，而不是只返回失败。
6. 恢复库持续沉淀：证明多类恢复事件会持续留存在恢复记录库中，形成后续复核和举证资产。

### 本轮验收命令

```powershell
python demo_runtime\rell_sample\validate_p014_execution_recovery.py
python demo_runtime\rell_sample\run_all_checks.py
```

预期结果：两条命令均通过，并生成 `demo_runtime/output/rell_sample/p014_execution_recovery/` 下的证据文件。
