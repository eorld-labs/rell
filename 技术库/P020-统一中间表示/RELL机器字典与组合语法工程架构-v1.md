# RELL机器字典与组合语法工程架构-v1

日期：2026-07-21

状态：工程实施基线

## 一、目标

RELL机器字典不是自然语言词典，而是可组合、可执行、可验真、可双向翻译的机器语义标准。

它使用有限的机器基本构件描述人类语言和物理世界，并保证：

```text
人类语言 -> 机器语义 -> 当前世界落地 -> 因果执行 -> 物理验真
物理观察 -> 机器语义 -> 证据与边界 -> 人类语言解释
```

## 二、字词句篇四层

| 层级 | 中文 | RELL | 工程对象 |
| --- | --- | --- | --- |
| 字 | 部首与笔画组成单字 | 七类基本类型、基本谓词、不可约算子与修饰维度 | `MachineDictionaryEntry`核心条目 |
| 词 | 单字组合成词 | 复合概念、算子合同、过程模板 | 可追溯`components`的组合条目 |
| 句 | 词按语法组成句子 | 情境事件图与已落地因果图 | `SituatedEventGraph`、`GroundedCausalGraph` |
| 篇 | 句子形成文章与对话 | 任务图、认识图、交流图及紧凑记忆 | 任务工作记忆与证据化事件胶囊 |

四层不是四套状态源。只有`WorldFactLedger`保存当前世界事实。

## 三、核心与扩展的边界

### 3.1 核心字

核心字只包括：

1. 不可约基本谓词；
2. 不可约事件算子；
3. 修饰维度及其基本值；
4. 七类RCIR基本类型。

核心字必须满足：

- `irreducible=true`；
- 不引用其他字作为组成部分；
- 有类型化角色；
- 有跨语言适配入口；
- 物理谓词有验真合同；
- 不因语言适配而获得事实提交权。

### 3.2 机器词

机器词由核心字组合，至少包括：

- 复合概念；
- 算子合同；
- 过程模板；
- 领域包条目。

机器词必须声明`components`，并允许反向展开到核心字。`fill_container`、`assemble`、`charge_battery`和菜谱均属于这一层，不应无条件进入核心原语表。

### 3.3 领域包

装配、烹饪、医疗、酒店服务等领域知识以插件式领域包存在。领域包可新增：

- 概念；
- 语言适配器；
- 过程模板；
- 规则候选；
- 专用验真适配器。

领域包不得新增第二事实源、绕过P018或直接写入P016事实。

## 四、每个字典条目的最小合同

每个条目至少回答：

```text
它是什么类型
是否不可再分
由哪些构件组成
有哪些角色以及角色类型
参与哪些关系
需要哪些前提
产生和销毁哪些事实
如何验真
有哪些人类语言适配形式
如何反向表达
由谁拥有事实提交权
在哪些版本和适用域内有效
```

语言适配器只负责将表面形式映射为语义候选。它不绑定当前实例、不提交事实、不授权执行。

## 五、组合语法

### 5.1 指代表达

语言中的名词短语不总是当前实体，因此角色填充统一使用`ReferentExpression`：

| 类型 | 含义 |
| --- | --- |
| `entity_ref` | 已在当前世界落地的具体实体 |
| `entity_selector` | 带概念与属性约束的待落地选择器 |
| `set_selector` | 并列、全称、数量或分配式集合 |
| `subregion_selector` | 依附父实体的边、角、面、接口等区域 |
| `future_entity_selector` | 尚未出现、需在未来条件满足时绑定的实体 |
| `interaction_role` | 当前说话者、接收者等交互角色 |
| `event_role` | 从某个事件参与者反向引用的角色 |

除`entity_ref`外，其他类型不得携带当前`EntityRef`冒充已落地实体。

### 5.2 作用域图

修饰、否定、量词、时态和语篇连接必须显式绑定作用域：

```text
Modifier/Negation/Quantifier
  -> target_event_ref
  -> scope_kind
  -> provenance
  -> conflict policy
```

“离哪个事件最近”只能产生候选，不能成为权威作用域规则。

### 5.3 多义候选

多义字和多义词首先形成多个带选择约束的语义候选。例如“上”可以产生：

```text
supported_by      requires: 名词后 + 承载参照物
aspect_attainment requires: 动词后
direction_upward  requires: 垂直空间目标
```

对象概念、句法位置、事件角色、世界事实和语篇范围共同消解候选。无法唯一消解时生成`InquiryContract`，禁止使用默认值静默变成唯一解释。

## 六、候选解释格与权威语义图

一轮输入可以在语言前端内部存在多个候选，但只能产生一个权威语义图：

```text
语言表面形式
  -> InterpretationLattice
  -> 类型约束与作用域求解
  -> 唯一解释：SituatedEventGraph
  -> 多个解释：InquiryContract
```

