# RELL 架构迭代历程与新颖性保护支柱-证据链

> 记录日期：2026-07-06
> 输入文档：`研发记录/讨论纪要/RELL架构迭代历程与新颖性保护支柱.md`
> 对照范围：`schemas/process_necessity.schema.json`、`schemas/causal_chain.schema.json`、`schemas/contingency_binding.schema.json`、`schemas/fact_observation.schema.json`、`schemas/engine_contract.schema.json`、`schemas/task_intent.schema.json`、`schemas/examples/`
> 文档性质：内部保护与披露边界整理，不作为对外开源说明直接发布。

---

## 一、证据链分层

RELL 当前证据分为三层：

1. **架构数据契约证据**：新增 RELL schema 与厨房倒水样例，证明“过程必然层、因果层、偶然层、事实观测、引擎契约、任务意图”的结构已经落成。
2. **现有运行时代码证据**：`demo_runtime/` 已证明治理预验真、来源链、预算裁决、受控执行、经验回写、恢复记录、技能包沉淀、审计输出的最小闭环。
3. **技术库与研发记录证据**：`技术库/代码-技术对应证据链.md`、`技术库/母案专利-技术特征-代码证据总表.md` 与 RELL 迭代纪要共同证明该批 schema 不是孤立字段，而是原有经验闭环与治理底座的架构升级。

当前不应把“schema 已定义”误表述为“完整 RELL 引擎已开源”。正确边界是：**开源数据契约与最小 demo，闭源编排算法、参数推断、治理裁决逻辑、经验库和恢复过程库。**

---

## 二、九个新颖性支柱证据链

