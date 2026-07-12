# EORLD-RELL Sample API Contract

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

`execution_trace.runtime_world_state_policy` 记录该状态的非持久化策略。实际产品中可以按需将关键阶段、事实成立、失败恢复和人工确认写入审计或经验记录，但不需要将每一帧物理状态写入长期数据库。自 P015 偏好层接入起，当前任务期快照还会携带 `active_preferences` 和 `preference_context`，用于把人类偏好记录作为运行时约束读入当前任务，而不直接改写经验层、概念层或底层控制。

自 P012 概念桥接实现起，`intent_translation` 中同步返回 `intent_frame`。该结构用于承接后续 LLM 或轻量 NLU 输出，但不允许语言模型直接绕过空间语义、概念层和因果层生成最终动作链。

`intent_frame` 至少包括：

- `goal_fact`：由人类输入翻译得到的目标因果事实。
- `action_concepts`：由端侧概念内化层识别出的高频动作概念候选，例如“前往操作台”“拿起杯子”“前往水源处”“接水”“倒水”，它们只负责桥接语义，不直接下发执行。
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

## POST /semantic/route

用途：统一语义路由器骨架。该接口不直接执行任务，而是将自然语言归入 `state_query`、`task_execution`、`teaching`、`clarification` 或 `unknown`，并输出统一语义帧。当前样品先用轻量规则路由，后续可在不改变下游执行主链的前提下，把复杂输入升级为更大的语义模型。

请求示例：

```json
{
  "utterance": "当前杯子有没有水"
}
```

响应至少包括：

- `request_type`：语义请求类别。
- `route_reason`：本次归类依据。
- `preferred_model_tier`：当前建议走 `rule_router_only` 还是 `llm_escalatable`。
- `intent_confidence`：系统对本次语义理解是否可靠的当前把握程度。
- `clarification_needed` / `clarification_reason`：是否需要先追问，以及触发原因。
- `confidence_reasons`：置信度形成依据，便于说明系统究竟卡在对象、方位、动作还是概念匹配。
- `alternative_interpretations`：当前样品下的候选解释或追问方向。
- `intent_frame`：与任务、空间、对象和事实相关的统一结构化语义。

当 `request_type=teaching` 时，响应中的 `teaching_plan.teaching_frame` 还会进一步把教学输入拆成四层：

- `goal_constraints`：本次教学想达成的目标事实；
- `process_constraints`：本次教学给出的步骤顺序与过程强度；
- `preference_constraints`：如“轻一点”“先别自动做”“等我确认”这类人类偏好或阻断约束；
- `flexibility_policy`：本次教学是否允许局部重排、是否要求严格跟随。

## POST /agent/query

用途：统一自然语言入口。该接口先调用 `/semantic/route` 完成语义分流，再根据请求类型调用现有能力：

- `state_query`：进入当前任务期运行时世界状态快照查询；
- `task_execution`：进入任务翻译或执行；
- `teaching`：进入教学解析；
- `clarification`：进入执行原因说明。

当 `task_execution` 的 `intent_confidence` 过低，或存在缺少共享指称、方位参照未落地、动作语义过于模糊等情况时，接口会优先返回：

- `decision=clarification_required`
- `clarification_prompt`
- `clarification_reason`
- `alternative_interpretations`

此时仅说明“我还需要你补充什么”，不会直接进入执行。

请求示例：

```json
{
  "task_id": "migration_xxx",
  "utterance": "当前杯子有没有水"
}
```

对于 `task_execution`，可选传入：

```json
{
  "utterance": "到水源处接一杯水",
  "auto_execute": true,
  "scenario": "auto"
}
```

这样会在路由后直接调用当前样品的执行链路；若未传 `auto_execute` 或其值为 `false`，则仅返回翻译结果而不执行。
在当前样品中，首页“运行任务”也已经改为经由 `POST /agent/query` 进入：先以 `auto_execute=false` 获取 `semantic_request`、`intent_translation` 和 `space_admission`，再以 `auto_execute=true` 在同一入口下触发执行。这样状态问答、任务执行和后续教学链路共用同一条自然语言主线。

对于 `state_query`，响应中的 `route_result` 现还会附带 `runtime_explanation_view`，用于把当前任务期运行时世界状态快照进一步外化为：

- `current_action`：当前正在做什么；
- `next_step`：若还能继续，当前任务链上的下一步是什么；
- `goal_fact`：当前任务的目标因果事实；
- `time_layers`：即时状态、任务状态、会话状态三层解释视图。

该解释视图仍坚持 `runtime_world_state_snapshot_and_current_runtime_context_only`，不回退到长期记忆臆造当前事实。

