# RCIR 语篇理解与双向语言桥工程证据

日期：2026-07-21

## 一、目标

本实现将自然语言中的时序回溯、事件连接、代词、省略和纠正编译为类型化
语篇事件图，并从同一 RCIR 的事件、目标、实体引用、证据和未决角色生成
人类可读回应。执行模块不重新解析原始句子，回应模块也不另建一份意图。

## 二、正向编译

`language_concept_composer.py` 生成：

- 独立事件作用域；
- `sequence`、`parallel`、`correction` 语篇边；
- `asserted` 与 `rejected` 纠正极性；
- 跨事件的类型化角色流；
- 指向已验真历史事件角色的时间约束。
- 独立于动作目标的类型化 `query` 节点。

连接词只决定图关系，不成为动作或实体。省略角色只允许从前一事件的唯一
结构化角色或当前对话焦点继承，不能通过改写字符串重新进入解析器。

## 三、上下文投影

短程执行细节在任务结束后释放，只保留目标模式和紧凑事件胶囊。出现
“照刚才再来一杯”等省略表达时：

1. 只投影最近完成任务的目标模式；
2. 不复用旧角色或旧验真事实；
3. 根据当前账本反向查询目标关系需要的角色；
4. 只有当前关系唯一时才重新绑定 `EntityRef`；
5. 多候选或无证据时进入最小追问。

例如，目标模式为 `human_received_filled_container` 时，可用当前谓词
`received_by(?theme, human_speaker)` 重新绑定容器；这不是把上次容器名称带回。

## 四、反向投影

`rcir_dialogue_realizer.py` 只读取：

- `SituatedEventGraph`；
- `GroundedCausalGraph`；
- `WorldFactLedger` 引用；
- 已落地角色和未决角色。

显示名称由最外层 `EntityRef -> label` 映射提供。对象改名只改变人类文本，
不改变机器目标、事件图或规划引用。输出同时携带 `source_bundle_ref`、
`grounded_graph_ref`、`fact_authority_ref` 和 `world_revision`，用于证明解释与
规划同源。

状态查询由 `query_type` 表达，不能借用动作的目标关系。区域名来自当前场景的
语义区域注册表；“房间、这里、当前空间”等指示表达绑定执行体当前区域。
查询只读取当前版本的世界状态或观察证据，不创建动作意图，也不进入最小因果
契约追问。

输入容错仅作用于明确状态谓词槽中的闭类疑问词，并要求唯一的一次编辑匹配。
该过程会生成规范化审计，且禁止改写对象名、区域名等开放类概念。

## 五、安全边界

- 被纠正的 `rejected` 事件不进入执行子图；
- “随后”之类语篇词不能进入本体方向解析；
- 人类报告和历史事件胶囊不作为当前物理事实；
- 角色继承不提交物理关系；
- 解释文本不回流为规划输入；
- 当前世界变化后必须重新落地实体和关系。
- 复合任务切换后，返回的语言视图必须属于当前子任务，不能沿用上一子任务。
- 查询语义优先于同形动作词法，例如查询中的“放着”表示状态而不是放置命令。

## 六、回归证据

```powershell
python .\demo_runtime\rell_sample\validate_discourse_event_graph.py
python .\demo_runtime\rell_sample\validate_language_paraphrase_properties.py
python .\demo_runtime\rell_sample\validate_contextual_language_runtime.py
python .\demo_runtime\rell_sample\validate_water_delivery_loop.py
```

性质测试覆盖：

- 216 种时间词、抓取动词、显式/代词/省略主题和承载面别名组合；
- 8 种顺序连接改写；
- 6 个代词唯一与歧义条件；
- 5 种纠正表达；
- 8 种区域/承载面清单查询与受限错字变体；
- 历史回溯、复合任务、目标模式续接、所有权纠正、查询不中断任务、子任务语言
  视图转交和机器解释同源的真实会话。

这些数字表示已复核的工程覆盖，不表示任意自然语言都能无条件执行。无法唯一
落地的输入必须形成结构化未决角色并安全追问。
