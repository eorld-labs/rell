# Admission Rules

第一阶段准入判断只做明确规则，不做相似度检索。

## 规则映射

以下输入映射到 `process_template: pour_water`：

- `倒水`
- `倒一杯水`
- `给客人倒水`
- `给客人倒一杯水`

默认绑定：

- `home_a_kitchen_daytime`

## 准入检查

1. 是否命中规则映射。
2. 是否存在 `pour_water` 过程模板。
3. 是否存在家庭 A 偶然绑定。
4. 是否存在目标事实 `cup_has_water` 的双通道验真定义。
5. Robot Adapter 是否报告最小能力词汇表。

## 不会做输出

若任一检查失败，Runtime 不进入真实执行，输出：

- `allowed: false`
- 缺失项列表
- 待标定或待共创任务

## 人工确认

双通道冲突时不做自动融合。Runtime 进入 `awaiting_human_confirmation`，调用 `request_human_confirmation()`。操作员选择继续后，Runtime 从最新快照重新进入验真窗口；选择停止时调用 `stop(reason="manual_stop")`。
