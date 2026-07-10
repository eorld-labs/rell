# RELL Sample API Contract

第一阶段对外仍以运行、准入和审计为主；经验教学接口作为样品学习闭环的最小入口，暂不扩展为通用规划或模板学习 API。自因果链最小实现起，`/process/run` 在检测到目标因果事实时，会优先通过因果层反向搜索形成过程链，而不是要求每一种自然语言任务都枚举为独立经验。

## POST /process/admit

用途：执行“会不会做”的最小准入判断。

请求体第一阶段可为空。Runtime 仅检查规则映射、过程实例、偶然绑定和 Adapter 能力。

响应示例：

```json
{
  "schema_version": "1.0.0",
  "task_id": "task_pour_water_001",
  "allowed": true,
  "decision": "allowed"
}
```

## POST /process/run

用途：异步任务接口的样品占位。第一阶段为了演示直接同步返回结果，但响应中保留 `task_id`。

请求示例：

```json
{
  "scenario": "simulated_success"
}
```

可选场景：

- `simulated_success`
- `simulated_no_water`
- `simulated_channel_conflict`
- `success`
- `no_flow`
- `channel_conflict`

`simulated_*` 场景由 SimulatedRobotAdapter 根据阶段动作生成连续状态变量；其余场景为固定 Mock 时间轴，用于回归对照。

当输入为 `到水源处接一杯水` 时，翻译层输出目标因果事实 `cup_contains_water`。编排层基于当前空间事实和过程事实注册表反向补齐前提事实，生成：

```text
move_to_counter -> pick_up_cup -> move_to_water_source -> fill_cup_at_water_source
```

当输入为 `走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水` 时，目标因果事实为 `water_poured`，系统生成：

```text
move_to_counter -> pick_up_cup -> move_to_water_source -> fill_cup_at_water_source -> move_to_counter -> pour_water
```

响应中的 `intent_translation.causal_plan` 会给出初始事实、最终事实、推导过程和生成的过程链。

过程链执行时，响应会返回 `runtime_world_state`。该结构表示端侧运行时世界状态快照，生命周期限定为当前任务执行期间，不作为长期世界数据库保存。它由 P010 主体侧空间认知模型初始化，并在每个过程步骤完成时依据 `requires_facts`、`produces_fact` 和 `destroys_facts` 更新，用于对齐“计划阶段”与“实际执行后的世界事实”。

例如执行 `move_to_water_source` 后，快照中的执行体位置会从上一空间区域更新为 `region_water_source`；执行 `pick_up_cup` 后，杯子的 `location_type` 会更新为 `executor_gripper`；执行 `fill_cup_at_water_source` 后，`established_facts` 中会出现 `cup_contains_water`。

`execution_trace.runtime_world_state_policy` 记录该状态的非持久化策略。实际产品中可以按需将关键阶段、事实成立、失败恢复和人工确认写入审计或经验记录，但不需要将每一帧物理状态写入长期数据库。

自 P012 概念桥接实现起，`intent_translation` 中同步返回 `intent_frame`。该结构用于承接后续 LLM 或轻量 NLU 输出，但不允许语言模型直接绕过空间语义、概念层和因果层生成最终动作链。

`intent_frame` 至少包括：

- `goal_fact`：由人类输入翻译得到的目标因果事实。
- `spatial_constraints`：从输入中抽取并绑定到 P010 主体侧空间认知模型的空间目标，例如 `门旁边 -> region_doorway`。
- `object_constraints`：从输入中抽取并绑定到当前空间对象的对象目标，例如 `杯子 -> object_cup_white_mug`。
- `concept_matches`：P012 概念层候选，例如空间目标导航概念、可盛装容器概念、水源资源区概念。
- `sequence_constraints`：用户显式给出的路标顺序或过程顺序。
- `planning_policy`：限定 LLM 只生成结构化候选语义，最终仍由空间语义、概念层、因果层和经验库共同决定。

