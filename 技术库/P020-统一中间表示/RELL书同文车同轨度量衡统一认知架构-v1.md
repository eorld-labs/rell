# RELL“书同文、车同轨、度量衡”统一认知架构-v1

日期：2026-07-20

状态：架构母稿

适用范围：P013 任务语义翻译、P016 物理验真、P018 运行时仲裁、P019 端侧概念内化及其工程样品

## 一、结论

RELL 下一阶段不应继续以“为一句自然语言增加一条处理分支”的方式扩展能力，而应把真实场景中的失败收敛为统一认知架构的不变量。

统一认知架构由三个互相约束的部分组成：

1. **书同文**：中文、英文、口语、省略、指代和教学语言，统一编译为机器内部的概念—事件—目标表示；
2. **车同轨**：语言、视觉、触觉、空间状态、任务编排和动作执行，统一使用同一组实体引用、关系谓词和因果算子；
3. **度量衡**：所有候选、事实、报告和经验统一携带证据来源、世界版本、时间范围、验真条件和失效条件。

三者共同解决的不是“机器人会不会回答一句话”，而是以下闭环是否成立：

> 人类语言能够稳定翻译为机器目标；机器能够把目标落到当前世界；机器能够用动作改变世界并验真；机器能够再把依据、过程和边界翻译回人类语言。

## 二、为什么当前修补既有价值又必须收敛

### 2.1 有价值的部分

真实场景持续暴露了以下架构问题：

- 已验真事实未进入恢复后的候选计划；
- 完整语句切成子句后丢失整句角色；
- 历史事件被误当成当前动作；
- 当前关系、历史记忆和人类报告的证据等级混淆；
- 经验模板绕过当前世界事实，从头执行旧路径；
- 相同概念换名称、换实例或换场景后无法复用。

这些失败是有效的压力测试。每一个失败都应形成一个架构不变量和跨场景回归测试。

### 2.2 必须停止的部分

以下做法不得继续成为主路径：

1. 在下游模块重新读取并解析原始自然语言；
2. 以完整句子、固定物体名称或场景 ID 选择执行分支；
3. 用历史任务绑定替代当前世界实例绑定；
4. 用人类报告直接提交物理事实；
5. 用感知候选直接授权执行；
6. 用经验中的原始步骤覆盖当前事实裁剪结果；
7. 在多个模块分别维护“当前对象”“当前目标”和“当前阶段”的不同答案。

因此，后续所谓“修复”必须回答一个问题：它补的是统一表示或统一契约，还是又增加了一个旁路。

## 三、总体架构

```mermaid
flowchart LR
    HL["人类语言\n中文/英文/口语/教学"] --> LF["语言前端\n概念组合与语篇解析"]
    LF --> SEG["SituatedEventGraph\n情境事件图"]

    PS["视觉/深度/触觉/本体状态"] --> PE["感知证据适配器"]
    PE --> WFL["WorldFactLedger\n世界事实账本"]

    SEG --> GR["Grounding Resolver\n角色与实例落地"]
    WFL --> GR
    GR --> GCG["GroundedCausalGraph\n已落地因果图"]

    GCG --> ARB["P018 状态优先仲裁"]
    WFL --> ARB
    ARB --> EXE["动作原语与本体适配器"]
    EXE --> VER["P016 末态与过程验真"]
    VER --> WFL

    WFL --> NLG["解释生成器"]
    GCG --> NLG
    NLG --> HL
```

这不是要求把所有代码合并为一个模块，而是要求所有模块通过同一套机器语言交换信息。

## 四、统一认知中间表示

统一认知中间表示暂称 `RELL Cognitive IR`，简称 `RCIR`。它不是一句话的槽位表，而是一组可以贯穿语言、世界和执行的基本类型。

### 4.1 七类基本类型

| 类型 | 回答的问题 | 示例 |
|---|---|---|
| `Concept` | 它本质上属于什么 | 可盛装容器、颜色、承载体、人类接收者 |
| `EntityRef` | 当前世界中具体是哪一个 | `entity_17`，不等于显示名称 |
| `Predicate` | 当前或目标关系是什么 | `received_by(x, human)` |
| `Event` | 发生或被报告了什么变化 | 抓取、放置、饮用完成 |
| `Goal` | 希望最终什么事实成立 | `received_by(filled_x, human)` |
| `Constraint` | 哪些条件限制角色或过程 | 颜色、材质、温度、承载能力 |
| `EvidenceEnvelope` | 为什么相信它、何时失效 | 触觉验真、视觉候选、人类报告 |

### 4.2 概念不等于词语

概念是可跨语言、跨名称、跨实例复用的结构：

```json
{
  "concept_id": "concept_fillable_container",
  "super_concepts": ["concept_physical_object", "concept_container"],
  "perceptual_invariants": ["bounded_inner_volume", "open_or_fillable_access"],
  "functional_affordances": ["graspable", "receive_liquid"],
  "state_schema": ["empty", "filled", "held", "supported"],
  "language_adapters": {
    "zh": ["杯子", "水杯", "饮具"],
    "en": ["cup", "drinking vessel"]
  }
}
```

“白色马克杯”应组合为：

```text
head_concept = concept_fillable_container
constraints = [color=white, container_form=mug]
```

不能把“白色马克杯”整体固化为一个不可分词项，也不能把品牌、型号或对象显示名当作概念本体。

