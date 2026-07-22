# P020/RELL 核心合同冻结 v1

## 冻结对象

七类基本类型固定为 `EntityRef`、`Predicate`、`Event`、`EvidenceEnvelope`、`WorldFact`、`Goal`、`Constraint`。

四个权威边界固定为：

- 语义准入：`DictionaryAuthorityAdmission`；
- 事实来源：`WorldFactLedger`；
- 控制入口：P018；
- 物理验真与事实回写入口：P016。

机器可执行合同位于 `schemas/p020_rell_core_contract_v1.json`，回归入口位于 `demo_runtime/rell_sample/validate_p020_core_contract.py`。

## 扩展规则

后续新增词语、概念、关系和动作能力只能通过 schema 扩展、合同版本升级或携带证据的新适配器进入。禁止：

- RCIR 下游重新解析原始文本；
- 建立第二事实源；
- 绕过 P018 控制入口；
- 绕过 P016 写入运行时事实；
- 把歧义候选静默提升为唯一绑定。

## 基准记录合同

自然语言基准的每条结果必须分别记录：

- `semantic_parse_correct`；
- `role_grounding_correct`；
- `inquiry_correct`；
- `planning_success`；
- `physical_verification_passed`；
- `safe_rejection`。

没有实际执行证据的层必须记录为 `null` 或“不适用”，不能按成功处理。
