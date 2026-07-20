from __future__ import annotations

import hashlib
import json
import os
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from concept_core.rcir_contracts import (
    build_portable_experience_contract,
    validate_portable_experience_contract,
)


DEFAULT_STORE_PATH = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "runtime" / "embodied_local_experiences.json"


def get_store_path() -> Path:
    configured = os.environ.get("RELL_EMBODIED_EXPERIENCE_STORE")
    return Path(configured).resolve() if configured else DEFAULT_STORE_PATH


def load_trusted_experiences() -> list[dict[str, Any]]:
    payload = _load_payload(get_store_path())
    experiences = []
    for item in payload["experiences"]:
        if item.get("status") != "trusted_local_experience":
            continue
        current = deepcopy(item)
        contract = current.get("portable_experience_contract")
        if not contract:
            contract = build_portable_experience_contract(current)
            current["portable_experience_contract"] = contract
        validation = validate_portable_experience_contract(contract)
        if not validation["valid"]:
            raise ValueError(
                "trusted_experience_portability_boundary_invalid:"
                + ",".join(validation["errors"])
            )
        current["execution_authority"] = {
            "source": "portable_experience_contract",
            "legacy_record_is_execution_authority": False,
            "current_world_rebinding_required": True,
        }
        experiences.append(current)
    return experiences


def get_trusted_experience(experience_id: str) -> dict[str, Any] | None:
    return next((item for item in load_trusted_experiences() if item.get("experience_id") == experience_id), None)


def persist_trusted_experience(experience: dict[str, Any]) -> dict[str, Any]:
    if experience.get("status") != "trusted_local_experience":
        raise ValueError("only_trusted_local_experience_can_be_persisted")
    portable = _build_portable_record(experience)
    path = get_store_path()
    payload = _load_payload(path)
    payload["experiences"] = [
        item for item in payload["experiences"] if item.get("experience_id") != portable["experience_id"]
    ] + [portable]
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(path, payload)
    return deepcopy(portable)


def _build_portable_record(experience: dict[str, Any]) -> dict[str, Any]:
    invariant = deepcopy(experience.get("invariant_contract", {}))
    forbidden = set(invariant.get("forbidden_storage", []))
    required_forbidden = {
        "absolute_world_coordinates",
        "robot_joint_angles",
        "fixed_action_durations",
        "teacher_key_sequence",
        "single_body_trajectory",
    }
    if not required_forbidden.issubset(forbidden):
        raise ValueError("experience_invariant_contract_missing_forbidden_storage_boundary")
    accepted_validations = [
        item
        for item in experience.get("validation_history", [])
        if item.get("physical_fact_verified") and item.get("human_accepted")
    ]
    source_contract = deepcopy(experience.get("source_concept_contract"))
    if source_contract:
        for role in source_contract.get("semantic_roles", {}).values():
            role.pop("entity_ref", None)
            role.pop("surface_form", None)
            role["binding_scope"] = "rebind_from_current_observation"
        source_contract.pop("world_revision", None)
    portable_experience = {
        "schema_version": "1.0.0",
        "experience_id": experience["experience_id"],
        "status": "trusted_local_experience",
        "source": "human_first_person_teleoperation_compiled_to_invariants",
        "source_goal_utterance": experience.get("source_goal_utterance"),
        "target_binding": {
            "concept_id": experience.get("target_binding", {}).get("concept_id"),
            "rebind_by_concept_and_current_observation": True,
        },
        "goal_fact": experience.get("goal_fact"),
        "source_concept_contract": source_contract,
        "process_chain": deepcopy(experience.get("process_chain", [])),
        "effect_contract": deepcopy(experience.get("effect_contract", {})),
        "applicability_constraints": deepcopy(experience.get("applicability_constraints", {})),
        "invariant_contract": invariant,
        "pedagogical_signals": {
            "signal_types": deepcopy((experience.get("pedagogical_signals") or {}).get("signal_types", [])),
            "interruption_occurred": bool((experience.get("pedagogical_signals") or {}).get("interruption_occurred", False)),
            "clarification_occurred": bool((experience.get("pedagogical_signals") or {}).get("clarification_occurred", False)),
            "outcome": (experience.get("pedagogical_signals") or {}).get("outcome", "unknown"),
        },
        "teaching_evidence_summary": deepcopy(experience.get("teaching_evidence_summary", {})),
        "promotion_policy": deepcopy(experience.get("promotion_policy", {})),
        "validation_summary": {
            "accepted_validation_count": len(accepted_validations),
            "latest_outcome": "accepted",
            "requires_runtime_rebinding_on_every_session": True,
        },
        "persisted_at": datetime.now(timezone.utc).isoformat(),
    }
    portable_experience["portable_experience_contract"] = (
        build_portable_experience_contract(portable_experience)
    )
    portable_experience["execution_authority"] = {
        "source": "portable_experience_contract",
        "legacy_record_is_execution_authority": False,
        "current_world_rebinding_required": True,
    }
    canonical = json.dumps(portable_experience, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    portable_experience["integrity"] = {
        "algorithm": "sha256",
        "portable_contract_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    return portable_experience


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0.0", "store_type": "embodied_trusted_local_experiences", "experiences": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("experiences"), list):
        raise ValueError("invalid_embodied_experience_store")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any], attempts: int = 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.replace(temporary, path)
            return
        except OSError as error:
            last_error = error
            time.sleep(0.1 * (attempt + 1))
    if last_error:
        raise last_error
