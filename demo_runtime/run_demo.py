from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WORKSPACE = ROOT / "workspace"
OUTPUT_DIR = ROOT / "output"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items}


def match_condition(obj: dict[str, Any], condition: dict[str, Any]) -> bool:
    if "sensitivity_level" in condition and obj.get("sensitivity_level") not in condition["sensitivity_level"]:
        return False
    if "source_state" in condition and obj.get("source_state") != condition["source_state"]:
        return False
    if "semantic_labels_any" in condition:
        labels = set(obj.get("semantic_labels", []))
        if not labels.intersection(condition["semantic_labels_any"]):
            return False
    return True


def matching_rules(obj: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rule for rule in rules if match_condition(obj, rule.get("condition", {}))]


def build_action_declaration(step: dict[str, Any], plan: dict[str, Any], obj: dict[str, Any] | None) -> dict[str, Any]:
    target_refs = [step["target"]] if step.get("target", "").startswith("file_") else [step.get("target")]
    return {
        "action_id": f"act_{step['step_id']}",
        "actor_id": plan["actor_id"],
        "plan_id": plan["plan_id"],
        "step_id": step["step_id"],
        "action_type": step["action_type"],
        "target_refs": target_refs,
        "target_region": step.get("target_region"),
        "parameter_digest": f"target_region={step.get('target_region', 'none')}",
        "expected_outcome": expected_outcome(step),
        "risk_level": step.get("risk_level", "unknown"),
        "rollback_capability": "full" if step["action_type"] == "move_file" else "not_required",
        "object_sensitivity": obj.get("sensitivity_level") if obj else "none",
        "source_state": obj.get("source_state") if obj else "trusted",
    }


def expected_outcome(step: dict[str, Any]) -> str:
    action_type = step["action_type"]
    if action_type == "read_metadata":
        return "metadata_read"
    if action_type == "move_file":
        return "file_moved"
    if action_type == "candidate_tag":
        return "candidate_record_created"
    return "unknown"


