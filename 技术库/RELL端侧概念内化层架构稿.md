# RELL端侧概念内化层架构稿

## 1. 目标

本文用于把当前讨论中形成的“端脑/云脑”路线落成一份可实施的架构稿。

核心判断如下：

1. 智能主体必须先在端侧成立，云端只能增益，不能代替主体。
2. 端侧智能不应依赖“大模型每次重新想一遍”，而应依赖概念、状态、经验三者交织形成的本地推理闭环。
3. 云脑负责外域经验、长程语义和跨设备知识聚合；端脑负责直接经验、当前真值、即时裁决和执行闭环。
4. 当前路线的真正价值，不在于“能跑一个任务”，而在于“执行主体逐渐形成自己的低成本工作语义系统”。

用当前哲学语言概括：

- 直接经验：沉在本体侧，构成端脑。
- 外域经验：沉在云侧，构成云脑。

## 2. 总体定位

端侧概念内化层不是聊天层，不是词典层，也不是直接执行层。

它的定位是：

`自然语言输入 -> 端侧概念解析 -> 状态/经验/编排映射 -> 执行主体裁决`

它在整体架构中的职责，是把高频自然语言中的公共语义压缩为本体可用的内部概念单元，使执行主体不必每次都依赖云端大模型才能理解任务、回答状态问题或接收教学。

## 3. 端脑与云脑分工

### 3.1 端脑负责

1. 当前空间语义的本地绑定
2. 当前任务期运行时世界状态快照
3. 高频概念的本地解析
4. 高频状态问答
5. 高频动作意图识别
6. 经验回放与经验适配
7. 执行前本地可行性判断
8. 不可执行原因分层
9. 教学过程中的即时复述与缺口说明
10. 本地偏好记忆和即时治理裁决

### 3.2 云脑负责

1. 陌生任务或长程复杂任务语义理解
2. 跨设备经验库检索
3. 公共概念扩展和概念晋升后的全局沉淀
4. 稀有场景恢复经验检索
5. 多主体经验共享和统计归纳
6. 低频复杂教学的辅助解析

### 3.3 调用原则

1. 端脑优先
2. 本地概念能解释时，不调用云脑
3. 本地状态能回答时，不调用云脑
4. 仅在“陌生、长程、歧义大、端侧概念不足”时调用云脑
5. 云脑输出始终是候选，不直接绕过编排层和执行层

## 4. 端侧概念内化层的内部结构

端侧概念内化层建议命名为 `Concept Core`，内部至少拆为五个子模块。

### 4.1 词项概念单元库

负责沉淀高频对象、动作、状态、时态和指示类概念。

第一版建议覆盖：

1. 对象概念：杯子、水壶、水源、桌子、门、通道、凳子
2. 动作概念：拿、放、去、接水、倒水、绕开、打开、关闭
3. 状态概念：有水、没水、拿着、空闲、阻挡、可达、不可达
4. 主体概念：我、你、执行体、本体
5. 时间概念：现在、下一步、刚才、完成后
6. 指示概念：这里、那里、左边、右边、前面、后面

### 4.2 概念槽位映射器

负责把自然语言表达映射到可结构化的内部槽位。

例如：

- “当前杯子有没有水” -> `query_type=liquid_state`
- “你现在在做什么” -> `query_type=current_action`
- “下一步做什么” -> `query_type=next_step`
- “去拿杯子” -> `action_intent=pick_up_cup`

### 4.3 状态槽位桥接器

负责把概念查询映射到当前任务期运行时世界状态快照中的真值字段，而不是回退到长期记忆或语言猜测。

典型槽位：

1. `executor.location_ref`
2. `executor.holding`
3. `current_stage`
4. `completed_stages`
5. `established_facts`
6. `active_preferences`
7. `runtime_environment.last_blocked_step`
8. `goal_fact`

### 4.4 经验候选桥接器

负责把动作概念、对象概念和空间概念组合成经验候选或过程链候选，再交回编排层判断。

例如：

- “接一杯水” -> 候选目标事实 `cup_contains_water`
- “把杯子拿过来” -> 候选过程链 `move_to_counter -> pick_up_cup -> move_to_requester`
- “从A走到B” -> 候选空间导航概念 + 本地空间绑定

### 4.5 云脑补给桥

负责在端侧概念不足时发起云端请求，并把云端返回结果压回端侧候选结构，而不是直接把云端当执行控制器。

输出必须保持：

1. 候选概念
2. 候选目标事实
3. 候选过程链
4. 候选澄清问题

而不是：

1. 直接动作序列
2. 连续控制指令
3. 绕过运行时世界状态快照的最终执行命令

## 5. 概念、状态、经验三者关系

### 5.1 概念

回答“这是什么类型的东西/动作/状态”。

### 5.2 状态

回答“当前真值是什么”。

### 5.3 经验

回答“通常如何从一个事实走到另一个事实”。

### 5.4 三者闭环

1. 概念层识别对象和动作语义
2. 状态层读取当前真实世界快照
3. 经验层给出候选过程链
4. 编排层判断当前是否可执行
5. 执行层根据当前真实环境落地动作
6. 结果再回流状态层与经验层