`InterpretationLattice`位于“禁止原文下沉”边界之上。它可以保存来源跨度用于语言分析，但输出的权威图只保留来源引用和结构化语义。

## 七、句到篇的三图结构

篇章级交互分为三类图：

1. `TaskGraph`：改变物理世界；
2. `InquiryGraph`：获取证据、消解知识缺口；
3. `CommunicativeGraph`：告知、询问、提醒、解释和内容交付。

三者共享：

- 同一`WorldFactLedger`；
- 同一`EvidenceEnvelope`；
- 同一P018控制准入；
- 相应的验真合同；
- 同一版本失效机制。

任何一个图都不得成为事实或控制旁路。

## 八、正向和反向编译

### 8.1 正向编译

```text
人类语言
  -> 字典适配候选
  -> 机器组合语法
  -> 情境事件图
  -> 当前实体落地
  -> 因果图与执行合同
```

### 8.2 反向编译

```text
当前事实、目标、规则评估、询问合同、验真收据
  -> 交流意图
  -> 字典反向适配
  -> 人类语言
```

正向和反向编译引用同一条目ID、同一谓词和同一证据引用，禁止解释层重读原始命令猜测机器状态。

## 九、知识进入字典的生命周期

新词、新概念和新过程不能直接进入可信字典：

```text
未知表达或重复模式
  -> 候选适配/候选概念/候选过程
  -> 预测增益与反例
  -> InquiryContract
  -> 观察或安全试验
  -> P018仲裁
  -> P016或合格证据验真
  -> P012治理
  -> P019晋级
```

晋级后仍保留来源、版本、适用域和回退关系。

## 十、工程不变量

1. `core_glyph_is_irreducible`；
2. `compound_entry_declares_components`；
3. `domain_pack_does_not_expand_core_implicitly`；
4. `surface_adapter_has_no_fact_authority`；
5. `polysemy_produces_candidates_before_selection`；
6. `ambiguous_semantics_never_silently_becomes_unique`；
7. `selector_is_not_entity_ref`；
8. `future_entity_is_bound_only_when_generation_condition_is_current`；
9. `scope_is_explicit_before_authoritative_graph_emission`；
10. `one_turn_has_one_authoritative_semantic_graph`；
11. `dictionary_round_trip_preserves_semantic_entry_ref`；
12. `bidirectional_translation_reads_shared_rcir_and_evidence`；
13. `dictionary_entry_cannot_bypass_p018_or_p016`；
14. `world_fact_ledger_remains_the_only_current_fact_source`。

## 十一、首期实施范围

第一阶段只建立：

- 最小机器字典Schema和登记表；
- `ReferentExpression`；
- `InterpretationLattice`；
- `ScopeGraph`；
- 多义表面形式返回候选而非静默选择；
- 字典正反向适配回归；
- 核心与复合条目边界断言。

后续再依次接入现有语言组合器、指代解析器、领域包和解释生成器。

## 十二、2026-07-21等价迁移状态

当前已进入`shadow_equivalence_migration`，完成以下工程连接：

- `FACTORY_EVENT_CONCEPT_UNITS`中的17个事件算子均有且仅有一个机器字典条目；
- 字典明确区分不可约算子与可组合因果合同，`fill_container`、`handover_object`等不再被平铺为核心原语；
- 修饰编译器从机器字典读取闭类词项、方向补语和类型元数据，仅在组合层保留句法附着规则；
- 指代解析器正式输出`ReferentExpression`：唯一落地产生`entity_ref`，多候选产生等待消歧的`entity_selector`；
- 在线语言路径逐轮输出`MachineDictionaryProjection`、`ScopeGraph`和`InterpretationLattice`；
- 覆盖审计、算子/角色/修饰等价、指代统一和权威边界均已进入全量回归入口。

本阶段“覆盖完成”不等于“切换执行权威”。机器字典仍不得直接控制执行或提交事实。只有在自然语言变体、复杂语篇、失败恢复和冷启动场景的逐字段等价证据持续为零冲突后，才允许将字典编译结果提升为`SituatedEventGraph`的权威输入；P018与P016边界不随迁移改变。

## 十三、复杂语篇影子等价证据

在线语言路径现已逐轮生成`MachineDictionaryEquivalenceReceipt`，分别比较：

- 言语行为与查询类型；
- 算子序列；
- 角色及`ReferentExpression`；
- 修饰参数与作用域；
- 目标关系；
- 未决变量；
- 跨轮指代；
- 语篇边；
- 失败恢复上下文；
- 复合语句的全部事件帧。

收据只用于迁移审计，`can_control_execution=false`、`can_commit_runtime_fact=false`、`surface_text_reparsed=false`。会话中最多保存64份收据，避免形成无界第二记忆源。

