from __future__ import annotations

import re
from typing import Any


MACHINE_TOKEN = re.compile(r"^[a-z][a-z0-9_.:-]*$")
CONCEPT_ID = re.compile(r"^(?:concept_[a-z0-9_]+|urn:[a-z0-9_.:-]+)$")
QUANTIFIED_PHYSICAL_CLAIM = re.compile(r"(?:\d|_gt_|_lt_|_min_|_max_|estimated_[0-9])")


def validate_concept_kernel_proposal(proposal: Any) -> list[dict[str, str]]:
    if not isinstance(proposal, dict):
        return [{"path": "$", "reason": "must_be_object"}]
    errors: list[dict[str, str]] = []
    _required_string(proposal, "concept_id", errors, pattern=CONCEPT_ID)
    _required_string(proposal, "display_name", errors)
    _string_list(proposal, "aliases", errors, machine_tokens=False)
    _string_list(proposal, "compatible_kinds", errors)
    _nested_string_lists(proposal, "functional_role_contract", ("roles", "affordances"), errors)
    _nested_string_lists(
        proposal,
        "physical_properties_and_boundaries",
        ("properties", "safety_boundaries"),
        errors,
    )
    _string_list(proposal, "perceptual_invariants", errors)
    _string_list(proposal, "variable_features", errors, allow_empty=True)
    _string_list(proposal, "expected_relations", errors, allow_empty=True)
    _nested_string_lists(
        proposal,
        "runtime_verification_policy",
        ("candidate_checks", "functional_checks"),
        errors,
    )
    return errors


def validate_external_visual_claims(proposal: Any) -> list[dict[str, str]]:
    if not isinstance(proposal, dict):
        return [{"path": "$", "reason": "must_be_object"}]
    errors: list[dict[str, str]] = []
    physical = proposal.get("physical_properties_and_boundaries", {})
    if not isinstance(physical, dict):
        return errors
    for field in ("properties", "safety_boundaries"):
        values = physical.get(field, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if isinstance(value, str) and QUANTIFIED_PHYSICAL_CLAIM.search(value):
                errors.append({
                    "path": f"physical_properties_and_boundaries.{field}[{index}]",
                    "reason": "quantified_physical_claim_requires_measurement_evidence",
                })
    return errors


def _required_string(
    container: dict[str, Any],
    key: str,
    errors: list[dict[str, str]],
    *,
    pattern: re.Pattern[str] | None = None,
) -> None:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append({"path": key, "reason": "must_be_non_empty_string"})
    elif pattern and not pattern.fullmatch(value):
        errors.append({"path": key, "reason": "invalid_machine_identifier"})


def _nested_string_lists(
    proposal: dict[str, Any],
    parent: str,
    children: tuple[str, ...],
    errors: list[dict[str, str]],
) -> None:
    value = proposal.get(parent)
    if not isinstance(value, dict):
        errors.append({"path": parent, "reason": "must_be_object"})
        return
    for child in children:
        _string_list(value, child, errors, path_prefix=parent)


def _string_list(
    container: dict[str, Any],
    key: str,
    errors: list[dict[str, str]],
    *,
    path_prefix: str = "",
    machine_tokens: bool = True,
    allow_empty: bool = False,
) -> None:
    path = f"{path_prefix}.{key}" if path_prefix else key
    value = container.get(key)
    if not isinstance(value, list):
        errors.append({"path": path, "reason": "must_be_array"})
        return
    if not value and not allow_empty:
        errors.append({"path": path, "reason": "must_be_non_empty_array"})
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, str) or not item.strip():
            errors.append({"path": item_path, "reason": "must_be_non_empty_string"})
        elif machine_tokens and not MACHINE_TOKEN.fullmatch(item):
            errors.append({"path": item_path, "reason": "must_be_machine_token"})