### 4.3 机器谓词是跨层轨道

同一个谓词必须同时可被语言目标、世界事实、经验前提和动作效果引用。例如：

```text
received_by(container, human)
supported_by(payload, carrier)
held_by(object, executor)
contains(container, liquid)
reachable(executor, entity)
```

语言层可以提出这些谓词作为目标；感知和执行层只能以证据候选或验真结果更新这些谓词。

## 五、书同文：人类语言到机器语言

### 5.1 单一编译入口

每轮人类输入只允许经过一次正式语言编译，生成不可变的 `SituatedEventGraph`。图生成后，下游模块禁止重新解析原始字符串。

`SituatedEventGraph` 至少包含：

```json
{
  "utterance_ref": "turn_42",
  "speech_act": "task_request",
  "events": [],
  "reported_events": [],
  "goals": [],
  "roles": {},
  "constraints": [],
  "discourse_links": [],
  "temporal_scope": "current_with_recent_reference",
  "unresolved_variables": [],
  "physical_fact_committed": false
}
```

### 5.2 整句语义先于子句执行

子句可以形成独立事件节点，但整句的角色、时态、因果连接和省略关系必须先完成，再允许拆分执行。

例如：

> 我喝完了，再接一杯水。这次把杯子放在托盘里然后给我。

应编译为：

```text
reported_event:
  consumption_completed(agent=human, theme=?payload)
  evidence=human_report
  physical_fact_committed=false

goal:
  received_by(?payload, human)

required_relations:
  contains(?payload, water)
  supported_by(?payload, ?carrier)
  held_by(?carrier, executor) at terminal

role_constraints:
  ?payload affords receive_liquid
  ?carrier affords transport_supported_payload
```

“给我”虽可构成省略子句，但其接收者角色必须进入整句目标；“喝完了”虽不是机器人动作，但必须成为当前关系查询的选择条件。

### 5.3 多语言是多个前端，不是多套认知

中文、英文、方言或行业术语只负责生成相同的 RCIR 结构。语言适配器可以不同，但不得产生不同的物理谓词和动作契约。

翻译正确性的判断不是两句话是否相似，而是它们生成的以下内容是否等价：

1. 目标事实；
2. 角色类型与约束；
3. 时态和事件范围；
4. 未决变量；
5. 代理权和禁止条件；
6. 验真要求。

## 六、车同轨：物理世界到机器语言

### 6.1 世界事实账本是唯一当前真值来源

`WorldFactLedger` 保存当前世界版本下仍然有效的事实。显示文本、任务历史、经验模板和语言解释均不得替代账本。

事实记录至少包含：

```json
{
  "predicate": "received_by",
  "subject": "entity_17",
  "object": "human_1",
  "world_revision": 12,
  "status": "established",
  "evidence_ref": "evidence_93",
  "valid_from": "event_210",
  "invalidated_by": null
}
```

### 6.2 感知只产生候选证据

视觉检测到“像杯子的白色物体”时，输出的是：

```text
perceptual_candidate(entity_candidate, concept_fillable_container)
observed_attribute(entity_candidate, color=white)
```

它不等于：

```text
target_object_in_gripper = true
```

空间落地、关系一致性和动作验真完成后，候选才能晋升为当前事实。

### 6.3 动作原语采用因果契约

动作原语不以固定轨迹为本体，而以类型化前提、效果和验真条件定义：

```json
{
  "operator": "fill_container",
  "roles": {
    "theme": "affords:receive_liquid",
    "source": "affords:provide_liquid"
  },
  "requires": [
    "held_by(theme, executor)",
    "reachable(executor, source)"
  ],
  "projects": [
    "contains(theme, liquid)"
  ],
  "verification": [
    "liquid_level_observed",
    "container_integrity_preserved"
  ]
}
```

轨迹、速度和关节序列属于本体适配后的短期执行细节，完成后释放；因果效果和验真摘要进入事实账本与紧凑事件记忆。

## 七、度量衡：统一证据与验真

### 7.1 证据等级

默认优先级从高到低为：

1. 当前物理验真关系；
2. 当前多模态一致感知；
3. 当前人类显式约束；
4. 当前任务角色绑定；
5. 最近验真事件胶囊；
6. 可信经验或持久概念；
7. 未约束类别候选。

高优先级证据可以排除低优先级候选，低优先级证据不得覆盖当前物理事实。

### 7.2 四种状态必须分开

| 状态 | 含义 | 是否可作为执行事实 |
|---|---|---|
| `reported` | 人类报告某事件或状态 | 否，可触发核查或上下文选择 |
| `observed_candidate` | 传感器形成候选 | 否 |
| `spatially_grounded` | 候选已绑定当前空间实例 | 仅可用于规划候选 |
| `runtime_verified` | P016 验真成立 | 是 |

### 7.3 失败按依赖关系失效

阶段失败不等于整项任务所有事实失效。

当 `fill_container` 末帧验真失败时：

- `container_filled` 不成立；
- 依赖 `container_filled` 的后续事实不得提交；
- 已独立验真的 `held_by(container, executor)` 继续成立；
- 恢复计划必须从事实账本重新裁剪，而不是重放完整经验模板。

## 八、从语义图到因果图

### 8.1 角色落地

角色落地只允许依据以下输入：