例如输入：

```text
走到门旁边，再走到服务位，再去操作台拿杯子，去水源处倒杯水
```

翻译层会保留门旁边、服务位、操作台和水源处四个空间约束，概念层匹配“空间目标导航概念”“可盛装容器概念”和“水源资源区概念”，再由因果层确认该显式路线能达成 `cup_contains_water`。

## POST /experience/migrate

用途：执行 P017 迁移适配控制器主链。该接口不直接控制机器人电机，而是把待迁移经验记录、当前空间语义数据、本体能力画像和任务期运行时世界状态快照组合起来，生成绑定候选、执行可行性结果和开放执行闭环调用载荷。

请求示例：

```json
{
  "utterance": "到水源处接一杯水"
}
```

响应至少包括：

- `migration_task_id`：迁移任务标识。
- `runtime_world_state_snapshot.runtime_world_state_snapshot_id`：任务期运行时世界状态快照标识。
- `binding_candidate`：经验不变量契约在当前空间语义、本体能力画像和任务期快照下的绑定方案。
- `execution_feasibility`：可执行、不可执行、部分不可执行、需降级执行、需人工确认、需补充教学或需搜索替代经验中的结构化结果。
- `execution_loop_payload`：可发送给 ROS、机器人 SDK、仿真执行器、数字执行体或其他执行闭环的开放调用载荷。

当本体能力画像缺少步骤能力、空间对象缺失或任务期前提事实不成立时，`execution_feasibility.infeasible_reasons` 会返回缺失能力、缺失绑定目标或缺失前提事实，并给出人工确认、替代经验搜索、补充教学、降级执行或终止执行等建议动作。

## GET /runtime_world_state/{task_id}

用途：查询任务期运行时世界状态快照。该快照用于当前任务执行期间的事实对齐和工作记忆，不作为长期世界数据库保存。

响应至少包括：

- `runtime_world_state_snapshot`：快照内容。
- `release_status`：当前释放状态。
- `release_token`：释放令牌，未释放时为空。
- `audit_record_id`：与审计记录的关联。

## POST /runtime_world_state/release

用途：触发任务期快照释放，证明任务期临时事实在任务结束后不再直接作为后续任务适配判断依据。

请求示例：

```json
{
  "task_id": "migration_xxx",
  "release_reason": "task_finished"
}
```

响应包括 `release_token`、`release_status`、`release_reason` 和 `audit_record_id`。释放在样品中表现为逻辑释放和审计关联，实际产品中可对应物理删除、缓存清空、任务标识解绑、权限隔离或停止作为后续任务事实输入。

## GET /audit/{task_id}

用途：查询最近一次运行写入内存的审计摘要。

第一阶段审计数据为进程内存存储，后续再替换为文件或数据库。

## POST /experience/teach

用途：当翻译层识别出多过程任务链但当前技能库不会执行时，接收人工教学步骤并生成候选经验。

请求示例：

```json
{
  "utterance": "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
  "steps": "走向操作台\n拿起杯子\n到水源处\n接一杯水\n倒水"
}
```

第一阶段采用轻量规则映射表解析教学步骤，不调用通用规划器，不自动生成新的 P016 过程模板。生成的经验链先标记为数字空间可回放经验，后续再进入人工审核、真机验证或模板化沉淀。若同一输入已经能被目标因果事实和因果层求解，则运行时优先采用因果求解结果，教学经验作为候选经验和审计依据保留。

## POST /experience/dialogue-teach

用途：接收自然语言形式的对话教学内容，并复用教学步骤解析器生成候选经验。

请求示例：

```json
{
  "utterance": "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
  "message": "教你：走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水"
}
```

该接口仍采用轻量规则映射表，不引入大模型推理；其意义在于证明用户可通过对话式输入触发经验形成，而不是必须编辑结构化 JSON。

自因果签名实现起，对话教学会在经验记录中同步生成 `causal_signature`：

