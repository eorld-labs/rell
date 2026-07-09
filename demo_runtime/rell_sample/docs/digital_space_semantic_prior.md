# Digital Space Semantic Prior

本文说明第一阶段数字厨房空间与 P010 空间语义自动生成方案的对应关系。

## P010 工程口径

P010 的核心链路是：

```text
外部视觉输入 / 虚拟相机画面 / 既有空间表达
-> 空间语义信息
-> 空间语义先验
-> 端侧加载
-> 主体侧空间认知模型
```

本样品暂不实现真实视觉识别，也不要求完整三维重建。第一阶段直接提供一份可解释的数字厨房语义先验，用于验证 RELL 后续调试环境的数据形态。

## 文件对应

| 文件 | 作用 | 对应 P010 特征 |
|---|---|---|
| `schemas/space_semantic_prior.schema.json` | 定义空间语义先验结构 | 语义区域集合、空间关系集合、端侧转换信息 |
| `data/digital_kitchen_semantic_prior.json` | 数字厨房空间语义先验 | 区域功能属性、空间关系、权限标识、适配主体类型 |
| `digital_space.py` | 端侧内化逻辑 | 将空间语义先验转换为主体侧空间认知模型 |
| `data/digital_kitchen_cognitive_model.json` | 模拟执行体认知模型 | 空间区域表、空间行动图、风险区域表、对象-区域索引 |
| `validate_digital_space.py` | 验收脚本 | 验证先验结构和内化结果可复现 |

## 与 RELL/P016 的关系

数字空间不是替代 P016 Runtime，也不是机器人底层执行模型。其作用是为 Runtime 提供空间上下文：

```text
P010 数字空间语义先验
-> simulated_robot 主体侧空间认知模型
-> RELL 准入、绑定、执行和审计使用的空间上下文
-> P016 过程模板在该空间中执行
```

第一阶段倒水任务使用的关键空间绑定包括：

- `CUP_OBJECT -> object_cup_white_mug`
- `KETTLE_OBJECT -> object_kettle_steel_1l`
- `CAMERA_SENSOR -> sensor_depth_front`
- `POUR_OPERATION_REGION -> region_counter_operation`
- `WALKABLE_REGION -> region_floor_walkway`

后续可以在该数字空间内继续加入移动、抓取、端水、放置、恢复和经验回写。运行时获得真实机器人或仿真反馈后，可以把不一致区域标记为待验证，并更新空间语义先验或主体侧空间认知模型。

## 会做与不会做

页面和 API 已接入规则式翻译层。第一阶段翻译层只承担结构化任务意图生成，不承担自由规划或机器人控制。

当前支持：

- `给客人倒一杯水`：命中 `pour_water`，进入空间准入和 P016 Runtime。
- `去楼下拿个快递`：识别为长程多过程任务，输出 `cannot_do`，不创建过程实例。
- `走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水`：识别为多过程任务链，保留 `move_to_counter -> pick_up_cup -> move_to_water_source -> fill_cup_at_water_source -> pour_water` 的候选链路，但第一阶段不执行，以避免将前置动作错误压缩为单一倒水过程。
- 涉及 `炉灶`、`火`、`热源` 的任务：识别为风险区域任务，阻断执行。

该机制用于证明 RELL 的可控性：技能库中有经验且空间条件满足时执行；技能库未覆盖或空间风险不允许时，系统明确输出不会做或阻断，而不是猜测执行。