1. `SituatedEventGraph` 中的概念和约束；
2. 当前 `WorldFactLedger`；
3. 当前有效感知证据；
4. 必要时的紧凑历史事件查询。

落地结果必须说明：

```text
绑定了哪个 EntityRef
使用了哪些概念约束
依据了哪些当前关系
是否唯一
世界版本是多少
何时必须重新绑定
```

### 8.2 因果图编译

落地后的目标编译为 `GroundedCausalGraph`：

```json
{
  "goal_facts": [],
  "nodes": [],
  "edges": [],
  "joins": [],
  "role_bindings": {},
  "verified_fact_ledger": [],
  "open_conditions": [],
  "authorization_scope": {},
  "verification_contract": {}
}
```

长程与短程不按句子长度区分，而按裁剪后因果拓扑区分：

- 单个已落地效果：原子动作；
- 少量单链节点：短程任务；
- 多分支、汇合、外部条件或未展开宏目标：长程任务。

### 8.3 当前事实裁剪是强制步骤

任何以下入口都必须经过同一个裁剪器：

- 新任务首次编排；
- 阶段失败恢复；
- 用户重复确认；
- 环境变化后重规划；
- 任务切换后恢复；
- 经验召回；
- 长程任务分支汇合。

裁剪规则：排除已完成节点、目标事实已成立节点及其效果已被更强当前事实覆盖的节点。

## 九、记忆生命周期

统一认知不等于保存完整对话和所有细节。记忆分为四层：

| 层级 | 保存内容 | 释放条件 |
|---|---|---|
| 当前世界记忆 | 当前有效事实和对象关系 | 世界变化或明确失效 |
| 任务工作记忆 | 活跃因果图、开放条件、角色绑定 | 目标验真、取消或被替代 |
| 情节胶囊 | 验真事件参与者、前后事实、来源关系 | 有界容量和相关性淘汰 |
| 语义记忆 | 概念、谓词、动作契约、可信经验不变量 | 版本治理或证据撤销 |

必须释放：

- 轨迹；
- 运动帧；
- 已完成叶节点计划；
- 临时澄清文本；
- 旧任务候选链；
- 单次教学按键和绝对坐标。

必须保留但压缩：

- 当前仍成立的物理事实；
- 已验真事件的紧凑参与者与事实变化；
- 已完成任务的目标模式；
- 可迁移概念与经验合同。

## 十、陌生语料与陌生环境的工作流程

### 10.1 陌生说法、已知概念

1. 语言前端识别已知概念组合和未知表面词；
2. 若事件、角色和目标仍可唯一形成，未知表面词只进入语言适配候选；
3. 当前任务继续使用既有概念和谓词；
4. 经人类确认后，只保存表面词到概念的适配关系，不修改物理事实。

### 10.2 已知语言、陌生实例

1. 从概念生成任务条件化感知契约；
2. 在当前环境中寻找满足感知不变量和功能可供性的候选；
3. 多候选时主动观察或询问可观察差异；
4. 唯一落地后生成新的 `EntityRef` 绑定；
5. 经验只提供过程不变量，所有坐标和路径重新规划。

### 10.3 陌生概念

系统必须明确缺失的是哪一种信息：

- 上位概念；
- 可感知不变量；
- 功能可供性；
- 状态模式；
- 可参与关系；
- 动作效果；
- 验真方式。

人类教学或云端补给只能形成候选概念包。候选必须经过观察、操作、预测和验真闭环后，才能成为端侧可信概念。

### 10.4 陌生任务

若目标可以由已知谓词表达，则先反向搜索已知动作原语和经验合同；若缺少生产某个前提的过程，系统应报告具体事实缺口，而不是笼统回答“不会”。

## 十一、机器理解成立的操作性标准

机器“理解一个概念”至少意味着它能够：

1. 把多种语言表达归入同一概念；
2. 在陌生实例上根据不变量识别候选；
3. 预测该概念可以参与的关系和动作；
4. 根据当前事实判断哪些动作可行；
5. 预测动作可能产生和销毁的事实；
6. 通过约定证据判断预测是否实现；
7. 在失败后指出缺失的是概念、实例、能力、资源还是证据；
8. 把机器内部判断翻译回人类语言并给出依据。

只有“识别词语”或“执行过一次脚本”均不构成概念理解。

## 十二、反向翻译与人机同步

机器对人类的回答不得从历史话术模板直接生成，而应由当前 RCIR 状态投影生成。

回答至少可以解释：

- 我理解的目标是什么；
- 当前绑定了哪些对象和角色；
- 哪些事实已经验真；
- 哪些只是人类报告或感知候选；
- 下一步为什么是这个动作；
- 为什么不能执行；
- 需要人类补充的最小信息是什么。

自然语言生成是机器语言到人类语言的反向编译器。正向和反向翻译必须引用同一图、同一事实账本和同一证据封装，避免“内部做一套、嘴上说一套”。

## 十三、模块边界与现有工程迁移

