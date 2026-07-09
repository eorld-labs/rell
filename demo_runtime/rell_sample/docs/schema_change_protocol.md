# Schema Change Protocol

阶段零的 Schema 冻结不是禁止变更，而是禁止未经记录和校验的隐式变更。

## 版本规则

- `minor` 版本递增：允许新增可选字段，旧数据仍可运行。
- `major` 版本递增：字段语义变化、必填字段变化或删除字段，旧数据必须重新生成。

## 变更条件

任何 Schema 或样例数据变更必须同时满足：

1. 更新对应 JSON Schema 或数据文件。
2. 更新 `schema_version`。
3. 更新受影响的 Mock JSON。
4. 运行 `python .\demo_runtime\rell_sample\validate_stage_zero.py` 并通过。
5. 在研发记录中说明变更原因、影响范围和对应技术特征。

## 快照与日志边界

- `stage_runtime_state` 是当前状态快照，供 Runtime、状态查询和验真窗口读取。
- `execution_trace` 是追加写日志，供审计、问题复盘和经验回写使用。

同一字段不应无理由同时成为快照字段和日志字段。若某个数据既需要当前值又需要历史轨迹，应在快照中保存最新值，在日志中保存事件来源和变化过程。
