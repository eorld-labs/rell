from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
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


class PatternDiscoveryEngine:
    """Incremental statistics over immutable history entries; it never explains causes."""

    def __init__(self) -> None:
        self._episodes: dict[str, list[dict[str, Any]]] = {}
        self._seen_entry_digests: set[str] = set()

    @staticmethod
    def _signature(entry: dict[str, Any]) -> str | None:
        payload = entry.get("payload") or {}
        event_type = payload.get("event_type")
        if not event_type:
            return None
        roles = sorted((payload.get("participant_refs") or {}).keys())
        return f"{event_type}|roles={','.join(roles)}"

    def ingest(self, entry: dict[str, Any]) -> None:
        entry_digest = str(entry.get("entry_digest") or "")
        if entry_digest and entry_digest in self._seen_entry_digests:
            return
        signature = self._signature(entry)
        if signature is None:
            return
        if entry_digest:
            self._seen_entry_digests.add(entry_digest)
        payload = entry["payload"]
        measurements = payload.get("measurements") or {}
        episode = {
            "source_ref": entry["source_ref"],
            "world_revision": entry["world_revision"],
            "instance_refs": sorted(set((payload.get("participant_refs") or {}).values())),
            "features": sorted(set(measurements.get("features") or [])),
            "effects": sorted(set(measurements.get("effects") or [])),
            "strength": float(measurements.get("strength") or 0.0),
        }
        self._episodes.setdefault(signature, []).append(episode)

    def ingest_ledger(self, ledger: EventHistoryLedger, from_revision: int = 0) -> None:
        for entry in ledger.replay(from_revision):
            self.ingest(entry)

    def query_active_patterns(self, min_strength: float = 0.0, min_episodes: int = 2) -> list[dict[str, Any]]:
        patterns = []
        for signature, episodes in sorted(self._episodes.items()):
            if len(episodes) < min_episodes:
                continue
            feature_sets = [set(item["features"]) for item in episodes]
            effect_sets = [set(item["effects"]) for item in episodes]
            stable_features = set.intersection(*feature_sets) if feature_sets else set()
            all_features = set.union(*feature_sets) if feature_sets else set()
            stable_effects = set.intersection(*effect_sets) if effect_sets else set()
            exact_profiles: dict[tuple[str, ...], int] = {}
            for item in episodes:
                profile = tuple(item["features"] + [f"effect:{value}" for value in item["effects"]])
                exact_profiles[profile] = exact_profiles.get(profile, 0) + 1
            consistency = max(exact_profiles.values()) / len(episodes)
            strengths = [item["strength"] for item in episodes]
            mean_strength = sum(strengths) / len(strengths)
            if mean_strength < min_strength:
                continue
            delta = strengths[-1] - strengths[0]
            trend = "rising" if delta > 0.05 else "decaying" if delta < -0.05 else "stable"
            patterns.append({
                "pattern_signature": signature,
                "observed_episodes": len(episodes),
                "cross_instance_count": len({ref for item in episodes for ref in item["instance_refs"]}),
                "cross_instance_consistency": consistency,
                "stable_features": sorted(stable_features),
                "stable_effects": sorted(stable_effects),
                "variable_features": sorted(all_features - stable_features),
                "measurements": {"strength_samples": strengths},
                "mean_strength": mean_strength,
                "strength_trend": trend,
                "candidate_only": True,
                "runtime_fact_committed": False,
            })
        return patterns


@dataclass
class EpistemicMetaParams:
    min_pattern_strength: float = 0.55
    min_investigation_score: float = 0.55
    min_verification_channels: int = 2
    hypothesis_generation_bias: float = 0.0

    def clamp(self) -> None:
        self.min_pattern_strength = min(0.95, max(0.2, self.min_pattern_strength))
        self.min_investigation_score = min(0.95, max(0.2, self.min_investigation_score))
        self.min_verification_channels = min(4, max(2, self.min_verification_channels))
        self.hypothesis_generation_bias = min(0.5, max(-0.5, self.hypothesis_generation_bias))