| 支柱 | schema / 样例证据 | 当前代码证据 | 开源边界 | 闭源保护点 |
|---|---|---|---|---|
| P-A 过程作为混合自动机 + 质·量·度 | `process_necessity.schema.json` 定义 `stages`、`qualities`、`entry_conditions`、`exit_degree`、`failure_degrees`；`process_pour_water.json` 用倾斜、保持、回正三阶段表达连续过程；`process_grasp_cup.json` 与 `process_serve_to_human.json` 证明抓取、搬运也可用同构结构表达。 | 当前 `demo_runtime/run_skill_cocreation.py` 仍是步骤级 MVP，已能生成任务步骤、经验、恢复、技能包；RELL schema 将该步骤级执行提升为阶段级过程定义，是现有 demo 的下一层精细化契约。 | 可开源 `process_necessity.schema.json` 与基础样例，用于建立过程定义标准。 | 阶段生成方法、真实机器人阶段调参、行业过程模板集合不可开源。 |
| **P-B 三层架构（必然-因果-偶然）【高保护】** | `process_necessity.schema.json` 承担必然层；`causal_chain.schema.json` 承担因果层；`contingency_binding.schema.json` 承担偶然层。`contingency_home_a.json` 与 `contingency_home_b.json` 证明同一 `pour_water` 必然过程可绑定到不同杯子、壶、传感器、阈值与偏好。 | `demo_runtime/data/*.json` 已把计划、对象、区域、规则、预算分离；`run_demo.py` 读取计划、对象、规则、预算后形成受控执行链，证明系统已有“结构定义与运行绑定分离”的工程习惯。 | 三层 schema 与最小样例可开源，作为生态接入契约。 | 三层之间的映射规则、继承策略、默认阈值推导、对象相似性映射不可开源。 |
| **P-C 因果编排而非状态匹配【高保护】** | `causal_chain.schema.json` 定义 `causal_facts`、`process_signatures.requires/produces/destroys`、`chains.nodes/edges`；`causal_chain_kitchen.json` 用 `cup_in_gripper -> cup_kettle_aligned -> cup_has_water -> task_completed` 形成因果图；`execution_plan_kitchen.json` 将因果依赖展开为可执行序列与并行组。 | `run_demo.py` 的 `run_pipeline()` 已形成“计划预验真 -> 动作声明 -> 来源链校验 -> 预算 -> 裁决 -> 执行 -> 经验 -> 审计”的链式执行证据；但它尚未实现 RELL 因果图搜索。 | 因果事实注册格式、过程签名格式、样例因果图可开源。 | 因果搜索算法、多路径优化、并行分支判定、替代过程选择、链断裂补救入口推导不可开源。 |
| P-D 结构化恢复：恢复作为一等过程 | `process_necessity.schema.json` 将 `failure_degrees.recovery` 定义为结构化对象，含 `strategy`、`recovery_process_ref`、`recovery_injection_point`；`process_pour_water.json` 中 `check_kettle_water_or_unblock`、`wipe_spill`、`regrasp_object`、`unblock_spout` 是恢复过程引用。 | `run_skill_cocreation.py` 的 `build_recovery_records()` 已把失败经验转成 `recovery_records.json`；`build_skill_package()` 将 `recovery_refs` 写入技能包步骤，证明恢复记录可以进入技能沉淀链。 | 恢复字段结构、恢复记录 schema 可开源。 | 恢复过程库内容、恢复过程选择算法、行业故障处置模板不可开源。 |
| **P-E 过程模板 + 偶然参数化【高保护】** | `process_necessity.schema.json` 定义 `is_template` 与 `template_parameters`；`contingency_binding.schema.json` 定义 `template_instance.parameter_bindings`；`execution_plan_kitchen.json` 在 `grasp_cup_1`、`grasp_kettle_1` 中使用 `template_bindings` 绑定对象、手爪、力阈值。 | 当前 demo 的 `build_task_plan()` 仍生成具体步骤；RELL schema 已把“具体步骤”提升为“模板实例化”的证据。经验库规模控制的代码侧落点将从技能包 `steps` 演进到过程模板库 + 偶然绑定。 | 仅开源模板字段定义与少量低风险示例，让外部知道如何声明模板。 | 模板参数推断算法、缺省参数生成、物体相似性到参数槽的映射表、行业过程模板库必须闭源。 |
| P-F 双通道状态重建：“世界就是状态存储” | `fact_observation.schema.json` 定义 `dual_channel`、`digital`、`physical`、`cross_validation`、`accumulation_rule`；`fact_observation_kitchen.json` 用 `cup_in_gripper`、`cup_has_water`、`cup_at_human_location` 证明数字通道和物理通道可独立确认同一事实；`engine_contract.schema.json` 的 `interruption_resumption.resume_strategy=reobserve_and_match` 明确不依赖内部断点。 | 现有 demo 暂无真实传感器闭环，但 `run_demo.py` 的输出证据全部可重建审计链；RELL 新 schema 补上物理执行中断后的状态重建契约。 | 双通道事实观测结构与中断恢复协议可开源，这是对外差异化卖点。 | 真实通道融合参数、视觉/力觉仲裁模型、机器人硬件适配细节可按商业项目闭源。 |
| **P-G 引擎-治理协程架构【高保护】** | `engine_contract.schema.json` 定义 15 个引擎状态、`monitoring_loop`、`execution_plan_schema`、`engine_inputs/outputs`；RELL 纪要明确治理层不是下层安全模块，而是引擎状态推进时的并行裁决协程。 | `run_demo.py` 已有 `plan_precheck()`、`verify_source_chain()`、`evaluate_budget()`、`issue_decision()`、`execute_action()`；`技术库/代码-技术对应证据链.md` 已把这些函数对应到计划预适配、来源链、代理权预算、代理权边界治理和审计摘要。 | 可开源引擎状态机、最小接口字段、恒放行或简化治理适配器。 | 治理规则引擎配置、裁决映射表、预算公式、物理安全包络线、Sayfos SDK 商业策略不可开源。 |
| P-H 因果事实观测模型 | `fact_observation.schema.json` 把因果事实和观测方法绑定；支持双通道、单通道、执行验真、证伪失败、完成证实、恢复事实标记；`fact_observation_kitchen.json` 证明 `kettle_has_water` 可由执行过程证实/证伪，而非必须预先静态观测。 | 当前 `demo_runtime/output/*` 已把输入、执行结果和审计输出固化为 JSON 证据；事实观测 schema 是下一步将物理观测纳入同一证据链的契约。 | 事实观测 schema 与样例可开源。 | 通道置信度计算、冲突仲裁优化、视觉模型和传感器标定数据可闭源。 |
| P-I LLM 只做翻译层 | `task_intent.schema.json` 定义 `human_utterance`、`goal_fact`、`constraints`、`context`、`preferences_ref`、`llm_audit`；`task_intent_pour_water.json` 把“给客人倒一杯水端过去”翻译成 `goal_fact=task_completed`，并记录歧义与未知声明。 | `run_skill_cocreation.py` 的 `build_task_plan()` 已将场景目标转为步骤；RELL 将 LLM 前置为纯结构化意图翻译，后续规划交给确定性因果编排。 | `task_intent.schema.json` 可全部开源，属于生态输入格式。 | 面向私有客户的提示词、意图消歧策略、领域语义词库可闭源。 |

