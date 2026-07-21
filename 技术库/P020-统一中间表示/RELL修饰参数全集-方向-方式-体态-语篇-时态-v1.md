# RELL 修饰参数全集 — 方向·方式·体态·语篇·时态·情态

版本：v1 / 2026-07-21
状态：架构母稿
目的：系统整理中文日常语言中附着在动词/谓词上的修饰参数，
     使 RELL 语言前端能将这些参数编译为 RCIR 中结构化的 modifier slots，
     而非当作无意义的虚词洗掉。

---

## 一、设计原则

### 1.1 修饰参数与认知原语的边界

| 认知原语（上篇文档） | 修饰参数（本文档） |
|---|---|
| 回答「发生了什么 / 什么关系」 | 回答「怎么发生的 / 在什么条件下」 |
| `supported_by(x, y)` — 世界的事实骨架 | `modifier.speed = fast` — 骨架上的调节旋钮 |
| 独立成为事件节点或谓词 | 永远依附于某个事件或谓词 |
| 跨语言通用（中英文都有） | 中文有独特系统（趋向补语、体标记） |

### 1.2 修饰参数在 RCIR 中的位置

```json
{
  "operator": "transport_object",
  "roles": { "theme": "...", "destination": "..." },
  "modifiers": {
    "direction": { "value": "toward_reference", "surface": "过来" },
    "speed": { "value": "fast", "surface": "快" },
    "aspect": { "value": "inceptive", "surface": "起来" },
    "carefulness": { "value": "careful", "surface": "小心" }
  },
  "discourse_role": {
    "relation": "sequence",
    "surface": "然后"
  }
}
```

### 1.3 参数的作用域

- **事件级修饰**：只影响当前事件（「快拿杯子」→ 拿的动作快）
- **全局级修饰**：影响整句任务（「小心一点」→ 整件事都要小心）
- **语篇级修饰**：影响事件间关系（「然后」→ 时序，「还有」→ 附加）

---

## 二、趋向补语系统（Directional Complements）

这是中文独有的、最复杂也最重要的修饰参数系统。一个动词带上不同的趋向补语，可以表达完全不同的空间-方向含义。

### 2.1 基本趋向

| 补语 | RCIR 方向值 | 含义 | 示例 | 事件绑定 |
|---|---|---|---|---|
| **来** | `toward_reference` | 朝向说话者/参考点运动 | 「拿来」「过来」「走来」 | navigate / transport / handover |
| **去** | `away_from_reference` | 远离说话者/参考点运动 | 「拿去」「过去」「走去」 | navigate / transport / handover |
| **上** | `upward` | 向上运动 | 「上去」「上来」「举起」 | lift / climb / raise |
| **下** | `downward` | 向下运动 | 「下去」「下来」「放下」 | lower / descend / place |
| **进** | `inward` | 进入内部 | 「进去」「进来」「走进」 | enter / insert |
| **出** | `outward` | 从内部到外部 | 「出去」「出来」「拿出」 | exit / extract |
| **回** | `return_to_origin` | 回到原点/原处 | 「回去」「回来」「放回」 | return / restore |
| **开** | `apart` | 分离 / 打开 | 「打开」「推开」「搬开」 | open / separate |
| **过** | `cross` | 越过/经过 | 「过去」「过来」「走过」 | cross / pass |
| **起** | `rise` | 从静止到向上 | 「拿起」「抬起」「举起」 | lift / raise / start |
| **到** | `arrive_at` | 到达某处 | 「放到」「拿到」「走到」 | arrive / reach |

### 2.2 复合趋向

