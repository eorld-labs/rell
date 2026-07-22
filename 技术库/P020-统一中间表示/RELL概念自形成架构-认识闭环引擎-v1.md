# RELL 概念自形成架构 — 认识闭环引擎

日期：2026-07-22

状态：架构设计稿

适用范围：P012 概念归纳跨域迁移、P019 端侧概念内化、P020 统一中间表示

---

## 一、核心命题

RELL 的概念形成不应依赖大模型提供概念候选，也不应依赖人工预设硬编码的假设和因果合同。系统应当能够：

1. **从运行时事件中自主发现重复模式**
2. **将模式提炼为可测试的概念候选**
3. **通过安全探针验证或证伪候选**
4. **将验证后的概念纳入概念空间，参与后续的模式匹配**
5. **形成一个永不停歇的自我迭代、自我进化闭环**

目标状态：**海量真实数据集进来，系统以科学方式自主完成概念的提炼、组织与进化。**

---

## 二、四层架构总览

```
┌──────────────────────────────────────────────────┐
│  认识闭环引擎 (Epistemic Loop Engine)             │ ← Layer 4: 主观能动性
│  永不停止的监控 → 判断 → 实验 → 学习循环          │
│  决定"追哪个模式""实验成本够不够""策略怎么调"      │
└──────────────────────────────────────────────────┘
                      ↕ 驱动
┌──────────────────────────────────────────────────┐
│  概念空间 (Concept Space)                         │ ← Layer 3: 结构化知识
│  可计算距离的概念网络                              │
│  最近邻查询 / 聚类 / 合并 / 分裂                  │
│  概念晋级后自动更新拓扑                            │
└──────────────────────────────────────────────────┘
                      ↕ 查询
┌──────────────────────────────────────────────────┐
│  模式发现引擎 (Pattern Discovery Engine)           │ ← Layer 2: 统计感知
│  持续运行的统计层                                  │
│  频率统计 / 跨实例一致性 / 异常检测                │
│  输出结构化 measurements                          │
└──────────────────────────────────────────────────┘
                      ↕ 写入
┌──────────────────────────────────────────────────┐
│  事件历史仓库 (Event History Ledger)               │ ← Layer 1: 原始记忆
│  只追加、不删除、可回溯                            │
│  记录每一次 Event / Predicate / EvidenceEnvelope   │
│  每个事件带 world_revision + timestamp             │
└──────────────────────────────────────────────────┘
```

### 各层职责边界

| 层 | 名称 | 职责 | 能动性 | 类比人脑 |
|---|---|---|---|---|
| L1 | 事件历史仓库 | 原始记录，只存不判 | 无，纯被动 | 海马体（情景记忆） |
| L2 | 模式发现引擎 | 持续统计，不问为什么 | 无，纯数学 | 潜意识模式识别 |
| L3 | 概念空间 | 存储概念及其关系，不主动 | 无，纯数据结构 | 语义网络（长期记忆） |
| L4 | 认识闭环引擎 | 监控→判断→行动→学习 | **有，主动驱动** | 前额叶（元认知） |

---

## 三、Layer 1：事件历史仓库

### 3.1 为什么需要

当前 `CognitiveInquiryRuntime` 的每一次 `run_xxx_loop()` 调用都自己构造假数据。事件产生后没有被持久化，下一次调用一切重来。

没有 L1，L2 就没有数据源。

### 3.2 设计

**核心约束**：只追加、不删除、可回溯。

```python
class EventHistoryLedger:
    """只追加的运行时事件持久化仓库。"""

    def append(self, entry: EventHistoryEntry) -> str: ...
    def query(self, filter: EventFilter) -> list[EventHistoryEntry]: ...
    def replay(self, from_revision: int) -> Iterator[EventHistoryEntry]: ...
    def snapshot(self) -> LedgerSnapshot: ...
```

**存储内容**：每一次 `Event`、`Predicate`、`EvidenceEnvelope` 的产生，都作为一条 `EventHistoryEntry` 追加写入。

**关键设计决策**：

- 每条记录带 `world_revision` + `timestamp`，支持时间旅行
- 不删除任何记录，历史不可篡改
- 支持按 `event_type`、`participant_refs`、`world_revision` 范围、`timestamp` 范围过滤
- 支持从指定 `world_revision` 开始重放，用于复盘或回归测试

### 3.3 与现有代码的关系

