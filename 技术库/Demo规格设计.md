# Demo 规格设计：文件与空间对象整理 Agent

## 一、Demo 目标

本 Demo 用于验证第一阶段最小闭环：

> 任务输入 -> 执行计划 -> 计划预验真 -> 来源链校验 -> 代理权预算 -> 裁决令牌 -> 动作执行 -> 经验记录 -> 审计摘要

Demo 不追求复杂 UI，不追求强规划模型，不追求机器人控制。重点是证明自动化执行体在真实数字环境中执行动作前，可以被计划边界、来源链和代理权预算共同治理，并在执行后形成经验和审计证据。

## 二、Demo 场景

场景名称：

> 项目资料整理 Agent

用户任务：

> 整理项目资料，把说明文档归类，把临时文件移到归档区，把涉及权限、专利、合同或敏感内容的文件只生成候选操作，不要直接修改；来源不明的文件不要自动处理。

执行环境：

1. 一个真实目录或模拟对象集合。
2. 若为真实目录，系统只允许在指定 demo 工作区内操作。
3. 高风险文件不直接移动，只生成候选操作记录。

## 三、样例对象集合

### 3.1 输入对象

```json
[
  {
    "object_id": "file_001",
    "name": "项目说明书.md",
    "object_type": "markdown",
    "path": "inbox/项目说明书.md",
    "semantic_labels": ["specification", "project_doc"],
    "sensitivity_level": "low",
    "source_state": "trusted",
    "allowed_actions": ["read", "move", "tag"]
  },
  {
    "object_id": "file_002",
    "name": "临时记录.txt",
    "object_type": "text",
    "path": "inbox/临时记录.txt",
    "semantic_labels": ["temporary_note"],
    "sensitivity_level": "low",
    "source_state": "trusted",
    "allowed_actions": ["read", "move", "tag"]
  },
  {
    "object_id": "file_003",
    "name": "专利权利要求草稿.md",
    "object_type": "markdown",
    "path": "inbox/专利权利要求草稿.md",
    "semantic_labels": ["patent_claim", "draft"],
    "sensitivity_level": "high",
    "source_state": "trusted",
    "allowed_actions": ["read", "candidate_tag"]
  },
  {
    "object_id": "file_004",
    "name": "合同扫描件.pdf",
    "object_type": "pdf",
    "path": "inbox/合同扫描件.pdf",
    "semantic_labels": ["contract", "legal"],
    "sensitivity_level": "high",
    "source_state": "trusted",
    "allowed_actions": ["read", "candidate_tag"]
  },
  {
    "object_id": "file_005",
    "name": "未知来源资料.docx",
    "object_type": "docx",
    "path": "inbox/未知来源资料.docx",
    "semantic_labels": ["unknown"],
    "sensitivity_level": "unknown",
    "source_state": "unverified",
    "allowed_actions": ["read_metadata"]
  }
]
```

### 3.2 目标分区

```json
[
  {
    "region_id": "region_docs",
    "name": "说明文档区",
    "path": "organized/docs",
    "allowed_sensitivity": ["low", "medium"]
  },
  {
    "region_id": "region_archive",
    "name": "归档区",
    "path": "organized/archive",
    "allowed_sensitivity": ["low"]
  },
  {
    "region_id": "region_candidates",
    "name": "候选操作区",
    "path": "organized/candidates",
    "allowed_sensitivity": ["medium", "high", "unknown"]
  }
]
```

## 四、治理规则

### 4.1 规则列表

```json
[
  {
    "rule_id": "rule_001",
    "name": "低风险说明文档可直接移动",
    "condition": {
      "sensitivity_level": ["low"],
      "semantic_labels_any": ["specification", "project_doc"],
      "source_state": "trusted"
    },
    "action_policy": {
      "move": "allow",
      "target_region": "region_docs"
    }
  },
  {
    "rule_id": "rule_002",
    "name": "低风险临时文件可归档",
    "condition": {
      "sensitivity_level": ["low"],
      "semantic_labels_any": ["temporary_note"],
      "source_state": "trusted"
    },
    "action_policy": {
      "move": "allow",
      "target_region": "region_archive"
    }
  },
  {
    "rule_id": "rule_003",
    "name": "高敏文件不得自动正式移动",
    "condition": {
      "sensitivity_level": ["high"]
    },
    "action_policy": {
      "move": "candidate_only",
      "confirmation_required": true
    }
  },
  {
    "rule_id": "rule_004",
    "name": "来源不明文件不得自动处理",
    "condition": {
      "source_state": "unverified"
    },
    "action_policy": {
      "move": "block",
      "tag": "block",
      "read_metadata": "allow"
    }
  }
]
```

