# RCIR 阶段 A/B 工程证据

日期：2026-07-20

## 一、范围

本证据对应统一认知架构的两个工程阶段：

- 阶段 A：共同技术骨架固化；
- 阶段 B：认识目标生成、证据获取、验真和关闭。

验证入口：

```powershell
python demo_runtime/rell_sample/validate_rcir_stage_a_b.py
```

## 二、七类基本类型

| 类型 | 正式 Schema | 权威边界 |
|---|---|---|
| `Concept` | `schemas/rcir_concept.schema.json` | 只提供分类和预测，不取得执行权 |
| `EntityRef` | `schemas/rcir_entity_ref.schema.json` | 身份由实例锚点和连续性保持，不由显示名决定 |
| `Predicate` | `schemas/rcir_predicate.schema.json` | 候选、目标与事实共用同一谓词 ID |
| `Event` | `schemas/rcir_event.schema.json` | 验真事件引用产出谓词和同一证据 |
| `Goal` | `schemas/rcir_goal.schema.json` | 只引用目标谓词，不直接控制执行器 |
| `Constraint` | `schemas/rcir_constraint.schema.json` | 受作用域、证据和世界版本约束 |
| `EvidenceEnvelope` | `schemas/rcir_evidence_envelope.schema.json` | 只有合格信封可以晋级执行事实 |

机器可读关系表为 `schemas/rcir_type_relations.json`。它明确禁止概念直接提交事实、人类报告或感知候选直接提交事实、目标直接控制执行器，以及 Inquiry 建立第二事实账本。

## 三、阶段 A 回归证据

### 3.1 EntityRef 连续性

同一对象以持久实例锚点注册后，依次经过：

```text
登记名称变更 -> 中文别名 -> 视觉轨迹 -> 触觉确认
库存阶段 -> 获取阶段 -> 处理阶段 -> 交接阶段
```

四次落地结果均为 `entity_stable_vessel_17`，身份变化次数为 0。别名和模态只增加证据收据，不生成新实例。

### 3.2 证据晋级门

`human_report`、`perception_candidate` 以及缺失信封三种输入均不能调用 `establish_predicate`。只有满足以下条件的证据可以晋级：

```text
source = p016_physical_verification
epistemic_status = physically_verified
current_world_bound = true
verifier = P016
```

现有 `WorldFactLedger` 已使用相同适配器。候选输入仍可进入证据列表，但不会进入 `authoritative_current_fact_ids`。

### 3.3 世界版本局部失效

世界版本从 8 变为 9 且 `entity_changed` 变化后，依赖链中的：

```text
EvidenceEnvelope -> Predicate -> Goal -> Constraint -> InquiryContract
```

按引用传播失效。依赖 `entity_unrelated` 的安全约束继续保持 `active`，证明失效是局部传播而不是全局清空。

### 3.4 规划与解释同源

P016 验真事件写回后，规划读取面和反向解释读取面返回完全相同的：

- `Event` 引用；
- `Predicate` 引用；
- `EvidenceEnvelope` 引用；
- `fact_authority_ref`。

### 3.5 无第二事实源和控制旁路

恢复、经验召回和认识目标合同统一声明：

```text
fact_authority_ref = WorldFactLedger 实例
control_gateway = P018
verification_gateway = P016
direct_execution_allowed = false
```

测试将恢复合同的控制网关替换为直接执行器后，`assert_shared_authority_contract` 必须拒绝。

## 四、阶段 B 三个闭环

三类输入首先通过同一个 `adapt_cognitive_signal` 适配为 `diagnostic_signal`。适配器拒绝携带 `conclusion` 或 `selected_hypothesis` 的异常信号；`generate_competing_hypotheses` 拒绝单一假设，因此信号只能触发认识目标，不能直接提交解释。

### 4.1 质量档案漂移

```text
历史均值 0.72 / 当前均值 0.51
  -> 三个竞争假设
  -> P018 授权多视角视觉与触觉主动观察
  -> 两个独立模态形成合格 EvidenceEnvelope
  -> 选择 object_surface_condition_changed
  -> 同一账本提交质量状态谓词
  -> Inquiry closed
```

异常信号本身未提交“磨损”结论。

### 4.2 重复恢复异常

```text
8 次窗口内 5 次同类 no_source_flow
  -> 模板流量边界、环境干扰、流量观测通道三个假设
  -> P018 授权在已验真稳定水源条件下安全复做
  -> 仓库现有 P016Runtime 双通道验真 cup_has_water=established
  -> 写回 template_requires_stable_source_flow
  -> Inquiry closed
```

恢复计数只触发认识目标，模板边界由安全试验和 P016 验真确定。

### 4.3 未解释重复模式

三个历史事件形成候选概念，但候选保持 `execution_authority=false`。系统在未见实例上执行经 P018 授权的安全探测：

- 预测被 P016 证实时，候选从 `validating` 进入 `trusted`；
- 预测被 P016 否证时，候选进入 `rejected`；
- 两条路径均保留新实例证据和回退关系。

## 五、当前边界

本阶段证明共同类型、证据权限和认识目标闭环已经可执行，不表示所有旧模块已经迁移完毕。旧 API、视觉概念库和部分任务结构仍有自己的兼容字段；后续迁移标准是这些模块逐步只交换七类原语引用，并继续由同一事实账本、P018 和 P016 约束。

## 六、具身服务接入

阶段 B 已接入具身会话和 `/embodied` 页面。每次运行前，服务按当前 `runtime_objects`、本体状态和 `world_revision` 重建会话的 `WorldFactLedger`，再将其 `ledger_id` 注入 `CognitiveAuthorityLedger`。认识闭环不创建自己的事实权威。

服务入口：

- `GET /cognitive/inquiry/catalog`：列出质量漂移、恢复边界、概念晋级和概念否决四个闭环；
- `POST /cognitive/inquiry/run`：在指定具身会话的当前世界版本上运行闭环。

响应同时返回：

- 竞争假设、选择结果和 Inquiry 状态迁移；
- P018 仲裁收据与 P016 验真引用；
- 同一个 `Event`、`Predicate`、`EvidenceEnvelope` 引用；
- 规划读取面与反向解释读取面的同源断言；
- `direct_execution_allowed=false` 和 `runtime_fact_committed_by_inquiry=false`。

认识结果作为同一账本的诊断扩展及会话审计历史保存，不成为第二事实源，也不直接改变具身运行时物理事实。恢复边界闭环通过真实 `run_simulated_runtime_sample(..., "simulated_success")` 获得 P016 双通道验真结果，而不是使用静态成功样本。

服务级回归：

```powershell
python .\demo_runtime\rell_sample\validate_cognitive_inquiry_api.py
```
