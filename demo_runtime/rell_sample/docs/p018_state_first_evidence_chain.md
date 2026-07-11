# P018 状态优先任务交互仲裁工程证据链

日期：2026-07-11

## 一、对应方案

本证据链对应 P018《一种面向自动化执行体的状态优先任务交互仲裁方法及系统》。

工程样品的主链为：

`交互输入 -> 读取任务期运行时世界状态快照 -> 状态查询/任务控制分流 -> 运行时事件仲裁 -> 基于当前事实续推/裁剪 -> 执行控制链路 -> 快照释放或恢复记录`

该主链与 P018 权利要求 1 的必要特征保持一致，并通过 API、页面显示、数据记录和验证脚本形成可复核证据。

## 二、权利要求特征与工程落点

| P018 特征 | 工程落点 | 证据文件 |
|---|---|---|
| 自动化执行体处于任务执行期间时接收交互输入 | `/agent/query`、`/process/run`、页面任务输入和状态提问入口 | `api_server.py`、`docs/api_contract.md` |
| 改变执行控制行为前读取任务期运行时世界状态快照 | `get_active_runtime_snapshot`、`run_process_with_runtime_context`、`build_llm_context_view` | `api_server.py` |
| 状态查询输入/任务控制输入分流 | `build_semantic_request_frame`、`resolve_runtime_state_query`、`concept_core/query_router.py` | `api_server.py`、`concept_core/` |
| 状态查询不触发执行控制链路改变 | `/runtime_world_state/query`、`/agent/query` 状态查询路径，回答来源限定为当前快照 | `api_server.py`、`validate_api_sample.py` |
| 任务控制输入输出仲裁结果 | `arbitrate_runtime_event`、`build_runtime_event_arbitration_result`，输出继续、暂停、切换、合并、终止或人工确认 | `api_server.py` |
| 基于当前事实生成后续待执行步骤集合 | `project_process_chain_against_runtime_world_state`、`step_already_satisfied_in_runtime_world_state` | `api_server.py` |
| 排除已满足执行前提、已完成执行或目标事实已成立步骤 | “拿起杯子后再接水”从当前持物状态续推，不回到操作台重新拿杯 | `validate_api_sample.py` |
| 交由执行控制链路继续执行 | `/execution/dispatch`、`run_process_chain_experience`、本地 digital executor trace | `api_server.py`、`run_all_checks.py` |
| 任务完成/取消/终止/释放条件成立时释放快照 | `/runtime_world_state/release`、释放后状态查询返回 `snapshot_released` | `api_server.py`、`validate_api_sample.py` |
| 分布式/接口/SDK 形态不改变主链 | API 合同中将云端候选、端侧概念、执行控制接口均限定为候选或接口层 | `docs/api_contract.md`、`docs/adapter_contract.md` |

## 三、从权防御点与工程落点

| 从权方向 | 工程证据 |
|---|---|
| 权 2：任务执行、状态查询、教学、澄清、中断、恢复、切换、约束追加输入 | `build_semantic_request_frame` 区分 `state_query`、`teaching`、`task_execution`、`clarification`；`validate_api_sample.py` 覆盖状态问答、教学、切换、暂停和澄清 |
| 权 3：快照字段和生命周期 | `runtime_world_state_snapshot` 包含执行体位置、持有对象、已成立事实、当前步骤、目标事实、偏好约束、扰动、恢复记录；释放接口验证生命周期 |
| 权 5：持物状态下的新任务切换确认 | `arbitrate_runtime_event` 在当前持物且新目标未落地时输出 `request_human_confirmation` |
| 权 6：当前事实裁剪 | `project_process_chain_against_runtime_world_state` 依据当前事实、持物状态、对象状态和目标事实裁剪候选链 |
| 权 7：暂停恢复以恢复时刻快照为起点 | `readapt_runtime_conflict`、恢复记录库和 P014 验证脚本保留恢复入口和当前事实 |
| 权 8：教学/约束先候选化再仲裁 | `concept_core/teaching_frames.py` 拆分目标约束、过程约束、偏好约束和变通授权；候选内容不得直接执行 |
| 权 9：系统单元和分布式数据流 | HTTP API、事件/状态存储、执行控制接口、云脑候选接口共同验证单元化实现 |
| 权 10：电子设备/仲裁控制装置 | 样品以 Python 服务运行，处理器执行程序指令完成方法流程，验证脚本作为可执行证据 |

