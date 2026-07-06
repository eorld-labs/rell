# RELL 真实世界经验引擎证据链

> 内部文档，不进入当前 Git 仓库提交。
> 来源纪要：`研发记录/讨论纪要/RELL-真实世界经验引擎-核心讨论纪要.md`
> 记录日期：2026-07-06

## 一、证据链定位

本文件用于把 2026-07-06 形成的 RELL 核心讨论结果，整理为可追溯的内部技术证据链。

本文件不是对外开源说明，也不是公开论文草稿，而是用于内部研发、专利文本支撑、后续代码实现规划、审查答复和合作尽调准备的证据索引。

核心链路：

> 讨论结论 -> 技术特征 -> 工程对象 -> 当前代码/Schema 入口 -> 输出证据 -> 后续补证任务

## 二、来源材料固定

| 项 | 内容 |
|---|---|
| 来源文件 | `研发记录/讨论纪要/RELL-真实世界经验引擎-核心讨论纪要.md` |
| 来源主题 | 真实世界经验引擎核心讨论纪要 |
| 项目名称 | RELL（Real-world Experience Learning Loop） |
| 讨论主线 | 机器人如何通过真实交互经验在物理世界中学习与执行 |
| 形成日期 | 2026-07-06 |
| SHA256 | `1D221CCC6EF8E91441C6E603104ADBDBE3E896D881B3F6B5DD4A1DB58B3E7DD7` |

## 三、总技术判断

RELL 的核心定位不是机器人本体、不是 VLA 大模型、不是世界大模型，也不是仿真训练平台。

RELL 的定位是：

> 面向真实物理场景的经验学习与执行引擎，通过过程经验、质-量-度阶段描述、实时感知-动作闭环、双通道验真和技能包生态，让机器人在真实世界中快速形成可复用能力。

它与主流路线的关键差异为：

1. 不试图把完整物理世界压缩进模型。
2. 不把 LLM 作为物理推理与后果预测主体。
3. 不依赖离线仿真穷举所有可能。
4. 不以端到端黑箱策略作为主要能力载体。
5. 把物理世界本身作为状态存储和反馈源。
6. 把真实执行经验沉淀为可审计、可复用、可分发的结构化过程。

## 四、核心技术特征总表

| 编号 | 技术特征 | 讨论结论 | 当前证据状态 | 对应项目技术链 |
|---|---|---|---|---|
| RELL-E01 | LLM 语义翻译层 | LLM 只做人类语言到结构化机器指令的翻译，不承担物理推理、规划和后果预测 | 已有 `task_plan.schema.json` 和任务计划输出雏形 | P013 任务语义翻译 |
| RELL-E02 | 真实世界经验引擎 | 结构化机器指令进入经验引擎，由经验检索、过程执行、补救和偏好形成闭环 | 已有 `run_skill_cocreation.py` MVP 闭环 | P011-P015 |
| RELL-E03 | 世界就是状态存储 | 不序列化全部状态，恢复时重新观察真实世界 | 已有 P014 补救记录雏形，缺少真实传感状态恢复实现 | P014 执行恢复 |
| RELL-E04 | 过程而非原子技能 | 存储完整意图下的过程，而不是离散动作碎片 | 已有 `skill_package.schema.json`，缺少过程级 schema | P012、P013 |
| RELL-E05 | 质-量-度过程描述 | 用变量类型、数值范围、阶段触发边界描述过程 | 当前为讨论结论，需新增 `process.schema.json` 与 `degree_condition` | P011、P012、P014 |
| RELL-E06 | 意图状态机与实际状态机 | 执行中持续比较期望状态和实际状态 | 当前为讨论结论，需新增状态机与对齐日志 | P014、物理执行链路验真 |
| RELL-E07 | 双通道验真 | 数字通道与视觉/物理通道交叉验证实际状态 | 已有治理层“物理执行链路验真”文本，缺少 demo 实现 | 物理执行链路验真 |
| RELL-E08 | 感知-动作闭环内置 | 闭环是执行引擎能力，不是经验库内容 | 当前为架构结论，需在运行时引擎实现 | P011、P014 |
| RELL-E09 | 中断恢复不依赖断点续传 | 中断后重新观察世界，按度条件匹配阶段入口 | 当前为讨论结论，需补恢复匹配 demo | P014 执行恢复 |
| RELL-E10 | 只存最优解 | 失败用于收敛，经验库只保留最优过程 | 当前为策略结论，需补经验版本与淘汰机制 | P011、P012 |
| RELL-E11 | 技能包生态 | 经验库可打包为厨房包、客厅包等可下载技能包 | 已有 `skill_package.schema.json` 和输出样例 | P012、P013、商业闭环 |
| RELL-E12 | 主动声明未知 | 系统可识别当前场景不在经验覆盖范围内 | 当前为讨论结论，需补 coverage/evidence 检索机制 | P011、P012、P014 |

## 五、专利文本逻辑映射

### 5.1 P010 空间语义自动生成

