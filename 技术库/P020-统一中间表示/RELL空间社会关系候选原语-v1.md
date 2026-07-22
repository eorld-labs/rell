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
