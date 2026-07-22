# RELL 空间与社会关系候选原语 v1

本轮登记 12 个候选原语：`near_human`、`beside`、`in_front_of`、`behind`、`facing`、`between`、`inside`、`contains`、`supports`、`held_by`、`owned_by`、`accessible_to`。

每个原语同时记录中文词语适配器、参数元数、Grounding 规则、规划合同和 P016 验真条件。登记状态为 `candidate_only`，候选关系只存在于任务工作记忆，不写入 WorldFactLedger，也不能绕过 P018 控制入口。

晋级流程固定为：候选概念 -> 最小因果合同 -> 主动观察 -> 新实例验证 -> 晋级或否决 -> 生成词条适配器。

机器合同：`schemas/rell_spatial_social_primitive_candidates_v1.json`。

校验入口：`demo_runtime/rell_sample/validate_rell_spatial_social_primitives.py`。