现有 `make_event()`、`make_predicate()`、`make_evidence_envelope()` 的输出可以直接写入 L1，不需要改变现有接口。

---

## 四、Layer 2：模式发现引擎

### 4.1 为什么需要

当前 `adapt_cognitive_signal()` 接收现成的 `measurements`，但没有人产出这些 measurements——数据是伪造的。

L2 是在 L1 之上持续运行的统计层，不问"为什么"，只问"数据里有什么重复结构"。

### 4.2 设计

```python
class PatternDiscoveryEngine:
    """在事件历史之上持续运行的统计引擎。"""

    def ingest(self, entry: EventHistoryEntry) -> None:
        """每个事件进来都增量更新统计。"""

    def query_active_patterns(
        self, min_strength: float = 0.0
    ) -> list[DiscoveredPattern]: ...
```

### 4.3 三种核心统计操作

| 操作 | 科学对应 | 数学本质 |
|---|---|---|
| **频率统计** | "这个现象反复出现" | 同一 `event_type` + role 组合的出现次数 |
| **一致性度量** | "每次出现都一样" | 跨实例的 predicate/effect 稳定性（方差倒数） |
| **异常检测** | "这次和以前不一样" | 偏离基线分布的幅度 |

### 4.4 输出结构

```python
@dataclass
class DiscoveredPattern:
    pattern_signature: str
    observed_episodes: int
    cross_instance_consistency: float  # 0~1
    stable_features: list[str]
    stable_effects: list[str]
    variable_features: list[str]
    measurements: dict[str, Any]
    mean_strength: float
    strength_trend: str  # "rising" | "stable" | "decaying"
```

### 4.5 工作机制

L2 不是一次性扫描，而是持续运行的守护进程。每个新事件进入 L1 后，L2 增量更新相关统计。当某个模式的累积强度超过阈值时，它成为"活跃模式"并进入 L4 的视野。

---

## 五、Layer 3：概念空间

### 5.1 为什么需要

当前 `concept_library.json` 是一个扁平的列表。概念之间只有手工写的 `super_concept_refs`，没有可计算的父子/兄弟关系，没有距离度量。

没有 L3，新概念无法与已有概念比较，无法自动合并/分裂，系统永远在"增加概念"但不会"重新组织概念"。

### 5.2 设计

```python
class ConceptSpace:
    """带可计算距离度量的概念网络。"""

    def nearest_neighbors(
        self, features: list[str], top_k: int = 3
    ) -> list[tuple[str, float]]: ...

    def distance(self, c1: str, c2: str) -> float: ...

    def add_concept(self, concept: dict[str, Any]) -> str: ...

    def propose_split(
        self, concept_id: str
    ) -> SplitProposal | None: ...

    def propose_merge(
        self, c1: str, c2: str
    ) -> MergeProposal | None: ...
```

### 5.3 距离度量

概念 `c1` 和 `c2` 之间的距离定义为：

```
d(c1, c2) = w₁ × J(perceptual_invariants)
           + w₂ × J(functional_affordances)
           + w₃ × J(effects)
           + w₄ × (1 - cos(applicability_constraints))
```

其中 `J` 为 Jaccard 距离，`w₁`~`w₄` 为权重参数（可由 L4 元学习调整）。

### 5.4 距离度量的作用

- **假设生成**：新模式 → 算到所有概念最近邻 → 如果距离 > 阈值 = "可能是新概念"，否则 = "可能是旧变体"
- **概念合并**：两个概念之间的距离持续缩小 → 自动触发合并评审
- **概念分裂**：一个概念下的实例出现两个明显分离的聚类 → 自动触发分裂评审

### 5.5 与现有 `concept_library.json` 的关系

L3 从现有的 `concept_library.json` 初始化。新概念晋级后自动加入空间并更新拓扑。`concept_library.json` 仍然是持久化存储格式，L3 是运行时内存视图。

---

## 六、Layer 4：认识闭环引擎

### 6.1 为什么需要

这是整个架构的"主观能动性"所在。L1/L2/L3 都是被动的——L1 只记录，L2 只统计，L3 只存储。让系统自己转起来的"飞轮"在 L4。

### 6.2 核心循环

