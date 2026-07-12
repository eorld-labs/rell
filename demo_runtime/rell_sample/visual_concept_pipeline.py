from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from concept_core.perceptual_grounding import load_object_concepts


DEFAULT_STORE = Path(__file__).resolve().parents[1] / "output" / "rell_sample" / "runtime" / "visual_concept_pipeline.json"
MANIFEST_FILE = Path(__file__).resolve().parent / "data" / "visual_concept_production_manifest.json"


class ImageGenerationProvider(Protocol):
    provider_id: str

    def generate(self, request: dict[str, Any]) -> list[dict[str, Any]]: ...


class DeterministicImageProvider:
    provider_id = "deterministic_test_image_provider"

    def generate(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "image_ref": f"mock://{request['request_id']}/{index}",
                "mime_type": "image/png",
                "content_digest": hashlib.sha256(f"{request['request_id']}|{index}".encode()).hexdigest(),
                "provider_metadata": {"variant": variant},
            }
            for index, variant in enumerate(request["variant_specs"])
        ]


class HttpImageGenerationProvider:
    provider_id = "generic_http_image_provider"

    def __init__(self, endpoint: str, authorization: str | None = None) -> None:
        self.endpoint = endpoint
        self.authorization = authorization

    def generate(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.authorization:
            headers["Authorization"] = self.authorization
        payload = json.dumps({"request_id": request["request_id"], "prompts": request["prompt_specs"]}).encode("utf-8")
        with urlopen(Request(self.endpoint, data=payload, headers=headers, method="POST"), timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        images = result.get("images")
        if not isinstance(images, list):
            raise ValueError("image_provider_response_missing_images")
        return images


def get_store_path() -> Path:
    configured = os.environ.get("RELL_VISUAL_PIPELINE_STORE")
    return Path(configured).resolve() if configured else DEFAULT_STORE


def _load_store() -> dict[str, Any]:
    path = get_store_path()
    if not path.exists():
        return {"schema_version": "1.0.0", "batches": [], "requests": [], "candidates": [], "concept_gap_candidates": [], "concept_kernel_candidates": [], "promoted_adapters": []}
    store = json.loads(path.read_text(encoding="utf-8"))
    for key in ("batches", "requests", "candidates", "concept_gap_candidates", "concept_kernel_candidates", "promoted_adapters"):
        store.setdefault(key, [])
    return store


def _save_store(store: dict[str, Any]) -> None:
    path = get_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _concept(concept_id: str) -> dict[str, Any] | None:
    return next((item for item in load_object_concepts()["concepts"] if item["concept_id"] == concept_id), None)


def load_production_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def compile_concept_kernel_candidate(
    gap_id: str,
    proposal: dict[str, Any],
    *,
    source_type: str,
) -> dict[str, Any]:
    if source_type not in {"human_structured_input", "external_model_candidate", "teaching_compiler"}:
        return {"error": "unsupported_concept_kernel_source", "source_type": source_type}
    store = _load_store()
    gap = next((item for item in store["concept_gap_candidates"] if item["gap_id"] == gap_id), None)
    if not gap:
        return {"error": "visual_concept_gap_not_found", "gap_id": gap_id}
    required_paths = {
        "concept_id": proposal.get("concept_id"),
        "functional_role_contract.roles": proposal.get("functional_role_contract", {}).get("roles"),
        "functional_role_contract.affordances": proposal.get("functional_role_contract", {}).get("affordances"),
        "physical_properties_and_boundaries.properties": proposal.get("physical_properties_and_boundaries", {}).get("properties"),
        "physical_properties_and_boundaries.safety_boundaries": proposal.get("physical_properties_and_boundaries", {}).get("safety_boundaries"),
        "perceptual_invariants": proposal.get("perceptual_invariants"),
        "runtime_verification_policy.candidate_checks": proposal.get("runtime_verification_policy", {}).get("candidate_checks"),
        "runtime_verification_policy.functional_checks": proposal.get("runtime_verification_policy", {}).get("functional_checks"),
    }
    missing = sorted(path for path, value in required_paths.items() if not value)
    if missing:
        return {
            "error": "concept_kernel_candidate_incomplete",
            "gap_id": gap_id,
            "missing_fields": missing,
            "candidate_only": True,
        }
    concept_id = str(proposal["concept_id"])
    if _concept(concept_id):
        return {"error": "factory_object_concept_already_exists", "concept_id": concept_id}
    candidate_seed = json.dumps([gap_id, proposal], ensure_ascii=False, sort_keys=True)
    candidate = {
        "kernel_candidate_id": "object_kernel_candidate_" + hashlib.sha1(candidate_seed.encode("utf-8")).hexdigest()[:12],
        "gap_id": gap_id,
        "item_id": gap["item_id"],
        "concept_id": concept_id,
        "display_name": str(proposal.get("display_name") or gap["display_name"]),
        "aliases": sorted(set(str(item) for item in proposal.get("aliases", [gap["display_name"]]) if item)),
        "compatible_kinds": sorted(set(str(item) for item in proposal.get("compatible_kinds", []) if item)),
        "functional_role_contract": deepcopy(proposal["functional_role_contract"]),
        "physical_properties_and_boundaries": deepcopy(proposal["physical_properties_and_boundaries"]),
        "perceptual_invariants": sorted(set(str(item) for item in proposal["perceptual_invariants"] if item)),
        "variable_features": sorted(set(str(item) for item in proposal.get("variable_features", []) if item)),
        "expected_relations": sorted(set(str(item) for item in proposal.get("expected_relations", []) if item)),
        "runtime_verification_policy": deepcopy(proposal["runtime_verification_policy"]),
        "source_type": source_type,
        "status": "awaiting_human_kernel_review",
        "candidate_only": True,
        "image_generation_allowed": False,
        "runtime_visible": False,
        "direct_execution_allowed": False,
        "must_reenter_orchestration_layer": True,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
    }
    store["concept_kernel_candidates"] = [
        item for item in store["concept_kernel_candidates"] if item["kernel_candidate_id"] != candidate["kernel_candidate_id"]
    ] + [candidate]
    gap["status"] = "concept_kernel_candidate_compiled"
    gap["kernel_candidate_id"] = candidate["kernel_candidate_id"]
    _save_store(store)
    return deepcopy(candidate)


def review_concept_kernel_candidate(
    kernel_candidate_id: str,
    *,
    approved: bool,
    reviewer_ref: str,
    review_notes: str = "",
) -> dict[str, Any]:
    if not reviewer_ref.strip():
        return {"error": "human_reviewer_reference_required"}
    store = _load_store()
    candidate = next((item for item in store["concept_kernel_candidates"] if item["kernel_candidate_id"] == kernel_candidate_id), None)
    if not candidate:
        return {"error": "concept_kernel_candidate_not_found", "kernel_candidate_id": kernel_candidate_id}
    candidate["human_review"] = {
        "reviewer_ref": reviewer_ref.strip(),
        "approved": bool(approved),
        "review_notes": review_notes,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    candidate["status"] = "approved_for_visual_generation" if approved else "kernel_revision_required"
    candidate["image_generation_allowed"] = bool(approved)
    _save_store(store)
    return deepcopy(candidate)


def release_kernel_candidate_generation(
    kernel_candidate_id: str,
    *,
    sample_count: int = 8,
) -> dict[str, Any]:
    store = _load_store()
    candidate = next((item for item in store["concept_kernel_candidates"] if item["kernel_candidate_id"] == kernel_candidate_id), None)
    if not candidate:
        return {"error": "concept_kernel_candidate_not_found", "kernel_candidate_id": kernel_candidate_id}
    if candidate.get("status") != "approved_for_visual_generation" or not candidate.get("image_generation_allowed"):
        return {"error": "concept_kernel_human_review_required", "kernel_candidate_id": kernel_candidate_id}
    concept_snapshot = {
        "concept_id": candidate["concept_id"],
        "display_name": candidate["display_name"],
        "kernel_candidate_id": kernel_candidate_id,
        "kernel_status": candidate["status"],
    }
    return _create_generation_request(
        concept_snapshot,
        sample_count,
        subject_label=candidate["display_name"],
        item_id=candidate["item_id"],
    )


def create_production_batch(*, sample_count_per_concept: int = 8) -> dict[str, Any]:
    manifest = load_production_manifest()
    request_ids = []
    concept_gaps = []
    for item in manifest["items"]:
        concept_id = item.get("concept_id")
        if concept_id and _concept(concept_id):
            request = create_generation_request(
                concept_id,
                sample_count_per_concept,
                subject_label=item["display_name"],
                item_id=item["item_id"],
            )
            request_ids.append(request["request_id"])
            continue
        gap_seed = json.dumps([manifest["manifest_id"], item["item_id"]], ensure_ascii=False)
        concept_gaps.append({
            "gap_id": "visual_concept_gap_" + hashlib.sha1(gap_seed.encode("utf-8")).hexdigest()[:12],
            "item_id": item["item_id"],
            "display_name": item["display_name"],
            "status": "object_concept_kernel_required",
            "proposed_roles": deepcopy(item.get("proposed_roles", [])),
            "required_before_image_generation": [
                "functional_role_contract",
                "physical_properties_and_boundaries",
                "perceptual_invariants",
                "runtime_verification_policy",
            ],
            "candidate_only": True,
            "image_generation_allowed": False,
            "direct_execution_allowed": False,
        })
    batch_seed = json.dumps([manifest["manifest_id"], request_ids, [item["gap_id"] for item in concept_gaps]], sort_keys=True)
    batch = {
        "batch_id": "visual_batch_" + hashlib.sha1(batch_seed.encode()).hexdigest()[:12],
        "manifest_id": manifest["manifest_id"],
        "status": "generation_pending",
        "request_ids": request_ids,
        "concept_gap_candidate_ids": [item["gap_id"] for item in concept_gaps],
        "item_count": len(manifest["items"]),
        "generation_request_count": len(request_ids),
        "concept_gap_count": len(concept_gaps),
        "results": [],
        "failure_isolation": "per_concept_request",
        "runtime_visible": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store = _load_store()
    store["batches"] = [item for item in store["batches"] if item["batch_id"] != batch["batch_id"]] + [batch]
    gap_index = {item["gap_id"]: item for item in store["concept_gap_candidates"]}
    gap_index.update({item["gap_id"]: item for item in concept_gaps})
    store["concept_gap_candidates"] = list(gap_index.values())
    _save_store(store)
    return deepcopy(batch)


def execute_production_batch(batch_id: str, provider: ImageGenerationProvider) -> dict[str, Any]:
    store = _load_store()
    batch = next((item for item in store["batches"] if item["batch_id"] == batch_id), None)
    if not batch:
        return {"error": "visual_production_batch_not_found", "batch_id": batch_id}
    results = []
    for request_id in batch["request_ids"]:
        try:
            candidate = execute_generation_request(request_id, provider)
            if "error" in candidate:
                raise ValueError(candidate["error"])
            results.append({"request_id": request_id, "status": "candidate_compiled", "candidate_id": candidate["candidate_id"]})
        except Exception as error:
            results.append({"request_id": request_id, "status": "provider_failed", "error_type": type(error).__name__})
    store = _load_store()
    batch = next(item for item in store["batches"] if item["batch_id"] == batch_id)
    batch["results"] = results
    batch["status"] = "completed_with_failures" if any(item["status"] == "provider_failed" for item in results) else "candidates_compiled"
    batch["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_store(store)
    return deepcopy(batch)


def create_generation_request(
    concept_id: str,
    sample_count: int = 8,
    *,
    subject_label: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    concept = _concept(concept_id)
    if not concept:
        return {"error": "object_concept_not_found", "concept_id": concept_id}
    return _create_generation_request(concept, sample_count, subject_label=subject_label, item_id=item_id)


def _create_generation_request(
    concept: dict[str, Any],
    sample_count: int,
    *,
    subject_label: str | None,
    item_id: str | None,
) -> dict[str, Any]:
    concept_id = concept["concept_id"]
    count = max(1, min(int(sample_count), 32))
    dimensions = [
        {"view": "front_three_quarter", "lighting": "daylight", "background": "home"},
        {"view": "side", "lighting": "soft_indoor", "background": "plain"},
        {"view": "top_three_quarter", "lighting": "daylight", "background": "table"},
        {"view": "partially_occluded", "lighting": "dim_indoor", "background": "home"},
    ]
    variants = [dimensions[index % len(dimensions)] for index in range(count)]
    subject = subject_label or concept["display_name"]
    seed = json.dumps([concept_id, item_id, subject, variants], ensure_ascii=False, sort_keys=True)
    request_id = "visual_gen_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    prompts = [
        {
            "variant_id": f"variant_{index + 1}",
            "prompt": f"写实生活物品照片：{subject}；视角={variant['view']}；光照={variant['lighting']}；背景={variant['background']}；无文字无水印。",
            "intended_use": "synthetic_visual_prior_candidate_only",
        }
        for index, variant in enumerate(variants)
    ]
    request = {
        "request_id": request_id,
        "concept_id": concept_id,
        "subject_profile": {
            "item_id": item_id,
            "concrete_label": subject,
            "parent_functional_concept": concept["display_name"],
            "kernel_candidate_id": concept.get("kernel_candidate_id"),
            "kernel_status": concept.get("kernel_status", "factory_object_concept"),
        },
        "status": "provider_generation_pending",
        "variant_specs": variants,
        "prompt_specs": prompts,
        "provider_contract": {
            "expected_response": ["image_ref", "mime_type", "content_digest"],
            "image_bytes_may_remain_in_provider_storage": True,
            "callback_or_synchronous_adapter_supported": True,
        },
        "candidate_only": True,
        "runtime_visible": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store = _load_store()
    store["requests"] = [item for item in store["requests"] if item["request_id"] != request_id] + [request]
    _save_store(store)
    return deepcopy(request)


def execute_generation_request(request_id: str, provider: ImageGenerationProvider) -> dict[str, Any]:
    store = _load_store()
    request = next((item for item in store["requests"] if item["request_id"] == request_id), None)
    if not request:
        return {"error": "visual_generation_request_not_found", "request_id": request_id}
    images = provider.generate(deepcopy(request))
    return ingest_provider_images(request_id, provider.provider_id, images)


def ingest_provider_images(request_id: str, provider_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
    store = _load_store()
    request = next((item for item in store["requests"] if item["request_id"] == request_id), None)
    if not request:
        return {"error": "visual_generation_request_not_found", "request_id": request_id}
    normalized = []
    seen = set()
    for image in images:
        digest = str(image.get("content_digest") or "")
        image_ref = str(image.get("image_ref") or "")
        if not digest or not image_ref or digest in seen:
            continue
        seen.add(digest)
        normalized.append({
            "image_ref": image_ref,
            "mime_type": str(image.get("mime_type") or "image/png"),
            "content_digest": digest,
            "source_type": "synthetic_image_api",
            "provider_id": provider_id,
            "evidence_level": "S0_synthetic_prior",
            "provider_metadata": deepcopy(image.get("provider_metadata", {})),
        })
    candidate_id = "visual_candidate_" + hashlib.sha1(f"{request_id}|{'|'.join(sorted(seen))}".encode()).hexdigest()[:12]
    candidate = {
        "candidate_id": candidate_id,
        "concept_id": request["concept_id"],
        "kernel_candidate_id": request.get("subject_profile", {}).get("kernel_candidate_id"),
        "status": "awaiting_real_world_calibration",
        "synthetic_samples": normalized,
        "real_calibration_evidence": [],
        "promotion_requirements": {
            "minimum_synthetic_samples": 4,
            "minimum_real_observations": 1,
            "human_or_physical_confirmation_required": True,
            "object_concept_kernel_must_be_promoted": bool(request.get("subject_profile", {}).get("kernel_candidate_id")),
        },
        "candidate_only": True,
        "runtime_visible": False,
        "direct_execution_allowed": False,
    }
    request["status"] = "provider_images_compiled_to_candidate"
    request["provider_id"] = provider_id
    store["candidates"] = [item for item in store["candidates"] if item["candidate_id"] != candidate_id] + [candidate]
    _save_store(store)
    return deepcopy(candidate)


def add_real_world_calibration(
    candidate_id: str,
    *,
    observation_ref: str,
    source_type: str,
    matched_features: list[str],
    human_confirmed: bool,
) -> dict[str, Any]:
    if source_type not in {"user_provided_real_image", "current_robot_camera_verified_crop"}:
        return {"error": "calibration_source_is_not_real_world_evidence", "source_type": source_type}
    store = _load_store()
    candidate = next((item for item in store["candidates"] if item["candidate_id"] == candidate_id), None)
    if not candidate:
        return {"error": "visual_candidate_not_found", "candidate_id": candidate_id}
    evidence = {
        "observation_ref": observation_ref,
        "source_type": source_type,
        "matched_features": sorted(set(matched_features)),
        "human_confirmed": bool(human_confirmed),
        "evidence_level": "R1_real_observation_confirmed" if human_confirmed else "R0_real_observation_candidate",
    }
    candidate["real_calibration_evidence"].append(evidence)
    candidate["status"] = "eligible_for_promotion_review" if human_confirmed else "awaiting_real_world_calibration"
    _save_store(store)
    return deepcopy(candidate)


def promote_visual_candidate(candidate_id: str) -> dict[str, Any]:
    store = _load_store()
    candidate = next((item for item in store["candidates"] if item["candidate_id"] == candidate_id), None)
    if not candidate:
        return {"error": "visual_candidate_not_found", "candidate_id": candidate_id}
    requirements = candidate["promotion_requirements"]
    kernel_candidate_id = candidate.get("kernel_candidate_id")
    if requirements.get("object_concept_kernel_must_be_promoted"):
        kernel_candidate = next(
            (item for item in store["concept_kernel_candidates"] if item["kernel_candidate_id"] == kernel_candidate_id),
            None,
        )
        if not kernel_candidate or kernel_candidate.get("status") != "promoted_object_concept_kernel":
            return {
                "error": "object_concept_kernel_promotion_required",
                "kernel_candidate_id": kernel_candidate_id,
                "candidate": deepcopy(candidate),
            }
    confirmed = [item for item in candidate["real_calibration_evidence"] if item.get("human_confirmed")]
    if len(candidate["synthetic_samples"]) < requirements["minimum_synthetic_samples"] or len(confirmed) < requirements["minimum_real_observations"]:
        return {"error": "visual_candidate_promotion_requirements_not_met", "candidate": deepcopy(candidate)}
    adapter = {
        "adapter_version_id": "visual_adapter_" + hashlib.sha1(candidate_id.encode()).hexdigest()[:12],
        "concept_id": candidate["concept_id"],
        "status": "promoted_visual_adapter",
        "synthetic_prior_digests": [item["content_digest"] for item in candidate["synthetic_samples"]],
        "real_calibration_evidence": deepcopy(confirmed),
        "load_policy": "on_demand",
        "runtime_use": "candidate_generation_only",
        "runtime_visible": False,
        "deployment_status": "awaiting_controlled_deployment",
        "direct_execution_allowed": False,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    candidate["status"] = "promoted"
    candidate["runtime_visible"] = False
    store["promoted_adapters"] = [item for item in store["promoted_adapters"] if item["concept_id"] != adapter["concept_id"]] + [adapter]
    _save_store(store)
    return deepcopy(adapter)


def get_pipeline_state() -> dict[str, Any]:
    return deepcopy(_load_store())