| 现有模块或方案 | 统一架构中的职责 | 需要收敛的边界 |
|---|---|---|
| P013 / `language_concept_composer` | 人类语言到 `SituatedEventGraph` | 每轮只编译一次，输出不可变图 |
| P019 / Concept Core | 概念、别名、可供性、概念证据 | 不直接绑定事实或授权执行 |
| `context_projection` | 为当前输入投影最小相关事实和事件 | 不保存完整旧任务，不复用旧验真账本 |
| 感知落地器 | 概念候选到当前空间实例 | 候选不等于事实 |
| 过程模板与经验库 | 提供事实生产者和过程不变量 | 禁止输出未经当前事实裁剪的完整旧路径 |
| 因果任务图 | 表达目标、节点、分支、汇合和开放条件 | 只消费 RCIR 与结构化角色绑定 |
| P018 Runtime | 状态优先仲裁、切换、恢复、裁剪 | 成为所有执行入口的强制门 |
| P016 | 动作执行与物理验真 | 只按依赖粒度提交或撤销事实 |
| 解释层 | RCIR 到人类语言 | 禁止凭原始话术猜测状态 |

### 13.1 强制禁止原始文本下沉

完成迁移后，以下模块不应再接收自然语言字符串作为决策输入：

- 角色落地器；
- 因果图编译器；
- 经验检索排序器；
- 失败恢复器；
- 动作执行器；
- 物理验真器。

为审计保留 `utterance_ref` 可以接受，但原文不得再次参与决策。

## 十四、架构不变量

以下规则应转为代码断言和回归测试：

1. `language_does_not_commit_physical_fact`；
2. `perception_candidate_is_not_runtime_fact`；
3. `one_turn_has_one_authoritative_semantic_graph`；
4. `downstream_does_not_reparse_surface_text`；
5. `current_verified_relation_precedes_history_and_category`；
6. `every_binding_has_evidence_and_world_revision`；
7. `every_action_has_requires_projects_verification`；
8. `every_recovery_reenters_current_fact_pruning`；
9. `failure_invalidates_only_dependent_facts`；
10. `experience_never_reuses_instance_or_trajectory`；
11. `completed_working_memory_is_released`；
12. `renaming_does_not_change_grounding_result`；
13. `cross_scene_equivalent_facts_produce_equivalent_graphs`；
14. `ambiguous_binding_never_silently_becomes_unique`；
15. `human_explanation_reads_the_same_graph_used_for_execution`。

## 十五、验证方法

### 15.1 表达不变性

同一目标使用不同语序、省略、同义词和语言表达，应生成等价目标与角色约束。

### 15.2 改名不变性

修改对象显示名但保留概念、可供性和当前关系后，落地结果不应变化。

### 15.3 场景不变性

更换坐标、对象实例数量和空间布局后，因果图结构保持，实例绑定和路径重新计算。

### 15.4 证据冲突测试

构造人类报告、视觉候选、历史事件和当前物理事实相互冲突的情况，验证证据优先级和澄清边界。

### 15.5 生命周期测试

验证任务完成后轨迹、子句、候选计划和澄清细节已释放，而当前物理事实、目标胶囊和紧凑事件仍可用于后续指代。

### 15.6 双向一致性测试

机器对外解释中的目标、对象、当前事实、未决条件和下一阶段，必须与实际执行所消费的数据结构逐字段一致。

## 十六、实施路线

### 里程碑 A：冻结统一模式

1. 定义 RCIR 基础类型和版本；
2. 定义 `SituatedEventGraph`、`WorldFactLedger`、`GroundedCausalGraph`；
3. 定义证据封装和事实失效协议；
4. 为现有结构建立兼容转换器。

完成标准：同一条输入只有一个权威语义图，所有绑定均可追踪证据。

### 里程碑 B：建立唯一编排入口

1. 下游模块改为只消费结构化图；
2. 禁止失败恢复、复合子任务和经验召回重新解析原文；
3. 把当前事实裁剪设为所有规划入口的强制步骤；
4. 将旧分支逐步迁移到统一编译器。

完成标准：删除任一场景显示名不会改变任务图；重复确认和失败恢复不会回到已完成节点。

### 里程碑 C：统一物理事实与证据

1. 合并重复的事实来源和阶段快照；
2. 为人类报告、视觉候选、空间落地和 P016 验真建立统一状态机；
3. 实现按依赖关系失效；
4. 解释层直接读取事实账本和因果图。

完成标准：状态查询、任务续推和解释输出引用同一事实版本。

### 里程碑 D：概念形成与跨域迁移

1. 陌生词适配到已有概念；
2. 陌生实例通过感知不变量和可供性落地；
3. 陌生概念通过教学形成候选概念包；
4. 可信经验抽取为无实例、无轨迹的因果合同；
5. 在陌生场景和陌生本体上重新绑定、规划和验真。

完成标准：概念复用不依赖名称，经验复用不依赖实例和轨迹。

### 里程碑 E：多语言与真机闭环

1. 为中文和英文建立独立语言前端；
2. 验证二者生成等价 RCIR；
3. 接入真实视觉、深度、触觉和本体状态；
4. 验证机器解释与真实执行逐事实一致。

完成标准：语言变化不改变机器目标，环境变化只改变实例绑定和路径。

## 十七、开发决策规则

以后每个新案例按以下顺序处理：

1. 记录期望的目标事实、角色、约束和验真条件；
2. 检查权威语义图是否正确；
3. 检查当前事实账本是否包含所需关系；
4. 检查角色落地是否遵守证据优先级；
5. 检查因果图是否正确表达依赖和汇合；
6. 检查 Runtime 是否按当前事实裁剪；
7. 检查 P016 是否只提交已验真效果；
8. 将失败归纳为架构不变量；
9. 增加表达、改名、场景和证据冲突回归；
10. 禁止以整句或场景对象名称作为最终修复。

