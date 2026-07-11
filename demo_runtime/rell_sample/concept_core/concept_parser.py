from __future__ import annotations

from typing import Any, Callable

from .action_units import find_action_concept_by_step, find_action_concepts_by_text
from .concept_evidence import build_concept_evidence_packet


def _build_action_concept_view(
    concept: dict[str, Any],
    *,
    activation_reason: str,
    step_detected_explicitly: bool,
) -> dict[str, Any]:
    match_basis = ["explicit_process_chain_step"] if step_detected_explicitly else ["local_action_alias_match"]
    confidence = 0.92 if step_detected_explicitly else 0.78
    return {
        "concept_id": concept.get("concept_id"),
        "display_name": concept.get("display_name"),
        "step_id": concept.get("step_id"),
        "capability": concept.get("capability"),
        "goal_fact_bridge": concept.get("goal_fact_bridge"),
        "activation_reason": activation_reason,
        "step_detected_explicitly": step_detected_explicitly,
        "source_policy": concept.get("source_policy"),
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "concept_evidence": build_concept_evidence_packet(
            concept,
            concept_type="action_concept",
            activation_reason=activation_reason,
            match_basis=match_basis,
            confidence=confidence,
        ),
    }


def resolve_action_concepts(
    text: str,
    detected_steps: list[str],
    *,
    normalize_text_fn: Callable[[str], str],
) -> list[dict[str, Any]]:
    normalized = normalize_text_fn(text)
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()

    for step_id in detected_steps:
        concept = find_action_concept_by_step(step_id)
        if not concept or concept["concept_id"] in seen:
            continue
        resolved.append(
            _build_action_concept_view(
                concept,
                activation_reason="显式过程链已识别出该动作步骤",
                step_detected_explicitly=True,
            )
        )
        seen.add(concept["concept_id"])

    for concept in find_action_concepts_by_text(normalized):
        if concept["concept_id"] in seen:
            continue
        resolved.append(
            _build_action_concept_view(
                concept,
                activation_reason="自然语言中命中高频动作概念表达",
                step_detected_explicitly=False,
            )
        )
        seen.add(concept["concept_id"])

    return resolved