对于 `teaching`，响应中的 `route_result` 还会直接携带 `teaching_frame`，用于把本轮教学中的目标约束、过程约束、偏好约束和局部变通授权分开保留，而不是把整段教学文本直接当作单一脚本。

## POST /llm/context-view

用途：为未来大模型接入提供只读的当前任务期世界状态语义视图。该接口严格从当前任务期运行时世界状态快照生成上下文，不回退到长期经验库，也不允许通过该接口写入事实。

请求示例：

```json
{
  "task_id": "migration_xxx"
}
```

响应至少包括：

- `usable_as_current_world_state`：当前快照是否仍可作为模型读取的当前世界状态；
- `source_policy`：固定为 `runtime_world_state_snapshot_only`；
- `task_context`：任务运行状态、目标事实、当前阶段和快照标识；
- `executor`、`objects`、`established_facts`：供模型读取的当前语义状态；
- `available_actions_now`、`blocked_actions`：由确定性规则从当前快照推导出的动作候选；
- `model_role_constraints`：明确模型不能写事实、不能生成底层控制、必须回到校验器和编排层。

若快照已经释放，则 `usable_as_current_world_state=false`，并返回 `context_status=snapshot_released`，表示不能再把该快照当作当前世界状态喂给模型。

## POST /llm/prompt-contract

用途：生成稳定的大模型提示词契约。该接口不调用大模型，而是把语义请求、候选意图预览、概念层解析结果、可选的当前任务期运行时世界状态快照视图以及输出边界打包为统一契约，供后续模型调用层复用。

请求示例：
```json
{
  "task_id": "migration_xxx",
  "utterance": "到水源处接一杯水"
}
```

响应至少包括：
- `role_definition`：明确模型仅负责长程或陌生任务的语义理解、候选建议和澄清，不参与连续控制与最终执行决策；
- `input_packet.semantic_request`：统一语义路由结果；
- `input_packet.intent_translation_preview`：当前任务的候选目标事实和候选过程链预览；
- `input_packet.concept_resolution`：概念层解析结果摘要；
- `input_packet.runtime_context_view`：可选的当前任务期运行时世界状态语义视图；
- `system_constraints`：禁止输出底层控制、禁止写回任务期快照、禁止臆造未观测事实；
- `output_contract`：允许的候选类型、禁止字段和下一跳校验端点；
- `handoff_contract`：固定声明 `validator_endpoint=/llm/candidate/validate`，且 `direct_execution_allowed=false`。

## POST /llm/candidate-intent

用途：生成未来大模型调用前的标准输入包。该接口不调用大模型，而是输出 `semantic_request`、`intent_translation_preview`、可选的 `runtime_context_view` 和模型输入约束，作为后续提示词或模型调用层的稳定边界。

请求示例：

```json
{
  "task_id": "migration_xxx",
  "utterance": "到水源处接一杯水"
}
```

响应中的 `llm_input_contract` 会显式给出：

- `allowed_candidate_types`：当前仅允许 `intent_frame_patch`、`candidate_plan`、`clarification_answer`；
- `forbidden_output_fields`：禁止输出绝对坐标、关节角、轨迹、运行时事实写回字段等；
- `next_endpoint`：固定为 `/llm/candidate/validate`，用于要求模型候选输出必须先通过确定性校验。

响应中的 `concept_resolution` 会给出与当前语义请求匹配的概念层候选，用于明确哪些公共概念可复用、哪些仍需回到经验层或执行层判断。

## POST /llm/candidate/validate

用途：对模型候选输出做确定性校验。该接口只检查“结构是否安全、字段是否越权、步骤是否可识别”，不直接执行候选计划。

请求示例：

```json
{
  "task_id": "migration_xxx",
  "candidate": {
    "candidate_type": "candidate_plan",
    "goal_fact": "cup_contains_water",
    "candidate_process_chain": [
      "move_to_counter",
      "pick_up_cup",
      "move_to_water_source",
      "fill_cup_at_water_source"
    ],
    "confidence": 0.77
  }
}
```

响应至少包括：

- `accepted_structure`：候选结构是否通过；
- `validation_errors`、`validation_warnings`：越权字段、未知步骤或上下文提醒；
- `direct_execution_allowed`：固定为 `false`；
- `must_reenter_orchestration_layer`：固定为 `true`。

也就是说，大模型未来即使参与理解、澄清或候选建议，仍不能绕过空间语义、本体能力、任务期快照和编排层，直接生成底层动作控制。

## GET /concept/library

