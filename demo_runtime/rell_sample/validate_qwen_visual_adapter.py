from __future__ import annotations

from qwen_visual_adapter import QwenVisualConceptAdapter


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    captured = {}

    def mock_requester(url: str, headers: dict[str, str], payload: dict) -> dict:
        captured.update({"url": url, "headers": headers, "payload": payload})
        return {
            "choices": [{"message": {"content": """```json
{
  "concept_id": "concept_fillable_bowl",
  "display_name": "可盛装碗状容器",
  "aliases": ["碗"],
  "compatible_kinds": ["graspable_container"],
  "functional_role_contract": {"roles": ["container"], "affordances": ["receive_material"]},
  "physical_properties_and_boundaries": {"properties": ["bounded_inner_volume"], "safety_boundaries": ["grasp_force_below_damage_limit"]},
  "perceptual_invariants": ["open_top", "stable_base"],
  "variable_features": ["color"],
  "expected_relations": ["on_top_of_support"],
  "runtime_verification_policy": {"candidate_checks": ["shape_invariants_observed"], "functional_checks": ["container_role_physically_verified_before_use"]}
}
```"""}}]
        }

    adapter = QwenVisualConceptAdapter(
        base_url="https://qwen.example/compatible-mode/v1",
        api_key="test-secret-not-real",
        model="qwen-vl-test",
        requester=mock_requester,
    )
    result = adapter.propose_kernel(
        {"gap_id": "gap_bowl", "display_name": "碗", "proposed_roles": ["container"]},
        ["data:image/png;base64,ZmFrZQ=="],
        language_context="这是家用饭碗",
    )
    require(result["proposal"]["concept_id"] == "concept_fillable_bowl", f"proposal JSON was not compiled: {result}")
    require(result["candidate_only"] and result["human_review_required"] and not result["runtime_visible"], f"provider gained authority: {result}")
    require(captured["url"].endswith("/chat/completions"), f"wrong compatible endpoint: {captured}")
    require(captured["headers"]["Authorization"] == "Bearer test-secret-not-real", "authorization contract missing")
    require(captured["payload"]["temperature"] == 0 and captured["payload"]["response_format"] == {"type": "json_object"}, f"structured output contract missing: {captured}")
    require(captured["payload"]["messages"][0]["content"][1]["type"] == "image_url", f"image input missing: {captured}")
    require("concept_<snake_case>" in captured["payload"]["messages"][0]["content"][0]["text"], f"concept identifier contract missing from prompt: {captured}")
    require(adapter.propose_kernel({"gap_id": "gap"}, ["file:///unsafe.jpg"]).get("error") == "unsupported_image_reference", "local file path escaped adapter boundary")

    repair_calls = []

    def repair_requester(url: str, headers: dict[str, str], payload: dict) -> dict:
        repair_calls.append(payload)
        properties = {"shape": "round"} if len(repair_calls) == 1 else ["bounded_inner_volume"]
        content = {
            "concept_id": "concept_fillable_bowl",
            "display_name": "可盛装碗状容器",
            "aliases": ["碗"],
            "compatible_kinds": ["graspable_container"],
            "functional_role_contract": {"roles": ["container"], "affordances": ["receive_material"]},
            "physical_properties_and_boundaries": {"properties": properties, "safety_boundaries": ["grasp_force_below_damage_limit"]},
            "perceptual_invariants": ["open_top"],
            "variable_features": [],
            "expected_relations": [],
            "runtime_verification_policy": {"candidate_checks": ["shape_observed"], "functional_checks": ["capacity_verified"]},
        }
        return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

    repaired = QwenVisualConceptAdapter(
        base_url="https://qwen.example/compatible-mode/v1",
        api_key="test-secret-not-real",
        model="qwen-vl-test",
        requester=repair_requester,
    ).propose_kernel({"gap_id": "gap_bowl", "display_name": "碗"}, ["data:image/png;base64,ZmFrZQ=="])
    require(len(repair_calls) == 2 and repaired["repair_attempted"] and repaired["contract_validated"], f"invalid provider structure was not repaired exactly once: {repaired}")
    require(len(repair_calls[1]["messages"]) == 3, f"repair feedback was not returned to provider: {repair_calls}")

    quantified_calls = []

    def quantified_requester(url: str, headers: dict[str, str], payload: dict) -> dict:
        quantified_calls.append(payload)
        boundary = "load_capacity_100kg_requires_verification" if len(quantified_calls) == 1 else "load_capacity_requires_physical_verification"
        content = {
            "concept_id": "concept_sofa",
            "display_name": "沙发",
            "aliases": ["沙发"],
            "compatible_kinds": ["furniture"],
            "functional_role_contract": {"roles": ["human_support_furniture"], "affordances": ["support_sitting_candidate"]},
            "physical_properties_and_boundaries": {"properties": ["ground_supported_structure"], "safety_boundaries": [boundary]},
            "perceptual_invariants": ["seating_surface", "back_support_structure"],
            "variable_features": [],
            "expected_relations": ["on_floor_candidate"],
            "runtime_verification_policy": {"candidate_checks": ["structure_observed"], "functional_checks": ["load_capacity_verified"]},
        }
        return {"choices": [{"message": {"content": __import__("json").dumps(content, ensure_ascii=False)}}]}

    quantified = QwenVisualConceptAdapter(
        base_url="https://qwen.example/compatible-mode/v1",
        api_key="test-secret-not-real",
        model="qwen-vl-test",
        requester=quantified_requester,
    ).propose_kernel({"gap_id": "gap_sofa", "display_name": "沙发"}, ["data:image/png;base64,ZmFrZQ=="])
    require(len(quantified_calls) == 2 and quantified["contract_validated"], f"quantified visual claim bypassed repair: {quantified}")
    print("Qwen visual concept adapter validation passed.")


if __name__ == "__main__":
    main()
