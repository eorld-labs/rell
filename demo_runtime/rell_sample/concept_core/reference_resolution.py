from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

from .composition_grammar import make_referent_expression


REFERENCE_SCHEMA_VERSION = "1.0.0"

_REFERENCE_PATTERNS = (
    ("possessive", re.compile(r"(?:我|你|他|她|主人|客人)(?:手里|手上)?的(?:那个|这个|杯子|马克杯|高脚杯)?")),
    ("relative_clause", re.compile(r"(?:刚才|之前)(?:拿|放|用|喝)(?:过|起|下)?的(?:那个|这个|杯子|桌子|地方)?")),
    ("attribute_limited", re.compile(r"(?P<attribute>红|白|黑|蓝|绿)色?的?那个")),
    ("analogical", re.compile(r"(?:同样的|一样的)")),
    ("contrastive_other", re.compile(r"(?:另一个|别的那个|其他那个)")),
    ("ordinal", re.compile(r"(?:第一个|最后一个|最左边的|最右边的)")),
    ("event_limited", re.compile(r"(?:刚才那个|之前那个)")),
    ("pronoun", re.compile(r"它们|他们|她们|这个|那个|它|(?<!其)他|她")),
    ("location_deictic", re.compile(r"那里|那边|这里|这边")),
)

_FOCUS_WEIGHTS = {
    "verified_holding_fact": 900,
    "verified_human_possession_fact": 850,
    "current_grounded_intent_frame": 800,
    "current_task_role": 780,
    "human_confirmed_visual_binding": 650,
    "dialogue_focus_binding": 600,
}

_AUTHORITY_TIERS = {
    "verified_holding_fact": 5,
    "verified_human_possession_fact": 5,
    "current_grounded_intent_frame": 4,
    "current_task_role": 4,
    "human_confirmed_visual_binding": 3,
    "dialogue_focus_binding": 2,
}

_COLOR_VALUES = {"红": "red", "白": "white", "黑": "black", "蓝": "blue", "绿": "green"}


def _stable_id(prefix: str, payload: str) -> str:
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_salience_projection(
    context_entities: list[dict[str, Any]],
    current_mentions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for item in context_entities:
        ref = item.get("entity_ref")
        if not ref:
            continue
        source = str(item.get("focus_source") or "dialogue_focus_binding")
        merged[ref] = {
            "entity_ref": ref,
            "score": _FOCUS_WEIGHTS.get(source, 400),
            "score_components": {"focus_source": _FOCUS_WEIGHTS.get(source, 400)},
            "focus_source": source,
            "authority_tier": _AUTHORITY_TIERS.get(source, 1),
            "entity": deepcopy(item),
        }
    for item in current_mentions:
        ref = item.get("entity_ref")
        if ref and ref in merged:
            merged[ref]["score"] += 1000
            merged[ref]["score_components"]["current_explicit_mention"] = 1000
    operator = next((item.get("operator") for item in events if item.get("operator")), None)
    required_affordance = {
        "grasp_object": "graspable",
        "fill_container": "receive_liquid",
        "place_object": "movable",
    }.get(operator)
    if required_affordance:
        for item in merged.values():
            if required_affordance in set((item["entity"] or {}).get("functional_affordances", [])):
                item["score"] += 120
                item["score_components"]["event_concept_compatibility"] = 120
    ranked = sorted(merged.values(), key=lambda item: (-item["score"], item["entity_ref"]))
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "projection_kind": "SalienceProjection",
        "ranked_entities": ranked,
        "derived_only": True,
        "persistent_state_source": False,
        "runtime_fact_committed": False,
    }


def _matches_attribute(entity: dict[str, Any], surface: str) -> bool:
    requested = next((value for marker, value in _COLOR_VALUES.items() if marker in surface), None)
    if not requested:
        return True
    observed = (entity.get("observed_attributes") or {}).get("color")
    label = str(entity.get("label") or entity.get("display_name") or "")
    return observed == requested or any(marker in label for marker, value in _COLOR_VALUES.items() if value == requested)