## 十八、与现有专利和工程线的关系

本架构不替代现有方案，而是规定它们如何通过统一机器语言协作：

- P013 负责“书同文”的任务语义翻译入口；
- P019 负责概念单元、概念证据和端侧内化；
- P012/P017 负责概念与经验跨域迁移；
- P011/P020 负责经验形成和教学闭环；
- P018 负责当前状态优先的运行时仲裁；
- P016 负责事实是否真正成立的物理验真；
- P014 负责失败后的恢复与再适配；
- P015 负责偏好约束，不把偏好冒充物理事实。

统一架构的新增价值在于：上述能力不再通过自然语言字符串、固定模板或隐式共享变量松散连接，而是通过同一套概念、谓词、实体引用、因果算子和证据封装形成闭环。

## 十九、最终判断

“书同文”解决人类说法不同但机器目标应相同的问题；“车同轨”解决语言、感知、规划和执行各说各话的问题；“度量衡”解决候选、报告、历史和物理事实真假混淆的问题。

真正的统一认知不是让机器人记住更多句子，而是让它在陌生表达、陌生实例和陌生环境中，仍能使用同一套机器语言完成：

```text
概念识别 -> 目标形成 -> 当前落地 -> 因果编排 -> 物理执行 -> 事实验真 -> 人类解释
```

当这条闭环成为唯一主路径后，场景测试仍然会不断暴露问题，但每次修复将提升整个底座，而不是只让某一句话暂时可用。

## 二十、最小版本工程落点

2026-07-20 已形成 RCIR 最小可执行版本，工程入口为：

- `demo_runtime/rell_sample/concept_core/cognitive_ir.py`；
- `schemas/rcir_bundle.schema.json`；
- `demo_runtime/rell_sample/validate_cognitive_ir.py`；
- `demo_runtime/rell_sample/docs/rcir_minimal_evidence_chain.md`。

当前版本已经实现：

1. 单轮权威 `RCIR Bundle`；
2. 不含原句的 `SituatedEventGraph`；
3. 带世界版本和证据引用的 `WorldFactLedger`；
4. 带结构化角色绑定的 `GroundedCausalGraph`；
5. Bundle 权威摘要和篡改检测；
6. 现有任务角色解析对 RCIR 的主链消费；
7. 新轮次替换和任务完成后的紧凑收据释放；
8. 改名不变性、事实版本一致性和原句不下沉回归。

当前仍属于迁移起点，而不是最终完成态。旧情境事件结构暂时并行存在，部分内部阶段仍经过旧语言入口，经验检索、恢复和全部复合任务编译器尚未强制改为只消费 RCIR。下一里程碑仍以“自然语言以下模块不再重新解析原文”为完成标准。

## 二十一、最小落地补充协议与强制不变量

### 21.1 角色落地失败追问合同

角色落地不再由各场景自行生成“请选择某个物体”的固定问句，而是进入统一循环：

```text
多候选 EntityRef
  -> 比较当前可观察属性
  -> 选择使最大剩余候选数最小的属性
  -> 请求该最小属性约束
  -> 将回答编译为概念谓词
  -> 在当前 world_revision 重新观测和落地
  -> 唯一则继续，否则再次追问
```

该合同只处理颜色、材质、形态、尺寸、透明度、温度和状态等可观察属性，不读取对象显示名，不提交物理事实。世界版本变化后，旧追问合同失效，必须重新观测。

### 21.2 旧经验到新环境的迁移合同

可信经验的执行权威被收缩为 `PortableExperienceContract`。允许迁移：

- 角色类型槽位和所需可供性；
- `requires / produces / destroys` 因果效果；
- 验真条件和终止条件；
- 算子顺序、拓扑、方向及物理不变量。

禁止迁移：

- 旧 `EntityRef` 和原目标语言；
- 绝对坐标、关节角、固定时长；
- 教师按键、单次轨迹和旧本体参数。

每次召回都必须在当前世界证据上重新绑定角色、按当前本体重新规划运动，并在规划前执行当前事实裁剪。旧经验记录可在迁移期保留用于审计和兼容，但不再是执行权威。

### 21.3 五条优先不变量

最小版本已将以下规则从文档要求升级为代码断言和回归测试：

1. `language_does_not_commit_physical_fact`：人类报告只形成事件候选；
2. `perception_candidate_is_not_runtime_fact`：感知证据保持 `epistemic_only`，不能直接改变执行状态；
3. `downstream_does_not_reparse_surface_text`：RCIR 以下禁止原始文本字段；
4. `current_verified_relation_precedes_history_and_category`：唯一当前验真关系优先于历史、经验和类别候选；
5. `every_recovery_reenters_current_fact_pruning`：每次续推或恢复生成绑定当前世界版本的裁剪审计令牌，旧路径不得复用。

对应工程落点：

- `concept_core/rcir_contracts.py`：追问合同和经验迁移合同；
- `concept_core/cognitive_ir.py`：五条不变量的编译期与校验期断言；
- `embodied_experience_store.py`：可信经验召回时生成并暴露可迁移合同；
- `embodied_scene.py::_prepare_long_intent_stage`：统一当前事实裁剪屏障；
- `validate_cognitive_ir.py`：合同、证据边界、优先级和恢复路径回归。

## 二十二、第四层：认识目标生成与消解循环