```python
class EpistemicLoopEngine:
    """永不停止的认识闭环引擎。"""

    def __init__(self, ledger, discovery, space):
        self.ledger = ledger        # L1
        self.discovery = discovery  # L2
        self.space = space          # L3
        self.meta_params = MetaParams()  # 元学习参数
        self.active_inquiries: dict[str, Inquiry] = {}

    async def run_forever(self):
        """主循环，永不停止。"""
        while True:
            await self._tick()
            await asyncio.sleep(IDLE_INTERVAL)

    async def _tick(self):
        # 1. 查 L2：有没有活跃模式
        patterns = self.discovery.query_active_patterns(
            min_strength=self.meta_params.min_pattern_strength
        )

        # 2. 对每个模式，决定是否值得追
        for pattern in patterns:
            if self._should_investigate(pattern):
                inquiry = await self._launch_inquiry(pattern)

        # 3. 检查进行中的 inquiry 是否有新结果
        for inquiry in list(self.active_inquiries.values()):
            result = await self._poll_result(inquiry)
            if result:
                self._close_inquiry(inquiry, result)
                self._meta_learn(inquiry, result)  # 元学习
```

### 6.3 五个核心决策点

认识闭环引擎有五个必须由它自己判断的决策点，这也是"主观能动性"的具体体现：

| 决策点 | 问题 | 判断依据 |
|---|---|---|
| **should_investigate** | 这个模式值得追吗？ | 强度阈值 + 与已有概念的距离 + 历史类似实验的 ROI |
| **hypothesis_priority** | 多个模式同时出现，先追哪个？ | 预期信息增益 / 探针成本 |
| **experiment_design** | 安全探针的风险等级？ | 模式涉及的事实是否在安全边界内 |
| **promotion_decision** | 验真通过后，直接晋级还是再观察？ | 跨实例验真次数 + 独立通道数 |
| **meta_adjustment** | 我的判断参数需要调整吗？ | 最近 K 次实验的成功率 / 误判率 |

### 6.4 元学习（Meta-Learning）

这是引擎能"自我进化"的关键——每次实验后，它根据结果调整自己的参数：

```python
def _meta_learn(self, inquiry: Inquiry, result: InquiryResult):
    """每次实验后调整判断参数。"""
    if result.outcome == "promoted":
        # 成功：可以适当降低启动门槛
        self.meta_params.min_pattern_strength *= 0.95
    elif result.outcome == "rejected":
        # 被证伪：检查是假设错了还是探针设计有问题
        if result.false_positive_risk:
            self.meta_params.hypothesis_generation_bias += 0.01
    elif result.outcome == "inconclusive":
        # 模棱两可：提高这个领域的重复验证要求
        self.meta_params.min_verification_channels += 1
```

### 6.5 与现有 `CognitiveInquiryRuntime` 的关系

| 现有组件 | 在 L4 中的角色 |
|---|---|
| `CognitiveInquiryRuntime` | 单个 inquiry 的状态机（状态转移逻辑） |
| `make_inquiry_contract` | 询问合同的构造器（由 L4 在 should_investigate 后调用） |
| `adapt_cognitive_signal` | 接收 L2 产出的 measurements，包装为认知信号 |
| `authorize_route` | 安全探针的 P018 授权接口 |
| P016 验真 | 安全探针的物理验真接口 |

**L4 不替代现有代码，而是把它们组装成一个自驱动的循环。**

---

## 七、完整的自我进化飞轮

```
  ① 运行时事件发生
     ↓
  ② L1 追加记录 (EventHistoryLedger.append)
     ↓
  ③ L2 增量更新统计 (PatternDiscoveryEngine.ingest)
     ↓
  ④ L4 主动查询活跃模式 (query_active_patterns)
     ↓
  ⑤ L4 判断 "这个值不值得追" (should_investigate)
     │
     ├─ 不值得 → 继续监控
     │
     └─ 值得追 →
          ├─ ⑥ L3 查最近邻 → 生成三个竞争假设
          ├─ ⑦ 从 measurements 合成因果合同
          ├─ ⑧ 调用 InquiryRuntime 发起询问
          ├─ ⑨ P018 授权 → P016 安全探针验真
          ├─ ⑩ 晋级/否决 → L3.add_concept / L3 更新
          └─ ⑪ L4 元学习调整参数
              ↓
         回到 ①，但概念空间已经变了
```

**每一轮循环后，概念空间变得更丰富，下次模式匹配就更精确。这就是飞轮。**

---

## 八、与现有 P 编号的映射

