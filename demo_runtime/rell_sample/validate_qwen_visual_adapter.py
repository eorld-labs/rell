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
    require(adapter.propose_kernel({"gap_id": "gap"}, ["file:///unsafe.jpg"]).get("error") == "unsupported_image_reference", "local file path escaped adapter boundary")
    print("Qwen visual concept adapter validation passed.")


if __name__ == "__main__":
    main()