| 补语 | RCIR 方向值 | 含义 | 示例 |
|---|---|---|---|
| **上来** | `upward + toward_reference` | 从下到上，朝向参考点 | 「爬上来」「传上来」 |
| **上去** | `upward + away_from_reference` | 从下到上，远离参考点 | 「爬上去」「贴上去」 |
| **下来** | `downward + toward_reference` | 从上到下，朝向参考点 | 「走下来」「放下来」 |
| **下去** | `downward + away_from_reference` | 从上到下，远离参考点 | 「走下去」「沉下去」 |
| **进来** | `inward + toward_reference` | 从外到内，朝向参考点 | 「走进来」「拿进来」 |
| **进去** | `inward + away_from_reference` | 从外到内，远离参考点 | 「走进去」「放进去」 |
| **出来** | `outward + toward_reference` | 从内到外，朝向参考点 | 「走出来」「拿出来」 |
| **出去** | `outward + away_from_reference` | 从内到外，远离参考点 | 「走出去」「扔出去」 |
| **回来** | `return + toward_reference` | 回到原点，朝向参考点 | 「走回来」「拿回来」 |
| **回去** | `return + away_from_reference` | 回到原点，远离参考点 | 「走回去」「放回去」 |
| **过来** | `cross + toward_reference` | 越过某处，朝向参考点 | 「走过来」「递过来」 |
| **过去** | `cross + away_from_reference` | 越过某处，远离参考点 | 「走过去」「递过去」 |
| **起来** | `rise + upward` | 向上抬起 / 开始做 | 「拿起来」「做起来」 |
| **开来** | `apart + toward_reference` | 分开，朝向参考点 | 「打开来」「摊开来」 |

### 2.3 趋向补语的组合规则

趋向补语的解析原则：

1. **先找动词**：趋向补语永远附着于某个动词
2. **区分空间义和体义**：同一个词可能既有方向又有体态含义
   - 「把书**拿起来**」→ 方向 `upward`（空间义）
   - 「突然**哭起来**」→ 体态 `inceptive`（开始义）
3. **来/去决定参考系**：有「来」表示朝向说话者，有「去」表示远离
4. **复合趋向 = 基本趋向组合**：上来 = 上 + 来，进去 = 进 + 去

### 2.4 趋向补语与事件关系对照表

| 事件 | 典型趋向补语 | 组合含义 |
|---|---|---|
| navigate_to | 来/去/过来/过去/进来/进去/出来/出去/回来/回去 | 移动方向 |
| grasp_object | 起/起来 | 从表面拿起 |
| place_object | 下/下去/下来/回/回去/回来 | 放下、放回 |
| transport_object | 来/去/过来/过去/进来/进去/出来/出去/回来/回去 | 运输方向 |
| handover_object | 来/去/过来/过去/回来/回去 | 递交方向 |
| apply_directional_force | 开/过来/过去 | 推开/拉开/拖过来 |
| change_open_state | 开/开来 | 打开 |
| fill_container / pour | 进去/出来 | 倒进去/倒出来 |
| insert / screw | 进去 | 拧进去/插进去 |
| cut / separate | 开/开来 | 切开/撕开 |

---

## 三、方式副词系统（Manner Modifiers）

### 3.1 速度

| 表层词 | RCIR 值 | 示例 |
|---|---|---|
| 快、赶快、赶紧、快点、迅速、快速、尽快 | `speed: fast` | 「快拿杯子」「赶紧走」 |
| 慢、慢慢、慢点、缓慢、徐徐 | `speed: slow` | 「慢慢放」「慢点走」 |
| 加速、加快 | `speed: accelerate` | 「加快速度」 |
| 减速、放慢 | `speed: decelerate` | 「放慢速度」 |

### 3.2 力度

| 表层词 | RCIR 值 | 示例 |
|---|---|---|
| 用力、使劲、重点、大力 | `force: strong` | 「用力拧」「使劲推」 |
| 轻、轻轻、轻点、轻柔 | `force: gentle` | 「轻轻放」「轻点拿」 |
| 适中、适当力度 | `force: moderate` | 默认值 |

### 3.3 精细度 / 注意力

| 表层词 | RCIR 值 | 示例 |
|---|---|---|
| 小心、当心、谨慎 | `carefulness: careful` | 「小心搬」「当心别摔了」 |
| 仔细、认真、专心 | `attentiveness: attentive` | 「仔细检查」「认真擦」 |
| 随便、随意、大概 | `attentiveness: casual` | 「随便放」「大概扫一下」 |
| 马马虎虎、粗略 | `attentiveness: rough` | 同上 |

