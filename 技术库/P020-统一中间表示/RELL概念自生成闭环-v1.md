# RELL 概念自生成闭环 v1

概念自生成流程已固定为：候选概念 -> 最小因果合同 -> 主动观察或安全试验 -> 新实例 P016 验真 -> 晋级或否决 -> 生成词条适配器候选。

每个候选概念必须包含：

- 可观察特征；
- 功能可供性；
- 可参与关系；
- 前置条件；
- 效果；
- P016 验真条件；
- 适用范围；
- 反例；
- 新实例验证要求。

概念晋级不会自动授予执行权限。生成的词条适配器仍为候选，`core_dictionary_write_allowed=false`，必须再次经过 `DictionaryAuthorityAdmission`。否决的候选不会生成可用词条。

工程入口：

- `concept_core/cognitive_inquiry.py::run_concept_validation_loop`；
- `validate_rell_concept_self_generation.py`。
