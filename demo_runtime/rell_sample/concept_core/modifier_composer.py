from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any


MODIFIER_SCHEMA_VERSION = "1.0.0"

_PATTERNS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("speed", "fast", ("赶快", "赶紧", "快点", "迅速", "快速", "尽快"), "event"),
    ("speed", "slow", ("慢慢", "慢点", "缓慢", "徐徐"), "event"),
    ("speed", "accelerate", ("加速", "加快"), "event"),
    ("speed", "decelerate", ("减速", "放慢"), "event"),
    ("force", "strong", ("用力", "使劲", "大力"), "event"),
    ("force", "gentle", ("轻轻", "轻点", "轻柔"), "event"),
    ("carefulness", "careful", ("小心", "当心", "谨慎"), "global"),
    ("attentiveness", "attentive", ("仔细", "认真", "专心"), "event"),
    ("orientation", "horizontal", ("横着",), "event"),
    ("orientation", "vertical", ("竖着", "立着", "直着"), "event"),
    ("orientation", "inverted", ("倒着", "反着"), "event"),
    ("orientation", "lateral", ("侧着",), "event"),
    ("orientation", "oblique", ("斜着",), "event"),
    ("orientation", "level", ("平着",), "event"),
    ("body_attachment", "empty_handed", ("空手",), "event"),
    ("aspect", "completive", ("喝完", "做完", "接完", "放完", "完成"), "event"),
    ("aspect", "durative", ("正在", "一直"), "event"),
    ("aspect", "negated_perfective", ("还没", "尚未", "还未"), "event"),
    ("temporal", "immediate_past", ("刚才", "刚刚"), "event"),
    ("temporal", "remote_past", ("曾经",), "event"),
    ("temporal", "immediate_future", ("马上", "立刻"), "event"),
    ("temporal", "persistent", ("始终", "一直"), "event"),
    ("modality", "capability_enabled", ("能不能", "可不可以", "可以", "能"), "event"),
    ("modality", "capability_disabled", ("不能", "不可以", "不行"), "event"),
    ("modality", "uncertain", ("可能", "也许", "或许"), "event"),
    ("modality", "deontic", ("应该", "应当"), "event"),
    ("modality", "required", ("必须", "务必", "千万"), "global"),
    ("politeness", "polite", ("请", "麻烦", "劳驾"), "global"),
    ("intensity", "brief_trial", ("一下",), "event"),
)

_DIRECTION_VALUES = (
    ("return_toward_reference", ("回来",)),
    ("return_away_from_reference", ("回去",)),
    ("inward_toward_reference", ("进来",)),
    ("inward_away_from_reference", ("进去",)),
    ("outward_toward_reference", ("出来",)),
    ("outward_away_from_reference", ("出去",)),
    ("upward_toward_reference", ("上来",)),
    ("upward_away_from_reference", ("上去",)),
    ("downward_toward_reference", ("下来",)),
    ("downward_away_from_reference", ("下去",)),
    ("cross_toward_reference", ("过来",)),
    ("cross_away_from_reference", ("过去",)),
)

_CONTEXTUAL_PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("temporal", "imminent", re.compile(r"快要|就要"), "event"),
    # A bare 快 before an action is manner; 快要/快...了 is temporal.
    ("speed", "fast", re.compile(r"快(?=[拿取放走去来接倒递送搬移开关])"), "event"),
)


def _stable_id(prefix: str, payload: str) -> str:
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _nearest_event_index(start: int, end: int, events: list[dict[str, Any]]) -> int | None:
    if not events:
        return None
    return min(
        range(len(events)),
        key=lambda index: min(
            abs(start - int(events[index].get("end", 0))),
            abs(end - int(events[index].get("start", 0))),
        ),
    )


def _modifier(
    dimension: str,
    value: str,
    surface: str,
    start: int,
    end: int,
    scope: str,
    event_index: int | None,
    basis: str,
) -> dict[str, Any]:
    seed = f"{dimension}|{value}|{surface}|{start}|{end}|{event_index}"
    return {
        "modifier_id": _stable_id("modifier", seed),
        "dimension": dimension,
        "value": value,
        "surface": surface,
        "span": [start, end],
        "scope": scope,
        "event_index": event_index,
        "basis": basis,
        "candidate_only": True,
        "runtime_fact_committed": False,
        "direct_execution_allowed": False,
    }