### 22.1 缺口不是异常检测，而是认识目标生成

RCIR 已经统一语言目标、当前事实、执行因果图和证据等级，但现有闭环仍主要由外部任务驱动。异常检测只能说明当前数据偏离历史分布，不能自动回答：

1. 当前究竟缺少哪项知识；
2. 哪个问题能够消除该知识缺口；
3. 该问题是否值得现在处理；
4. 应通过已有证据、被动观察、主动观察、安全试验还是人类询问获得答案；
5. 获得何种证据后可以关闭问题；
6. 答案能够更新事实、经验、过程模板还是候选概念。

因此，统一认知架构需要增加独立于任务执行触发、但不独立于状态与权限控制的 `Cognitive Inquiry Loop`，即认识目标生成与消解循环。

```text
证据变化 / 经验异常 / 概念缺口
  -> 形成带来源的认知缺口
  -> 生成结构化认识目标和竞争假设
  -> 评估信息价值、风险、成本、权限和时效
  -> 选择自查、观察、试验、询问或延迟
  -> 获取新证据
  -> 定向更新事实、经验边界、模板或候选概念
  -> 关闭、降级、失效或保留认识目标
```

该循环不得直接修改物理事实、执行动作或晋级概念。任何主动观察、物理试验或任务控制均须进入 P018 仲裁；任何物理结果均须由 P016 或等价验真闭环确认。

### 22.2 五类认识目标

| 类型 | 触发条件 | 需要回答的问题 |
|---|---|---|
| 事实缺口 | 当前目标依赖的谓词缺少有效证据 | 哪个事实当前是否成立 |
| 模型漂移 | 观测分布持续偏离历史质量档案 | 是对象变化、环境变化、传感器漂移还是样本变化 |
| 过程异常 | 同类恢复、失败或人工介入频率异常 | 模板、阈值、适用边界或本体绑定是否需要修订 |
| 概念缺口 | 反复出现的模式无法由现有概念压缩和预测 | 是否存在新的可复用概念或已有概念需要拆分 |
| 生命周期问题 | 事实、绑定或经验长期未验证或证据已过期 | 是否应复核、降级、失效或保留 |

“长期未被任务引用”不等于事实为假，只能触发复核或降低缓存优先级；“均值偏移”不等于对象磨损；“追问频率升高”不等于用户群体改变。每个异常信号必须先生成多个可区分的竞争假设，禁止直接提交结论。

### 22.3 InquiryContract

机器内部不得以自然语言问句作为认识目标的权威表示。RCIR 增加 `InquiryContract`：

```json
{
  "inquiry_id": "inquiry_104",
  "gap_type": "model_drift",
  "subject_refs": ["entity_17"],
  "trigger_evidence_refs": ["grasp_81", "grasp_92", "grasp_97"],
  "candidate_hypotheses": [
    "surface_wear",
    "sensor_drift",
    "task_distribution_change"
  ],
  "question_predicate": "current_grasp_profile(entity_17, ?value)",
  "answer_routes": [
    "existing_evidence",
    "passive_observation",
    "active_observation",
    "safe_probe",
    "human_query"
  ],
  "expected_information_gain": 0.72,
  "risk_if_ignored": "medium",
  "acquisition_cost": "low",
  "authorization_scope": "observe_only",
  "world_revision": 31,
  "expiry_condition": "entity_removed_or_world_changed",
  "closure_condition": "two_independent_channels_agree",
  "status": "open"
}
```

自然语言问题只是解释层对 `InquiryContract` 的投影。人类回答必须重新进入语言前端，形成带证据等级的结构化回答，不得直接成为物理事实。

### 22.4 回答路径和最小打扰原则

认识目标按以下优先顺序尝试消解：

1. 查询当前账本、情节胶囊和可信经验；
2. 等待任务自然产生的被动观察；
3. 请求低成本主动观察，例如改变视角或重新采样；
4. 在权限允许且风险可控时生成安全试验候选，交 P018 仲裁并由 P016 验真；
5. 只有人类拥有答案时，生成最小可观察差异问题；
6. 信息价值不足、风险过高或打扰成本过大时，延迟、降级或关闭。

机器“会提出问题”不等于频繁询问人类。系统应优先自主消解，仅将无法自证且预期信息价值超过成本的问题提交人类。

### 22.5 认识目标的状态机

`InquiryContract` 至少包括以下状态：

```text
candidate
  -> admitted
  -> observing / probing / awaiting_human
  -> resolved
  -> verified
  -> closed
```

以及：

```text
candidate -> suppressed
admitted -> deferred
任一未关闭状态 -> expired / invalidated
```

认识目标的世界版本失效、主体消失、依赖事实变化或问题已经被其他证据回答时，应失效或合并，禁止继续使用旧问题驱动观察和执行。

## 二十三、概念自形成

### 23.1 候选概念形成条件

反复出现不等于形成概念。候选概念至少应满足：

1. 在多个事件、对象或场景中重复出现；
2. 对后续事实或动作效果提供可验证的预测增益；
3. 能降低经验描述复杂度或提高检索稳定性；
4. 与已有概念不完全等价；
5. 具有可观察不变量、适用条件和反例；
6. 能够形成明确的验证合同。

候选概念只进入候选概念库，不取得事实提交权和动作执行权。

### 23.2 概念验证闭环