### 3.4 姿态 / 方式

| 表层词 | RCIR 值 | 示例 |
|---|---|---|
| 横着 | `orientation: horizontal` | 「横着放」 |
| 竖着、立着、直着 | `orientation: vertical` | 「竖着放」「立起来」 |
| 正着 | `orientation: normal` | 「正着放」 |
| 倒着、反着 | `orientation: inverted` | 「倒着拿」 |
| 侧着 | `orientation: lateral` | 「侧着放进去」 |
| 斜着 | `orientation: oblique` | 「斜着放」 |
| 平着 | `orientation: level` | 「平着端」 |
| 叠着 | `arrangement: stacked` | 「叠着放」 |
| 排着、挨着 | `arrangement: aligned` | 「排着放」「挨着放」 |
| 散着 | `arrangement: scattered` | 「散着放」 |

### 3.5 伴随状态

| 表层词 | RCIR 值 | 示例 |
|---|---|---|
| 带着 | `accompanied_by: object` | 「带着身份证」 |
| 穿着、戴着 | `body_attachment: worn` | 「穿着手套」 |
| 拿着、端着 | `body_attachment: held` | 「拿着杯子过来」 |
| 背着、扛着 | `body_attachment: carried` | 「背着包」 |
| 空手 | `body_attachment: empty_handed` | 「空手过来就行」 |

---

## 四、体标记系统（Aspectual Markers）

体标记回答的是「这个事件处于什么时间状态」——完成没、进行中、刚要开始、持续中。

### 4.1 基本体标记

| 标记 | RCIR 体值 | 含义 | 示例 |
|---|---|---|---|
| **了** | `perfective` | 动作已完成、状态已变化 | 「喝了水」「放好了」「门关了」 |
| **着** | `durative` | 动作/状态正在进行或持续 | 「拿着杯子」「灯亮着」 |
| **过** | `experiential` | 曾经经历过某事件 | 「去过北京」「用过这个工具」 |
| **没(有)** | `negated_perfective` | 尚未完成某动作 | 「没喝水」「还没放好」 |

### 4.2 复合体标记

| 标记 | RCIR 体值 | 含义 | 示例 |
|---|---|---|---|
| **起来**（体用法） | `inceptive` | 动作开始 | 「笑起来」「做起来」 |
| **下去**（体用法） | `continuative` | 动作继续 | 「做下去」「活下去」 |
| **下来**（体用法） | `resultative_continuation` | 从过去持续到现在 | 「坚持下来」「习惯下来」 |
| **出来**（体用法） | `resultative_completion` | 从无到有的结果 | 「画出来」「想出来」 |
| **完** | `completive` | 动作完毕 | 「吃完」「做完」「喝完」 |
| **好**（补语用法） | `preparatory_completion` | 动作准备好/完成 | 「放好」「穿好衣服」「装好」 |
| **到**（补语用法） | `achievement` | 成功达成某结果 | 「找到」「拿到」「看到」 |
| **住**（补语用法） | `fixation` | 固定/停止在某状态 | 「抓住」「记住」「停住」 |
| **掉**（补语用法） | `disposal` | 去除/消耗 | 「扔掉」「吃掉了」「关掉」 |
| **上**（体用法） | `attainment` | 达成/附着成功 | 「关上」「考上」「追上」 |
| **着**（补语用法，zháo） | `successful_contact` | 成功接触/碰到 | 「够着了」「睡着了」「点着了」 |

### 4.3 体标记与证据等级的关系

体标记直接影响事实的验真要求和证据等级：

```
「我喝了水」
  → reported_event: consumption_completed
  → aspect: perfective
  → physical_fact_committed: false  # 人类报告，不是物理事实

「杯子放在桌上」
  → 如果是从语言来的：candidate_only
  → 如果是从 P016 验真来的：established_fact
```

体标记 `perfective`（了）**不代表物理事实已提交**，只代表语言中表达为「已完成」。

### 4.4 「了」的位置歧义

「了」在中文中有两个位置，含义不同，必须区分：