def plan_precheck(
    plan: dict[str, Any],
    objects: dict[str, dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    violations = []
    allowed_steps = []
    restricted_steps = []
    blocked_steps = []

    for step in plan["steps"]:
        step_id = step["step_id"]
        target = step.get("target")
        obj = objects.get(target)

        if step["action_type"] == "read_metadata":
            allowed_steps.append(step_id)
            continue

        if not obj:
            blocked_steps.append(step_id)
            violations.append(
                {
                    "step_id": step_id,
                    "violated_boundary": "target_not_found",
                    "reason_code": "target_missing",
                    "recommended_action": "block",
                }
            )
            continue

        rules_for_obj = matching_rules(obj, rules)
        if obj.get("source_state") == "unverified":
            blocked_steps.append(step_id)
            violations.append(
                {
                    "step_id": step_id,
                    "violated_boundary": "unverified_source",
                    "reason_code": "source_chain_required",
                    "recommended_action": "block_or_verify_source",
                }
            )
            continue

        if step["action_type"] == "move_file" and obj.get("sensitivity_level") == "high":
            restricted_steps.append(step_id)
            violations.append(
                {
                    "step_id": step_id,
                    "violated_boundary": "high_sensitivity_direct_modify",
                    "reason_code": "candidate_state_required",
                    "recommended_action": "convert_move_to_candidate_tag",
                }
            )
            continue

        action_allowed = any(
            rule.get("action_policy", {}).get(normalize_policy_action(step["action_type"])) == "allow"
            for rule in rules_for_obj
        )
        if action_allowed or step["action_type"] == "candidate_tag":
            allowed_steps.append(step_id)
        else:
            restricted_steps.append(step_id)

    return {
        "precheck_id": "pre_demo_001",
        "plan_id": plan["plan_id"],
        "feasibility": "restricted" if violations else "pass",
        "violations": violations,
        "allowed_steps": allowed_steps,
        "restricted_steps": restricted_steps,
        "blocked_steps": blocked_steps,
    }


def normalize_policy_action(action_type: str) -> str:
    if action_type == "move_file":
        return "move"
    if action_type == "candidate_tag":
        return "tag"
    return action_type


def verify_source_chain(step: dict[str, Any], source_templates: dict[str, Any]) -> dict[str, Any]:
    template = source_templates.get(step["step_id"], source_templates["default"])
    chain = {
        "source_chain_id": f"src_{step['step_id']}",
        **template,
    }
    chain["chain_hash"] = stable_hash(chain)

    missing = [
        key
        for key in ["root_authorization_ref", "parent_task_ref", "input_sources", "tool_reason_ref"]
        if not chain.get(key)
    ]
    if missing or "unknown_doc_source" in chain.get("input_sources", []):
        return {
            **chain,
            "integrity_state": "failed",
            "trust_state": "untrusted",
            "risk_labels": ["source_chain_incomplete"],
            "reason_codes": ["source_unverified"],
        }

    return {
        **chain,
        "integrity_state": "verified",
        "trust_state": "trusted",
        "risk_labels": [],
        "reason_codes": ["root_authorization_valid", "input_source_trusted"],
    }


def evaluate_budget(action: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    action_type = action["action_type"]
    risk = action.get("risk_level", "unknown")
    execution_mode = action.get("effective_execution_mode", "formal")
    if execution_mode == "none":
        return {
            "budget_decision_id": f"budget_{action['action_id']}",
            "budget_state": "not_consumed_for_blocked_action",
            "decision": "not_applicable",
            "deductions": {},
            "remaining": {
                "tool_budget": deepcopy(budget["tool_budget"]),
                "risk_budget": deepcopy(budget["risk_budget"]),
            },
            "reason_codes": ["blocked_before_budget_consumption"],
        }
    if execution_mode == "candidate_only" and action_type == "move_file":
        action_type = "candidate_tag"
        risk = "medium"

    tool_budget = budget["tool_budget"]
    risk_budget = budget["risk_budget"]
    reason_codes = []

    if tool_budget.get(action_type, 0) <= 0:
        return {
            "budget_decision_id": f"budget_{action['action_id']}",
            "budget_state": "exhausted",
            "decision": "deny",
            "deductions": {},
            "remaining": {"tool_budget": deepcopy(tool_budget), "risk_budget": deepcopy(risk_budget)},
            "reason_codes": ["tool_budget_exhausted"],
        }

    if risk in risk_budget and risk_budget[risk] <= 0:
        return {
            "budget_decision_id": f"budget_{action['action_id']}",
            "budget_state": "risk_budget_exhausted",
            "decision": "deny",
            "deductions": {},
            "remaining": {"tool_budget": deepcopy(tool_budget), "risk_budget": deepcopy(risk_budget)},
            "reason_codes": [f"{risk}_risk_budget_exhausted"],
        }

    tool_budget[action_type] = tool_budget.get(action_type, 0) - 1
    deductions = {action_type: 1}
    if risk in risk_budget:
        risk_budget[risk] -= 1
        deductions[f"risk_{risk}"] = 1
    reason_codes.append("budget_sufficient")

    return {
        "budget_decision_id": f"budget_{action['action_id']}",
        "budget_state": "active_after_deduction",
        "decision": "allow_with_deduction",
        "deductions": deductions,
        "remaining": {"tool_budget": deepcopy(tool_budget), "risk_budget": deepcopy(risk_budget)},
        "reason_codes": reason_codes,
    }


def issue_decision(
    action: dict[str, Any],
    precheck: dict[str, Any],
    source: dict[str, Any],
    budget_decision: dict[str, Any],
    obj: dict[str, Any] | None,
) -> dict[str, Any]:
    step_id = action["step_id"]
    reason_codes = []
    execution_mode = "formal"

    if action["action_type"] == "read_metadata":
        decision = "metadata_only"
        execution_mode = "metadata_only"
        reason_codes.extend(["metadata_read_allowed"])
    elif step_id in precheck["blocked_steps"]:
        decision = "block"
        execution_mode = "none"
        reason_codes.extend(["blocked_by_precheck"])
    elif source["integrity_state"] != "verified":
        decision = "block"
        execution_mode = "none"
        reason_codes.extend(source["reason_codes"])
    elif budget_decision["decision"] == "deny":
        decision = "block"
        execution_mode = "none"
        reason_codes.extend(budget_decision["reason_codes"])
    elif step_id in precheck["restricted_steps"] or (obj and obj.get("sensitivity_level") == "high"):
        decision = "limited_allow"
        execution_mode = "candidate_only"
        reason_codes.extend(["candidate_state_required"])
    else:
        decision = "allow"
        reason_codes.extend(["source_verified", "budget_ok"])

    return {
        "decision_token_id": f"dt_{step_id}",
        "action_id": action["action_id"],
        "step_id": step_id,
        "decision": decision,
        "execution_mode": execution_mode,
        "allowed_parameters": {"execution_state": execution_mode},
        "expires_at": now_iso(),
        "reason_codes": reason_codes,
        "audit_ref": "audit_demo_001",
    }


def execute_action(
    action: dict[str, Any],
    decision: dict[str, Any],
    obj: dict[str, Any] | None,
    regions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if action["action_type"] == "read_metadata":
        return {"outcome_type": "success", "state_delta": "metadata_read"}, None

    if decision["decision"] == "block":
        return {
            "outcome_type": "blocked",
            "state_delta": "no_change",
            "reason": ",".join(decision["reason_codes"]),
        }, None

    if decision["execution_mode"] == "candidate_only":
        candidate = {
            "candidate_id": f"cand_{action['step_id']}",
            "source_object": action["target_refs"][0],
            "proposed_action": action["action_type"],
            "proposed_target_region": action.get("target_region"),
            "status": "pending_confirmation",
            "reason_codes": decision["reason_codes"],
        }
        return {"outcome_type": "candidate_created", "state_delta": "no_file_change"}, candidate

    if action["action_type"] == "move_file" and obj:
        target_region = regions[action["target_region"]]
        source_path = WORKSPACE / obj["path"]
        target_dir = WORKSPACE / target_region["path"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / source_path.name
        if source_path.exists():
            shutil.move(str(source_path), str(target_path))
            obj["path"] = str(target_path.relative_to(WORKSPACE)).replace("\\", "/")
            return {"outcome_type": "success", "state_delta": f"{obj['object_id']}_moved"}, None
        return {"outcome_type": "failed", "state_delta": "source_missing"}, None

    return {"outcome_type": "noop", "state_delta": "no_change"}, None


def reset_workspace(objects: list[dict[str, Any]]) -> None:
    organized = WORKSPACE / "organized"
    if organized.exists():
        shutil.rmtree(organized)
    inbox = WORKSPACE / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    placeholders = {
        "file_001": "# 项目说明书\n\n这是一个低风险说明文档，用于演示可直接归类。",
        "file_002": "临时记录：低风险，可归档。",
        "file_003": "# 专利权利要求草稿\n\n高敏文件。Demo 中不得自动移动。",
        "file_004": "Demo placeholder for contract PDF. High sensitivity.",
        "file_005": "Demo placeholder for unverified source document.",
    }
    for obj in objects:
        path = WORKSPACE / obj["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(placeholders.get(obj["object_id"], ""), encoding="utf-8")


def run_pipeline() -> dict[str, Any]:
    objects_list = read_json(DATA_DIR / "objects.json")
    regions_list = read_json(DATA_DIR / "regions.json")
    rules = read_json(DATA_DIR / "rules.json")
    budget = read_json(DATA_DIR / "budget.json")
    plan = read_json(DATA_DIR / "plan.json")
    source_templates = read_json(DATA_DIR / "source_chains.json")

    reset_workspace(objects_list)
    objects = index_by(objects_list, "object_id")
    regions = index_by(regions_list, "region_id")

    precheck = plan_precheck(plan, objects, rules)
    action_declarations = []
    sources = []
    budget_decisions = []
    decisions = []
    experiences = []
    candidates = []

    for step in plan["steps"]:
        obj = objects.get(step.get("target"))
        action = build_action_declaration(step, plan, obj)
        if step["step_id"] in precheck["restricted_steps"]:
            action["effective_execution_mode"] = "candidate_only"
        elif step["step_id"] in precheck["blocked_steps"]:
            action["effective_execution_mode"] = "none"
        else:
            action["effective_execution_mode"] = "formal"
        action_declarations.append(action)

        source = verify_source_chain(step, source_templates)
        sources.append(source)

        budget_decision = evaluate_budget(action, budget)
        budget_decisions.append(budget_decision)

        decision = issue_decision(action, precheck, source, budget_decision, obj)
        decisions.append(decision)

        outcome, candidate = execute_action(action, decision, obj, regions)
        if candidate:
            candidates.append(candidate)

        experiences.append(
            {
                "experience_id": f"exp_{step['step_id']}",
                "context_ref": "ctx_demo_001",
                "action_ref": action["action_id"],
                "outcome": outcome,
                "decision_ref": decision["decision_token_id"],
                "created_at": now_iso(),
            }
        )

    audit = build_audit(plan, precheck, decisions, experiences, budget)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_json(OUTPUT_DIR / "precheck.json", precheck)
    write_json(OUTPUT_DIR / "action_declarations.json", action_declarations)
    write_json(OUTPUT_DIR / "source_chains.json", sources)
    write_json(OUTPUT_DIR / "budget_decisions.json", budget_decisions)
    write_json(OUTPUT_DIR / "decision_tokens.json", decisions)
    write_json(OUTPUT_DIR / "candidate_actions.json", candidates)
    write_json(OUTPUT_DIR / "experience_records.json", experiences)
    write_json(OUTPUT_DIR / "audit_summary.json", audit)
    write_json(OUTPUT_DIR / "final_objects.json", list(objects.values()))

    return audit


def main() -> None:
    audit = run_pipeline()
    print("Demo completed.")
    print(f"Output: {OUTPUT_DIR}")
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))


def build_audit(
    plan: dict[str, Any],
    precheck: dict[str, Any],
    decisions: list[dict[str, Any]],
    experiences: list[dict[str, Any]],
    budget: dict[str, Any],
) -> dict[str, Any]:
    decision_counts = {"allow": 0, "limited_allow": 0, "block": 0, "metadata_only": 0}
    for decision in decisions:
        decision_counts[decision["decision"]] = decision_counts.get(decision["decision"], 0) + 1

    return {
        "audit_id": "audit_demo_001",
        "task_goal": plan["task_goal"],
        "actor_id": plan["actor_id"],
        "plan_id": plan["plan_id"],
        "precheck_ref": precheck["precheck_id"],
        "summary": {
            "total_steps": len(plan["steps"]),
            "allowed": decision_counts.get("allow", 0),
            "limited_allowed": decision_counts.get("limited_allow", 0),
            "blocked": decision_counts.get("block", 0),
            "metadata_only": decision_counts.get("metadata_only", 0),
        },
        "source_chain_state": "verified_except_blocked_or_untrusted_steps",
        "budget_state": deepcopy(budget),
        "executed_actions": [d["action_id"] for d in decisions if d["decision"] == "allow"],
        "candidate_actions": [d["action_id"] for d in decisions if d["decision"] == "limited_allow"],
        "blocked_actions": [d["action_id"] for d in decisions if d["decision"] == "block"],
        "experience_refs": [exp["experience_id"] for exp in experiences],
        "created_at": now_iso(),
    }


if __name__ == "__main__":
    main()
