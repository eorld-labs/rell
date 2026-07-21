# RELL 认知原语全集 — 空间·事件·状态·社会·物理

版本：v1 / 2026-07-21
状态：架构母稿
目的：一次性补齐所有够得上「基本认知原语」级别的关系谓词、事件算子和状态谓词，
     使 RELL 语言前端能覆盖日常生活和生产活动中的绝大部分表达。

---

## 一、设计原则

### 1.1 什么才算「认知原语」

加入本列表的条件：

1. **不可再分**：不能由其他原语组合表达（或者说组合后语义损失过大）
2. **跨场景复用**：不是单一场景的特例
3. **有物理/社会/认知的可验真条件**：P016 或等价机构能够确认它是否成立
4. **有语言适配器的映射价值**：中文/英文中有多个表面词指向它

### 1.2 本表不包含的内容

- 具体物体概念（杯子、桌子、苹果）→ 属于 `concept_units.py`
- 具体物体别名（"马克杯"→ cup）→ 属于语言适配器
- 具体场景的复合技能（"接一杯水"→ fill_container + transport）→ 属于过程模板
- 细粒度运动参数（轨迹、速度、关节角）→ 属于本体适配器

### 1.3 符号约定

```
谓词（Predicate）:   relation(subject, object)       — 表示两个实体之间的关系
算子（Operator）:    operator(theme, ...roles)        — 表示一个可以执行的事件类型
状态谓词（State）:   state(entity, value)              — 表示实体当前的属性状态
```

---

## 二、空间关系谓词（Spatial Predicates）

这是当前最薄弱、也是最急需扩充的类别。人类语言中大约 80% 的「去哪、放哪、在哪」表达依赖空间关系谓词。

### 2.1 拓扑空间关系

| 谓词 | 意义 | 示例 | 验真条件 | 反义/补集 |
|---|---|---|---|---|
| `supported_by(x, y)` | x 被 y 从下方承托 | 杯子在桌子上 | 接触检测 + 重力支撑 | `not_supported_by` |
| `contained_by(x, y)` | x 在 y 的内部容积中 | 苹果在篮子里 | 边界检测 | `outside_of` |
| `attached_to(x, y)` | x 机械/物理附着于 y | 夹爪装在手臂上 | 紧固件检测 | `detached_from` |
| `connected_to(x, y)` | x 与 y 通过线缆/管路连接 | 吸管连着杯子 | 通路检测 | `disconnected_from` |
| `inserted_into(x, y)` | x 插入 y 的开口/插槽 | 插头插入插座 | 插入深度检测 | `withdrawn_from` |
| `stacked_on(x, y)` | x 叠放在 y 之上（非固定） | 盘子叠在盘子上 | 垂直对齐 + 接触 | `unstacked` |
| `hung_on(x, y)` | x 悬挂在 y 上 | 衣服挂在衣架上 | 上端受力 + 悬空 | `taken_off` |
| `leaning_against(x, y)` | x 斜靠 y（非垂直承托） | 扫帚靠在墙上 | 角度检测 + 接触 | `upright` / `removed` |
| `resting_in(x, y)` | x 搁在 y 的凹槽/凹陷中 | 笔搁在笔托上 | 形状匹配 + 接触 | `displaced` |
| `wrapped_around(x, y)` | x 缠绕/包裹 y | 线绕在线轴上 | 多圈环绕检测 | `unwrapped` |

### 2.2 方向空间关系

| 谓词 | 意义 | 示例 | 验真条件 |
|---|---|---|---|
| `in_front_of(x, y)` | x 在 y 的前方（y 的朝向为参考） | 站到我的前面 | 朝向向量点积 > 0 |
| `behind(x, y)` | x 在 y 的后方 | 到门后面去 | 朝向向量点积 < 0 |
| `beside(x, y)` | x 在 y 的侧面（左右不分） | 站到桌子旁边 | 横向距离 < 阈值 |
| `left_of(x, y)` | x 在 y 的左侧（y 的朝向为参考） | 站到我的左边 | 横向叉积方向 |
| `right_of(x, y)` | x 在 y 的右侧 | 靠右站 | 同上 |
| `above(x, y)` | x 在 y 的正上方（重力方向） | 吊灯在桌子上方 | 垂直投影重叠 + 高度差 > 0 |
| `below(x, y)` | x 在 y 的正下方 | 地毯在桌子下方 | 垂直投影重叠 + 高度差 < 0 |
| `between(x, y, z)` | x 在 y 和 z 之间 | 站到桌子和柜子中间 | 到两点距离同时 < 阈值 |
| `facing(x, y)` | x 朝向 y | 面向我 | 朝向向量指向 y |
| `aligned_with(x, y)` | x 与 y 对齐（指定轴） | 把杯子和我对齐 | 轴投影重合度 |
| `parallel_to(x, y)` | x 的长轴与 y 的长轴平行 | 把笔和桌子边平行放 | 方向向量夹角 < 阈值 |
| `perpendicular_to(x, y)` | x 的长轴与 y 的长轴垂直 | 横着放 | 方向向量夹角 ≈ 90° |