```json
{
  "requires_facts": ["executor_at_counter", "cup_at_counter", "gripper_empty"],
  "produces_fact": "cup_contains_water",
  "destroys_facts": ["cup_empty"],
  "expands_to": ["pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"]
}
```

例如输入：

```text
教你一个技能：接一杯水需要先拿杯子，再去水源处接水。接完以后杯子里有水。
```

系统会将“需要先”之后的内容解析为前置过程，将“接完以后杯子里有水”解析为目标因果事实说明，并把该经验作为可被因果编排器读取的过程能力。后续用户说 `帮我接水` 时，系统可以从 `cup_contains_water` 反向搜索并调用该教学经验签名，而不是匹配原始教学语句。

自经验不变量契约实现起，经验记录还会同步生成 `invariant_contract`。该结构用于明确经验库保存的是跨空间、跨本体可迁移的不变量，而不是某次执行的具体坐标、关节角或执行时长。

`invariant_contract` 至少包括：

- `topology_invariants`：拓扑关系，例如执行体到达语义区域、末端执行器到达可抓取对象、容器开口与水源资源区对齐。
- `action_constraints`：试探方向与物理约束，例如朝绑定区域导航、接近对象直到可抓取、保持容器稳定并避免过量。
- `termination_conditions`：事实终止条件，例如 `cup_contains_water == established`。
- `forbidden_storage`：禁止沉淀 `absolute_coordinates`、`robot_specific_joint_angles` 和 `fixed_execution_duration`。

具体机器人如何满足拓扑关系、如何规划轨迹、如何求解关节角，由当前 Robot Adapter、厂商 SDK 或运动控制器在执行时完成，不进入经验库长期保存。

## GET /experience/library

用途：查询当前样品经验库。

经验库第一阶段存储在 `demo_runtime/rell_sample/data/experience_library.json`，用于演示“不会做 -> 人工教学 -> 经验形成 -> 数字执行体回放”的最小闭环。

## POST /teaching/session/start

用途：启动“边教边动”教学会话。该接口把网页中的数字执行主体作为第一阶段执行主体，生成任务期运行时世界状态快照，并等待用户逐步教学。

请求示例：

```json
{
  "utterance": "到水源处接一杯水"
}
```

响应至少包括：

- `session_id`：教学会话标识。
- `goal_fact`：本轮教学希望达成的目标事实，例如 `cup_contains_water`。
- `runtime_world_state_snapshot`：本轮教学期间的任务期运行时世界状态快照。
- `status`：初始为 `teaching_in_progress`。

## POST /teaching/session/step

用途：接收一个或多个人工教学步骤，由数字执行主体立即判断并执行。若前提事实已满足，则调用运行时世界状态更新逻辑，返回因果产出事实、因果销毁事实和当前快照；若前提事实缺失，则返回缺失事实和建议先教学步骤，不强行执行。

请求示例：

```json
{
  "session_id": "teach_session_xxx",
  "teaching_input": "走向操作台"
}
```

典型反馈：

```json
{
  "step": "move_to_counter",
  "status": "executed",
  "causal_produced_facts": ["executor_at_counter"],
  "causal_destroyed_facts": ["executor_at_water_source"],
  "goal_achieved": false
}
```

若用户先教 `拿起杯子` 但执行体尚未到达操作台，响应会返回 `needs_more_teaching`，并在 `missing_before_step` 中列出 `executor_at_counter` 等缺失前提。

## POST /teaching/session/finish

用途：在目标事实已成立或用户确认成功后，把本次已执行过程链固化为经验记录，并释放任务期运行时世界状态快照。

请求示例：

```json
{
  "session_id": "teach_session_xxx",
  "success_confirmed": true
}
```

响应包括 `experience_result` 和 `release_result`。固化后的经验记录会生成 `causal_signature` 与 `invariant_contract`，并将来源标记为 `stepwise_teaching_session`。`release_result.release_token` 用于证明本次教学快照已经完成逻辑释放。

