# RELL Sample API Contract

第一阶段对外仍以运行、准入和审计为主；经验教学接口作为样品学习闭环的最小入口，暂不扩展为通用规划或模板学习 API。自因果链最小实现起，`/process/run` 在检测到目标因果事实时，会优先通过因果层反向搜索形成过程链，而不是要求每一种自然语言任务都枚举为独立经验。

## POST /process/admit

用途：执行“会不会做”的最小准入判断。

请求体第一阶段可为空。Runtime 仅检查规则映射、过程实例、偶然绑定和 Adapter 能力。

响应示例：

```json
{
  "schema_version": "1.0.0",
  "task_id": "task_pour_water_001",
  "allowed": true,
  "decision": "allowed"
}
```

## POST /process/run

用途：异步任务接口的样品占位。第一阶段为了演示直接同步返回结果，但响应中保留 `task_id`。

请求示例：

```json
{
  "scenario": "simulated_success"
}
```

可选场景：

- `simulated_success`
- `simulated_no_water`
- `simulated_channel_conflict`
- `success`
- `no_flow`
- `channel_conflict`

`simulated_*` 场景由 SimulatedRobotAdapter 根据阶段动作生成连续状态变量；其余场景为固定 Mock 时间轴，用于回归对照。

当输入为 `到水源处接一杯水` 时，翻译层输出目标因果事实 `cup_contains_water`。编排层基于当前空间事实和过程事实注册表反向补齐前提事实，生成：

```text
move_to_counter -> pick_up_cup -> move_to_water_source -> fill_cup_at_water_source
```

当输入为 `走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水` 时，目标因果事实为 `water_poured`，系统生成：

```text
move_to_counter -> pick_up_cup -> move_to_water_source -> fill_cup_at_water_source -> move_to_counter -> pour_water
```

响应中的 `intent_translation.causal_plan` 会给出初始事实、最终事实、推导过程和生成的过程链。

## GET /audit/{task_id}

用途：查询最近一次运行写入内存的审计摘要。

第一阶段审计数据为进程内存存储，后续再替换为文件或数据库。

## POST /experience/teach

用途：当翻译层识别出多过程任务链但当前技能库不会执行时，接收人工教学步骤并生成候选经验。

请求示例：

```json
{
  "utterance": "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
  "steps": "走向操作台\n拿起杯子\n到水源处\n接一杯水\n倒水"
}
```

第一阶段采用轻量规则映射表解析教学步骤，不调用通用规划器，不自动生成新的 P016 过程模板。生成的经验链先标记为数字空间可回放经验，后续再进入人工审核、真机验证或模板化沉淀。若同一输入已经能被目标因果事实和因果层求解，则运行时优先采用因果求解结果，教学经验作为候选经验和审计依据保留。

## POST /experience/dialogue-teach

用途：接收自然语言形式的对话教学内容，并复用教学步骤解析器生成候选经验。

请求示例：

```json
{
  "utterance": "走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水",
  "message": "教你：走向操作台，然后拿起杯子，到水源处接一杯水，然后倒水"
}
```

该接口仍采用轻量规则映射表，不引入大模型推理；其意义在于证明用户可通过对话式输入触发经验形成，而不是必须编辑结构化 JSON。

自因果签名实现起，对话教学会在经验记录中同步生成 `causal_signature`：

```json
{
  "requires_facts": ["executor_at_counter", "cup_at_counter", "gripper_empty"],
  "produces_fact": "cup_contains_water",
  "destroys_facts": ["cup_empty"],
  "expands_to": ["pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"]
}
```

例如输入：

```text
教你一个技能：接一杯水需要先拿杯子，再去水源处接水。接完以后杯子里有水。
```

系统会将“需要先”之后的内容解析为前置过程，将“接完以后杯子里有水”解析为目标因果事实说明，并把该经验作为可被因果编排器读取的过程能力。后续用户说 `帮我接水` 时，系统可以从 `cup_contains_water` 反向搜索并调用该教学经验签名，而不是匹配原始教学语句。

## GET /experience/library

用途：查询当前样品经验库。

经验库第一阶段存储在 `demo_runtime/rell_sample/data/experience_library.json`，用于演示“不会做 -> 人工教学 -> 经验形成 -> 数字执行体回放”的最小闭环。

## 调试接口

`GET /process/status/{task_id}` 为调试接口，不作为对外承诺接口。

## 验收命令

```powershell
python .\demo_runtime\rell_sample\run_all_checks.py
```