### 2.3 距离空间关系

| 谓词 | 意义 | 示例 | 验真条件 |
|---|---|---|---|
| `near(x, y, [threshold])` | x 在 y 附近（可设置阈值） | 靠近我 | 欧氏距离 < 阈值 |
| `far_from(x, y)` | x 远离 y | 远离电源 | 欧氏距离 > 阈值 |
| `adjacent_to(x, y)` | x 紧贴 y（面接触或边接触） | 把两张桌子并在一起 | 接触面面积 > 阈值 |
| `surrounding(x, y)` | x 环绕 y | 围在桌子周围 | 多实体以 y 为中心分布 |
| `beyond(x, y, z)` | x 越过 y 到达 z 侧 | 在线后面 | 线/面穿越检测 |

### 2.4 以人为参考的空间关系

| 谓词 | 意义 | 示例 | 特殊处理 |
|---|---|---|---|
| `near_human(x, h)` | x 在人类 h 的附近 | 站到我身边 | h 是运动实体，参考系随动 |
| `beside_human(x, h)` | x 在人类 h 的侧方 | 站我旁边 | 区分左/右需要 h 的朝向 |
| `in_hand(x, h)` | x 在人类 h 的手里 | 在我手里 | 需要手部追踪 |
| `handed_to(x, h)` | x 是人类 h 正准备接过的 | 递给你的 | 过渡状态，非稳态 |
| `within_arm_reach(x, h)` | x 在人类 h 的可及范围内 | 够得到 | 距离 + 人体工学参数 |

---

## 三、事件算子（Event Operators）

### 3.1 当前已有算子（P020 已定义，列出来供对照）

| 算子 | 已有 heads | 建议补充 heads |
|---|---|---|
| `observe_entity` | 观察、瞧、看、找 | 「查看」、「检查」、「巡视」、「扫一眼」 |
| `navigate_to` | 返回到、回到、返回、前往、靠近、走、去 | **「站到」、「站」、「移动到」、「走到...旁边」、「靠过来」、「退到」、「闪到」** |
| `orient_executor` | 转向、面向、朝向、转 | **「转过来」、「转过去」、「调头」、「转身」** |
| `grasp_object` | 捡、拾、抓、取、拿 | **「握住」、「捏住」、「夹住」、「捧起」、「端起」、「托起」、「抱起」** |
| `release_object` | 释放、撒手、松开、放开 | **「放下」、「松手」、「丢下」、「脱落」** |
| `place_object` | 放回、送回、搁回、摆回、归还、搁、摆、放 | **「放置」、「安放」、「摆放」、「归位」** |
| `handover_object` | 递回来、交回来、递给、交给、拿给、送给、递过去、交过去、递回、交回 | **「传」、「转交」、「递交」、「呈递」** |
| `transport_object` | 拿过来、带过来、送过来、端过来、带到、拿到、送到、端到、带走、拿来、送来、端来 | — |
| `fill_container` | 接一杯水、取一杯水、接杯水、盛水、装水、倒一杯水 | — |
| `apply_directional_force` | 拖、挪、推、拉 | **「牵引」、「拽」、「顶」、「抵住」、「按压」、「提」、「抬」** |
| `change_open_state` | 打开、关上、关闭、合上 | **「拉开」、「推拉」、「掀开」、「盖上」、「锁上」、「解锁」** |
| `change_device_activation` | 启动、开启、关掉、开机、关机 | **「打开电源」、「关闭电源」、「暂停」、「复位」、「急停」** |
| `transfer_material` | 倒入、倒进、倒出、装入、装进、取出 | **「灌入」、「倾倒」、「舀出」、「舀入」、「撒」** |
| `remove_surface_contaminant` | 打扫、清洁、清理、擦 | **「扫」、「拖」、「抹」、「刷」、「冲洗」、「吸尘」** |
| `stop_current_activity` | 停止、停下、取消 | — |
| `wait_until` | 等待、等等、等 | **「等...完」、「等...到」** |

