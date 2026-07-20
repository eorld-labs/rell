# RCIR 最小统一认知架构工程证据链

日期：2026-07-20

## 一、目的

本记录对应《RELL“书同文、车同轨、度量衡”统一认知架构-v1》的最小代码实现，用于证明该架构已经进入可执行主链，而不是停留在概念说明或孤立样板代码中。

本记录只陈述技术组合、实现时间、代码位置和可复核行为，不直接判断专利法意义上的新颖性、创造性或权利稳定性。正式申请前仍需进行专利与非专利文献检索、权利要求边界设计和代理人复核。

## 二、最小技术组合

本次实现形成以下组合：

1. 每次语言组合生成一个版本化 `RCIR Bundle`；
2. 原始语言只生成 SHA-256 引用，不进入下游图结构；
3. `SituatedEventGraph` 保存概念、事件、语篇角色、目标候选和未决变量；
4. `WorldFactLedger` 保存同一世界版本下的事实、证据封装和可用状态；
5. `GroundedCausalGraph` 使用当前事实、当前感知和交互角色形成结构化实例绑定；
6. 三张结构共同写入一个权威摘要，任何下游修改都会导致摘要校验失败；
7. 现有接水意图的主题角色优先消费 RCIR 的当前世界绑定；
8. 新交互到来时，旧 Bundle 失去权威性并压缩为收据；
9. 任务完成后释放当前图，只保留不含原文、计划和轨迹的紧凑收据；
10. 所有候选继续保持 `direct_execution_allowed=false`，执行前必须进入当前事实裁剪与物理验真。

该组合的关键不在于单独使用知识图、语义解析、哈希或事实表，而在于：人类语言、当前世界事实、角色落地、因果目标、证据等级和执行生命周期通过同一版本化中间表示形成可校验闭环。

## 三、代码映射

| 技术点 | 工程落点 |
|---|---|
| RCIR Bundle 编译与校验 | `concept_core/cognitive_ir.py::compile_rcir_bundle`、`validate_rcir_bundle` |
| 情境事件图 | `build_situated_event_graph` |
| 世界事实账本 | `build_world_fact_ledger` |
| 当前角色证据合并 | `_binding_candidates`、`_resolve_role_binding` |
| 已落地因果图 | `build_grounded_causal_graph` |
| 原句不下沉 | `source_language.utterance_ref`、`FORBIDDEN_DOWNSTREAM_TEXT_KEYS` |
| 权威性防篡改 | `authority_digest`、`authority_digest_mismatch` |
| RCIR 进入主链 | `embodied_scene.py::_resolve_current_role_binding` |
| 单轮唯一权威图 | `session.current_rcir` 与 `superseded_by_new_authoritative_turn` |
| 任务完成后释放 | `compact_rcir_receipt`、`_archive_and_release_task_context` |
| 正式数据契约 | `schemas/rcir_bundle.schema.json` |
| 独立回归 | `validate_cognitive_ir.py` |

## 四、权威边界

### 4.1 语言边界

RCIR 中不允许出现以下原始语言字段：

- `utterance`；
- `normalized_utterance`；
- `canonical_utterance`；
- `surface`；
- `matched_surface`；
- `label`；
- `question`。

RCIR 只保存：

```text
utterance_ref = sha256:<digest>
character_count = <length>
raw_text_included = false
```

这样可以保留来源一致性验证能力，同时防止下游规划器重新利用原始表面文本形成旁路。

### 4.2 事实边界

语言事件、报告事件和目标事实均为候选，不直接提交物理事实。当前可用事实只来自 `WorldFactLedger.authoritative_current_fact_ids`，每条事实必须绑定：

- `world_revision`；
- `evidence_ref`；
- `status`；
- `current_world_usable`。

### 4.3 执行边界

`GroundedCausalGraph` 固定声明：

```text
current_fact_pruning_required = true
direct_execution_allowed = false
runtime_fact_committed = false
```

RCIR 可以统一目标、角色和事实，但不能替代 P018 仲裁和 P016 物理验真。

## 五、可复核场景

### 5.1 同一句语言形成统一目标

输入服务请求后，RCIR 同时形成：

- `theme=mug_white`；
- `recipient=guest`；
- `goal_relation=human_received_filled_container`；
- `contains_liquid(theme, liquid)`；
- `received_by(theme, recipient)`。

语言没有直接提交上述物理事实。

### 5.2 对象改名不改变绑定

