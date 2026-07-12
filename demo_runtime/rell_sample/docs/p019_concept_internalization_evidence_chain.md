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
| 不会到教学后置闭环 | `build_learning_followup`、`no_local_action_concept_or_experience_match` | 已识别对象但无动作/经验时说明原因、询问人类并进入教学入口，教学后形成经验供再次执行 |
| P019 行为场景回归 | `validate_p019_behavior_scenarios.py` | 独立验证不会-教学-复用、阶段目标反向补前提、组合中断任务切换和可绕障碍 |
| 经验进入概念前的可迁移准入 | `validate_experience_portability` | 只有通过类型化槽位编译和不可迁移字段净化的经验，才可进入公共经验库并继续作为概念晋升来源 |
| 泛化压力分支 | `validate_p017_generalization_pressure.py` | 验证唯一候选、多候选确认、资源不可用、主体能力缺口和泛化结果回写，不以理想单候选冒充泛化能力 |
| 任务条件化概念感知落地 | `concept_core/perceptual_grounding.py`、`data/embodied_object_concepts.json` | 任务只激活相关对象与关系概念，感知适配器输出受限候选，落地器不读取场景真值且不得直接提交运行时事实 |
| 安全感知不可随任务注意力裁剪 | `perception_observation.safety_channels_always_on`、`safety_observations` | 无关对象可停止高层语义分析，但动态障碍、碰撞和保护策略等安全输入持续生效 |
| 多实例不得擅自绑定 | `concept_grounding.candidate_options`、`perception_disambiguation_required` | 同一对象概念命中多个当前实例时保留全部候选并进入澄清，不以最高分类分数替代任务指代证据 |
| 遮挡触发本体允许的主动观察 | `active_perception_trace`、`executor_profile.sensor_frames.head_rgbd` | 观测不足时只选择本体画像允许的传感器视角，新的观测证据仍不直接取得执行权 |
| 属性澄清重新解释当前观测 | `target_constraints`、`constraint_rejections` | 人类补充可观察属性后重新筛选当前候选，保留被排除实例及理由，不沿用上一轮歧义结论 |
| 对象移位撤销旧观测资格 | `perception_history.current_use_status=stale`、世界版本绑定观测标识 | 对象或环境变化后旧绑定仅保留为历史证据，必须基于新世界版本重新观察和落地 |
| 不会时进入受控真人教学 | `start_embodied_teaching`、`begin_teaching_control` | 人类只取得当前教学会话的动作候选生成权，本体、碰撞、策略和事实验真边界不被替换 |
| 遥操作编译为经验不变量 | `embodied_teaching.py::compile_demonstration_experience` | 按键、坐标和轨迹不进入经验，只保存拓扑、物理约束、因果事实与终止条件 |
| 自主复做后再晋升 | `begin_learned_replay`、`evaluate_learned_replay` | 候选经验必须重新绑定并自主复做，物理事实与人类验收共同成立后才成为本地可信经验 |
| 纯转向与侧向任务分离 | `execute_command.rotation_only` | “向右转”只产生朝向变化，“往右边走”才根据轮式本体实现转向后平移 |
| 可信经验白名单持久化 | `embodied_experience_store.py` | 只有完成自主复做和人类验收的本地可信经验可写盘，持久记录不含会话、实例、作业或轨迹字段 |
| 冷启动概念槽位重绑定 | `begin_persisted_experience_replay` | 新会话加载经验后必须用当前观测重新绑定目标概念槽位并重新规划，不复用示教实例和轨迹 |

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
8. “去桌子上拿杯子”必须由任务概念生成受限观测请求，并以观测中的类别和 `on_top_of` 关系证据完成空间候选落地；
9. 删除关系观测后必须回退为继续观察，不得由落地器读取场景配置补齐答案；
10. 任务注意力抑制无关语义时，动态障碍安全观测必须继续保留。
11. 两个同类杯子必须返回两个候选且不得生成目标绑定；
12. 正面遮挡必须先形成失败观测，再由本体画像允许的头部视角完成第二次观察，且不得移动底盘；
13. 杯子移位后旧观测必须变为 `stale`，新观测必须使用新的世界版本、观测标识和估计位置；
14. “拿白色杯子”必须在保留两个原始检测结果的同时，只绑定带白色观测属性的实例，并记录浅蓝实例的约束排除原因。
15. “向右转”执行后主体位置必须保持不变，只提交朝向变化事实；
16. 教学模式下远距离抓取必须被本体可达范围拒绝，靠近后的抓取必须通过两个观测通道验真；
17. 示教编译结果不得保存按键序列、绝对坐标、固定时长、关节角或单次轨迹；
18. 候选经验必须从初始状态自主完成导航和抓取，并在物理事实验真和人类确认后才进入本地可信状态。
19. 教学期间策略或目标绑定改变必须撤销旧教学权；自主复做期间世界或策略版本改变必须安全终止专用作业，不得回退为普通语言命令继续执行。
20. 持久化记录必须通过便携字段白名单，且不包含 `demonstration_entity_ref`、教学会话 ID、复做作业 ID或原始遥操作轨迹；
21. 全新会话必须发现可信经验、基于当前观测重新绑定杯子并自主复做，且明确 `trajectory_reused=false`。

这些断言保证端侧概念内化不会退化为“概念命中后直接动作”，而是继续服从 P018 的状态优先仲裁主链。

## 五、与 P018 的边界

P018 保护主链是：交互输入进入执行控制行为之前，先读取任务期运行时世界状态快照，并基于快照完成状态查询/任务控制分流、任务控制仲裁、当前事实续推和快照释放。

本工程记录保护或沉淀的是该主链上游的端侧概念证据机制：

1. 概念层负责把高频语义内化为可复用候选；
2. 证据包负责说明候选为何成立或为何不足；
3. 云端候选只在本地证据不足时补给；
4. 最终是否执行仍由 P018 的状态优先仲裁和执行控制链路决定。

因此，本记录可以作为后续端侧概念内化方案的工程证据种子，也可作为 P018 中“端侧概念/云端候选不直接取得执行权”的实施支撑。