用途：查询当前样品的概念层公共语义单元库。该接口返回的概念单元用于承接公共空间能力、对象语义和任务语义，不直接替代经验层、因果层或执行层。

响应至少包括：
- `concept_units[].concept_id`、`display_name`、`concept_level`；
- `capability_semantics`：该概念对应的公共能力语义；
- `effect_contract`：必要效果事实，而非轨迹或关节角；
- `applicability_constraints`：绑定约束、所需运行时事实和禁止的底层字段；
- `experience_link_policy`：明确 `direct_execution_allowed=false`，并说明该概念优先由哪一层承接。

## GET /preference/library

用途：查询当前样品中的人类偏好记录库。

响应至少包括：
- `preference_records[].preference_id`：偏好记录标识；
- `context_ref`：偏好适用的空间或上下文；
- `preference_signal`：例如 `prefer`、`avoid`、`forbid`；
- `applies_to`：偏好作用范围，例如 `goal:water_poured`、`step:pick_up_cup`、`capability:pour_container`；
- `enforcement_policy`：`advisory` 或 `blocking`。

## POST /preference/record

用途：写入新的人类偏好记录，并可选附着到当前任务期运行时世界状态快照。

请求示例：
```json
{
  "task_id": "migration_xxx",
  "preference_signal": "forbid",
  "human_feedback": "不要自动拿起杯子，先请求我确认。",
  "applies_to": [
    "step:pick_up_cup",
    "object:object_cup_white_mug"
  ],
  "enforcement_policy": "blocking",
  "strength": 1.0
}
```

当携带 `task_id` 时，系统会在记录入库后把该偏好同步附着到当前任务期快照，使后续状态查询、可行性判断和解释链可以立即读取。

## POST /concept/cloud-recall

用途：当端侧概念内化层无法稳定理解当前任务语义时，向“云脑补给桥”发起候选补给请求。该接口当前返回的是本地模拟的 cloud brain stub，不直接执行任务，只返回候选概念、候选过程链和澄清问题。

请求示例：
```json
{
  "task_id": "migration_xxx",
  "utterance": "把那个给我弄一下"
}
```

响应至少包括：
- `should_request_cloud_recall`：当前输入是否已触发端侧概念缺口；
- `cloud_recall_packet.local_concept_gap`：端侧识别到的缺口类型；
- `cloud_recall_packet.runtime_context_summary`：发送给云脑的当前任务摘要；
- `concept_gap_evidence`：本地概念缺口证据，说明为什么需要追问或请求云端候选，并固定 `direct_execution_allowed=false`；
- `concept_fallback_event`：本地概念复用失败事件，记录缺口、回退目标及是否请求云脑候选；
- `cloud_recall_result.candidate_concepts`：云脑返回的候选概念；
- `cloud_recall_result.candidate_process_chain`：云脑返回的候选过程链；
- `cloud_recall_result.clarification_questions`：仍需向人追问的澄清问题；
- `direct_execution_allowed=false`；
- `must_reenter_orchestration_layer=true`。

说明：
- 该接口只做外域经验和陌生任务语义的候选补给；
- 返回结果不得直接写入运行时世界状态快照；
- 返回结果不得直接下发执行层；
- 所有候选结果必须重新回到编排层做空间语义、本体能力、概念层、经验层和任务期快照联合校验。

另外：
- `POST /llm/prompt-contract` 在检测到端侧概念缺口时，会在 `input_packet.cloud_recall_packet` 中带出同构的云脑补给请求包；
- `POST /llm/candidate-intent` 会在 `cloud_recall_preview` 中带出同构的候选补给预览，供后续模型调用层复用。

## POST /concept/resolve

用途：把当前自然语言请求解析为概念层候选，作为经验层和编排层之间的可复用中间语义单元。该接口只做概念识别和边界声明，不直接下发动作。

请求示例：
```json
{
  "task_id": "migration_xxx",
  "utterance": "走到门旁边，再去操作台拿杯子，到水源处接一杯水"
}
```

