# Schemas

`schemas/` 定义 RELL 第一期开源对象模型。当前公开层以 P010-P016 的产品接口为主，不包含内部专利证据链和行业私有经验库。

## P016 物理动作底座

| 正式入口 | 作用 |
| --- | --- |
| `space_semantic_prior.schema.json` | 定义 P010 空间语义先验，包括语义区域、空间关系和端侧转换信息。 |
| `process_template.schema.json` | 定义过程模板、连续状态变量、阶段跃迁条件和参数槽。 |
| `occasional_binding.schema.json` | 将过程模板参数槽绑定到当前环境中的对象、传感器和阈值。 |
| `causal_chain.schema.json` | 声明因果前提、产出事实、销毁事实和过程链编排关系。 |
| `fact_observation.schema.json` | 定义目标因果事实的独立观测通道、成立判断和最终成立状态。 |
| `engine_contract.schema.json` | 定义运行时执行计划、监控循环、恢复和执行轨迹接口。 |
| `executor_profile.schema.json` | 预留执行体能力画像，用于承接 P008 主体物理约束和后续空间可进入性准入。 |
| `rcir_bundle.schema.json` | 定义单轮权威情境事件图、世界事实账本、已落地因果图及其不可绕过的证据边界。 |
| `rcir_concept.schema.json` | 定义跨语言、跨实例复用的 `Concept`。 |
| `rcir_entity_ref.schema.json` | 定义与名称、别名和模态分离的稳定 `EntityRef`。 |
| `rcir_predicate.schema.json` | 定义候选、目标和当前事实共用的 `Predicate`。 |
| `rcir_event.schema.json` | 定义报告、观察、请求和验真变化共用的 `Event`。 |
| `rcir_goal.schema.json` | 定义只引用目标谓词且受世界版本约束的 `Goal`。 |
| `rcir_constraint.schema.json` | 定义属性、空间、物理、安全和过程边界 `Constraint`。 |
| `rcir_evidence_envelope.schema.json` | 定义证据来源、资格、世界版本、依赖和事实晋级权限。 |
| `rcir_type_relations.json` | 定义七类基本类型间的允许关系、权限含义和禁止旁路。 |
| `inquiry_contract.schema.json` | 定义认识目标、竞争假设、消解路线、关闭条件及 P018/P016 网关。 |
| `rcir_modifier_contract.schema.json` | 定义事件级、全局级与语篇级修饰参数、冲突询问和只收紧不放宽的执行边界。 |
| `rcir_reference_resolution.schema.json` | 定义指代候选、权威层级、时态来源、歧义询问及非事实提交边界。 |
| `rcir_salience_projection.schema.json` | 定义从当前事实、任务角色和对话焦点派生且不可持久化为第二状态源的显著性投影。 |
| `rcir_rule_evaluation.schema.json` | 定义经 P018 仲裁、经 P016 验真的规则结果及其非事实源边界。 |

## 兼容入口

`process_necessity.schema.json` 和 `contingency_binding.schema.json` 是早期命名保留下来的兼容入口。新示例优先引用正式入口，旧入口暂不删除。

## 示例

`schemas/examples/` 中的倒水、抓取、端水和家庭环境绑定示例展示了过程模板如何通过偶然绑定数据实例化，并通过因果事实验证结果驱动后续执行。