def resolve_references(
    text: str,
    objects: list[dict[str, Any]],
    context_entities: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    salience = build_salience_projection(context_entities, objects, events)
    ranked = salience["ranked_entities"]
    resolved, unresolved = [], []
    consumed: list[tuple[int, int]] = []
    for reference_type, pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in consumed):
                continue
            consumed.append((match.start(), match.end()))
            candidates = deepcopy(ranked)
            if reference_type == "attribute_limited":
                candidates = [item for item in candidates if _matches_attribute(item["entity"], match.group(0))]
            if reference_type == "possessive":
                wants_human_possession = any(marker in match.group(0) for marker in ("我", "主人", "客人"))
                if wants_human_possession:
                    candidates = [
                        item for item in candidates
                        if item.get("focus_source") == "verified_human_possession_fact"
                    ]
            if reference_type == "relative_clause":
                event_markers = {
                    "拿": {"verified_holding_fact", "current_task_role", "dialogue_focus_binding"},
                    "放": {"current_task_role", "dialogue_focus_binding", "human_confirmed_visual_binding"},
                    "喝": {"verified_human_possession_fact", "dialogue_focus_binding"},
                }
                allowed_sources = next(
                    (sources for marker, sources in event_markers.items() if marker in match.group(0)),
                    set(),
                )
                if allowed_sources:
                    candidates = [item for item in candidates if item.get("focus_source") in allowed_sources]
            if reference_type == "contrastive_other" and candidates:
                candidates = candidates[1:]
            if reference_type == "ordinal" and "最后" in match.group(0):
                candidates = list(reversed(candidates))
            unique = len(candidates) == 1
            if len(candidates) > 1:
                top, runner_up = candidates[0], candidates[1]
                unique = bool(
                    int(top.get("authority_tier", 1))
                    > int(runner_up.get("authority_tier", 1))
                    or (
                        int(top.get("authority_tier", 1))
                        == int(runner_up.get("authority_tier", 1))
                        and int(top["score"]) - int(runner_up["score"]) >= 150
                    )
                )
            record = {
                "surface": match.group(0),
                "span": [match.start(), match.end()],
                "reference_type": reference_type,
                "candidates": [
                    {
                        "entity_ref": item["entity_ref"],
                        "score": item["score"],
                        "provenance": {
                            "method": "derived_salience_projection",
                            "score_components": deepcopy(item["score_components"]),
                            "authority_tier": item.get("authority_tier", 1),
                            "world_revision": (item.get("entity") or {}).get("world_revision"),
                            "temporal_window": {
                                "valid_at_world_revision": (item.get("entity") or {}).get("world_revision"),
                                "expires_after_turn": (item.get("entity") or {}).get("expires_after_turn"),
                            },
                        },
                    }
                    for item in candidates[:5]
                ],
                "selected": candidates[0]["entity_ref"] if unique and candidates else None,
                "unique": unique,
                "requires_confirmation": not unique,
                "runtime_fact_committed": False,
                "constraints": (
                    [{
                        "constraint_type": reference_type,
                        "validation_source": "WorldFactLedger",
                        "candidate_only": True,
                    }]
                    if reference_type in {"possessive", "relative_clause"}
                    else []
                ),
            }
            (resolved if unique else unresolved).append(record)
    seed = f"{text}|{len(resolved)}|{len(unresolved)}"
    resolution = {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "resolution_kind": "ReferenceResolution",
        "resolution_id": _stable_id("reference_resolution", seed),
        "resolved_references": resolved,
        "unresolved": unresolved,
        "inquiry_contracts": [
            {
                "contract_kind": "InquiryContract",
                "reason": "reference_binding_not_unique",
                "reference_span": deepcopy(item.get("span")),
                "candidate_entity_refs": [
                    candidate.get("entity_ref") for candidate in item.get("candidates", [])
                ],
                "minimum_information_requested": "observable_discriminating_feature",
                "candidate_only": True,
                "runtime_fact_committed": False,
            }
            for item in unresolved
        ],
        "salience_projection": salience,
        "evidence_boundary": {
            "reference_binding_is_not_physical_fact": True,
            "ambiguous_binding_never_silently_becomes_unique": True,
            "current_verified_relation_precedes_salience": True,
        },
    }
    resolution["referent_expressions"] = reference_resolution_referents(
        resolution, context_entities
    )
    return resolution


def reference_resolution_referents(
    resolution: dict[str, Any], context_entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    index = {item.get("entity_ref"): item for item in context_entities}
    referents = []
    for record in [
        *resolution.get("resolved_references", []),
        *resolution.get("unresolved", []),
    ]:
        selected = record.get("selected")
        if selected:
            world_revision = (index.get(selected) or {}).get("world_revision")
            expression = make_referent_expression(
                "entity_ref",
                entity_ref=selected,
                world_revision=world_revision,
            )
        else:
            candidate_refs = [
                item.get("entity_ref")
                for item in record.get("candidates", [])
                if item.get("entity_ref")
            ]
            revisions = {
                (index.get(ref) or {}).get("world_revision")
                for ref in candidate_refs
                if (index.get(ref) or {}).get("world_revision") is not None
            }
            expression = make_referent_expression(
                "entity_selector",
                concept_refs=(
                    [record["selected_concept_id"]]
                    if record.get("selected_concept_id")
                    else []
                ),
                constraints=[
                    {
                        "constraint_kind": "reference_candidate_set",
                        "candidate_entity_refs": candidate_refs,
                        "reference_type": record.get("reference_type"),
                        "source_resolution_id": resolution.get("resolution_id"),
                        "candidate_only": True,
                    }
                ],
                world_revision=next(iter(revisions)) if len(revisions) == 1 else None,
            )
        referents.append(
            {
                "surface_span": deepcopy(record.get("span")),
                "surface_forwarded_downstream": False,
                "reference_type": record.get("reference_type"),
                "referent_expression": expression,
                "requires_confirmation": bool(record.get("requires_confirmation")),
                "runtime_fact_committed": False,
            }
        )
    return referents


def resolved_reference_mentions(
    resolution: dict[str, Any], context_entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    index = {item.get("entity_ref"): item for item in context_entities}
    mentions = []
    for item in resolution.get("resolved_references", []):
        if item.get("reference_type") == "location_deictic":
            continue
        entity = deepcopy(index.get(item.get("selected")) or {})
        if not entity:
            continue
        entity.update(
            {
                "matched_alias": item.get("surface"),
                "start": item.get("span", [None, None])[0],
                "end": item.get("span", [None, None])[1],
                "source": "structured_reference_resolution",
                "reference_resolution_id": resolution.get("resolution_id"),
                "binding_strength": "derived_salience_unique",
            }
        )
        mentions.append(entity)
    return mentions
