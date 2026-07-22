from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class EventHistoryLedger:
    """Append-only history for Event, Predicate and EvidenceEnvelope records."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._entries: list[dict[str, Any]] = []
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._entries.append(json.loads(line))

    def append(self, payload: dict[str, Any]) -> str:
        kind = str(payload.get("type") or payload.get("ir_kind") or "unknown")
        source_ref = next((payload.get(key) for key in ("event_id", "predicate_id", "envelope_id", "concept_id") if payload.get(key)), None)
        if not source_ref:
            raise ValueError("history_entry_source_ref_missing")
        previous_digest = self._entries[-1]["entry_digest"] if self._entries else None
        entry_base = {
            "schema_version": "1.0.0",
            "sequence": len(self._entries) + 1,
            "kind": kind,
            "source_ref": source_ref,
            "world_revision": int(payload.get("world_revision") or 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_digest": previous_digest,
            "payload": deepcopy(payload),
        }
        entry = {**entry_base, "entry_digest": _digest(entry_base)}
        self._entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry["entry_digest"]

    def query(
        self,
        *,
        kind: str | None = None,
        participant_ref: str | None = None,
        min_world_revision: int | None = None,
        max_world_revision: int | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for entry in self._entries:
            if kind and entry["kind"] != kind:
                continue
            revision = entry["world_revision"]
            if min_world_revision is not None and revision < min_world_revision:
                continue
            if max_world_revision is not None and revision > max_world_revision:
                continue
            if participant_ref and participant_ref not in json.dumps(entry["payload"], ensure_ascii=False):
                continue
            result.append(deepcopy(entry))
        return result

    def replay(self, from_revision: int = 0) -> Iterable[dict[str, Any]]:
        for entry in self._entries:
            if entry["world_revision"] >= from_revision:
                yield deepcopy(entry)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "entry_count": len(self._entries),
            "head_digest": self._entries[-1]["entry_digest"] if self._entries else None,
            "append_only": True,
            "mutable_fact_authority": False,
        }


def _feature_set(concept: dict[str, Any], field: str) -> set[str]:
    value = concept.get(field) or []
    if isinstance(value, dict):
        return {f"{key}={item}" for key, item in value.items()}
    return {str(item) for item in value}


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - len(left & right) / len(left | right)


class ConceptSpace:
    """Runtime concept topology; proposals never mutate the authority dictionary."""

    FIELDS = ("perceptual_invariants", "functional_affordances", "effects", "applicability_constraints")

    def __init__(self, concepts: Iterable[dict[str, Any]] = (), weights: dict[str, float] | None = None) -> None:
        self.concepts = {str(item["concept_id"]): deepcopy(item) for item in concepts}
        self.weights = weights or {field: 0.25 for field in self.FIELDS}
        if abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError("concept_distance_weights_must_sum_to_one")

    def distance(self, left_ref: str, right_ref: str) -> float:
        return self.distance_to_features(self.concepts[left_ref], self.concepts[right_ref])

    def distance_to_features(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        return sum(
            self.weights[field] * _jaccard_distance(_feature_set(left, field), _feature_set(right, field))
            for field in self.FIELDS
        )

    def nearest_neighbors(self, features: dict[str, Any], top_k: int = 3) -> list[tuple[str, float]]:
        ranked = sorted(
            ((ref, self.distance_to_features(features, concept)) for ref, concept in self.concepts.items()),
            key=lambda item: (item[1], item[0]),
        )
        return ranked[:top_k]

    def add_concept(self, concept: dict[str, Any], *, admission_ref: str) -> str:
        concept_ref = str(concept["concept_id"])
        if concept_ref in self.concepts:
            raise ValueError("concept_already_exists")
        admitted = deepcopy(concept)
        admitted["dictionary_authority_admission_ref"] = admission_ref
        self.concepts[concept_ref] = admitted
        return concept_ref

    def propose_merge(self, left_ref: str, right_ref: str, threshold: float = 0.15) -> dict[str, Any] | None:
        distance = self.distance(left_ref, right_ref)
        if distance > threshold:
            return None
        return {"status": "candidate_only", "operation": "merge", "concept_refs": [left_ref, right_ref], "distance": distance, "direct_dictionary_write_allowed": False}

    def propose_split(self, concept_ref: str, instance_profiles: list[dict[str, Any]], threshold: float = 0.6) -> dict[str, Any] | None:
        if len(instance_profiles) < 2:
            return None
        maximum = max(self.distance_to_features(left, right) for index, left in enumerate(instance_profiles) for right in instance_profiles[index + 1:])
        if maximum < threshold:
            return None
        return {"status": "candidate_only", "operation": "split", "concept_ref": concept_ref, "maximum_instance_distance": maximum, "direct_dictionary_write_allowed": False}