| 位置 | 含义 | 示例 |
|---|---|---|
| 动词后 | 动作完成（体标记） | 「喝**了**一杯水」→ 动作完成 |
| 句尾 | 新情况出现 / 变化（语气词） | 「我喝水**了**」→ 状态变化 |
| 动词后+句尾 | 动作完成且当前相关 | 「我喝**了**水**了**」→ 完成+状态变化 |

---

## 五、语篇连接词系统（Discourse Connectives）

### 5.1 时序连接

| 连接词 | RCIR 值 | 含义 | 示例 |
|---|---|---|---|
| 然后、随后、接着、继而 | `sequence` | 按顺序发生 | 「拿杯子**然后**接水」 |
| 先...再/然后... | `ordered_sequence` | 明确先后顺序 | 「**先**拿杯子，**再**接水」 |
| 同时、一边...一边... | `parallel` | 同时发生 | 「**一边**烧水**一边**洗杯子」 |
| 之后、以后、而后 | `temporal_after` | 某时间点之后 | 「吃完饭**之后**收拾」 |
| 之前、以前、事先 | `temporal_before` | 某时间点之前 | 「出门**之前**检查」 |
| 期间、时、的时候 | `temporal_during` | 在某时段内 | 「烧水**期间**准备杯子」 |

### 5.2 逻辑连接

| 连接词 | RCIR 值 | 含义 | 示例 |
|---|---|---|---|
| 因为、由于 | `causal_reason` | 原因 | 「**因为**没水了，去接一杯」 |
| 所以、因此、于是 | `causal_result` | 结果 | 「没水了，**所以**去接一杯」 |
| 为了、以便、好（口语） | `purpose` | 目的 | 「**为了**喝水，去接一杯」 |
| 如果、要是、假如 | `conditional` | 条件假设 | 「**如果**没水了就去接」 |
| 虽然、尽管 | `concessive` | 让步 | 「**虽然**有杯子，但没水」 |
| 但是、可是、不过、然而 | `contrastive` | 转折 | 「有杯子，**但是**没水」 |
| 而且、并且、还、也 | `additive` | 附加/并列 | 「有杯子，**而且**有水」 |
| 或者、要么、还是 | `disjunctive` | 选择 | 「拿杯子**或者**拿碗」 |
| 否则、要不然、不然 | `alternative` | 否则 | 「快点，**否则**来不及了」 |

### 5.3 语篇结构标记

| 标记 | RCIR 值 | 含义 | 示例 |
|---|---|---|---|
| 嗯、好的、行、知道了 | `acknowledgment` | 确认收到 | 「**嗯**，好的」 |
| 对了、话说、顺便问一下 | `topic_shift` | 话题切换 | 「**对了**，杯子在哪」 |
| 首先、第一、其次、最后 | `discourse_enumeration` | 列举 | 「**首先**拿杯子，**其次**接水」 |
| 总之、总而言之、说白了 | `discourse_summary` | 总结 | 「**总之**，就是接杯水」 |
| 也就是说、即、换言之 | `discourse_reformulation` | 换种说法 | 「**也就是说**，你渴了」 |

---

## 六、时态与时间副词系统（Temporal Adverbs）

### 6.1 时间定位

| 副词 | RCIR 值 | 示例 |
|---|---|---|
| 刚才、刚刚 | `temporal: immediate_past` | 「**刚才**放这了」 |
| 已经 | `temporal: past` | 「**已经**接了水」 |
| 曾经、曾 | `temporal: remote_past` | 「**曾经**用过这个」 |
| 正在、在（口语） | `temporal: present_ongoing` | 「**正在**接水」 |
| 将要、就要、快（要） | `temporal: imminent_future` | 「水**快**开了」 |
| 会、将、要 | `temporal: future` | 「我**会**去接水」 |
| 马上、立刻、赶紧 | `temporal: immediate_future` | 「**马上**就来」 |
| 一直、始终、从来 | `temporal: persistent` | 「**一直**放在那」 |
| 偶尔、有时、时不时 | `temporal: intermittent` | 「**偶尔**用一下」 |
| 经常、常常、总是 | `temporal: frequent` | 「**经常**放这里」 |
| 从来、从未（否定） | `temporal: never` | 「**从来**没用过」 |

