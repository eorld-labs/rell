# RELL Sample API Contract

第一阶段对外仍以运行、准入和审计为主；经验教学接口作为样品学习闭环的最小入口，暂不扩展为通用规划或模板学习 API。

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

第一阶段采用轻量规则映射表解析教学步骤，不调用通用规划器，不自动生成新的 P016 过程模板。生成的经验链先标记为数字空间可回放经验，后续再进入人工审核、真机验证或模板化沉淀。

## GET /experience/library

用途：查询当前样品经验库。

经验库第一阶段存储在 `demo_runtime/rell_sample/data/experience_library.json`，用于演示“不会做 -> 人工教学 -> 经验形成 -> 数字执行体回放”的最小闭环。

## 调试接口

`GET /process/status/{task_id}` 为调试接口，不作为对外承诺接口。

## 验收命令

```powershell
python .\demo_runtime\rell_sample\run_all_checks.py
```