---

## 三、高保护优先级清单

### 1. P-E：过程模板 + 偶然参数化

**保护原因**：这是经验库规模上限可控的根本机制。若公开模板参数推断、默认参数生成和相似性映射，竞争者可复刻“一个过程模板 + N 个偶然绑定”的经验压缩路径。

**证据链**：
- 输入证据：`process_necessity.schema.json` 的 `is_template`、`template_parameters`；`contingency_binding.schema.json` 的 `template_instance.parameter_bindings`。
- 输出证据：`execution_plan_kitchen.json` 的 `template_bindings`。
- 当前代码承接：`run_skill_cocreation.py` 的 `skill_package.steps` 和 `evidence.experience_refs`，后续可演进为模板实例化后的技能包。
- 开源边界：字段公开，参数推理逻辑不公开。
- 闭源保护点：模板库、参数推断、物体相似性映射、缺省阈值生成。

### 2. P-G：引擎-治理协程架构

**保护原因**：这是 RELL 与 Sayfos 治理价值的交汇点。若把治理决策树、预算公式和物理安全包络线公开，会削弱商业治理层的不可替代性。

**证据链**：
- 输入证据：`engine_contract.schema.json` 的状态机、`monitoring_loop`、`engine_inputs`、`engine_outputs`。
- 输出证据：`demo_runtime/output/precheck.json`、`source_chains.json`、`budget_decisions.json`、`decision_tokens.json`、`audit_summary.json`。
- 当前代码承接：`run_demo.py` 的 `plan_precheck()`、`verify_source_chain()`、`evaluate_budget()`、`issue_decision()`、`execute_action()`。
- 开源边界：引擎状态机和接口格式公开；裁决逻辑以 mock、恒放行或极简示例呈现。
- 闭源保护点：治理规则配置、裁决映射表、预算消耗公式、来源链评分、物理因果验真安全包络线。

### 3. P-C：因果编排算法

**保护原因**：schema 可以让生态声明事实和过程签名，但真正的壁垒是从目标事实反推过程图、做多路径优化、并行分支与恢复入口选择。

**证据链**：
- 输入证据：`causal_chain.schema.json` 的 `requires`、`produces`、`destroys`。
- 输出证据：`causal_chain_kitchen.json` 的节点和边；`execution_plan_kitchen.json` 的 `causal_dependencies`、`parallel_groups`、`critical_path`。
- 当前代码承接：`run_demo.py` 已有顺序执行链，后续 RELL 引擎替换为因果图编排。
- 开源边界：因果事实和签名格式公开。
- 闭源保护点：因果图搜索、多路径优化、资源冲突调度、链断裂诊断与修复策略。

### 4. P-B：三层架构映射规则

**保护原因**：三层结构本身可以公开，但“必然过程如何被偶然层自动填充并进入因果层”是泛化能力的核心。

**证据链**：
- 输入证据：`process_necessity.schema.json`、`causal_chain.schema.json`、`contingency_binding.schema.json`。
- 输出证据：`contingency_home_a.json` 与 `contingency_home_b.json` 对同一过程给出不同传感器、阈值、对象和偏好绑定。
- 当前代码承接：`run_demo.py` 对计划、对象、规则、预算做分离读取和运行组合，证明代码层已具备“定义与绑定分离”的底座。
- 开源边界：三层 schema 与少量静态示例公开。
- 闭源保护点：继承规则、参数覆盖优先级、默认值推导、对象相似性映射、跨环境自动适配策略。