### 3.2 新增算子

#### 身体动作类

| 算子 | 语义 | 示例 | requires | projects |
|---|---|---|---|---|
| `sit_on(x)` | 坐/坐到 x 上 | 「坐下」、「坐到椅子上」 | `reachable(executor, x)`, `support_human_sitting(x)` | `body_supported_by(x)` |
| `stand_up()` | 从坐/躺状态站起 | 「站起来」、「起身」 | `body_supported_by(x)` | `body_upright` |
| `lie_on(x)` | 躺到 x 上 | 「躺下」、「躺在床上」 | `reachable(executor, x)` | `body_supported_by(x)` |
| `crouch()` | 蹲下 | 「蹲下来」、「蹲下」 | — | `body_crouched` |
| `bend_over()` | 弯腰 | 「弯下腰」、「俯身」 | — | `body_bent` |
| `turn_body(angle)` | 身体转动 | 「转过去」、「转过来」 | — | `body_orientation` |
| `lean_toward(x)` | 身体倾向 x | 「凑过来看看」、「俯身靠近」 | — | `body_angle_toward(x)` |
| `reach_for(x)` | 伸手够 x | 「伸手拿那个」 | `within_arm_reach(executor, x)` | `hand_near(x)` |

#### 精细操作类

| 算子 | 语义 | 示例 | requires | projects |
|---|---|---|---|---|
| `screw(x, y)` | 拧/旋入 | 「把螺丝拧进去」、「旋紧瓶盖」 | `held_by(x, executor)` | `threaded_into(x, y)` |
| `unscrew(x, y)` | 拧出/旋出 | 「把瓶盖拧开」 | `engaged_with(x, y)` | `detached(x, y)` |
| `cut(x, y)` | 切割 x（工具 y） | 「用刀切开」 | `contact(executor, y)`, `sharp(y)` | `separated_into(x, parts)` |
| `stir(x, y)` | 搅拌 x（工具 y） | 「搅拌一下」 | `contained_by(x, container)`, `held_by(y, executor)` | `contents_mixed(x)` |
| `fold(x)` | 折叠 x | 「把衣服叠起来」 | `held_by(x, executor)`, `flexible(x)` | `folded(x)` |
| `unfold(x)` | 展开 x | 「把地图展开」 | `folded(x)` | `flat(x)` |
| `tie(x, y)` | 绑/系 | 「把绳子系在杆子上」 | `access_to(executor, x, y)` | `fastened_to(x, y)` |
| `untie(x, y)` | 解开 | 「解开绳子」 | `fastened_to(x, y)` | `detached(x, y)` |
| `insert(x, y)` | 插入 | 「把钥匙插进锁孔」 | `held_by(x, executor)`, `has_slot(y)` | `inserted_into(x, y)` |
| `withdraw(x, y)` | 拔出 | 「把插头拔掉」 | `inserted_into(x, y)` | `detached(x, y)` |
| `pour(x, y)` | 倾倒（液体/颗粒） | 「把水倒进杯子」 | `held_by(x, executor)`, `contains(x, fluid)` | `transferred_to(fluid, y)` |

#### 工具与设备操作类

| 算子 | 语义 | 示例 | 说明 |
|---|---|---|---|
| `press_button(x)` | 按按钮 x | 「按一下开关」、「按电梯」 | 可复用 `apply_directional_force` |
| `turn_knob(x, dir)` | 旋转旋钮 x | 「把音量调大」、「旋钮拧到三档」 | 角度参数 |
| `pull_lever(x)` | 拉杆 | 「拉一下闸」 | 行程参数 |
| `type_text(x)` | 输入文本 | 「输入密码」、「打字」 | 文字序列参数 |
| `pick_up_phone()` | 接电话 | 「接一下电话」 | 复合操作 |
| `open_door(x)` | 开门 | 「打开门」 | 特殊化 `change_open_state` |
| `close_door(x)` | 关门 | 「关上门」同上 | |
| `lock(x)` | 锁上 x | 「把门锁上」 | `change_open_state` 的扩展 |
| `unlock(x)` | 解锁 x | 「把门打开」（钥匙场景） | |