| 层 | 关联专利 | 关系 |
|---|---|---|
| L1 事件历史仓库 | P020 统一中间表示 | 事件是 RCIR 的核心类型 |
| L2 模式发现引擎 | P011 物理经验内化 | 从经验中发现重复模式 |
| L3 概念空间 | P012 概念归纳跨域迁移 | 概念的组织、距离、合并/分裂构成跨域迁移基础 |
| L4 认识闭环引擎 | P019 端侧概念内化 | 主动监控→实验→学习的持续闭环 |
| L4→P018 接口 | P018 运行时仲裁 | 安全探针的控制授权 |
| L4→P016 接口 | P016 物理验真 | 概念预测的物理验证 |

---

## 九、实施路线

### 阶段 A：L1 + L3 基础设施（当前优先级）

| 步骤 | 产出 |
|---|---|
| A1 | `EventHistoryLedger` — 只追加事件仓库 |
| A2 | `ConceptSpace` — 从现有 `concept_library.json` 初始化的概念空间 |

### 阶段 B：L2 统计引擎

| 步骤 | 产出 |
|---|---|
| B1 | `PatternDiscoveryEngine` — 频率统计 + 一致性度量 |
| B2 | 与 L1 集成，增量更新 |
| B3 | 活跃模式查询接口 |

### 阶段 C：L4 认识闭环引擎

| 步骤 | 产出 |
|---|---|
| C1 | `EpistemicLoopEngine` — 主循环 + should_investigate |
| C2 | 与现有 `CognitiveInquiryRuntime` 集成 |
| C3 | 实验全流程自动化 |
| C4 | 元学习参数调整 |

### 阶段 D：闭环验证

| 步骤 | 产出 |
|---|---|
| D1 | 用真实运行时事件验证完整循环 |
| D2 | 验证概念空间自动更新后的模式匹配提升 |
| D3 | 性能与稳定性测试 |

---

## 十、设计原则

1. **L4 不替代 L1/L2/L3，而是组装它们**——每一层职责单一，L4 是唯一的"判断者"
2. **L2 不问为什么，只问"数据有什么结构"**——统计不判断，判断是 L4 的事
3. **概念晋级后必须让下一次模式匹配变好**——否则闭环断了
4. **安全探针的成本必须计入决策**——不是所有模式都值得追
5. **元学习参数必须有边界**——防止正反馈失控（过度自信循环）

---

## 十一、工程落地状态（2026-07-22）

阶段 A 的最小工程骨架已落地：

- `EventHistoryLedger`：保存 Event、Predicate、EvidenceEnvelope，记录世界版本和 UTC 时间戳；采用前向摘要链保证顺序可审计，提供条件查询、版本重放和快照；它是历史源，不是当前事实源。
- `ConceptSpace`：实现感知不变量、功能可供性、效果和适用约束的加权 Jaccard 距离，支持最近邻查询、概念加入、合并候选和分裂候选。
- 概念加入必须携带 `DictionaryAuthorityAdmission` 引用；合并和分裂只生成 `candidate_only` 提案，禁止直接写核心字典。

工程入口：

- `concept_core/epistemic_flywheel.py`；
- `validate_rell_epistemic_flywheel_stage_a.py`。

阶段 B 的增量统计骨架也已落地：`PatternDiscoveryEngine` 直接重放或增量消费 L1 事件，根据事件类型和参与角色形成模式签名，输出出现频率、跨实例数量、一致性、稳定特征、变量特征、稳定效果、平均强度和强度趋势。L2 的输出保持 `candidate_only`，不解释因果，也不提交事实。

阶段 B 校验入口：`validate_rell_epistemic_flywheel_stage_b.py`。

阶段 C 的最小 L4 调度器已落地：`EpistemicLoopEngine.tick()` 使用模式强度、概念空间距离、跨实例一致性、预期信息增益和探针成本计算调查分数。达到阈值的模式进入 `awaiting_p018_authorized_probe`；没有探针结果时不会执行。

探针通过 P018 和 P016 后，晋级概念先进入 `pending_dictionary_admission`，不会直接改变概念空间。只有调用 `admit_promoted_concept(..., admission_ref=...)` 并提供字典准入引用后，概念才加入 L3。每次晋级或否决会更新元参数，所有参数都有上下界。

阶段 C 校验入口：`validate_rell_epistemic_flywheel_stage_c.py`。

下一阶段进入 D：使用运行时执行闭环产生的真实 Event/Predicate/EvidenceEnvelope 驱动 L1-L4，验证概念加入后下一轮最近邻匹配确实改善，并建立飞轮收益指标。