对应讨论点：

1. 空间语义生成与内化。
2. 房间、区域、对象、属性和关系构成场景理解入口。
3. 技能包在具体空间内运行，需要先形成空间语义上下文。

当前代码/Schema 入口：

```text
schemas/space_object.schema.json
schemas/scenario.schema.json
demo_runtime/skill_data/scenario.json
demo_runtime/output/skill_cocreation/scenario_context.json
```

当前证据状态：

已有场景输入与空间语义对象雏形，但尚未实现从真实视觉/传感输入自动生成空间语义的过程。

后续补证任务：

1. 增加 `space_observation.schema.json`。
2. 增加从观察记录到 `scenario_context` 的转换 demo。
3. 生成“空间观察 -> 语义对象 -> 任务约束”的输出证据。

### 5.2 P011 物理经验内化机制

对应讨论点：

1. 经验不是抽象文本，而是 `{情境, 动作/过程, 后果}`。
2. 真实世界经验由在线执行产生。
3. 失败的意义在于收敛到最优过程。
4. 每个过程形成可复用经验。

当前代码/Schema 入口：

```text
schemas/experience_record.schema.json
demo_runtime/run_demo.py
demo_runtime/run_skill_cocreation.py
demo_runtime/output/experience_records.json
demo_runtime/output/skill_cocreation/experience_records.json
```

当前证据状态：

已有经验记录 schema 与输出证据，能够证明经验记录链路已跑通。尚缺过程级“质-量-度”字段。

后续补证任务：

1. 增加 `process_experience.schema.json`。
2. 将经验记录从动作级升级为过程级。
3. 补充“最优过程版本号、淘汰原因、适用情境范围”。

### 5.3 P012 概念归纳跨域迁移

对应讨论点：

1. 概念归纳不是跨所有机器人本体泛化，而是在限定场景内抽取可复用过程模式。
2. 技能包是经验归纳后的分发单元。
3. 同类过程可通过调节“度”的阈值适配不同偏好。

当前代码/Schema 入口：

```text
schemas/concept_pattern.schema.json
schemas/skill_package.schema.json
demo_runtime/output/skill_cocreation/concept_patterns.json
demo_runtime/output/skill_cocreation/skill_package.json
```

当前证据状态：

已有概念模式和技能包输出雏形。尚缺将多个真实经验归纳为同一过程模式的算法证据。

后续补证任务：

1. 增加多条过程经验样例。
2. 增加概念归纳 eval。
3. 验证不同任务共享同一过程模板但参数阈值不同。

### 5.4 P013 任务语义翻译

对应讨论点：

1. LLM 只做人类语言到结构化机器指令的翻译。
2. LLM 不参与物理后果预测。
3. 结构化机器指令进入 RELL 经验引擎。

当前代码/Schema 入口：

```text
schemas/task_plan.schema.json
demo_runtime/output/skill_cocreation/task_plan.json
demo_runtime/api_server.py
```

当前证据状态：

已有任务计划对象和输出雏形。尚缺“自然语言输入 -> 结构化任务计划”的可运行翻译接口。

后续补证任务：

1. 增加 `instruction_translation.schema.json`。
2. 增加 LLM 翻译层 mock 或可替换接口。
3. 明确翻译层输出不包含物理预测字段。

### 5.5 P014 执行恢复

对应讨论点：

1. 中断后不做断点续传。
2. 重新观察世界状态。
3. 按过程阶段的“度”条件匹配当前阶段入口。
4. 从匹配阶段继续执行。

当前代码/Schema 入口：

```text
schemas/recovery_record.schema.json
demo_runtime/run_skill_cocreation.py
demo_runtime/output/skill_cocreation/recovery_records.json
```

当前证据状态：

已有补救记录输出，但尚未实现“重新观察世界 -> 匹配度条件 -> 恢复阶段”的完整 demo。

后续补证任务：

1. 增加 `world_observation.schema.json`。
2. 增加 `degree_condition.schema.json`。
3. 增加 `match_recovery_stage()` demo。
4. 输出 `recovery_stage_match.json`。

### 5.6 P015 人类偏好

对应讨论点：

1. 人类偏好可作用于过程阈值。
2. “倒八分满”和“倒满”不需要新技能，只需调整度的阈值。
3. 偏好不应破坏过程结构，而是改变参数边界。

当前代码/Schema 入口：

```text
schemas/preference_record.schema.json
demo_runtime/run_skill_cocreation.py
demo_runtime/output/skill_cocreation/preference_records.json
```

当前证据状态：

已有偏好记录输出。尚缺偏好对 `degree_condition` 的参数化影响证据。

后续补证任务：

1. 增加偏好到阶段阈值的映射 demo。
2. 输出 `preference_applied_process.json`。
3. 验证同一过程在不同偏好下生成不同结束阈值。

## 六、与运行时治理技术的映射