#### 环境改变类

| 算子 | 语义 | 示例 | 特殊要求 |
|---|---|---|---|
| `illuminate(x)` | 照亮 x | 「把灯打开」、「照亮这个区域」 | 光源设备控制 |
| `dim(x)` | 调暗 x | 「把灯调暗」 | 可调光源 |
| `set_temperature(x, v)` | 设定 x 的温度为 v | 「空调设到26度」 | 温控设备 |
| `ventilate(x)` | 通风 | 「把窗户打开通通风」 | 开窗 + 等待 |
| `dry(x)` | 弄干 x | 「把桌子擦干」、「吹干」 | 工具相关 |
| `wet(x)` | 弄湿 x | 「把抹布打湿」 | 水源相关 |
| `heat(x)` | 加热 x | 「把饭热一下」 | 加热设备 |
| `cool(x)` | 冷却 x | 「把饮料冰一下」 | 制冷设备 |

---

## 四、状态谓词（State Predicates）

状态谓词描述世界在某一时刻的**静态事实**。它们不改变世界，只描述世界的某个切面。

### 4.1 物体状态

| 状态谓词 | 取值 | 示例 |
|---|---|---|
| `temperature(x)` | 连续值 ℃ | `temperature(soup) = 85℃` |
| `wetness(x)` | dry / damp / wet / soaked | `wetness(towel) = wet` |
| `cleanliness(x)` | clean / dirty / stained | `cleanliness(floor) = dirty` |
| `integrity(x)` | intact / cracked / broken / shattered | `integrity(cup) = cracked` |
| `open_state(x)` | open / closed / locked / ajar | `open_state(door) = closed` |
| `fullness(x)` | empty / partial / full / overflowing | `fullness(cup) = empty` |
| `orientation(x)` | upright / inverted / tilted(angle) | `orientation(bottle) = inverted` |
| `stability(x)` | stable / unstable / toppling | `stability(stack) = unstable` |
| `contained_volume(x)` | 连续值 ml | 仅用于容器 |
| `charge_level(x)` | 0%~100% | `charge_level(robot) = 30%` |
| `connection_status(x)` | connected / disconnected | `connection_status(cable) = disconnected` |
| `illumination(x)` | 连续值 lux | `illumination(room) = 50` |

### 4.2 机器人/执行器状态

| 状态谓词 | 取值 | 示例 |
|---|---|---|
| `body_posture` | standing / sitting / lying / crouching / bending | `body_posture = standing` |
| `gripper_state` | open / closed / holding / locked | `gripper_state = holding` |
| `gripper_force` | 连续值 N | `gripper_force = 3.5N` |
| `location(x)` | 区域/坐标 | `location(robot) = "kitchen"` |
| `battery_level` | 0%~100% | `battery_level = 45%` |
| `velocity` | 连续值 m/s | `velocity = 0.2m/s` |
| `load_weight` | 连续值 kg | `load_weight = 0.5kg` |

### 4.3 人际关系与社会状态

| 状态谓词 | 取值 | 示例 |
|---|---|---|
| `has_permission(entity, action)` | boolean | `has_permission(robot, enter_kitchen) = true` |
| `has_ownership(entity, object)` | boolean | `has_ownership(human_A, cup) = true` |
| `is_occupied(entity)` | boolean | `is_occupied(robot) = true`（正在执行任务） |
| `is_available(entity)` | boolean | `is_available(human) = false`（在忙） |
| `is_authorized(entity, scope)` | boolean | `is_authorized(robot, "kitchen_area") = true` |
| `proximity_to_human(entity)` | alone / nearby / crowded | `proximity_to_human(robot) = nearby` |

---

## 五、可供性谓词（Affordance Predicates）

可供性是概念可以参与的关系/功能的**抽象声明**，在编译期已知，在执行期用于推理和约束。

### 5.1 结构可供性