### 6.2 体时复合

中文中时态和体态经常复合出现：

| 复合 | 拆解 | 示例 |
|---|---|---|
| 已经 + 了 | past + perfective | 「已经拿**了**」 |
| 正在 + 着 | present + durative | 「正在拿**着**」 |
| 还没 + 呢 | negated + perspective + pending | 「还没拿**呢**」 |
| 快 + 了 | imminent + change_of_state | 「快好**了**」 |
| 一直 + 着 | persistent + durative | 「一直拿**着**」 |

---

## 七、情态与语气系统（Modal & Mood Markers）

### 7.1 能愿动词

| 词 | RCIR 值 | 含义 | 示例 |
|---|---|---|---|
| 能、可以、行 | `possibility: enabled` | 有能力/允许 | 「**能**拿起来」 |
| 不能、不可以、不行 | `possibility: disabled` | 无能力/禁止 | 「**不能**碰」 |
| 会 | `possibility: capable` | 掌握技能 | 「我**会**用这个」 |
| 可能、也许、大概、或许 | `possibility: uncertain` | 可能性推测 | 「**可能**在桌上」 |
| 一定、肯定、绝对、必须 | `necessity: certain` | 必然/必须 | 「**一定**在桌上」 |
| 应该、应当、得（děi） | `necessity: deontic` | 道义/建议 | 「你**应该**去充电」 |
| 想、要、愿意 | `volition: desire` | 意愿 | 「我**想**喝水」 |
| 不想、不要、不愿 | `volition: undesired` | 不意愿 | 「我**不想**去」 |
| 敢 | `volition: dare` | 大胆做 | 「我**敢**拿」 |
| 懒得 | `volition: unwilling` | 懒得做 | 「我**懒得**去」 |

### 7.2 语气词（句尾）

| 词 | RCIR 值 | 含义 | 示例 |
|---|---|---|---|
| 吗、么 | `mood: interrogative_yes_no` | 是非问 | 「有水**吗**」 |
| 呢 | `mood: interrogative_contextual` | 语境问（承接上文） | 「杯子**呢**」 |
| 吧 | `mood: suggestive / uncertain` | 建议/推测 | 「放这**吧**」「大概在**吧**」 |
| 啊、呀、嘛 | `mood: emphasis / obvious` | 强调/当然 | 「对**啊**」「就是它**嘛**」 |
| 哦、噢 | `mood: realization` | 恍然 | 「原来是这样**哦**」 |
| 呗 | `mood: resigned` | 无奈/只好 | 「那就这样**呗**」 |

---

## 八、数量与程度修饰（Quantitative Modifiers）

### 8.1 程度副词

| 词 | RCIR 值 | 示例 |
|---|---|---|
| 很、非常、特别、极其、太 | `degree: high` | 「**很**大」、「**太**重了」 |
| 有点、稍微、略微、一点儿 | `degree: low` | 「**稍微**抬一点」 |
| 比较、还算、挺 | `degree: moderate` | 「**比较**轻」 |
| 最、顶、至 | `degree: superlative` | 「**最**大的那个」 |
| 更、更加、还（比较级） | `degree: comparative` | 「**更**大的那个」 |
| 过于、太（过头） | `degree: excessive` | 「**过于**沉重」 |

### 8.2 数量修饰

| 词 | RCIR 值 | 示例 |
|---|---|---|
| 一个、两个、几 | `quantity: numeral` | 「**一**个杯子」 |
| 一些、一点、若干 | `quantity: indefinite_small` | 「**一些**水」 |
| 很多、许多、大量 | `quantity: indefinite_large` | 「**很多**杯子」 |
| 所有、全部、都 | `quantity: universal` | 「**所有**杯子都洗了」 |
| 各、每 | `quantity: distributive` | 「**每**个杯子都检查」 |
| 又（数量追加） | `quantity: additional` | 「**又**接了一杯」 |
| 还（数量追加） | `quantity: additional` | 「**还**要一杯」 |