首批工程证据共9案：8案正常语义等价，1案人为篡改目标关系并被正确判定为差异；7案满足当前晋级前提。另1个正常等价案因指代仍有歧义而按设计阻断，篡改案是差异检测对照。该`7/9`不是语言成功率，而是影子迁移门的准入分布。证据报告输出到`demo_runtime/output/rell_sample/dictionary_shadow_equivalence/shadow_equivalence_report.json`。

## 十四、交流字典层

机器字典`1.1.0`新增三类正式条目：

- `speech_act`：9类不可约言语行为原语；
- `query_contract`：12类当前状态查询合同；
- `communicative_contract`：确认、否决、纠正和澄清回答合同。

查询合同只允许读取声明的权威来源，例如`WorldFactLedger`、当前任务图、合格观察证据或偏好记录。交流条目的`fact_commit_authority`必须为`none`；人类报告、确认和纠正只能改变交流或候选语义状态，不能直接建立物理事实。

同一表面形式允许形成类型兼容的组合语义。例如“请”可以同时对应`request_action`与`politeness`，不应被错误处理为二选一歧义；“上”在承载面清单查询中则由`support_inventory`合同约束为`supported_by`，方向和体貌候选被排除。真正无法由类型、作用域和上下文消解的候选仍进入`InquiryContract`。

当前在线路径已接入任务请求、状态查询、禁止、语言教学、确认、否决、显式纠正、各类澄清回答和人类信息报告。确认必须绑定当前`pending_confirmation`，纠正必须绑定被替换的RCIR或活跃意图，并重新进入当前世界落地。澄清回答绑定活跃对话合同的稳定引用，是否真正消费仍由对应合同解析器决定；新的完整任务可以继续按原有优先级取代旧询问。人类信息报告只形成`information_report`候选，其`qualified_for_physical_fact=false`。

反向对话和结构化解释现同时输出`speech_act_ref`、`query_contract_ref`和`response_act_ref`，引用与正向编译相同的机器字典条目。反向生成仍只读取RCIR、规则评估和证据引用，不重读原始命令。至此，交流字典已经形成“人类语言→机器交流合同→RCIR/当前事实读取→共享字典引用→人类语言”的首个双向闭环。

## 十五、2026-07-22受控语义权威切换

机器字典现已从影子比较进入`controlled_authority_trial`。这里提升的是“生成`SituatedEventGraph`的语义权威”，不是执行权、事实提交权或物理验真权。

每一轮输入必须依次形成：

```text
旧语言前端兼容适配
  -> MachineDictionaryProjection
  -> InterpretationLattice
  -> MachineDictionaryEquivalenceReceipt
  -> DictionaryAuthorityAdmission
  -> 单一 semantic_input
  -> SituatedEventGraph
  -> GroundedCausalGraph
  -> P018控制仲裁
  -> P016执行验真
  -> WorldFactLedger
```

`DictionaryAuthorityAdmission`检查以下条件：

- 解释格已经唯一收敛，歧义未被静默消除；
- 算子、角色、修饰、作用域、目标、指代、语篇和事件帧的等价票据通过；
- 投影、解释格、票据、角色落地和过程绑定均属于当前世界版本；
- 恢复路径已经声明重新进入当前事实裁剪；
- 完整投影的`projection_id`和SHA-256摘要与票据一致；
- 字典层仍为`can_control_execution=false`、`can_commit_runtime_fact=false`。

任一条件失败时，只允许生成带原因的`legacy_structured_compatibility_adapter`回退输入。字典投影与兼容回退在同一轮中不得同时成为权威。回退保证旧能力可运行，但其使用情况必须可统计、可定位并可逐步归零。

本轮同时关闭了四条历史旁路：

1. `SituatedEventGraph`不再直接读取旧分析字段，只读取准入后的`semantic_input`；
2. 运行规则评估读取同一准入语义和当前实体绑定，不再读取第二份算子/修饰词解释；
3. 旧`SituatedEventFrame`改为从RCIR投影，时间范围、人类报告和历史事件约束不再重读原文；
4. 复合任务子节点携带字典事件帧、`EntityRef`和证据引用，阶段切换时不再重新造句并进入语言解析器。

人类报告现覆盖完成事件和持续占有状态。`我喝完了`、`杯子还在我手上`等表达先形成`information_report`及候选关系；恢复门只能用它们发起当前事实核对，不能直接写入物理事实。

世界版本变化时，当前语义准入和RCIR立即局部失效，旧图进入紧凑收据；下一轮必须重新投影、重新落地和重新签发准入合同。反向对话复用RCIR中已有的交流字典引用，并校验引用与类型一致，不重新根据语义值搜索另一条解释路径。

本阶段的架构完结判据是：语义主链只有一个准入入口，事实主链只有`WorldFactLedger`，控制和验真仍分别只经P018与P016，恢复、复合语篇、查询、澄清和反向解释不存在第二语义源。词汇覆盖、领域包和认识目标仍可持续扩展，但扩展必须进入本合同，不得新增旁路。
