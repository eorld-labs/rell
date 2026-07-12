from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Callable
from urllib.request import Request, urlopen


JsonRequester = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class QwenVisualConceptAdapter:
    provider_id = "qwen_openai_compatible_visual_candidate_provider"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        requester: JsonRequester | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("qwen_base_url_must_use_https")
        if not api_key.strip():
            raise ValueError("qwen_api_key_required")
        if not model.strip():
            raise ValueError("qwen_visual_model_required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.requester = requester or _post_json

    def propose_kernel(
        self,
        gap: dict[str, Any],
        image_refs: list[str],
        *,
        language_context: str = "",
    ) -> dict[str, Any]:
        normalized_refs = [item.strip() for item in image_refs if item and item.strip()]
        if not normalized_refs:
            return {"error": "real_image_reference_required"}
        if any(not _supported_image_ref(item) for item in normalized_refs):
            return {"error": "unsupported_image_reference"}
        content: list[dict[str, Any]] = [{"type": "text", "text": _proposal_prompt(gap, language_context)}]
        content.extend({"type": "image_url", "image_url": {"url": item}} for item in normalized_refs)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        response = self.requester(
            self.base_url + "/chat/completions",
            {"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            payload,
        )
        proposal = _extract_proposal(response)
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "gap_id": gap.get("gap_id"),
            "image_evidence_refs": normalized_refs,
            "proposal": proposal,
            "source_type": "external_model_candidate",
            "candidate_only": True,
            "human_review_required": True,
            "runtime_visible": False,
            "direct_execution_allowed": False,
            "raw_provider_response_retained": False,
        }


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _supported_image_ref(value: str) -> bool:
    return value.startswith("https://") or value.startswith("data:image/")


def _extract_proposal(response: dict[str, Any]) -> dict[str, Any]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("qwen_response_missing_message_content") from error
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    text = str(content).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("qwen_response_is_not_json") from error
    if not isinstance(result, dict):
        raise ValueError("qwen_response_is_not_object")
    return deepcopy(result)


def _proposal_prompt(gap: dict[str, Any], language_context: str) -> str:
    return (
        "你是具身智能对象概念候选编译器，不是事实裁决者。根据图片只提出可审核草案；"
        "不得声称已识别、已验真或可执行。不能从外观证明的功能与物理属性必须写成待验候选。"
        f"对象名称候选：{gap.get('display_name', '')}；建议角色：{gap.get('proposed_roles', [])}；"
        f"教师补充：{language_context or '无'}。仅输出 JSON 对象，必须包含："
        "concept_id, display_name, aliases, compatible_kinds, "
        "functional_role_contract.roles, functional_role_contract.affordances, "
        "physical_properties_and_boundaries.properties, physical_properties_and_boundaries.safety_boundaries, "
        "perceptual_invariants, variable_features, expected_relations, "
        "runtime_verification_policy.candidate_checks, runtime_verification_policy.functional_checks。"
    )