### 5. 经验库 / 恢复过程库

**保护原因**：经验库和恢复过程库是长期积累资产。schema 开源后，真实行业经验、恢复过程、技能包仍应作为商业数据和服务能力保护。

**证据链**：
- 输入证据：`experience_record.schema.json`、`recovery_record.schema.json`、`skill_package.schema.json`，以及 RELL 新增 `process_necessity.schema.json` 的 `failure_degrees.recovery`。
- 输出证据：`demo_runtime/output/skill_cocreation/experience_records.json`、`recovery_records.json`、`skill_package.json`、`skill_audit.json`。
- 当前代码承接：`run_skill_cocreation.py` 的 `build_experience()`、`build_recovery_records()`、`build_skill_package()`、`build_skill_audit()`。
- 开源边界：记录格式、最小 toy 示例、验证脚本公开。
- 闭源保护点：行业真实经验库、恢复过程库、种子技能包、高价值场景偶然绑定、评估结果。

---

## 四、schema 与样例对应表

| 文件 | 承担层级 | 关键证据 |
|---|---|---|
| `schemas/process_necessity.schema.json` | 必然层 / 过程模板 | 阶段序列、质变量、度条件、失败度、结构化恢复、模板参数。 |
| `schemas/causal_chain.schema.json` | 因果层 | 因果事实、过程因果签名、资源声明、因果图节点和边、并行组。 |
| `schemas/contingency_binding.schema.json` | 偶然层 | 传感器绑定、通道标签、交叉验证对、阈值覆写、对象映射、偏好附着。 |
| `schemas/fact_observation.schema.json` | 事实观测层 | 双通道 / 单通道 / 执行验真、累积规则、证伪失败、完成证实。 |
| `schemas/engine_contract.schema.json` | 引擎契约 | 15 状态状态机、执行计划、监控循环、中断恢复、输入输出。 |
| `schemas/task_intent.schema.json` | LLM 翻译层 | 自然语言到目标因果事实、约束、上下文、偏好引用和审计记录。 |
| `schemas/examples/process_pour_water.json` | 过程样例 | 倾斜、保持、回正三阶段；偏好阈值；恢复过程引用。 |
| `schemas/examples/process_grasp_cup.json` | 过程样例 | 抓取力、位移、接触、抬升稳定性，证明非倒水过程也同构。 |
| `schemas/examples/process_serve_to_human.json` | 过程样例 | 搬运、碰撞风险、呈现释放，证明复合物理任务可阶段化。 |
| `schemas/examples/causal_chain_kitchen.json` | 因果样例 | 倒水任务的因果事实、过程签名、节点和边。 |
| `schemas/examples/contingency_home_a.json` | 偶然样例 | 家庭 A 的马克杯、不锈钢壶、传感器与“倒满”偏好。 |
| `schemas/examples/contingency_home_b.json` | 偶然样例 | 家庭 B 的高脚玻璃杯、玻璃壶、更严阈值与“八分满”偏好。 |
| `schemas/examples/fact_observation_kitchen.json` | 观测样例 | `cup_in_gripper`、`cup_has_water` 等事实的双通道验证。 |
| `schemas/examples/task_intent_pour_water.json` | 意图样例 | LLM 只输出 `task_completed` 目标事实、约束、上下文和歧义审计。 |
| `schemas/examples/execution_plan_kitchen.json` | 引擎输出样例 | 因果依赖展开、并行抓取、资源占用、验证检查点、恢复计划。 |

---

## 五、当前代码证据对应表

