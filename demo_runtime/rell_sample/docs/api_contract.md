# RELL Sample API Contract

第一阶段只保留三个外部 API，避免 API 先行绑架 Runtime Core。

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
  "scenario": "success"
}
```

可选场景：

- `success`
- `no_flow`
- `channel_conflict`

## GET /audit/{task_id}

用途：查询最近一次运行写入内存的审计摘要。

第一阶段审计数据为进程内存存储，后续再替换为文件或数据库。

## 调试接口

`GET /process/status/{task_id}` 为调试接口，不作为对外承诺接口。

## 验收命令

```powershell
python .\demo_runtime\rell_sample\run_all_checks.py
```