### 8.3 范围限定

| 词 | RCIR 值 | 示例 |
|---|---|---|
| 只、仅、就（范围限定） | `scope: exclusive` | 「**只**拿这一个」 |
| 除了...都 | `scope: excluding` | 「**除了**这个**都**拿走」 |
| 连...都 | `scope: including_unlikely` | 「**连**盖子**都**拿走了」 |

---

## 九、否定系统（Negation）

### 9.1 否定形式与作用域

| 否定词 | 作用域 | 示例 |
|---|---|---|
| 不 | 意愿/状态/一般性否定 | 「**不**去」「**不**是」「**不**知道」 |
| 没（有） | 完成/存在否定 | 「**没**拿」「**没有**水」 |
| 别、不要、请勿 | 祈使否定（禁止） | 「**别**碰」「**不要**去」 |
| 尚未、还未 | 仍未发生 | 「**尚未**完成」 |
| 从没、从未 | 从未发生过 | 「**从没**用过」 |
| 不必、不用 | 必要性否定 | 「**不用**拿来」 |
| 不可能、不会 | 可能性否定 | 「**不可能**在那」 |

### 9.2 否定作用域规则

```
否定词作用的「范围」取决于它在句中的位置：

「不要把杯子放在桌子上」
  → 否定范围: 整件事（不要执行 place_object）

「把杯子不要放在桌子上，放在柜子里」
  → 第一个子句否定，第二个子句替换

「杯子没放在桌子上」
  → 否定范围: 当前事实状态（report / query）
```

---

## 十、疑问系统（Interrogative Modifiers）

### 10.1 疑问词

| 词 | RCIR 值 | 示例 |
|---|---|---|
| 什么 | `wh: object` | 「拿**什么**」 |
| 谁 | `wh: person` | 「**谁**拿的」 |
| 哪里、哪儿 | `wh: location` | 「放**哪里**」 |
| 什么时候、几时 | `wh: time` | 「**什么时候**拿」 |
| 怎么 | `wh: manner` | 「**怎么**拿」 |
| 为什么 | `wh: reason` | 「**为什么**拿这个」 |
| 多少、几 | `wh: quantity` | 「**几**个杯子」 |
| 哪个 | `wh: selection` | 「**哪个**杯子」 |
| 怎么样 | `wh: state_or_opinion` | 「这个杯子**怎么样**」 |

### 10.2 疑问类型到 RCIR 查询类型

| 疑问类型 | RCIR query_type | 示例 |
|---|---|---|
| 是不是/有没有/吗 | `yes_no_query` | 「有杯子**吗**」 |
| 什么 | `object_query` | 「桌子上有**什么**」 |
| 哪里 | `location_query` | 「杯子在**哪里**」 |
| 怎么（方法） | `method_query` | 「这个**怎么**打开」 |
| 为什么 | `reason_query` | 「**为什么**不工作」 |
| 谁 | `person_query` | 「**谁**拿走了」 |
| 哪个 | `selection_query` | 「拿**哪个**」 |
| 能不能/可以不可以 | `capability_query` | 「**能不能**拿起来」 |

---

## 十一、感知与证据标记（Evidential Modifiers）

这些词标记信息的来源，直接影响证据等级。

| 词 | RCIR 证据标记 | 证据等级影响 | 示例 |
|---|---|---|---|
| 看见/看到 | `evidential: visual` | 视觉证据 | 「我**看到**在桌上」 |
| 听见/听到 | `evidential: auditory` | 听觉证据 | 「我**听到**有声音」 |
| 感觉/觉得 | `evidential: felt` | 体感 | 「我**感觉**有点歪」 |
| 听说/据说 | `evidential: hearsay` | 间接报告 | 「**听说**那边有」 |
| 好像/似乎/看起来 | `evidential: apparent` | 表象推测 | 「**好像**在桌上」 |
| 明明/显然 | `evidential: obvious` | 显而易见 | 「**明明**就在那」 |
| 应该/按理说 | `evidential: expected` | 按常理推断 | 「**按理说**应该在这」 |