| 可供性 | 适用于 | 含义 |
|---|---|---|
| `support_object` | 桌子、台面、托盘、架子 | 可承托其他物体 |
| `receive_object` | 容器、袋子、箱子 | 可容纳/接收物体 |
| `contain` | 杯子、碗、桶、池塘 | 有内部容积 |
| `graspable` | 杯子、工具、水果 | 可被抓取 |
| `movable` | 椅子、箱子、小桌子 | 可被移动 |
| `flexible` | 布、绳、纸 | 可弯曲/折叠 |
| `sharp` | 刀、剪刀、锯 | 可切割 |
| `adhesive` | 胶带、胶水 | 可粘贴 |
| `magnetic` | 磁铁、铁质物体 | 可被磁力吸附 |
| `rollable` | 球、桶、轮子 | 可滚动 |
| `pivotable` | 门、盖子、铰接件 | 可绕轴转动 |
| `threaded` | 螺丝、瓶盖 | 有螺纹可旋入 |
| `elastic` | 弹簧、橡皮筋 | 可拉伸恢复 |
| `porous` | 海绵、布 | 可吸收液体 |
| `buoyant` | 空瓶、泡沫 | 可在液体中漂浮 |

### 5.2 功能可供性

| 可供性 | 适用于 | 含义 |
|---|---|---|
| `support_human_sitting` | 椅子、沙发、床 | 可承托人体坐姿 |
| `support_human_lying` | 床、沙发、地板 | 可承托人体躺姿 |
| `provides_illumination` | 灯、手电、窗户 | 可提供光照 |
| `provides_temperature_change` | 空调、暖气、冰箱 | 可改变温度 |
| `provides_airflow` | 风扇、空调、窗户 | 可提供气流 |
| `provides_sound` | 音箱、铃铛 | 可发声 |
| `provides_information` | 屏幕、书、标志 | 可提供视觉信息 |
| `allows_passage` | 门、窗、通道 | 可通行 |
| `blocks_passage` | 墙、围栏、关闭的门 | 阻挡通行 |
| `contains_fluid` | 水管、水龙头、瓶子 | 可导流/储存液体 |
| `conducts_electricity` | 电线、金属 | 可导电 |
| `wearable` | 衣服、手套、头盔 | 可穿戴在人体上 |
| `edible` | 食物、水果 | 可安全食用 |
| `drinkable` | 水、饮料、汤 | 可饮用 |
| `flammable` | 纸、木柴、酒精 | 可燃烧 |
| `fragile` | 玻璃、瓷器、屏幕 | 易碎，需轻柔操作 |

### 5.3 环境可供性

| 可供性 | 适用于 | 含义 |
|---|---|---|
| `navigable` | 地面、通道、楼梯 | 机器人可通行 |
| `work_surface` | 操作台、桌面 | 适合进行精密操作 |
| `storage_volume` | 柜子、抽屉、货架 | 可储物 |
| `rest_zone` | 充电站、停车位 | 机器人可停留 |
| `interaction_zone` | 服务台、入口 | 适合人机交互 |

---

## 六、时态关系谓词（Temporal Predicates）

### 6.1 事件时序

| 谓词 | 语义 | 示例 |
|---|---|---|
| `before(e1, e2)` | e1 发生在 e2 之前 | 「先拿杯子再接水」 |
| `after(e1, e2)` | e1 发生在 e2 之后 | 「接完水之后给我」 |
| `during(e1, e2)` | e1 发生在 e2 期间 | 「等水烧开的时候准备杯子」 |
| `overlap(e1, e2)` | e1 和 e2 时间上有重叠 | 「一边烧水一边洗杯子」 |
| `immediately_after(e1, e2)` | e1 紧接在 e2 之后 | 「放好杯子就离开」 |
| `until(e, condition)` | e 持续到 condition 成立 | 「一直拿着直到我来」 |
| `while(e, condition)` | condition 成立期间执行 e | 「趁热喝」 |

### 6.2 状态持续性

| 谓词 | 语义 | 示例 |
|---|---|---|
| `persists(s, [t1, t2])` | 状态 s 在 [t1, t2] 内持续成立 | 「灯一直亮着」 |
| `changes(s, t)` | 状态 s 在 t 时刻发生变化 | 「灯在 8 点灭了」 |
| `intermittent(s, pattern)` | 状态 s 间歇性成立 | 「灯在闪烁」 |