| 代码 / 输出 | 证明点 | 对应支柱 |
|---|---|---|
| `demo_runtime/run_demo.py -> plan_precheck()` | 执行前边界预验真，证明治理可在计划阶段介入。 | P-G |
| `demo_runtime/run_demo.py -> verify_source_chain()` | 来源链完整性验证，证明执行准入不是单纯动作调用。 | P-G |
| `demo_runtime/run_demo.py -> evaluate_budget()` | 预算扣减和拒绝逻辑，证明代理权预算可进入运行链。 | P-G |
| `demo_runtime/run_demo.py -> issue_decision()` | 多源治理结果合并为裁决令牌。 | P-G |
| `demo_runtime/run_demo.py -> execute_action()` | 正式执行、候选态、阻断三种执行模式。 | P-G / 经验库 |
| `demo_runtime/run_demo.py -> experiences append` | 每步生成经验记录，含动作、结果、裁决引用。 | 经验库 / P-D |
| `demo_runtime/run_skill_cocreation.py -> build_recovery_records()` | 失败经验生成结构化恢复记录。 | P-D / 恢复过程库 |
| `demo_runtime/run_skill_cocreation.py -> build_skill_package()` | 经验、恢复、偏好进入技能包沉淀。 | 经验库 / P-E |
| `demo_runtime/run_skill_cocreation.py -> build_skill_audit()` | 任务、经验、恢复、偏好、技能包进入审计报告。 | P-G / 经验库 |
| `demo_runtime/api_server.py -> /experience/record` | 外部经验写入 API 雏形。 | 经验库 |
| `demo_runtime/output/*.json` | 运行后可核验输出：预验真、来源链、预算、裁决、候选动作、经验、审计。 | P-G / 经验库 |
| `demo_runtime/output/skill_cocreation/*.json` | 技能共创输出：任务计划、训练会话、经验、恢复、偏好、概念、技能包、审计。 | P-D / 经验库 |

---

## 六、公开边界建议

### 可公开

1. `schemas/*.schema.json` 的数据契约。
2. `schemas/examples/*.json` 的低风险 toy 示例。
3. `demo_runtime/` 的最小闭环，保持治理逻辑为示意级或 mock 级。
4. JSON 语法校验、schema 格式校验、示例运行脚本。
5. 对外叙事：RELL 是真实世界经验闭环的数据格式和最小运行时入口。

### 不公开

1. 因果编排搜索算法与优化策略。
2. 三层架构映射规则、参数继承、默认阈值推导。
3. 过程模板库与模板参数推断。
4. 治理裁决映射表、预算公式、来源链评分、物理安全包络线。
5. 行业真实经验库、恢复过程库、高价值技能包、场景偶然绑定。

---

## 七、校验记录

已修复以下 JSON 语法问题：

1. `schemas/fact_observation.schema.json`：description 中的 `"问世界"` 改为中文单引号 `‘问世界’`。
2. `schemas/examples/fact_observation_kitchen.json`：description 中的 `"水倒到哪了"` 改为中文单引号 `‘水倒到哪了’`。

校验命令：

```powershell
Get-ChildItem .\schemas\*.schema.json, .\schemas\examples\*.json | ForEach-Object { Get-Content -Raw -Encoding UTF8 $_.FullName | ConvertFrom-Json | Out-Null; Write-Output "OK $($_.Name)" }
```

预期结论：所有 schema 与样例通过 JSON 语法解析。注意：该命令只校验 JSON 语法，不校验样例是否完全符合对应 JSON Schema。

---

## 八、提交摘要建议

技术对应：
- 对应技术层：RELL 必然层 / 因果层 / 偶然层 / 事实观测层 / 引擎契约 / LLM 翻译层 / 经验库与恢复过程库。
- 对应专利/技术链特征：过程混合自动机、三层架构、因果编排、结构化恢复、过程模板参数化、双通道状态重建、引擎-治理协程、因果事实观测、LLM 翻译层。
- 对应文档或代码模块：`schemas/*.schema.json`、`schemas/examples/*.json`、`demo_runtime/run_demo.py`、`demo_runtime/run_skill_cocreation.py`、`技术库/代码-技术对应证据链.md`。

证据链：
- 输入证据：RELL 架构迭代纪要、新增 schema、厨房任务样例、现有 demo 输入数据。
- 输出证据：本证据链文档、JSON 语法校验结果、demo 运行输出中的经验 / 恢复 / 技能包 / 治理审计文件。
- 验证方式：PowerShell `ConvertFrom-Json` 校验；`python .\demo_runtime\run_demo.py`；`python .\demo_runtime\run_skill_cocreation.py`。
- 公开边界：schema 和 toy demo 可开源；算法、治理逻辑、经验库、恢复过程库、行业模板闭源。
