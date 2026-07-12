# P019 端侧概念内化证据包工程记录

日期：2026-07-11

## 一、对应问题

本记录对应“端侧概念内化闭环”的第一阶段工程证据：自动化执行体在本地命中高频状态概念、动作概念或语义概念时，必须同时说明为什么命中、依据来自哪里、是否绑定当前任务期运行时世界状态快照，以及证据不足时如何回退。

该工程线不改变 P018 的状态优先主链。端侧概念仅提供候选语义和证据包，不直接取得执行权；任何候选概念、候选过程链或云端补给结果，均需重新进入任务期快照和编排层校验。

## 二、技术点与保护特征对应

| 技术点 | 工程落点 | 对应保护特征 |
|---|---|---|
| 概念命中必须附带证据 | `concept_core/concept_evidence.py`、`concept_evidence_packets` | 端侧概念内化不是黑箱分类，而是带有命中依据和置信边界的候选语义形成 |
| 动作概念不得直接执行 | `concept_core/concept_parser.py` 中每个 `action_concept` 固定 `direct_execution_allowed=false` | 候选动作必须回到编排层和执行控制链路，不绕过 P018 状态优先仲裁 |
| 状态概念只读当前快照 | `concept_core/query_router.py` 的 `state_query_concept` 证据包 | 状态查询输入由任务期运行时世界状态快照响应，不触发执行控制链路改变 |
| 语义概念绑定运行时上下文 | `api_server.py::build_concept_unit_view` | 概念候选可附着当前任务期快照，但不能代替快照完成事实裁剪或执行控制 |
| 本地概念缺口形成回退证据 | `build_cloud_recall_preview` 输出 `concept_gap_evidence` | 云脑补给仅是候选或澄清，不得直接写入快照或触发执行 |
| 统一证据摘要 | `resolve_concepts_for_intent` 输出 `concept_evidence_summary` | 为后续页面、审计、专利证据链提供可复核边界 |
| 概念形成与复用留痕 | `concept_core/concept_lifecycle.py`、`concept_lifecycle` | 同一概念首次命中记为形成，后续命中记为复用，并保留次数、证据和快照绑定 |
| 复用失败进入回退 | `concept_fallback_event` | 本地概念不足时形成失败事件，再进入云脑候选或人工澄清，不静默越权执行 |
| 动作概念组合式内核 | `action_units.py::concept_kernel` | 高频动作由抽象因果算子、语义角色和事实契约定义，不再以固定步骤作为概念本体 |
| 提及与落地分离 | `concept_parser.py::_role_binding` | 明确提及不等于现实对象已唯一绑定，隐含对象不允许被臆造为已落地实体 |
| 当前事实前提对齐 | `concept_package.fact_alignment` | 从任务期快照区分已满足和缺失前提，并以缺失前提驱动后续经验检索 |
| 验真后提交事实 | `commit_requires_p016_verification=true` | `produces/destroys` 在概念阶段只作状态投影，必须经 P016 验真后提交 |
| 隐含角色状态落地 | `concept_parser.py::_role_binding` | 当前手中唯一兼容对象、当前位置或空间模型中唯一可用资源可形成带依据的 `implicit + inferred` 绑定，条件不唯一时保持未解析 |
| 缺失前提驱动经验检索 | `attach_missing_fact_experience_candidates` | 以当前缺失事实检索步骤或经验生产者并按覆盖率排序，不按整句输入绑定固定经验 |
| 必需角色执行前门控 | `build_concept_grounding_gate`、`handle_agent_query` | 必需角色未落地时预览和自动执行统一返回澄清态，禁止绕过确认进入执行 |

## 三、证据包字段

`concept_evidence` 至少包括：

- `concept_id`：命中的端侧概念；
- `concept_type`：状态查询概念、动作概念或语义概念；
- `activation_reason`：本次被激活的原因；
- `match_basis`：别名命中、显式过程步骤、空间/对象语义约束、经验背书或运行时快照绑定；
- `match_confidence`：当前样品中的示例性命中强度；
- `runtime_binding`：是否绑定任务期运行时世界状态快照；
- `fallback_policy`：证据不足时澄清、请求云端候选或回编排层；
- `patent_feature_mapping`：该证据包对应的保护特征说明。

所有证据包均固定：

- `candidate_only=true`；
- `direct_execution_allowed=false`；
- `must_reenter_orchestration_layer=true`。

## 四、测试证据

`validate_api_sample.py` 新增断言：

1. `/concept/resolve` 必须返回 `concept_evidence_packets`；
2. 本地概念证据包不得授予直接执行权；
3. `concept_evidence_summary.all_candidate_only` 必须为真；
4. 模糊任务的 `cloud_recall_preview` 必须返回 `concept_gap_evidence`；
5. 状态查询命中的状态概念必须带有只读快照证据包。
6. 同一输入重复解析时，概念生命周期必须由 `concept_formed` 进入 `concept_reused`；
7. 模糊输入必须生成 `local_concept_reuse_failed` 回退事件，并继续禁止直接执行。

这些断言保证端侧概念内化不会退化为“概念命中后直接动作”，而是继续服从 P018 的状态优先仲裁主链。

## 五、与 P018 的边界

P018 保护主链是：交互输入进入执行控制行为之前，先读取任务期运行时世界状态快照，并基于快照完成状态查询/任务控制分流、任务控制仲裁、当前事实续推和快照释放。

本工程记录保护或沉淀的是该主链上游的端侧概念证据机制：

1. 概念层负责把高频语义内化为可复用候选；
2. 证据包负责说明候选为何成立或为何不足；
3. 云端候选只在本地证据不足时补给；
4. 最终是否执行仍由 P018 的状态优先仲裁和执行控制链路决定。

因此，本记录可以作为后续端侧概念内化方案的工程证据种子，也可作为 P018 中“端侧概念/云端候选不直接取得执行权”的实施支撑。