```text
未解释的重复模式
  -> 候选概念及适用边界
  -> 预测该概念在新实例上的关系或效果
  -> 形成观察或安全试验 InquiryContract
  -> P018 仲裁
  -> P016 或其他证据通道验真
  -> P012 管理置信度、拆分、合并和待验证状态
  -> P019 晋级为端侧可信概念
```

若新证据只支持部分样本，系统应缩小适用域或拆分概念；若多个候选具有相同因果签名和适用边界，系统可提出合并候选。任何自动拆分或合并均须保留证据、版本和可回退关系。

## 二十四、跨域类比发现

### 24.1 不按词面或宽泛动作名称类比

跨域类比基于类型化因果图的反统一，而不是自然语言相似度或“都是移动”之类的宽泛描述。

源经验和目标候选至少比较：

```text
角色类型与可供性
requires 前提事实
produces 产出事实
destroys 销毁事实
阶段拓扑
验真谓词
失败边界
```

例如，倒水的关键效果是 `contains(container, liquid)`，放置杯子的关键效果是 `supported_by(cup, surface)`。二者可以在更高层共享“源关系变化、受控转移、目标关系建立”等结构，但不得因该高层相似性而丢弃各自的对象类型、物理约束和验真条件。

### 24.2 类比只形成候选合同

跨域匹配输出 `AnalogicalExperienceCandidate`，包括共同因果骨架、不能迁移的字段、目标域待绑定角色、需要重新验证的效果以及类比置信度。候选必须进入 P017 进行当前空间和本体适配，进入 P018 取得控制准入，并由 P016 验真后才能形成可信经验。

## 二十五、双循环总体架构

```mermaid
flowchart TD
    H["人类目标"] --> RCIR["RCIR任务闭环"]
    RCIR --> ARB["P018仲裁"]
    ARB --> EXE["P016执行与验真"]
    EXE --> WFL["WorldFactLedger"]
    WFL --> EXP["经验/概念/质量档案"]

    WFL --> SIG["认知信号适配器"]
    EXP --> SIG
    SIG --> GAP["认知缺口与竞争假设"]
    GAP --> INQ["InquiryContract"]
    INQ --> GATE["价值/风险/成本/权限门"]
    GATE --> SELF["自查或被动观察"]
    GATE --> ARB
    GATE --> HUMAN["最小人类询问"]
    SELF --> EVID["新证据"]
    HUMAN --> EVID
    EXE --> EVID
    EVID --> WFL
    EVID --> EXP
```

任务闭环负责实现外部目标；认识目标循环负责发现和消解知识缺口。两者共享同一事实账本、证据协议、权限仲裁和验真边界，禁止形成第二套事实或执行旁路。

## 二十六、新增强制不变量

1. `anomaly_signal_does_not_commit_hypothesis`；
2. `inquiry_is_structured_before_language_projection`；
3. `every_inquiry_has_evidence_world_revision_and_closure`；
4. `active_observation_and_probe_require_arbitration`；
5. `human_answer_is_evidence_not_physical_fact`；
6. `candidate_concept_has_no_execution_authority`；
7. `analogy_transfers_causal_structure_not_instance_binding`；
8. `expired_inquiry_cannot_trigger_action`；
9. `unreferenced_does_not_mean_false`；
10. `self_answer_and_human_answer_use_the_same_evidence_protocol`。

## 二十七、下一阶段工程验证

1. 为质量度档案、恢复记录、概念原语表、空间快照和事实账本建立统一认知信号接口；
2. 实现竞争假设生成，不允许单一异常直接提交结论；
3. 实现 `InquiryContract` schema、状态机、合并、失效和关闭；
4. 实现无需人类的证据查询与被动观察路径；
5. 实现低风险主动观察候选并接入 P018；
6. 为安全试验建立 P016 验真合同；
7. 实现最小可观察差异的人类询问生成；
8. 建立概念候选的预测增益、反例和适用边界测试；
9. 建立因果图反统一与跨域类比候选；
10. 验证任务闭环和认识目标循环不会产生双重事实源或控制旁路。

---

## 二十八、附录：RCIR 作为机器的象形文字体系

### 28.1 核心观点

本附录不是工程规范，而是一个设计哲学——把 RCIR 视为机器独有的「表意文字」体系，而非一组临时数据结构。类比中文汉字的构造原理来审视 RCIR，能揭示许多隐藏的设计一致性。

### 28.2 汉字六书与 RCIR 的对偶

| 汉字造字法 | 原理 | RCIR 对应 | 示例 |
|---|---|---|---|
| **象形** | 画成其物 | **基本类型**（Concept/EntityRef/Predicate/Event/Goal/Constraint/EvidenceEnvelope） | `EntityRef` 类似于「日」「月」——不能再分的基本构件 |
| **指事** | 符号表示抽象概念 | **证据等级**、**世界版本**、**状态机状态** | `evidence_level = verified` 类似于「上」「下」——抽象的方位标记 |
| **会意** | 两个象形字组合出新义 | **复合谓词**、**因果契约** | `supported_by + held_by + reachable → place_object` 类似于「休」（人+木=人在树旁休息） |
| **形声** | 形旁表类别 + 声旁表音 | **概念 + 语言适配器** | `concept_cup.aliases = [杯子, cup]` 类似于「江」=水（形）+工（声） |
| **转注** | 同一事物不同叫法 | **同义语言适配器** | 「杯」和「盅」→ 都映射到同一 `concept_fillable_container` |
| **假借** | 借字表音 | **一字多义的路由** | 「上」在不同上下文映射到不同算子，类似于汉字被借用作虚词 |

