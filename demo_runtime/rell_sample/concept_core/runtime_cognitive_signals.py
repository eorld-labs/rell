from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .cognitive_inquiry import adapt_cognitive_signal
from .rcir_primitives import make_predicate, stable_id


def _question_predicate(
    name: str,
    subject_ref: str,
    world_revision: int,
    fact_authority_ref: str,
) -> dict[str, Any]:
    return make_predicate(
        name,
        [
            {"role": "subject", "value_type": "EntityRef", "value": subject_ref},
            {"role": "value", "value_type": "role_variable", "value": "?value"},
        ],
        world_revision=world_revision,
        modality="hypothesis",
        status="candidate",
        depends_on_refs=[subject_ref, fact_authority_ref],
    )


def _signal_candidate(
    signal_kind: str,
    *,
    pattern_key: str,
    subject_refs: list[str],
    question_name: str,
    measurements: dict[str, Any],
    depends_on_refs: list[str],
    world_revision: int,
    fact_authority_ref: str,
    candidate_hypotheses: list[str],
    answer_routes: list[str],
    strength: int,
) -> dict[str, Any]:
    question = _question_predicate(
        question_name,
        subject_refs[0],
        world_revision,
        fact_authority_ref,
    )
    evidence = adapt_cognitive_signal(
        signal_kind,
        subject_refs=subject_refs,
        question_predicate_ref=question["predicate_id"],
        world_revision=world_revision,
        depends_on_refs=[fact_authority_ref, *depends_on_refs],
        measurements=measurements,
        strength=strength,
    )
    return {
        "signal_candidate_id": stable_id(
            "cognitive_signal_candidate",
            {
                "pattern_key": pattern_key,
                "world_revision": world_revision,
                "fact_authority_ref": fact_authority_ref,
            },
        ),
        "signal_kind": signal_kind,
        "pattern_key": pattern_key,
        "subject_refs": sorted(set(subject_refs)),
        "question_predicate": question,
        "trigger_evidence": evidence,
        "candidate_hypotheses": list(dict.fromkeys(candidate_hypotheses)),
        "answer_routes": list(dict.fromkeys(answer_routes)),
        "world_revision": world_revision,
        "depends_on_refs": sorted(set([fact_authority_ref, *depends_on_refs])),
        "fact_authority_ref": fact_authority_ref,
        "lifecycle_status": "current_candidate",
        "current_world_usable": True,
        "invalidated_by_world_change": False,
        "control_gateway": "P018",
        "verification_gateway": "P016",
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
        "inquiry_created": False,
    }


