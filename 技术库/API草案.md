# API 草案

## 一、定位

本文定义第一阶段 MVP 的 API 草案。API 面向 Agent、机器人控制栈、工具网关、企业自动化平台、空间对象系统和未来物理 AI 执行端。

第一阶段 API 只覆盖最小闭环：

> 计划预验真 -> 动作声明 -> 来源链校验 -> 代理权预算 -> 裁决令牌 -> 动作结果回写 -> 审计查询

## 二、通用约定

### 2.1 数据格式

请求和响应默认使用 JSON。

### 2.2 通用字段

所有请求建议包含：

```json
{
  "request_id": "req_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "timestamp": "2026-06-28T12:00:00Z"
}
```

### 2.3 通用响应

```json
{
  "request_id": "req_001",
  "status": "ok",
  "reason_codes": [],
  "data": {}
}
```

## 三、计划预验真 API

### 3.1 `POST /plans/precheck`

用于在执行计划任一步骤实际执行前，对多步计划进行边界预验真。

请求：

```json
{
  "request_id": "req_plan_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "plan": {
    "plan_id": "plan_001",
    "task_goal": "organize_project_files",
    "steps": [
      {
        "step_id": "step_001",
        "action_type": "read_metadata",
        "target": "folder_A",
        "risk_level": "low"
      },
      {
        "step_id": "step_002",
        "action_type": "move_file",
        "target": "draft_file.md",
        "risk_level": "medium"
      }
    ]
  },
  "boundary_constraints": {
    "allow_direct_modify_sensitive": false,
    "max_medium_risk_actions": 3,
    "requires_confirmation_for_irreversible": true
  }
}
```

响应：

```json
{
  "request_id": "req_plan_001",
  "status": "ok",
  "data": {
    "precheck_id": "pre_001",
    "plan_id": "plan_001",
    "feasibility": "restricted",
    "violations": [
      {
        "step_id": "step_002",
        "violated_boundary": "sensitive_object_direct_modify",
        "reason_code": "candidate_state_required",
        "recommended_action": "convert_to_candidate"
      }
    ],
    "decision_hint": "limited_execute"
  }
}
```

## 四、动作声明 API

### 4.1 `POST /actions/declare`

用于在动作进入真实执行端前生成结构化动作声明。

请求：

```json
{
  "request_id": "req_action_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "action": {
    "action_id": "act_001",
    "plan_id": "plan_001",
    "step_id": "step_002",
    "action_type": "move_file",
    "target_refs": ["file_001"],
    "parameter_digest": "move_to=archive",
    "expected_outcome": "file_moved_to_archive",
    "risk_level": "medium",
    "rollback_capability": "full"
  },
  "context": {
    "context_id": "ctx_001",
    "object_sensitivity": "medium",
    "user_intent": "organize_project_files"
  }
}
```

响应：

```json
{
  "request_id": "req_action_001",
  "status": "ok",
  "data": {
    "action_declaration_id": "decl_001",
    "action_id": "act_001",
    "normalized_risk_level": "medium",
    "requires_provenance_check": true,
    "requires_budget_check": true
  }
}
```

## 五、来源链 API

### 5.1 `POST /provenance/verify`

用于验证动作来源链完整性、可信性和一致性。

请求：

```json
{
  "request_id": "req_src_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "action_id": "act_001",
  "source_chain": {
    "source_chain_id": "src_001",
    "root_authorization_ref": "auth_001",
    "parent_task_ref": "task_001",
    "input_sources": ["user_command_001"],
    "tool_reason_ref": "reason_001",
    "previous_decision_refs": ["pre_001"],
    "chain_hash": "hash_value"
  }
}
```

响应：

```json
{
  "request_id": "req_src_001",
  "status": "ok",
  "data": {
    "source_chain_id": "src_001",
    "integrity_state": "verified",
    "trust_state": "trusted",
    "risk_labels": [],
    "reason_codes": ["root_authorization_valid", "input_source_trusted"]
  }
}
```

## 六、代理权预算 API

### 6.1 `POST /agency-budget/evaluate`

用于判断当前动作是否适配代理权预算，并输出预算裁决。

请求：

```json
{
  "request_id": "req_budget_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "budget_id": "budget_001",
  "action": {
    "action_id": "act_001",
    "action_type": "move_file",
    "risk_level": "medium",
    "target_scope": "project_folder"
  }
}
```

响应：

```json
{
  "request_id": "req_budget_001",
  "status": "ok",
  "data": {
    "budget_decision_id": "budget_decision_001",
    "budget_state": "active_after_deduction",
    "decision": "allow_with_deduction",
    "deductions": {
      "medium_risk_actions": 1
    },
    "remaining": {
      "medium_risk_actions": 2
    },
    "reason_codes": ["budget_sufficient"]
  }
}
```

## 七、裁决令牌 API

### 7.1 `POST /decision/issue`

用于合并计划预验真、来源链、预算和治理规则结果，生成最终裁决令牌。

请求：

```json
{
  "request_id": "req_decision_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "action_id": "act_001",
  "precheck_ref": "pre_001",
  "source_chain_state": "verified",
  "budget_decision": "allow_with_deduction",
  "governance_context": {
    "object_sensitivity": "medium",
    "confirmation_required": false
  }
}
```

响应：

```json
{
  "request_id": "req_decision_001",
  "status": "ok",
  "data": {
    "decision_token_id": "dt_001",
    "action_id": "act_001",
    "decision": "limited_allow",
    "allowed_parameters": {
      "execution_state": "candidate_or_reversible"
    },
    "expires_at": "2026-06-28T12:05:00Z",
    "reason_codes": ["source_verified", "budget_ok", "restricted_by_precheck"],
    "audit_ref": "audit_001"
  }
}
```

## 八、动作结果回写 API

### 8.1 `POST /experience/record`

用于将动作执行后果写入经验库。

请求：

```json
{
  "request_id": "req_exp_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "action_id": "act_001",
  "context_id": "ctx_001",
  "decision_token_id": "dt_001",
  "outcome": {
    "outcome_type": "success",
    "state_delta": "file_moved_to_archive",
    "error": null
  },
  "human_feedback": null
}
```

响应：

```json
{
  "request_id": "req_exp_001",
  "status": "ok",
  "data": {
    "experience_id": "exp_001",
    "audit_ref": "audit_001",
    "record_state": "stored"
  }
}
```

## 九、审计查询 API

### 9.1 `GET /audit/{audit_id}`

用于查询任务、计划、动作、裁决和经验记录的审计摘要。

响应：

```json
{
  "audit_id": "audit_001",
  "tenant_id": "tenant_001",
  "actor_id": "actor_001",
  "plan_id": "plan_001",
  "action_id": "act_001",
  "precheck_state": "restricted",
  "source_chain_state": "verified",
  "budget_state": "active_after_deduction",
  "decision": "limited_allow",
  "outcome": "success",
  "experience_ref": "exp_001",
  "timestamp": "2026-06-28T12:00:05Z"
}
```

## 十、第一阶段 API 优先级

第一阶段必须实现：

1. `POST /plans/precheck`
2. `POST /actions/declare`
3. `POST /provenance/verify`
4. `POST /agency-budget/evaluate`
5. `POST /decision/issue`
6. `POST /experience/record`
7. `GET /audit/{audit_id}`

第一阶段暂缓实现：

1. 人类真实意图验真 API。
2. 物理控制因果验真 API。
3. 保护策略声明 API。
4. 多主体空间治理 API。
5. 偏好迁移 API。
6. 补救经验检索 API。

这些可在第二阶段接入。