---

## 七、因果关系谓词（Causal Predicates）

| 谓词 | 语义 | 示例 |
|---|---|---|
| `causes(e1, e2)` | e1 导致 e2 发生 | 「按开关会亮灯」 |
| `enables(e1, e2)` | e1 使 e2 成为可能 | 「开门后才能进去」 |
| `prevents(e1, e2)` | e1 阻止 e2 发生 | 「锁上了就打不开」 |
| `requires(e, s)` | e 需要前提条件 s | 「倒水需要先有杯子」 |
| `produces(e, s)` | e 产生状态 s | 「加热使水变热」 |
| `destroys(e, s)` | e 消除状态 s | 「喝完使杯子变空」 |
| `maintains(e, s)` | e 维持状态 s | 「按住按钮保持门开」 |

---

## 八、模态与意图谓词（Modal & Intentional Predicates）

### 8.1 能力与可能性

| 谓词 | 语义 | 示例 |
|---|---|---|
| `can(entity, action)` | 实体有能力做某动作 | 「机器人能拿起杯子」 |
| `cannot(entity, action)` | 实体无能力 | 「我够不到」 |
| `possible(state)` | 状态在当前世界有可能成立 | 「可能还在桌上」 |
| `impossible(state)` | 状态不可能成立 | 「不可能在冰箱里」 |
| `certain(state)` | 状态确定成立 | 「肯定在充电站」 |

### 8.2 意图与偏好

| 谓词 | 语义 | 示例 |
|---|---|---|
| `intends(human, goal)` | 人类意图达成某目标 | 「我想喝水」 |
| `prefers(human, state)` | 人类偏好某状态 | 「我喜欢温的」 |
| `forbids(human, action)` | 人类禁止某动作 | 「别碰那个」 |
| `allows(human, action)` | 人类允许某动作 | 「可以用这个杯子」 |

### 8.3 认知状态

| 谓词 | 语义 | 示例 |
|---|---|---|
| `knows(entity, fact)` | 实体知道某事实 | 「我知道杯子在哪」 |
| `believes(entity, fact)` | 实体相信某事 | 「我以为是干净的」 |
| `uncertain(entity, fact)` | 实体对事实不确定 | 「我不确定门锁了没」 |
| `remembers(entity, event)` | 实体记得某事件 | 「我记得你放在这里了」 |
| `notices(entity, state)` | 实体注意到某状态 | 「我看到杯子在那」 |
| `understands(entity, concept)` | 实体理解某概念 | 「我明白什么是'旁边'」 |

---

## 九、社会与道义谓词（Social & Deontic Predicates）

### 9.1 所有权与责任

| 谓词 | 语义 | 示例 |
|---|---|---|
| `owns(human, object)` | 人类拥有某物 | 「这是我的杯子」 |
| `assigned_to(entity, task)` | 实体被分配了某任务 | 「你的任务是擦桌子」 |
| `responsible_for(entity, area)` | 实体负责某区域 | 「你负责厨房」 |
| `borrowed(entity, object, from)` | 实体向某人借了某物 | 「我借了他的工具」 |

### 9.2 许可与义务

| 谓词 | 语义 | 示例 |
|---|---|---|
| `permitted(entity, action, scope)` | 实体被允许做某事 | 「你可以用这把刀」 |
| `forbidden(entity, action)` | 实体被禁止做某事 | 「你不能进那间房」 |
| `obligated(entity, action)` | 实体有义务做某事 | 「你必须每天充电」 |
| `waived(entity, obligation)` | 实体的义务被免除 | 「今天不用充电」 |

### 9.3 社交交互

| 谓词 | 语义 | 示例 |
|---|---|---|
| `greeting(entity1, entity2)` | 问候 | 「你好」、「早上好」 |
| `thanking(entity1, entity2)` | 感谢 | 「谢谢」、「辛苦了」 |
| `apologizing(entity1, entity2)` | 道歉 | 「对不起」、「抱歉」 |
| `requesting(entity1, entity2, action)` | 请求 | 「请帮我拿一下」 |
| `confirming(entity, fact)` | 确认 | 「是的」、「对的」、「没错」 |
| `rejecting(entity, claim)` | 否认/拒绝 | 「不是」、「不对」、「不用」 |
| `clarifying(entity, question)` | 澄清 | 「我的意思是...」 |

