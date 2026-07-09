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

## 兼容入口

`process_necessity.schema.json` 和 `contingency_binding.schema.json` 是早期命名保留下来的兼容入口。新示例优先引用正式入口，旧入口暂不删除。

## 示例

`schemas/examples/` 中的倒水、抓取、端水和家庭环境绑定示例展示了过程模板如何通过偶然绑定数据实例化，并通过因果事实验证结果驱动后续执行。