将对象显示名改为未登记名称后，语言仍通过概念约束和当前观测绑定相同 `entity_ref`。接水意图的 `role_binding_evidence.theme` 包含：

- `rcir_bundle_id`；
- `rcir_authority_digest`；
- `current_snapshot_revalidated=true`。

这证明 Runtime 已消费 RCIR，而不是仅在页面旁路展示。

### 5.3 篡改检测

复制 Bundle 后修改已落地角色的 `entity_ref`，但不重新生成权威摘要，`validate_rcir_bundle` 返回：

```text
authority_digest_mismatch
```

### 5.4 生命周期

新轮次产生后：

- 前一 Bundle 压缩为 `superseded_by_new_authoritative_turn` 收据；
- `session.current_rcir` 只指向最新 Bundle。

任务完成后：

- `session.current_rcir=null`；
- 收据不含原文、候选计划和轨迹；
- 当前物理效果继续保留在运行时世界状态中。

## 六、验证命令

```powershell
python demo_runtime/rell_sample/validate_cognitive_ir.py
python demo_runtime/rell_sample/validate_semantic_grounding_architecture.py
python demo_runtime/rell_sample/validate_context_projection.py
python demo_runtime/rell_sample/validate_situated_event_reasoning.py
python demo_runtime/rell_sample/validate_stage_zero.py
```

`validate_cognitive_ir.py` 已加入 `run_all_checks.py` 的正式回归序列。

## 七、当前未完成边界

最小实现尚未表示整个架构迁移已经完成：

1. 旧 `situated_event_frame` 和 RCIR 暂时并行存在；
2. 仅部分任务角色解析已切换为优先消费 RCIR；
3. 部分内部阶段仍通过生成语言进入旧入口；
4. 所有经验检索器、恢复器和复合任务编译器尚未全部改为只接收 RCIR；
5. 真机感知证据尚未接入 `WorldFactLedger` 的统一证据适配器；
6. 多语言等价图测试尚未建立。

后续完成标准不是“RCIR 字段出现在返回值中”，而是自然语言以下的编排、恢复、经验和执行模块不再以原始字符串作为决策输入。

## 八、证据结论

当前版本已经形成统一认知架构的最小可执行证据：

```text
语言概念图
  + 当前世界事实账本
  + 带证据的角色落地
  + 候选因果目标图
  + 权威摘要
  + 生命周期释放
  + Runtime 实际消费
```

该证据可以作为后续专利检索、技术交底、权利要求提炼和工程迭代的共同基线。

## 九、落地失败追问合同

`concept_core/rcir_contracts.py::build_grounding_clarification_contract` 从同一角色的多个当前候选中计算可区分的可观察属性，并选择最小歧义属性。`apply_grounding_constraint` 将回答编译为属性约束，只在相同 `world_revision` 上重新落地。该循环不读取显示名，也不把语言回答提交为物理事实。

真实输入“给我接一杯水”存在多个容器候选时，合同被附加到：

```text
GroundedCausalGraph.grounding_clarification_contracts.theme
```

合同包含候选 `EntityRef`、请求的观察字段、可接受值、累计约束和重新观测步骤。

## 十、可迁移经验合同

`build_portable_experience_contract` 只提取角色类型槽位、因果条件、效果、验真、终止条件和过程不变量。`load_trusted_experiences` 为旧记录补建并校验该合同，同时声明：

```text
execution_authority.source = portable_experience_contract
legacy_record_is_execution_authority = false
current_world_rebinding_required = true
```

绝对坐标、旧实例引用、关节角、固定时长、教师按键、单次轨迹和原始目标语言禁止进入合同。

## 十一、五条不变量的代码证据

| 不变量 | 强制位置 | 失败行为 |
|---|---|---|
| 语言不提交物理事实 | `assert_rcir_architecture_invariants` | 拒绝 Bundle |
| 感知候选不是运行时事实 | `assert_perception_candidate_is_not_runtime_fact` | 拒绝状态写入 |
| 下游不重解析原文 | `assert_no_surface_text_below_rcir_boundary` | 报告泄漏路径 |
| 当前验真关系优先 | `_resolve_role_binding` | 冲突时触发断言 |
| 恢复重新进入事实裁剪 | `_enter_current_fact_pruning_barrier` | 无审计令牌禁止执行 |

`validate_cognitive_ir.py` 对上述五条规则、歧义循环和经验迁移边界进行独立回归。这里证明的是已实现的工程组合和可复核行为，不直接替代专利新颖性检索、权利要求设计或法律判断。
