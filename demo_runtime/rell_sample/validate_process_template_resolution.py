from __future__ import annotations

from copy import deepcopy

from concept_core.factory_event_units import FACTORY_EVENT_CONCEPT_UNITS
from concept_core.language_concept_composer import compose_language_concepts
from concept_core.perceptual_grounding import load_object_concepts
from concept_core.process_template_resolver import build_process_template_catalog, resolve_process_request
from embodied_scene import SESSIONS, begin_motion_command, get_session, load_scene, start_session, step_motion_command


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def drain_chain(started: dict) -> list[dict]:
    outcomes = []
    current = started
    while current:
        immediate = current.get("immediate_result")
        if immediate:
            outcomes.append(immediate)
            break
        job_id = current.get("job_id")
        require(bool(job_id), f"expected motion job: {current}")
        while True:
            stepped = step_motion_command(job_id)
            if stepped.get("status") == "motion_completed":
                result = stepped["result"]
                outcomes.append(result)
                current = result.get("next_stage_started")
                break
            require(stepped.get("status") == "frame_verified_and_committed", f"motion failed: {stepped}")
    return outcomes


def compose(text: str) -> dict:
    return compose_language_concepts(
        text,
        event_concepts=FACTORY_EVENT_CONCEPT_UNITS,
        object_concepts=load_object_concepts()["concepts"],
    )


def resolve(text: str, scene_id: str = "home_semantic_3d_a") -> dict:
    scene = load_scene(scene_id)
    analysis = compose(text)
    return resolve_process_request(
        text,
        analysis,
        runtime_objects=scene["objects"],
        runtime_state=deepcopy(scene["initial_state"]),
        semantic_regions=scene["semantic_regions"],
        executor_profile=scene["executor_profiles"]["home_humanoid"],
        world_revision=0,
    ) or {}


def main() -> None:
    catalog = build_process_template_catalog()
    require({item["template_id"] for item in catalog["templates"]} == {"grasp_object", "place_object", "handover_object", "transport_object"}, f"initial process template set incomplete: {catalog}")
    require(catalog["resolution_contract"]["templates_declare_slots_not_question_strings"], f"questions leaked into individual templates: {catalog}")

    unknown = resolve("把苹果捎给人类")
    require(unknown.get("status") == "template_confirmation_required", f"unknown relational verb did not form a bounded template candidate: {unknown}")
    require(unknown.get("template_id") == "handover_object" and unknown.get("template_candidate", {}).get("novel_surface") == "捎给", f"unknown surface was learned as a whole sentence or wrong template: {unknown}")
    require(unknown.get("bindings", {}).get("theme", {}).get("value_ref") == "apple_a" and unknown.get("bindings", {}).get("recipient", {}).get("value_ref") == "human_a", f"current snapshot did not fill unique handover slots: {unknown}")

    ambiguous_session = start_session("home_humanoid", "home_semantic_3d_a")
    ambiguous_runtime = SESSIONS[ambiguous_session["session_id"]]
    first_human = next(item for item in ambiguous_runtime["runtime_objects"] if item["entity_id"] == "human_a")
    first_human["label"] = "老张"
    second_human = deepcopy(first_human)
    second_human.update({"entity_id": "human_2", "label": "老李", "position": [-2.2, 1.3], "received_object_refs": []})
    ambiguous_runtime["runtime_objects"].append(second_human)
    asked = begin_motion_command(ambiguous_session["session_id"], "把苹果捎给他")
    asked_result = asked.get("immediate_result") or asked
    require(asked_result.get("status") == "process_slot_clarification_required" and asked_result.get("pending_slot") == "recipient", f"multiple recipients did not trigger the recipient slot question: {asked}")
    require("老张" in asked_result.get("prompt", "") and "老李" in asked_result.get("prompt", ""), f"recipient candidates were not enumerated from the snapshot: {asked}")
    selected = begin_motion_command(ambiguous_session["session_id"], "老张")
    selected_result = selected.get("immediate_result") or selected
    require(selected_result.get("status") == "process_template_confirmation_required", f"slot answer did not advance to template confirmation: {selected}")
    confirmed = begin_motion_command(ambiguous_session["session_id"], "对")
    outcomes = drain_chain(confirmed)
    live = get_session(ambiguous_session["session_id"])
    apple = next(item for item in live["runtime_objects"] if item["entity_id"] == "apple_a")
    require(apple.get("received_by") == "human_a", f"confirmed unknown expression did not resume and verify the original goal: {outcomes}: {apple}")
    learned = confirmed.get("process_template_mapping_learned", {})
    require(learned.get("surface_form") == "捎给" and learned.get("modifies_concept_kernel") is False, f"template confirmation did not create a scoped language adapter: {confirmed}")

    unsafe_session = start_session("home_mobile_manipulator", "home_semantic_3d_a")
    unsafe_runtime = SESSIONS[unsafe_session["session_id"]]
    cup = next(item for item in unsafe_runtime["runtime_objects"] if item["entity_id"] == "cup_a")
    cup["attached_to_executor"] = True
    cup["held_by_effector"] = "primary_gripper"
    unsafe_runtime["state"]["holding"] = "cup_a"
    unsafe_runtime["state"]["holding_by_effector"] = {"primary_gripper": "cup_a"}
    unsafe = begin_motion_command(unsafe_session["session_id"], "拿起苹果")
    unsafe_result = unsafe.get("immediate_result") or unsafe
    require(unsafe_result.get("status") == "process_slot_clarification_required" and "白色杯子" in unsafe_result.get("prompt", ""), f"holding conflict did not become a structured unsafe-switch question: {unsafe}")

    carry_session = start_session("home_humanoid", "home_semantic_3d_a")
    carry_outcomes = drain_chain(begin_motion_command(carry_session["session_id"], "把苹果带到厨房"))
    carry_live = get_session(carry_session["session_id"])
    require([item.get("terminal_fact") for item in carry_outcomes] == ["target_object_in_gripper", "object_at_target_region"], f"retain-holding transport did not compose from current facts: {carry_outcomes}")
    require(carry_live["state"].get("active_region") == "kitchen" and carry_live["state"].get("holding") == "apple_a", f"carry mode lost region or holding truth: {carry_live['state']}")

    deliver_session = start_session("home_humanoid", "home_semantic_3d_a")
    deliver_outcomes = drain_chain(begin_motion_command(deliver_session["session_id"], "把苹果送到厨房"))
    deliver_live = get_session(deliver_session["session_id"])
    delivered_apple = next(item for item in deliver_live["runtime_objects"] if item["entity_id"] == "apple_a")
    require([item.get("terminal_fact") for item in deliver_outcomes] == ["target_object_in_gripper", "object_at_target_region", "object_supported_at_destination"], f"place-at-region transport did not derive its final placement stage: {deliver_outcomes}")
    require(delivered_apple.get("support_ref") == "counter_a" and deliver_live["state"].get("holding") is None, f"delivery mode did not establish stable placement: {delivered_apple}")

    print("Process template and slot gap resolution validation passed.")
    print({
        "templates": 4,
        "unknown_surface": "捎给",
        "recipient_clarification": ["老张", "老李"],
        "transport_modes": ["retain_holding", "place_at_region"],
    })


if __name__ == "__main__":
    main()