def _recovery_pattern_candidates(
    diagnostics: list[dict[str, Any]],
    *,
    world_revision: int,
    fact_authority_ref: str,
    minimum_repetitions: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in diagnostics:
        if item.get("world_revision") != world_revision:
            continue
        key = (
            str(item.get("category") or "unknown_runtime_failure"),
            str(item.get("stage") or "unknown_stage"),
            str(item.get("reason") or "unknown_reason"),
        )
        groups[key].append(item)
    candidates = []
    for (category, stage, reason), members in groups.items():
        if len(members) < minimum_repetitions:
            continue
        pattern_key = stable_id(
            "recovery_pattern",
            {"category": category, "stage": stage, "reason": reason},
        )
        diagnostic_refs = [
            str(item.get("diagnostic_id"))
            for item in members
            if item.get("diagnostic_id")
        ]
        subject_ref = f"process_stage:{stage}"
        candidates.append(
            _signal_candidate(
                "recovery_pattern",
                pattern_key=pattern_key,
                subject_refs=[subject_ref],
                question_name="repeated_recovery_causal_boundary",
                measurements={
                    "category": category,
                    "stage": stage,
                    "reason": reason,
                    "repetition_count": len(members),
                },
                depends_on_refs=[subject_ref, *diagnostic_refs],
                world_revision=world_revision,
                fact_authority_ref=fact_authority_ref,
                candidate_hypotheses=[
                    "process_template_boundary_missing",
                    "persistent_environment_constraint",
                    "verification_channel_degraded",
                ],
                answer_routes=["existing_evidence", "passive_observation", "safe_probe"],
                strength=min(850, 420 + len(members) * 60),
            )
        )
    return candidates


def _episode_signature(episode: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(episode.get("operator") or "unknown_operator"),
        tuple(sorted(str(item.get("predicate")) for item in episode.get("produces", []))),
        tuple(sorted(str(item.get("predicate")) for item in episode.get("destroys", []))),
    )


def _unexplained_pattern_candidates(
    episodes: list[dict[str, Any]],
    *,
    known_operators: set[str],
    world_revision: int,
    fact_authority_ref: str,
    minimum_repetitions: int,
    minimum_distinct_entities: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        if episode.get("world_revision") != world_revision:
            continue
        operator = str(episode.get("operator") or "unknown_operator")
        explicitly_unexplained = episode.get("concept_explained") is False
        if operator in known_operators and not explicitly_unexplained:
            continue
        groups[_episode_signature(episode)].append(episode)
    candidates = []
    for signature, members in groups.items():
        entity_refs = {
            str((item.get("participants") or {}).get("theme"))
            for item in members
            if (item.get("participants") or {}).get("theme")
        }
        if (
            len(members) < minimum_repetitions
            or len(entity_refs) < minimum_distinct_entities
        ):
            continue
        pattern_key = stable_id("unexplained_event_pattern", signature)
        episode_refs = [
            str(item.get("episode_id"))
            for item in members
            if item.get("episode_id")
        ]
        subject_ref = pattern_key
        candidates.append(
            _signal_candidate(
                "unexplained_repeated_pattern",
                pattern_key=pattern_key,
                subject_refs=[subject_ref, *sorted(entity_refs)],
                question_name="repeated_pattern_has_predictive_concept",
                measurements={
                    "operator": signature[0],
                    "produces": list(signature[1]),
                    "destroys": list(signature[2]),
                    "episode_count": len(members),
                    "distinct_entity_count": len(entity_refs),
                },
                depends_on_refs=[subject_ref, *episode_refs, *sorted(entity_refs)],
                world_revision=world_revision,
                fact_authority_ref=fact_authority_ref,
                candidate_hypotheses=[
                    "new_causal_concept",
                    "existing_concept_boundary_missing",
                    "scene_specific_coincidence",
                ],
                answer_routes=["existing_evidence", "passive_observation", "safe_probe"],
                strength=min(880, 450 + len(members) * 70),
            )
        )
    return candidates


def derive_runtime_cognitive_signal_candidates(
    *,
    verified_episodes: list[dict[str, Any]],
    runtime_diagnostics: list[dict[str, Any]],
    known_operators: set[str],
    world_revision: int,
    fact_authority_ref: str,
    minimum_repetitions: int = 3,
    minimum_distinct_entities: int = 2,
) -> list[dict[str, Any]]:
    """Turn real runtime records into non-authoritative cognition candidates."""
    if not fact_authority_ref:
        raise ValueError("runtime_cognitive_signal_requires_fact_authority")
    candidates = [
        *_recovery_pattern_candidates(
            deepcopy(runtime_diagnostics),
            world_revision=world_revision,
            fact_authority_ref=fact_authority_ref,
            minimum_repetitions=minimum_repetitions,
        ),
        *_unexplained_pattern_candidates(
            deepcopy(verified_episodes),
            known_operators=set(known_operators),
            world_revision=world_revision,
            fact_authority_ref=fact_authority_ref,
            minimum_repetitions=minimum_repetitions,
            minimum_distinct_entities=minimum_distinct_entities,
        ),
    ]
    return sorted(candidates, key=lambda item: item["signal_candidate_id"])


__all__ = ["derive_runtime_cognitive_signal_candidates"]