---

## 十二、语气强度与礼貌（Politeness & Intensity）

| 词 | RCIR 值 | 示例 |
|---|---|---|
| 请、麻烦、劳驾 | `politeness: polite` | 「**请**拿一下」 |
| 帮我、替我 | `politeness: service_request` | 「**帮我**拿一下」 |
| 一下 | `intensity: brief_trial` | 「拿**一下**」 |
| 看看/试试 | `intensity: tentative` | 「**看看**在不在」 |
| 务必、千万、一定（强调） | `intensity: urgent` | 「**务必**放好」 |
| 随便、反正、无所谓 | `intensity: casual` | 「**随便**放哪」 |

---

## 十三、修饰参数组合规则

### 13.1 允许多个修饰共存

```json
{
  "operator": "transport_object",
  "modifiers": {
    "direction": { "value": "toward_reference", "surface": "过来" },
    "speed": { "value": "fast", "surface": "赶快" },
    "carefulness": { "value": "careful", "surface": "小心" },
    "aspect": { "value": "completive", "surface": "完" },
    "politeness": { "value": "polite", "surface": "请" }
  }
}
```

实际句子：**「请赶快小心地把杯子拿过来」**

### 13.2 冲突处理

当修饰参数冲突时：

| 冲突 | 处理规则 | 示例 |
|---|---|---|
| 快 + 慢 | 取最新或人类最确认的 | 「快拿——算了慢点」→ 取慢 |
| 用力 + 轻点 | 同上，或进入 InquiryContract | 「用力——别，轻点」 |
| 来 + 去 | 不可能同时出现，解析错误 | 不可能在同一动词上 |

### 13.3 省略与默认

事件级修饰的大部分参数在有明确的上下文时可以省略，省略时采用默认值：

| 参数 | 默认值 | 依据 |
|---|---|---|
| 趋向 | 无（必须从动词显式推断或上下文推断） | — |
| 速度 | `moderate` | 非紧急任务 |
| 力度 | `moderate` | 标准操作 |
| 仔细度 | `normal` | 标准操作 |
| 礼貌度 | `neutral` | 标准交互 |
| 体态 | 从时态副词推断，否则默认为祈使 | 「拿杯子」→ 祈使/未完成 |

---

## 十四、与认知原语文档的集成

### 14.1 处理流水线

```
原始句子
  → 1. 语篇切分（discourse_clause_specs）→ 分句 + 语篇连接词提取
  → 2. 事件识别（event_mentions）→ 动词/事件算子
  → 3. 角色提取（roles）→ 主题/目的地/接收者
  → 4. 修饰参数提取（NEW）→ 趋向/方式/体态/时态/情态/否定
  → 5. 修饰参数消歧与组合
  → 6. RCIR Bundle 输出
```

### 14.2 新修改器提取模块建议位置

在 `language_concept_composer.py` 中，`_roles()` 之后增加一个新的函数：

```
_extract_modifiers(text, events) → dict[str, Any]
```

输出一个结构化的 modifiers dict，附加到每个事件的 `modifiers` 字段和整句的 `discourse_modifiers` 字段。

---

## 十五、总结：中文修饰参数的独特性

中文相较于英文，修饰参数体系有两个显著特点：

1. **趋向补语系统是中文独有的**。英文用介词短语（"pick **up**"、"come **in**"、"put **back**"），中文用动词后的补语系统，且能与几乎所有动作动词组合。

2. **体标记不靠词形变化，靠虚词**。英文通过时态变形（"-ed"、"-ing"）表达体态，中文用「了/着/过/起来/下去」等独立词附着在动词后。

这两个特点使得中文的语言前端不能简单套用英文的介词短语解析策略，而需要专门的趋向补语和体标记解析器。

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-21 | v1 | 初稿：趋向补语 14 类、方式副词 5 子类、体标记 12+、语篇连接 4 子类 20+、时态副词 12+、情态/语气/否定/疑问/证据/礼貌 |
