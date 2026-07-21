# P020 运行时语义与事实优先级技术特征映射

## 提交范围

本批代码用于验证 P020 统一认知中间表示在自然语言变体、当前事实优先级、历史事件角色、复合任务角色传递和因果任务图激活中的工程作用。

## 技术特征对应

| P020 技术特征 | 代码落点 | 验证证据 |
|---|---|---|
| 概念约束与对象类别组合，而非依赖完整对象名称枚举 | `concept_core/language_concept_composer.py` | 历史失败语料与陌生改写语料中的颜色、容器形态、材料和动作变体 |
| 当前世界版本中的已验真关系优先于历史和无约束类别候选 | `concept_core/process_template_resolver.py::normalize_perception_gap` | 人手持杯关系不再被两个可见杯候选降级为歧义 |
| 历史关系由结构化事件约束解析，后续阶段不重新依赖原始措辞 | `embodied_scene.py::_historical_support_reference_candidate` | “原先取它的台面”“刚才拿杯子的桌子”“归还原桌”统一解析为历史支撑角色 |
| 复合任务的实体角色以 `EntityRef` 跨子任务传递 | `embodied_scene.py::_compile_compound_subtasks`、`_dispatch_compound_subtask` | 先归还当前杯、再换高脚杯接水的两个主题和目的地保持独立 |
| 场景任务图按算子、目标关系和概念签名激活 | `causal_task_graph_runtime.py::causal_graph_activation_matches`、`hospitality_task_graph.py` | 招待任务图与普通单杯托盘交付不再仅依赖场景名称或单一词面 |
| 后续规划读取 RCIR 中的正式当前谓词及权威摘要 | `embodied_scene.py::_resolve_current_role_binding` | `received_by` 谓词、RCIR bundle 标识和 authority digest 共同进入角色绑定证据 |

## 回归结果

- 冻结自然语言案例：16/16，规划成功率 100%；
- 历史失败案例：8/8；
- 陌生改写案例：8/8；
- 端到端模拟执行抽样：4/4；
- 浏览器实测陌生表达“拿那只白色的马克杯装水递给我”完成取杯、接水和交付；
- 语言组合、语义接地、过程模板、上下文投影、招待任务图、RCIR 阶段 A/B、认识目标 API、任务尺度、因果图运行时和水服务长回归通过。

评估程序：`evaluate_natural_language_variants.py`。

证据包：`技术库/P020-统一中间表示/证据包/自然语言变体评估-20260721-113324`。

## 验证边界

本批结果证明本机模拟场景中统一语义、当前事实裁剪和结构化角色传递能够提高冻结语料的规划与执行成功率。该结果不等同于开放世界自然语言达到 100%，不等同于真机物理执行验证，也不证明运行事件已经能够自动发现并生成新概念。

概念自形成目前已有候选概念、竞争假设、询问合同、新实例验证及晋级或否决的最小闭环；自动从运行事件聚类未解释模式、持久化候选概念库、反例驱动拆分或合并以及晋级后进入在线概念注册表仍属于下一阶段。