## 四、云脑候选与端侧概念边界

本次工程样品新增 `concept_core/` 模块，提供端侧概念内化的第一版工程骨架：

- `concept_units.py`：高频状态概念，例如杯中液体状态、当前位置、当前动作、下一步；
- `action_units.py`：高频动作概念，例如到操作台、拿起杯子、到水源处、接水、倒水；
- `concept_bridge.py`：将任务语义、空间约束、对象约束和概念候选桥接到编排层；
- `cloud_recall.py`：当端侧概念缺口存在时生成云脑候选包。

边界原则：

1. 端侧概念只提供候选概念、候选目标事实、候选过程链或状态查询映射；
2. 云脑候选只提供候选概念、候选过程链和澄清问题；
3. 二者均设置 `direct_execution_allowed=false`；
4. 二者均要求 `must_reenter_orchestration_layer=true`；
5. 候选内容不得直接写入任务期运行时世界状态快照中的已成立事实。

该边界对应 P018 说明书中“云端候选服务、端侧概念内化不直接取得执行权”的实施方式。

## 五、状态优先工程场景

### 1. 拿起杯子后继续接水

场景：先执行“拿起杯子”，再输入“到水源处接一杯水”。

工程行为：

1. 系统读取当前任务期快照；
2. 发现 `cup_in_gripper` 或当前持有对象已成立；
3. 将候选链中的拿杯步骤裁剪；
4. 从当前状态继续到水源处并接水。

对应 P018 特征：基于当前事实生成后续待执行步骤集合，而不是从任务初始状态重跑。

### 2. 中途叫停

场景：活动任务中输入“别做了”。

工程行为：

1. 语义层识别为中断事件；
2. 事件进入运行时仲裁；
3. 系统输出暂停当前任务，并保留当前持物状态和任务期事实；
4. 不直接释放或重置当前世界状态。

对应 P018 特征：任务控制输入经快照仲裁后才改变执行控制链路。

### 3. 当前持物下切换未知任务

场景：当前持有杯子，输入“去给我拿苹果”。

工程行为：

1. 系统识别为新目标切换表达；
2. 读取当前持物状态；
3. 因新目标对象、区域或目标状态未在快照中确认，输出 `request_human_confirmation`；
4. 不直接丢弃当前杯子，也不直接启动未知任务。

对应 P018 特征：持物状态下的新任务目标未确认时请求人工确认或暂停。

### 4. 偶然扰动与重适配

场景：移动到水源处前注入可绕行或阻断扰动。

工程行为：

1. 步骤前预检读取任务期快照和扰动状态；
2. 可绕行时标记 `local_detour` 并保留主链；
3. 阻断时输出 `readaptation_required`，生成恢复记录；
4. 恢复记录进入独立恢复库，可按任务或记录 ID 查询。

对应 P018/P014/P017 关系：P018 负责事件仲裁入口，P014/P017 负责恢复和迁移适配证据。

## 六、验证脚本

已通过的验证命令：

```powershell
python run_all_checks.py
```

覆盖结果：

- `validate_api_sample.py`：状态查询、任务执行、概念晋升、云脑候选、状态释放、运行时仲裁；
- `validate_p014_execution_recovery.py`：恢复记录、再适配、恢复库查询；
- `validate_p015_preference_alignment.py`：偏好约束进入任务期快照并影响执行；
- `validate_p017_minimal_loop.py`：任务期快照在迁移适配中的生成、使用和释放；
- HTTP smoke：页面、API、云脑候选、恢复库、偏好库、执行控制接口联通。

## 七、提交结论

本次提交不是单点功能提交，而是 P018 工程证据链提交：

1. 将“状态优先”落实为任务入口的第一判断规则；
2. 将状态查询与任务控制输入拆成不同控制路径；
3. 将新任务、中断、持物切换、偶然扰动统一纳入运行时事件仲裁；
4. 将当前事实裁剪、恢复记录和快照释放做成可验证数据链；
5. 将端侧概念和云脑候选限制为候选层，禁止绕过编排层直接执行。

后续开发可在该基线上继续推进端侧概念内化的形成、复用、失败回退和云脑候选召回策略。