响应至少包括：
- `semantic_request`：统一语义路由结果；
- `intent_frame_summary`：目标事实、显式过程链、空间约束和对象约束摘要；
- `action_concepts`：端侧动作概念候选，说明这次输入在本地动作语义层命中了哪些可复用动作单元；
- `action_concepts[].concept_package`：以因果算子为核心的端侧概念包，包含语义角色、事实契约、当前事实对齐和经验检索策略；`step_id` 仅作为兼容性的经验提示；
- `concept_package.concept_kernel.semantic_roles`：分别声明 `mention_status` 与 `grounding_status`，避免把语言明确提及误当成现实对象已经唯一绑定；
- `concept_package.concept_kernel.effect_contract`：声明 `requires`、`produces`、`destroys` 和 `verification`，其中事实变化在 P016 验真前仅为投影；
- `concept_package.fact_alignment`：基于当前可用事实输出已满足前提、缺失前提和目标是否已成立；
- 当携带有效 `task_id` 时，隐含对象可依据当前快照中的唯一手持兼容对象形成 `implicit + inferred` 绑定；隐含空间角色可依据执行体当前位置形成有依据的推定。当前空间模型只有一个满足概念类型且状态可用的默认资源时，也可形成较低置信度的弱推定。多候选、无可用候选或约束冲突时继续保持 `unresolved` 并要求确认；
- `concept_package.experience_lookup.candidates`：按缺失前提事实检索能够生产该事实的步骤或经验链，并按缺口覆盖数排序；该检索明确不使用整句输入到经验的直接匹配；
- `concept_package.grounding_summary`：汇总必需角色是否已落地、未落地角色和确认问题；
- 统一 `/agent/query` 入口在必需角色未落地时返回 `decision=concept_grounding_required`。该门控同时作用于预览和 `auto_execute=true`，防止第二次执行请求绕过澄清；
- 当对象或场景可以识别、但没有本地动作概念或可执行经验时，响应附带 `learning_followup`：明确不会的原因、需要向人询问的问题，以及对话教学和边教边动入口。对象概念命中不再被视为任务能力充分；
- `concept_lifecycle`：本次概念首次形成或重复复用事件，以及对应的形成数、复用数；
- `resolved_concepts`：概念层候选，每个候选带有 `activation_reason`、`effect_contract`、`runtime_binding_status` 和 `experience_link_policy`；
- `concept_evidence_packets`：端侧概念命中的证据包，说明命中依据、置信度、运行时快照绑定和失败回退策略；
- `concept_evidence_summary`：证据包摘要，固定声明本地概念为候选层，`direct_execution_allowed=false`，且必须回到编排层；
- `concept_resolution_policy`：明确概念层只提供可复用语义单元，`direct_execution_allowed=false`，且必须重新进入编排层。

`concept_evidence_packets[].match_basis` 可包含 `semantic_constraint_match`、`concept_library_unit_match`、`runtime_snapshot_binding`、`explicit_process_chain_step`、`local_action_alias_match` 或 `experience_backed_promoted_concept` 等示例性依据。证据包只用于说明端侧概念为何被信任或为何需要回退，不得直接触发执行控制链路。

## GET /concept/candidates

用途：查询由成功经验自动生成、但尚未人工确认的概念晋升候选。该接口用于承接“经验 -> 概念候选 -> 人工确认晋升”的最小闭环。

响应至少包括：
- `concept_candidates[].candidate_id`：候选标识；
- `proposal_type`：`create_promoted_concept_unit` 或 `strengthen_existing_concept`；
- `target_concept_id`：将要新建或补强的概念标识；
- `source_experience_id`：来源经验；
- `promotion_rationale`：晋升理由；
- `human_confirmation_required`：固定为 `true`。

## POST /concept/candidates/confirm

用途：对概念晋升候选做人工确认。确认后，候选概念将正式写入概念库，或补强现有概念与真实经验之间的证据关系。

请求示例：
```json
{
  "candidate_id": "concept_candidate_xxx",
  "confirmed_by": "human_reviewer"
}
```

响应至少包括：
- `status=promoted`；
- `promoted_concept_id`：确认后进入概念库或被补强的概念标识；
- `promoted_concept_unit`：确认后的概念单元内容或补强后的概念内容；
- `source_experience_id`：概念候选来源经验。

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

## GET /recovery/library

用途：查询当前样品中的补救/恢复记录库。该接口用于把执行失败、运行时冲突、人工确认升级和再适配建议固化为结构化记录，而不是只停留在一次性的日志输出中。

响应至少包括：
- `recovery_records[].recovery_id`：补救记录标识；
- `task_id`：对应的任务标识；
- `failed_experience_ref`：触发补救记录的失败过程、执行回调或经验引用；
- `deviation_context`：偏离类型、观测状态和期望状态；
- `recovery_action`：建议的补救动作、参数和是否需要人工介入；
- `recovery_outcome`：`recovered`、`partially_recovered`、`failed` 或 `escalated`。

## GET /recovery/task/{task_id}

用途：按任务查询补救/恢复记录。该接口用于把某次执行中的失败、冲突和再适配记录与当前任务、审计摘要和任务期快照关联起来，便于复核单次任务的完整恢复链路。

## GET /recovery/{recovery_id}