### 4.2 代理权预算

```json
{
  "budget_id": "budget_demo_001",
  "actor_id": "agent_demo_001",
  "authorized_scope": ["demo_workspace"],
  "tool_budget": {
    "read_metadata": 20,
    "move_file": 3,
    "candidate_tag": 5
  },
  "risk_budget": {
    "low": 10,
    "medium": 3,
    "high": 0
  },
  "autonomy_level": "limited",
  "revocation_conditions": [
    "source_chain_break",
    "high_risk_direct_modify_attempt",
    "budget_exhausted"
  ]
}
```

## 五、预期执行计划

```json
{
  "plan_id": "plan_demo_001",
  "actor_id": "agent_demo_001",
  "task_goal": "organize_project_materials",
  "steps": [
    {
      "step_id": "step_001",
      "action_type": "read_metadata",
      "target": "inbox",
      "risk_level": "low"
    },
    {
      "step_id": "step_002",
      "action_type": "move_file",
      "target": "file_001",
      "target_region": "region_docs",
      "risk_level": "low"
    },
    {
      "step_id": "step_003",
      "action_type": "move_file",
      "target": "file_002",
      "target_region": "region_archive",
      "risk_level": "low"
    },
    {
      "step_id": "step_004",
      "action_type": "move_file",
      "target": "file_003",
      "target_region": "region_docs",
      "risk_level": "high"
    },
    {
      "step_id": "step_005",
      "action_type": "candidate_tag",
      "target": "file_004",
      "target_region": "region_candidates",
      "risk_level": "medium"
    },
    {
      "step_id": "step_006",
      "action_type": "move_file",
      "target": "file_005",
      "target_region": "region_archive",
      "risk_level": "unknown"
    }
  ]
}
```

## 六、预期计划预验真结果

```json
{
  "precheck_id": "pre_demo_001",
  "plan_id": "plan_demo_001",
  "feasibility": "restricted",
  "violations": [
    {
      "step_id": "step_004",
      "violated_boundary": "high_sensitivity_direct_modify",
      "reason_code": "candidate_state_required",
      "recommended_action": "convert_move_to_candidate_tag"
    },
    {
      "step_id": "step_006",
      "violated_boundary": "unverified_source",
      "reason_code": "source_chain_required",
      "recommended_action": "block_or_verify_source"
    }
  ],
  "allowed_steps": ["step_001", "step_002", "step_003", "step_005"],
  "restricted_steps": ["step_004"],
  "blocked_steps": ["step_006"]
}
```

## 七、预期裁决结果

### 7.1 step_002

文件：`项目说明书.md`

预期裁决：

```json
{
  "action_id": "act_step_002",
  "decision": "allow",
  "reason_codes": ["low_risk", "source_verified", "budget_sufficient"],
  "execution_mode": "formal"
}
```

### 7.2 step_003

文件：`临时记录.txt`

预期裁决：

```json
{
  "action_id": "act_step_003",
  "decision": "allow",
  "reason_codes": ["low_risk", "archive_allowed", "budget_sufficient"],
  "execution_mode": "formal"
}
```

### 7.3 step_004

文件：`专利权利要求草稿.md`

预期裁决：

```json
{
  "action_id": "act_step_004",
  "decision": "limited_allow",
  "reason_codes": ["high_sensitivity", "candidate_state_required"],
  "execution_mode": "candidate_only"
}
```

### 7.4 step_005

文件：`合同扫描件.pdf`

预期裁决：

```json
{
  "action_id": "act_step_005",
  "decision": "limited_allow",
  "reason_codes": ["high_sensitivity", "candidate_tag_allowed"],
  "execution_mode": "candidate_only"
}
```