---

## 十、交流与信息谓词（Communication Predicates）

| 谓词 | 语义 | 示例 |
|---|---|---|
| `tells(speaker, listener, content)` | 告知 | 「我跟你说杯子在桌上」 |
| `asks(speaker, listener, question)` | 询问 | 「杯子在哪」 |
| `answers(speaker, listener, answer)` | 回答 | 「在桌上」 |
| `instructs(speaker, listener, action)` | 指令 | 「你去拿杯子」 |
| `warns(speaker, listener, danger)` | 警告 | 「小心烫」 |
| `suggests(speaker, listener, option)` | 建议 | 「你可以用那个」 |

---

## 十一、部分-整体关系（Mereological Predicates）

| 谓词 | 语义 | 示例 | 验真条件 |
|---|---|---|---|
| `part_of(x, y)` | x 是 y 的一部分 | 「杯盖是杯子的一部分」 | 组合体检测 |
| `contains_part(y, x)` | y 包含部分 x（`part_of` 逆） | 「这个设备有三个模块」 | 部件清单匹配 |
| `members(x, group)` | x 是 group 的成员 | 「这台机器属于产线 A」 | 组/类归属 |
| `connected_parts(x, y)` | x 和 y 通过接口连接 | 「摄像头通过 USB 连接」 | 接口检测 |
| `layered_under(x, y)` | x 在 y 下方（多层结构） | 「底板在面板下面」 | 层叠顺序检测 |
| `nested_in(x, y)` | x 嵌套在 y 内部 | 「内杯在外壳里面」 | 包含检测 |

---

## 十二、量化与比较谓词（Quantitative & Comparative Predicates）

### 12.1 基础比较

| 谓词 | 语义 | 示例 |
|---|---|---|
| `greater_than(x, y, attr)` | x 的 attr 大于 y 的 attr | 「这个杯子比那个大」 |
| `less_than(x, y, attr)` | x 的 attr 小于 y 的 attr | 「这个比那个轻」 |
| `equal_to(x, y, attr)` | x 的 attr 等于 y 的 attr | 「两个一样高」 |
| `similar_to(x, y, attr_set)` | x 与 y 在指定属性上相似 | 「和这个差不多的杯子」 |
| `same_as(x, y)` | x 与 y 是同一实体 | 「这是刚才那个」 |
| `different_from(x, y)` | x 与 y 不是同一个 | 「不是那个，是另一个」 |
| `best_in(set, attr)` | set 中 attr 最好/最大的 | 「最大那个」 |
| `first_in(set, order)` | 按 order 排序的第一个 | 「最左边的」 |
| `last_in(set, order)` | 按 order 排序的最后一个 | 「最上面的」 |

### 12.2 数量表达

| 谓词 | 语义 | 示例 |
|---|---|---|
| `count(set, n)` | set 中的实体数量为 n | 「有 3 个杯子」 |
| `all(set, condition)` | set 中所有实体满足 condition | 「所有杯子都在桌上」 |
| `some(set, condition)` | set 中存在实体满足 condition | 「有些杯子是满的」 |
| `none(set, condition)` | set 中没有实体满足 condition | 「没有一个空的」 |
| `majority(set, condition)` | 大多数满足 | 「大部分杯子是干净的」 |
| `exactly(n, set, condition)` | 恰好 n 个满足 | 「正好有两个有水的」 |

---

## 十三、物理过程基础谓词（Physical Process Predicates）

用于描述不涉及机器人主动操作的物理过程。

| 谓词 | 语义 | 示例 |
|---|---|---|
| `melting(x)` | x 正在熔化 | 「冰在化」 |
| `freezing(x)` | x 正在结冰 | 「水在结冰」 |
| `boiling(x)` | x 正在沸腾 | 「水开了」 |
| `evaporating(x)` | x 正在蒸发 | 「水在蒸发」 |
| `condensing(x)` | x 正在凝结 | 「窗户上有水珠」 |
| `burning(x)` | x 正在燃烧 | 「纸着火了」 |
| `rusting(x)` | x 正在生锈 | 「铁管生锈了」 |
| `decaying(x)` | x 正在腐烂 | 「水果烂了」 |
| `growing(x)` | x 正在生长 | 「植物长高了」 |
| `flowing(x, dir)` | 液体/气体在流动 | 「水在流」 |
| `leaking(x)` | x 正在泄漏 | 「水管漏水了」 |
| `vibrating(x)` | x 正在振动 | 「手机在震」 |
| `rotating(x, axis)` | x 正在旋转 | 「风扇在转」 |
| `oscillating(x)` | x 在来回摆动 | 「钟摆在摇」 |