def compile_modifier_contract(
    text: str,
    events: list[dict[str, Any]],
    *,
    discourse_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    occupied: list[tuple[int, int, str]] = []
    for dimension, value, surfaces, declared_scope in _PATTERNS:
        for surface in sorted(surfaces, key=len, reverse=True):
            for match in re.finditer(re.escape(surface), text):
                if any(
                    match.start() < end and match.end() > start and dimension == prior_dimension
                    for start, end, prior_dimension in occupied
                ):
                    continue
                event_index = _nearest_event_index(match.start(), match.end(), events)
                scope = declared_scope if declared_scope == "global" else "event"
                candidates.append(
                    _modifier(
                        dimension,
                        value,
                        surface,
                        match.start(),
                        match.end(),
                        scope,
                        None if scope == "global" else event_index,
                        "closed_class_modifier_lexicon",
                    )
                )
                occupied.append((match.start(), match.end(), dimension))
    for dimension, value, pattern, declared_scope in _CONTEXTUAL_PATTERNS:
        for match in pattern.finditer(text):
            if any(
                match.start() < end
                and match.end() > start
                and dimension == prior_dimension
                for start, end, prior_dimension in occupied
            ):
                continue
            event_index = _nearest_event_index(match.start(), match.end(), events)
            candidates.append(
                _modifier(
                    dimension,
                    value,
                    match.group(0),
                    match.start(),
                    match.end(),
                    declared_scope,
                    None if declared_scope == "global" else event_index,
                    "contextual_closed_class_modifier",
                )
            )
            occupied.append((match.start(), match.end(), dimension))
    for event_index, event in enumerate(events):
        event_start = int(event.get("start", 0))
        event_end = int(event.get("end", event_start))
        window = text[event_start : min(len(text), event_end + 4)]
        surface = str(event.get("matched_surface") or "")
        for value, forms in _DIRECTION_VALUES:
            matched = next((form for form in forms if form in surface or form in window), None)
            if not matched:
                continue
            start = text.find(matched, event_start, min(len(text), event_end + 4))
            if start < 0:
                start = event_start
            candidates.append(
                _modifier(
                    "direction",
                    value,
                    matched,
                    start,
                    start + len(matched),
                    "event",
                    event_index,
                    "directional_complement_decomposition",
                )
            )
            break
    if any(item.get("operator") == "stop_current_activity" for item in events):
        candidates.append(
            _modifier(
                "mood",
                "stop_request",
                "停止",
                0,
                len(text),
                "global",
                None,
                "event_operator_semantics",
            )
        )
    discourse_modifiers = [
        {
            "relation": edge.get("relation"),
            "source_scope_ref": edge.get("from"),
            "target_scope_ref": edge.get("to"),
            "basis": "typed_discourse_event_graph",
        }
        for edge in (discourse_graph or {}).get("edges", [])
    ]
    grouped: dict[tuple[str, int | None], set[str]] = {}
    for item in candidates:
        grouped.setdefault((item["dimension"], item.get("event_index")), set()).add(item["value"])
    conflicts = [
        {
            "dimension": dimension,
            "event_index": event_index,
            "values": sorted(values),
            "resolution": "inquiry_required",
        }
        for (dimension, event_index), values in grouped.items()
        if len(values) > 1 and dimension not in {"temporal", "aspect"}
    ]
    inquiry_contract = None
    if conflicts:
        inquiry_contract = {
            "contract_kind": "InquiryContract",
            "reason": "modifier_scope_or_value_conflict",
            "minimum_information_requested": [
                {
                    "dimension": item["dimension"],
                    "event_index": item["event_index"],
                    "allowed_values": item["values"],
                }
                for item in conflicts
            ],
            "candidate_only": True,
            "runtime_fact_committed": False,
        }
    execution_constraints = {
        "duration_scale_min": max(
            [
                1.5 if item["dimension"] == "speed" and item["value"] == "slow" else
                1.25 if item["dimension"] in {"carefulness", "force"} and item["value"] in {"careful", "gentle"} else
                1.0
                for item in candidates
            ]
            or [1.0]
        ),
        "requested_fast_cannot_exceed_executor_or_policy_limit": any(
            item["dimension"] == "speed" and item["value"] in {"fast", "accelerate"}
            for item in candidates
        ),
        "requested_strong_cannot_raise_contact_force_limit": any(
            item["dimension"] == "force" and item["value"] == "strong"
            for item in candidates
        ),
        "minimum_disturbance_requested": any(
            item["dimension"] in {"carefulness", "force"}
            and item["value"] in {"careful", "gentle"}
            for item in candidates
        ),
    }
    seed = "|".join(item["modifier_id"] for item in candidates)
    return {
        "schema_version": MODIFIER_SCHEMA_VERSION,
        "contract_kind": "ModifierContract",
        "contract_id": _stable_id("modifier_contract", seed or text),
        "modifiers": candidates,
        "event_modifiers": [
            {
                "event_index": index,
                "operator": event.get("operator"),
                "modifier_refs": [
                    item["modifier_id"]
                    for item in candidates
                    if item.get("scope") == "global" or item.get("event_index") == index
                ],
            }
            for index, event in enumerate(events)
        ],
        "discourse_modifiers": discourse_modifiers,
        "conflicts": conflicts,
        "inquiry_contract": inquiry_contract,
        "execution_constraints": execution_constraints,
        "evidence_boundary": {
            "modifier_does_not_commit_physical_fact": True,
            "urgency_does_not_override_safety_or_authorization": True,
            "evidential_surface_does_not_upgrade_evidence_envelope": True,
        },
    }


def modifiers_for_event(
    contract: dict[str, Any], event_index: int
) -> list[dict[str, Any]]:
    refs = next(
        (
            set(item.get("modifier_refs", []))
            for item in contract.get("event_modifiers", [])
            if item.get("event_index") == event_index
        ),
        set(),
    )
    return [
        deepcopy(item)
        for item in contract.get("modifiers", [])
        if item.get("modifier_id") in refs
    ]