### 28.3 RCIR 的「偏旁部首」体系

中文有 214 个部首。RCIR 的基本类型就是机器的部首：

| 机器部首 | 含义 | 能组成的「合体字」举例 |
|---|---|---|
| `EntityRef` | 实体引用 | `supported_by(EntityRef, EntityRef)` |
| `Concept` | 概念类别 | `Concept.fillable_container + Constraint.color_white` |
| `Predicate` | 关系谓词 | 所有空间谓词都是 `Predicate(EntityRef, EntityRef)` |
| `Event` | 事件算子 | 所有 `grasp_object / place_object / navigate_to` 等 |
| `Goal` | 目标状态 | `Goal(Predicate(EntityRef, EntityRef))` |
| `Constraint` | 约束条件 | `Constraint(EntityRef, attribute=value)` |
| `EvidenceEnvelope` | 证据封装 | 包裹任何事实的元信息 |

### 28.4 机器「合体字」的构造规则

正如中文合体字由偏旁+部件按固定空间位置组合，RCIR 合体字由基本类型按固定结构组合：

**左中右结构**（对应中文「做」「谢」）：

```
[EvidenceEnvelope] + [Predicate] + [EntityRef, EntityRef]
```

类似于：包在证据中的关系连接两个实体。

**上下结构**（对应中文「想」「架」）：

```
[Goal]
  ↓
[Event(Predicate)]
```

类似于：上层目标驱动下层事件。

**包围结构**（对应中文「国」「围」）：

```
EvidenceEnvelope(
  [Predicate(subject, object)]
)
```

类似于：证据封装包围事实。

### 28.5 机器「甲骨文」到机器「楷书」

正如中文从甲骨文演化到楷书，机器语言也可以有不同精度的表示层：

| 层级 | 性质 | 类似人类文字 |
|---|---|---|
| **原始感知信号** | 传感器原始数据，未结构化 | 甲骨文/金文——原始但不规范 |
| **RCIR 标准形式** | JSON 或结构化数据，完整包含所有字段 | 楷书/宋体——规范、完整、可交换 |
| **RCIR 紧凑形式** | 去除冗余字段，用于机器间高速通信 | 行书/草书——快速但需训练 |
| **RCIR 内部缓存** | 内存中的对象图，非序列化 | 人脑中的概念——最高效但不可读 |

设计原则：**对外交换用标准形式（楷书），内部处理可用紧凑形式（行书），但任何时候都可以无损恢复到标准形式。**

### 28.6 机器「文言文」：紧凑 RCIR

机器的紧凑通信形式可以设计为类似文言文的精炼表达：

```
标准 RCIR:
{
  "predicate": "supported_by",
  "subject": {"type": "EntityRef", "value": 17, "concept": "cup"},
  "object": {"type": "EntityRef", "value": 3, "concept": "table"},
  "evidence": {"level": "verified", "ref": "ev_93"},
  "world_revision": 42
}

机器文言文（紧凑格式）:
↑(17,3)[93,42]  // ↑ = supported_by, 17/3 = 实体, 93 = 证据, 42 = 世界版本
```

这种紧凑格式不应该取代标准格式，而应该作为**内部高频通信的优化**——就像人类不会用文言文写合同，但会用文言文写笔记。

### 28.7 机器「字典」：语言适配器

正如人类有《说文解字》解释每个汉字的含义，RCIR 的**语言适配器**就是机器字典：

```json
{
  "character": "放",
  "radical": "扌(hand)",
  "machine_definition": {
    "primary_template": "place_object(theme=?, destination=?, spatial_relation=?)",
    "variants": [
      {"context": "放+里", "spatial_relation": "inside_container"},
      {"context": "放+上", "spatial_relation": "on_support_surface"},
      {"context": "放+回", "modifier": "restore_prior_relation"}
    ]
  },
  "cross_reference": {
    "置": "place_object（更正式）",
    "搁": "place_object（更随意）",
    "摆": "place_object（强调位置调整）"
  }
}
```

### 28.8 设计原则：每一个新概念自问「它是一个什么字」

以后每次新增一个 RCIR 类型、算子或谓词，都回答三个问题：

1. **它属于哪一类基本构件？**（部首/偏旁？还是合体字？）
2. **它由哪些更基本的构件组合而成？**（如果是合体字，能拆吗？）
3. **它在机器字典里如何定义？**（语言适配器怎么映射？）

回答完这三个问题，就能确保新增加的东西和整个 RCIR 体系保持表意一致性，而不是一个孤立的临时补丁。

### 28.9 这个视角回答的本质问题

这个视角最终回答了一个问题：**机器应该用什么样的语言思考？**

答案是：**用和中文一样的表意原则思考——但不是用中文的汉字，而是用机器自己的基本构件（七类基本类型）组合出无限复杂的认知结构。**

正如人类用有限的部首组合出数万个汉字，机器用有限的基本类型组合出无限的世界表示。这不是比喻，这是你的 RCIR 架构已经实现的事实——只是现在给它找到了一个准确的文化类比。|

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-20 | v1 | 初稿 |
| 2026-07-21 | v2 | 新增 §㉘ RCIR 作为机器象形文字体系 |