---

## 十四、附录：原语组合示例

以下展示认知原语如何组合覆盖复杂的自然语言表达。

### 14.1 「站到我身边」

```
事件：navigate_to
目的地角色：
  target_reference: human_speaker
  空间关系: near_human(human_speaker)
  距离阈值: 0.5m（默认社交距离）
目标末态: body_stationary ∧ near_human(executor, human_speaker)
语言适配：
  heads = ["站到", "站到...身边", "站到...旁边"]
```

### 14.2 「把螺丝拧进孔里」

```
事件：screw
角色：
  theme: 螺丝（threaded 可供性）
  target: 孔（has_slot 可供性）
目标末态: inserted_into(螺丝, 孔) ∧ threaded_engaged(螺丝, 孔)
前提：held_by(螺丝, executor) ∧ reachable(executor, 孔)
验真：扭矩达阈值 + 插入深度达标
```

### 14.3 「把菜切成片」

```
事件：cut
角色：
  theme: 菜（edible 可供性）
  tool: 刀（sharp 可供性）
目标末态：separated_into(菜, pieces) ∧ each(piece, thickness≈5mm)
前提：held_by(刀, executor) ∧ reachable(executor, 菜)
约束：thickness_constraint = "片状, ~5mm"
验真：视觉确认分离 + 厚度观察
```

### 14.4 「你站在我左边，面向我」

```
复合：
  事件1：navigate_to
    目的地: beside_human(human_speaker)
    空间关系: left_of(executor, human_speaker)
  事件2：orient_executor
    朝向: facing(executor, human_speaker)
语言适配：站到左边，面向我
```

### 14.5 「把热水倒进保温杯，盖上盖子，放在包里」

```
复合：
  事件1：pour
    角色: theme=热水（contained_in=水壶）, destination=保温杯
    前提: held_by(水壶, executor)
    效果: transferred_to(热水, 保温杯)
  事件2：screw / place_object
    角色: theme=杯盖, target=保温杯
    效果: threaded_engaged(杯盖, 保温杯)
  事件3：place_object / transport_object
    角色: theme=保温杯, destination=包
    空间关系: contained_by(保温杯, 包)
```

---

## 十五、补充说明与实施建议

### 15.1 实现优先级

| 批次 | 类别 | 包含内容 | 预估能覆盖的表达增量 |
|---|---|---|---|
| 第一批 | 空间关系 2.1-2.4 | 拓扑 + 方向 + 距离 + 人参考系 | ~+40% |
| 第二批 | 事件算子 3.2 | 身体动作 + 精细操作 + 工具 | ~+30% |
| 第三批 | 状态谓词 4 | 物体 + 机器人 + 社会状态 | ~+15% |
| 第四批 | 因果 + 时态 6-7 | before/after/causes/requires | ~+10% |
| 第五批 | 模态 + 社会 + 量化 8-12 | can/knows/owns/count | ~+5% |

### 15.2 与现有架构的集成方式

每一类原语需要三个地方的修改：

1. **`language_concept_composer.py`**：增加语言适配器（heads + 模式匹配）
2. **`rcir_primitives.py`（或新建 `spatial_predicates.py`）**：谓词类型的 schema 定义
3. **`cognitive_inquiry.py`**：当推理歧义时生成对应的 InquiryContract

### 15.3 验真条件映射

每个新谓词需要同时定义它的验真条件，写入 P016 的验真契约中：

```
near_human(executor, human_speaker):
  verification:
    - distance(executor, human_speaker) < threshold
    - human_detected_in_scene
    - executor_stationary
```

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-21 | v1 | 初稿：空间谓词 4 类 30+、事件算子 3 类 50+、状态谓词 4 类 20+、可供性 3 类 40+、时态/因果/模态/社会/量化等 |
