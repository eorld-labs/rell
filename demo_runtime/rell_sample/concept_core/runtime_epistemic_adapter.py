from __future__ import annotations

import json
from typing import Any

from .epistemic_flywheel import EventHistoryLedger
from .rcir_primitives import make_evidence_envelope, make_event, make_predicate


def ingest_p016_runtime_result(
    ledger: EventHistoryLedger,
    result: dict[str, Any],
    *,
    run_ref: str,
    world_revision: int,
) -> dict[str, Any]:
    """Adapt actual runtime receipts into L1 without making history the current fact authority."""
    trace = result["execution_trace"]
    task_ref = str(trace.get("task_id") or result["audit_summary"].get("task_id"))
    appended = []
    for trace_event in trace.get("events", []):
        event = make_event(
            f"runtime_{trace_event.get('trigger_reason') or 'transition'}",
            participant_refs={"run": run_ref, "task": task_ref},
            world_revision=world_revision,
            temporal_scope="recorded_runtime_transition",
            status="observed",
        )
        event["measurements"] = {
            "features": [str(trace_event.get("before_state")), str(trace_event.get("after_state"))],
            "effects": [str(trace_event.get("trigger_reason"))],
            "strength": 0.6,
        }
        appended.append(ledger.append(event))
    for fact in result["audit_summary"].get("fact_summary", []):
        fact_state = str(fact.get("state"))
        predicate = make_predicate(
            str(fact["fact_id"]),
            [{"role": "run", "value_type": "EntityRef", "value": run_ref}],
            world_revision=world_revision,
            status="established" if fact_state == "established" else "candidate",
            modality="verified" if fact_state == "established" else "hypothesis",
        )
        notes = json.loads(fact.get("channel_notes") or "{}")
        agreement = len(set(notes.values())) == 1 and bool(notes)
        evidence = make_evidence_envelope(
            "p016_runtime_result",
            epistemic_status="physically_verified" if fact_state == "established" else "conflicted",
            world_revision=world_revision,
            supports_refs=[predicate["predicate_id"]],
            strength=950 if fact_state == "established" else 300,
            independent_channels=max(1, len(notes)),
            physical_verification=fact_state == "established",
            verifier="P016",
            payload={"fact_state": fact_state, "channel_notes": notes},
        )
        event = make_event(
            "p016_fact_outcome",
            participant_refs={"run": run_ref, "task": task_ref},
            world_revision=world_revision,
            temporal_scope="verified_transition",
            status="observed",
            produces_predicate_refs=[predicate["predicate_id"]],
            verification_ref=evidence["envelope_id"],
        )
        event["measurements"] = {
            "features": ["multi_channel_agreement" if agreement else "channel_conflict", f"state:{fact_state}"],
            "effects": [str(fact["fact_id"])],
            "strength": 0.95 if fact_state == "established" else 0.3,
        }
        appended.extend((ledger.append(predicate), ledger.append(evidence), ledger.append(event)))
    return {
        "schema_version": "1.0.0",
        "run_ref": run_ref,
        "entries_appended": len(appended),
        "history_head_digest": ledger.snapshot()["head_digest"],
        "current_fact_authority_changed": False,
    }