| 治理技术 | RELL 对应点 | 当前证据 | 后续补证 |
|---|---|---|---|
| 代理权边界治理 | 机器人执行真实动作前必须判断是否越界 | `decision_tokens.json` | 接入真实动作风险分级 |
| 来源链 | 人类指令、任务翻译、技能包来源都需要可追溯 | `source_chains.json` | 给技能包增加来源链字段 |
| 代理权预算 | 动作、恢复、人工接管可消耗预算 | `budget_decisions.json` | 增加技能执行预算 |
| 计划预适配 | 结构化任务计划执行前预验真 | `precheck.json` | 接入任务计划和过程图 |
| 物理执行链路验真 | 数字通道与物理通道双通道验真 | 技术文本已有 | 增加双通道状态对齐 demo |
| 保护策略声明 | 人、物、空间的安全边界声明 | 技术文本已有 | 增加场景级保护策略样例 |

## 七、当前代码证据与讨论结论的覆盖关系

### 7.1 已有较强代码证据

1. 经验记录：`experience_records.json`。
2. 任务计划：`task_plan.json`。
3. 补救记录：`recovery_records.json`。
4. 偏好记录：`preference_records.json`。
5. 概念模式：`concept_patterns.json`。
6. 技能包：`skill_package.json`。
7. 审计报告：`skill_audit.json`。

### 7.2 已有雏形但需要加强

1. LLM 翻译层：目前有任务计划对象，缺少自然语言翻译入口。
2. 技能包生态：目前有单个技能包输出，缺少安装、版本、来源和依赖机制。
3. 过程式经验：目前更偏步骤级经验，缺少过程级状态机结构。
4. 执行恢复：目前有补救记录，缺少按真实观察状态恢复的 demo。

### 7.3 尚需新增工程对象

建议新增以下 schema 和最小 demo：

```text
schemas/process.schema.json
schemas/degree_condition.schema.json
schemas/world_observation.schema.json
schemas/state_alignment.schema.json
schemas/skill_package_manifest.schema.json
demo_runtime/run_rell_process_demo.py
demo_runtime/output/rell_process/
```

## 八、第一批代码补证建议

第一批不要做重型机器人接入，先做可审计的过程引擎最小闭环。

建议顺序：

1. 定义 `process.schema.json`：描述过程、阶段、质、量、度、出口条件。
2. 定义 `world_observation.schema.json`：描述当前真实世界观察状态。
3. 实现 `run_rell_process_demo.py`：以“倒水”作为第一个过程样例。
4. 输出 `process_instance.json`：证明过程不是原子动作。
5. 输出 `state_alignment.json`：证明意图状态机与实际状态机可对齐。
6. 输出 `recovery_stage_match.json`：证明中断后可按度条件恢复。
7. 输出 `preference_applied_process.json`：证明偏好可调节度阈值。
8. 更新内部证据链，不进入公开 GitHub。

## 九、公开与私有边界

这份纪要及本证据链包含项目路线判断、核心工程抓手、专利文本映射和后续补证顺序，不适合直接公开。

对外可公开：

1. RELL 是真实世界经验学习闭环。
2. 项目提供 schema、demo 和技能包格式。
3. 项目关注真实场景经验复用。
4. 开发者可以贡献技能包和场景样例。

不宜公开：

1. “世界就是状态存储”的完整攻防逻辑。
2. “质-量-度”与权利要求之间的精确映射。
3. P010-P015 的逐项技术对应。
4. 运行时治理与 RELL 的组合保护路径。
5. 后续补证顺序和专利申诉策略。

## 十、私有 Git 仓库建议

建议建立一个独立的 Gitee 私有仓库，用于存放内部讨论纪要、证据链、哈希清单和审查/申诉材料。

建议名称：

```text
rell-evidence-vault
```

建议该仓库与当前代码仓库分离：

1. 当前 `worldmodels` 仓库继续保留代码、公开白名单、工程文档和可提交研发记录。
2. `rell-evidence-vault` 只保留敏感内部证据材料。
3. 不设置 GitHub remote。
4. 不给外部合作方访问权限。
5. 对合作方只输出脱敏 PDF 或 NDA 材料包。

如果短期不建私有仓库，至少应做到：

1. 当前 `研发记录/讨论纪要/` 不进入 Git。
2. 定期生成 SHA256 哈希清单。
3. 关键版本做加密备份。
4. 需要时使用可信时间戳或电子数据存证。

## 十一、结论

2026-07-06 的讨论已经形成 RELL 的核心技术轮廓：

> LLM 翻译层 + 真实世界经验引擎 + 过程式经验 + 质-量-度阶段条件 + 双通道验真 + 中断恢复 + 偏好阈值调节 + 技能包生态。

当前项目已有 P010-P015 的部分 schema、demo 和输出证据，可以支撑第一阶段“经验世界模型闭环”的实施存在性。

下一步最关键的补证对象不是机器人本体，而是：

> 过程级经验 schema 与“质-量-度”驱动的最小可运行 demo。

只要该 demo 跑通，RELL 就能从讨论纪要进入可复现、可审计、可提交的工程证据阶段。