这是端侧主体性的核心闭环。

## 6. 与现有体系的关系

### 6.1 与P013的关系

P013负责统一任务语义翻译。

概念内化层是 P013 在端侧的高频语义压缩实现，用于把“高频任务语言”沉为本体可直接复用的概念单元和查询模式。

### 6.2 与P015的关系

P015负责人类偏好记录和偏好约束。

概念内化层不替代偏好层，而是把偏好解释为：

- 当前约束
- 当前追认范围
- 当前自主预算边界

### 6.3 与P017的关系

P017负责跨空间跨本体真实经验迁移。

概念内化层不替代 P017 的迁移适配控制器，而是帮助端侧更稳定地把自然语言映射到：

1. 目标事实
2. 绑定候选
3. 候选经验
4. 澄清需求

### 6.4 与治理层的关系

治理层负责：

1. 法律法规和制度边界
2. 高风险动作保护策略
3. 代理权预算
4. 来源链与审计要求

概念内化层只负责理解与解释，不负责自创治理规则。

## 7. 数据结构建议

### 7.1 ConceptUnit

```json
{
  "concept_id": "concept_fillable_container",
  "display_name": "可盛装容器",
  "concept_type": "object",
  "aliases": ["杯子", "水杯", "杯"],
  "effect_contract": {
    "related_facts": ["cup_contains_water", "cup_empty"]
  },
  "binding_policy": {
    "requires_space_binding": true,
    "direct_execution_allowed": false
  },
  "runtime_query_support": [
    "liquid_state"
  ]
}
```

### 7.2 ConceptIntentFrame

```json
{
  "request_type": "state_query",
  "query_type": "current_action",
  "object_concepts": [],
  "action_concepts": ["concept_current_action_query"],
  "time_scope": "current_runtime_snapshot",
  "confidence": 0.96,
  "clarification_needed": false
}
```

### 7.3 CloudRecallPacket

```json
{
  "task_id": "migration_xxx",
  "local_concept_gap": [
    "unknown_action_phrase"
  ],
  "runtime_context_summary": {
    "goal_fact": "cup_contains_water",
    "current_facts": ["cup_empty"]
  },
  "expected_return": [
    "candidate_concepts",
    "candidate_process_chain",
    "clarification_questions"
  ]
}
```

## 8. 第一版最小实现范围

第一版不要做全语义系统，只做两个主干。

### 8.1 状态概念主干

目标：让执行主体稳定理解并回答以下高频问题：

1. 当前杯子有没有水
2. 我现在在哪
3. 你现在在做什么
4. 下一步做什么
5. 我手里拿着什么
6. 当前偏好约束是什么

### 8.2 高频动作概念主干

目标：让执行主体稳定理解以下高频任务表达：

1. 接一杯水
2. 倒水
3. 拿起杯子
4. 走到操作台
5. 去水源处
6. 绕开障碍

## 9. 第二版扩展范围

### 9.1 指示与澄清

支持：

1. 那个
2. 这个
3. 左边那个
4. 白色那本

并能说出：

1. 我没定位到对象
2. 我缺少空间参照
3. 请补充颜色/位置/名称

### 9.2 教学概念化

支持把教学语言拆成：

1. 目标约束
2. 过程约束
3. 可变区间
4. 风格/服从偏好

### 9.3 云脑补给

仅在本地概念不足时请求：

1. 候选概念
2. 候选经验
3. 候选澄清问句

## 10. 工程拆解

### 10.1 模块拆分

建议新增以下模块：

1. `demo_runtime/rell_sample/concept_core/concept_units.py`
2. `demo_runtime/rell_sample/concept_core/concept_parser.py`
3. `demo_runtime/rell_sample/concept_core/query_router.py`
4. `demo_runtime/rell_sample/concept_core/concept_bridge.py`
5. `demo_runtime/rell_sample/concept_core/cloud_recall.py`

### 10.2 第一批接口

1. `resolve_local_concepts(utterance, task_id=None)`
2. `map_concept_query_to_runtime_slot(query_type, runtime_world_state)`
3. `build_local_concept_intent_frame(utterance, task_id=None)`
4. `request_cloud_concept_support(gap_packet)`

### 10.3 第一批验证

1. 本地状态问答六句稳定命中
2. 高频动作六句稳定映射
3. 不能命中时稳定澄清
4. 不因云脑缺席而失去基本工作能力

## 11. 当前建议的实施顺序

1. 先把状态概念主干做稳
2. 再把高频动作概念主干做稳
3. 再把教学语言拆到目标/过程/偏好三层
4. 最后接云脑补给桥

## 12. 结论

端侧概念内化层不是“替代大模型”，而是把执行主体真正需要长期拥有的那部分工作语义，从云端依赖中剥离出来，沉到本体侧。

只有当概念、状态、经验三者在端侧闭成环，执行主体才会从“能跑流程”成长为“能理解自己、能解释自己、能积累自己”的智能体。
