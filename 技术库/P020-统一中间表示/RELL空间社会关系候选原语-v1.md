# RELL 空间与社会关系候选原语 v1

本轮登记 12 个候选原语：`near_human`、`beside`、`in_front_of`、`behind`、`facing`、`between`、`inside`、`contains`、`supports`、`held_by`、`owned_by`、`accessible_to`。

每个原语同时记录中文词语适配器、参数元数、Grounding 规则、规划合同和 P016 验真条件。登记状态为 `candidate_only`，候选关系只存在于任务工作记忆，不写入 WorldFactLedger，也不能绕过 P018 控制入口。

晋级流程固定为：候选概念 -> 最小因果合同 -> 主动观察 -> 新实例验证 -> 晋级或否决 -> 生成词条适配器。

机器合同：`schemas/rell_spatial_social_primitive_candidates_v1.json`。

校验入口：`demo_runtime/rell_sample/validate_rell_spatial_social_primitives.py`。

## 首批语言与规划接入

已接入以下人体参照表达：

- “站到我身边” -> `navigate_to + near_human(human_speaker)`；
- “站到我前面” -> `navigate_to + in_front_of(human_speaker)`；
- “站到我后面” -> `navigate_to + behind(human_speaker)`；
- “面向我” -> `orient_executor + facing(human_speaker)`。

规划层只生成候选合同：动态人体参考系、相对目标区域或目标朝向、P018 控制入口和 P016 末态验真条件。语言理解本身不能启动执行，也不能提交关系事实。

已进一步区分：

- “操作台A旁边” -> `beside(操作台A)`，要求侧向相对位姿验真；
- “操作台A附近” -> `near_landmark(操作台A)`，只要求宽松距离范围；
- “操作台A和操作台B之间” -> `between(操作台A, 操作台B)`，两个参考实体分别落地为稳定 `EntityRef`，规划目标是由二者共同定义的派生空间区域。

关系正反合同已登记在 `schemas/rell_relation_duality_contract_v1.json`：

- `inside` <-> `contains`；
- `supports` <-> `supported_by`；
- `held_by` <-> `holds`；
- `owned_by` <-> `owns`；
- `accessible_to` <-> `can_be_accessed_by`。

反向投影只生成候选解释，不产生第二事实；物理关系需要 P016 验真，社会关系需要社会证据，可达关系同时需要可达性和权限证据。

## 社会关系落地

- “杯子还在我手里”生成 `held_by` 候选，需要多模态观测或 P016 持有验真；
- “这是我的杯子”生成 `owned_by` 候选，需要所有权记录或带上下文的人类确认；
- “我能够得到这个杯子”生成 `accessible_to` 候选，同时需要当前可达性和权限策略验真。

这些候选由结构化语篇角色或报告事件生成，RCIR 以下不读取原始文本；所有候选均为 `fact_commit_eligible=false`。