### 7.5 step_006

文件：`未知来源资料.docx`

预期裁决：

```json
{
  "action_id": "act_step_006",
  "decision": "block",
  "reason_codes": ["source_unverified", "source_chain_required"],
  "execution_mode": "none"
}
```

## 八、预期真实动作

真实数字环境中允许执行：

1. 将 `项目说明书.md` 移动到 `organized/docs/`。
2. 将 `临时记录.txt` 移动到 `organized/archive/`。
3. 为 `专利权利要求草稿.md` 生成候选操作记录，不移动原文件。
4. 为 `合同扫描件.pdf` 生成候选操作记录，不移动原文件。
5. 对 `未知来源资料.docx` 仅记录阻断原因，不移动、不改名、不打标签。

## 九、候选操作记录

```json
[
  {
    "candidate_id": "cand_001",
    "source_object": "file_003",
    "proposed_action": "move_file",
    "proposed_target_region": "region_docs",
    "status": "pending_confirmation",
    "reason_codes": ["high_sensitivity", "human_confirmation_required"]
  },
  {
    "candidate_id": "cand_002",
    "source_object": "file_004",
    "proposed_action": "tag_as_legal",
    "status": "pending_confirmation",
    "reason_codes": ["high_sensitivity", "candidate_tag_allowed"]
  }
]
```

## 十、经验记录样例

```json
[
  {
    "experience_id": "exp_001",
    "context_ref": "ctx_demo_001",
    "action_ref": "act_step_002",
    "outcome": {
      "outcome_type": "success",
      "state_delta": "file_001_moved_to_docs"
    },
    "decision_ref": "dt_step_002",
    "created_at": "2026-06-28T12:00:00Z"
  },
  {
    "experience_id": "exp_002",
    "context_ref": "ctx_demo_001",
    "action_ref": "act_step_006",
    "outcome": {
      "outcome_type": "blocked",
      "state_delta": "no_change",
      "reason": "source_unverified"
    },
    "decision_ref": "dt_step_006",
    "created_at": "2026-06-28T12:00:03Z"
  }
]
```

## 十一、审计摘要样例

```json
{
  "audit_id": "audit_demo_001",
  "task_goal": "organize_project_materials",
  "actor_id": "agent_demo_001",
  "plan_id": "plan_demo_001",
  "precheck_ref": "pre_demo_001",
  "summary": {
    "total_steps": 6,
    "allowed": 2,
    "limited_allowed": 2,
    "blocked": 1,
    "metadata_only": 1
  },
  "source_chain_state": "verified_except_step_006",
  "budget_state": {
    "move_file_remaining": 1,
    "candidate_tag_remaining": 3,
    "high_risk_remaining": 0
  },
  "executed_actions": ["act_step_002", "act_step_003"],
  "candidate_actions": ["act_step_004", "act_step_005"],
  "blocked_actions": ["act_step_006"],
  "experience_refs": ["exp_001", "exp_002"],
  "created_at": "2026-06-28T12:00:05Z"
}
```

## 十二、演示脚本

1. 展示输入对象集合。
2. 输入用户任务。
3. 展示系统生成的执行计划。
4. 展示计划预验真结果。
5. 展示每一步来源链和预算裁决。
6. 执行低风险动作。
7. 展示高风险动作转候选态。
8. 展示来源不明动作被阻断。
9. 展示经验记录。
10. 展示审计摘要。

## 十三、Demo 证明点

该 Demo 证明：

1. 自动化执行体不是直接执行计划，而是先经过边界预验真。
2. 来源链和代理权预算能够影响动作准入。
3. 敏感对象可被转为候选态，而不是直接正式修改。
4. 来源不明对象可被阻断。
5. 动作后果可以回写成经验。
6. 审计摘要能够串联计划、裁决和后果。

## 十四、后续扩展

该 Demo 跑通后，可扩展到：

1. 三维空间对象整理。
2. 智能家居设备控制。
3. Agent 工具调用治理。
4. 云运维计划预验真。
5. 机器人低风险物理动作治理。