class EpistemicLoopEngine:
    """Bounded L4 scheduler. A tick proposes work; only P018/P016 may execute and verify it."""

    def __init__(self, ledger: EventHistoryLedger, discovery: PatternDiscoveryEngine, space: ConceptSpace) -> None:
        self.ledger = ledger
        self.discovery = discovery
        self.space = space
        self.meta_params = EpistemicMetaParams()
        self.active_inquiries: dict[str, dict[str, Any]] = {}
        self.closed_inquiries: dict[str, dict[str, Any]] = {}
        self.pending_dictionary_admission: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _pattern_features(pattern: dict[str, Any]) -> dict[str, Any]:
        return {
            "perceptual_invariants": pattern.get("stable_features") or [],
            "functional_affordances": [],
            "effects": pattern.get("stable_effects") or [],
            "applicability_constraints": [],
        }

    def _assessment(self, pattern: dict[str, Any]) -> dict[str, Any]:
        nearest = self.space.nearest_neighbors(self._pattern_features(pattern), top_k=1)
        nearest_ref, novelty = nearest[0] if nearest else (None, 1.0)
        consistency = float(pattern.get("cross_instance_consistency") or 0.0)
        strength = float(pattern.get("mean_strength") or 0.0)
        information_gain = consistency * novelty
        probe_cost = 0.1
        score = 0.4 * strength + 0.3 * novelty + 0.3 * consistency - probe_cost + self.meta_params.hypothesis_generation_bias
        already_explained = nearest_ref is not None and novelty <= 0.15
        return {
            "nearest_concept_ref": nearest_ref,
            "concept_distance": novelty,
            "expected_information_gain": information_gain,
            "probe_cost": probe_cost,
            "investigation_score": score,
            "already_explained_by_concept": already_explained,
            "should_investigate": not already_explained and score >= self.meta_params.min_investigation_score,
        }

    def tick(self, probe_outcomes: dict[str, bool] | None = None) -> dict[str, Any]:
        from .cognitive_inquiry import run_concept_validation_loop

        self.discovery.ingest_ledger(self.ledger)
        probe_outcomes = probe_outcomes or {}
        patterns = self.discovery.query_active_patterns(min_strength=self.meta_params.min_pattern_strength)
        launched = []
        resolved = []
        monitored = []
        for pattern in patterns:
            signature = pattern["pattern_signature"]
            if signature in self.closed_inquiries:
                continue
            assessment = self._assessment(pattern)
            if not assessment["should_investigate"]:
                monitored.append({"pattern_signature": signature, **assessment})
                continue
            inquiry = self.active_inquiries.setdefault(signature, {
                "pattern_signature": signature,
                "status": "awaiting_p018_authorized_probe",
                "assessment": assessment,
                "pattern": deepcopy(pattern),
                "direct_execution_allowed": False,
            })
            if signature not in probe_outcomes:
                launched.append(deepcopy(inquiry))
                continue
            loop = run_concept_validation_loop(prediction_confirmed=bool(probe_outcomes[signature]))
            if loop["action"]["arbitration_receipt"]["decision"] != "authorized":
                raise AssertionError("epistemic_probe_bypassed_p018")
            if loop["decision"]["basis"] != "new_instance_p016_verification":
                raise AssertionError("epistemic_probe_bypassed_p016")
            decision = loop["decision"]["decision"]
            closed = {**inquiry, "status": "closed", "decision": decision, "loop": loop}
            self.closed_inquiries[signature] = closed
            self.active_inquiries.pop(signature, None)
            if decision == "promoted":
                self.pending_dictionary_admission[signature] = {
                    "candidate": deepcopy(loop["candidate"]),
                    "pattern_features": self._pattern_features(pattern),
                }
                self.meta_params.min_investigation_score *= 0.95
            else:
                self.meta_params.hypothesis_generation_bias += 0.01
            self.meta_params.clamp()
            resolved.append({"pattern_signature": signature, "decision": decision})
        return {
            "status": "tick_completed",
            "active_pattern_count": len(patterns),
            "launched": launched,
            "resolved": resolved,
            "monitored": monitored,
            "pending_dictionary_admission": sorted(self.pending_dictionary_admission),
            "meta_params": deepcopy(self.meta_params.__dict__),
            "fact_authority": "WorldFactLedger",
            "control_gateway": "P018",
            "verification_gateway": "P016",
            "direct_execution_allowed": False,
        }

    def admit_promoted_concept(self, pattern_signature: str, *, admission_ref: str) -> str:
        pending = self.pending_dictionary_admission.pop(pattern_signature)
        candidate = pending["candidate"]
        causal = candidate.get("minimal_causal_contract") or {}
        pattern_features = pending.get("pattern_features") or {}
        concept = {
            "concept_id": candidate["concept_id"],
            "perceptual_invariants": pattern_features.get("perceptual_invariants", causal.get("observable_features") or candidate.get("perceptual_invariants") or []),
            "functional_affordances": pattern_features.get("functional_affordances", causal.get("functional_affordances") or candidate.get("functional_affordances") or []),
            "effects": pattern_features.get("effects", causal.get("effects") or []),
            "applicability_constraints": pattern_features.get("applicability_constraints", (candidate.get("applicability_contract") or {}).get("scope") or []),
        }
        return self.space.add_concept(concept, admission_ref=admission_ref)