用途：按标识查询单条补救/恢复记录，用于定位某次失败后的补救建议、人工确认入口和后续再适配来源。

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

## POST /runtime_world_state/query

用途：直接从当前任务期运行时世界状态快照回答状态问题，不回退到长期空间语义存量，不根据执行历史做补充推理。当前样品先支持“当前杯子有没有水”这一类状态查询。

请求示例：

```json
{
  "task_id": "migration_xxx",
  "question": "当前杯子有没有水"
}
```

响应中的 `answer` 取值为 `true`、`false`、`unknown` 或 `conflict`：

- `true`：当前快照中存在 `cup_contains_water`。
- `false`：当前快照中存在 `cup_empty` 且不存在 `cup_contains_water`。
- `unknown`：当前快照中两者都不存在，或快照已经释放，不再代表当前世界状态。
- `conflict`：当前快照中同时存在 `cup_contains_water` 与 `cup_empty`。

该接口的 `source` 固定为 `runtime_world_state_snapshot_only`，用于明确回答依据只能来自当前任务期运行时世界状态快照。

自端侧概念内化层第一版主干接入后，响应中还会附带 `state_concept_resolution.matched_state_concepts`，用于说明这次状态提问先命中了哪一个端侧状态概念单元，再映射到当前任务期运行时世界状态快照或当前运行上下文槽位完成回答。也就是说，状态问答不再只是零散规则命中，而是已经进入可复用的端侧概念主干。

当前样品支持的自然语言问题包括：

- `当前杯子有没有水`
- `当前水壶里有没有水`
- `我手里拿着什么`
- `我现在在哪`
- `当前偏好约束是什么`
- `当前状态`

这一步中的自然语言解析仍然是轻量规则层：语言只负责识别问题类型和对象指向，真正回答时只读取当前任务期运行时世界状态快照。

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

当前样品中，教学经验还会在经验记录里保存 `teaching_contract`，用于把本次教学中的目标约束、过程约束、偏好约束和局部变通授权一并保存下来，而不是只保存过程链本身。

当经验成功生成后，响应中还会附带 `concept_promotion_candidates`。这些候选由经验记录、因果签名和经验不变量契约自动抽取生成，用于后续人工确认是否将该经验晋升为概念层公共语义单元，或补强现有概念。

经验写入公共经验库前必须通过可迁移契约编译与净化：

- `invariant_contract.binding_slots` 保存类型化槽位及语义要求，不以来源空间的对象或区域 ID 作为规范执行依赖；
- `invariant_contract.source_binding_evidence` 可保留本次形成经验时的对象/区域绑定，但仅作来源审计，不参与后续迁移的规范匹配；
- `action.target_slots` 引用类型化槽位，不再保存来源环境 `target_refs`；
- `portable_contract_validation` 校验三类不变量、事实终止条件和类型化槽位是否完整，并递归拒绝绝对坐标、关节角、固定执行时长、轨迹和底层控制信号；
- 校验失败返回 `nonportable_experience_rejected`，经验不得进入公共经验库；
- `bind_portable_invariant_contract` 可在不改写规范契约的情况下，针对当前空间语义实体和执行体能力重新绑定。

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

通过 `POST /agent/query` 走 `teaching` 路由时，当前样品还会先返回 `teaching_feedback.acknowledgement`，用于把“我理解你这次在教我什么”复述出来；若本轮教学仍过于模糊，则会沿用 `clarification_needed` / `clarification_reason` 先请求补充更具体步骤。

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
请求可携带 `space_id`。当前样品支持：

- `home_a_kitchen`：原厨房空间；
- `site_b_corridor`：走廊饮水区，用于验证同一经验契约绑定到不同操作台、容器和水源区域。

迁移响应中的 `experience_invariant_contract` 为规范契约，`binding_candidate.step_bindings[].contract_slot` 为各步骤使用的类型化槽位，`space_binding/object_binding.target_ref` 为当前空间解析得到的实体。执行载荷携带同一绑定候选，运行时状态跃迁按当前实体更新，不回退到来源空间实体。

候选绑定遵循状态过滤优先：不可达或不可用候选写入 `rejected_candidates`；过滤后只有一个候选时自动绑定；多个有效候选写入 `ambiguous_bindings` 并返回 `requires_human_confirmation`；没有有效候选时形成 `missing_binding_target`。主体缺少槽位所需能力时形成 `missing_body_capability`。

执行反馈中的 `generalization_result` 记录空间、主体、槽位绑定、排除候选、歧义候选和目标事实结果。单次结果只进入验证历史，不直接改写公共经验契约。