## GET /teaching/session/{session_id}

用途：查询边教边动会话，包括已执行过程链、每一步事实反馈、目标事实状态和当前任务期快照。该接口用于调试和演示，不替代长期经验库查询。

## GET /experience/gap/{gap_record_id}

用途：查询迁移适配过程中生成的经验缺口记录。

当 `POST /experience/migrate` 或运行时再适配结果不是 `executable` 时，系统会生成 `experience_gap_record`。该记录包含阻断步骤、不可执行原因、建议动作、补充教学入口、替代经验检索条件和可降级执行步骤，用于把“不可执行/部分不可执行”结果接入后续教学闭环。

## POST /runtime_world_state/readapt

用途：在执行闭环返回事实冲突后，基于更新后的任务期运行时世界状态快照重新生成绑定候选和执行可行性结果。

请求示例：

```json
{
  "task_id": "task_pour_water_001",
  "utterance": "到水源处接一杯水"
}
```

当审计记录或执行 trace 中存在不同观测通道对同一事实给出冲突状态时，响应会返回 `readaptation_id`、`runtime_conflicts`、新的 `runtime_world_state_snapshot`、`binding_candidate`、`execution_feasibility` 和可选的 `experience_gap_record`。该接口用于演示“执行闭环事实回传 -> 冲突进入任务期快照 -> 重新适配或请求人工确认”的链路。

## GET /runtime_readaptation/{readaptation_id}

用途：查询运行时冲突再适配记录。该记录不替代原执行审计，而是记录冲突发生后的再适配快照、绑定候选、可行性结果和建议动作。

## POST /execution/dispatch

用途：接收 `POST /experience/migrate` 返回的 `execution_loop_payload`，并通过统一开放执行闭环接口分发给不同类型的执行器。

请求示例：

```json
{
  "executor_type": "robot_sdk",
  "execution_loop_payload": {
    "execution_callback_id": "exec_xxx",
    "runtime_world_state_snapshot_id": "migration_xxx_snapshot",
    "target_causal_fact": "cup_contains_water",
    "execution_step_payload": []
  }
}
```

`executor_type` 当前支持 `process_template_executor`、`digital_executor`、`simulated_robot`、`ros_controller`、`robot_sdk` 和 `vla_policy`。样品阶段不会真实控制外部机器人，而是验证统一接口约束：执行器必须返回 `fact_established`、`fact_not_established`、`failure`、`conflict`、`recovered` 或 `human_confirmation` 等事实状态。响应会返回 `dispatch_id`、`fact_feedback`、更新后的 `runtime_world_state_snapshot` 和 `audit_record_id`。

## GET /execution/dispatch/{dispatch_id}

用途：查询执行闭环分发记录和事实回传结果。该记录用于证明迁移适配控制器能够通过开放接口调用不同底层执行模块，并将因果产出事实和因果销毁事实回写任务期快照。

## GET /p017/minimal-loop

用途：读取 P017 最小特征闭环证据包，用于首页“P017 最小闭环”展示模式。

该接口读取 `demo_runtime/output/rell_sample/p017_minimal_loop/` 下的 `evidence_index.json`、`00_summary.json` 以及六个分段证据 JSON，返回每段证据对应的技术特征、权利要求步骤、关键字段、代码来源和原始 JSON 内容。

使用前可运行：

```powershell
python .\demo_runtime\rell_sample\validate_p017_minimal_loop.py
```

## 调试接口

`GET /process/status/{task_id}` 为调试接口，不作为对外承诺接口。

## 验收命令

生成 P017 最小特征闭环证据：

```powershell
python .\demo_runtime\rell_sample\validate_p017_minimal_loop.py
```

输出目录：

```text
demo_runtime/output/rell_sample/p017_minimal_loop/
```

全量样品验收：

```powershell
python .\demo_runtime\rell_sample\run_all_checks.py
```
