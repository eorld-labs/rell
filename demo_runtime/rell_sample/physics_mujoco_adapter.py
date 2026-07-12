from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mujoco
import numpy as np


EXECUTOR_CAPABILITIES = {
    "mobile_manipulator": {"navigate_to_region", "grasp_object", "fill_container"},
    "mobile_base": {"navigate_to_region"},
    "fixed_arm": {"grasp_object", "fill_container"},
}


LAYOUTS = {
    "kitchen_a": {
        "start": (-2.2, 0.0),
        "operation_region": (0.0, 0.0),
        "water_source_region": (2.2, 0.0),
        "obstacle_center": (1.1, 0.0),
        "detour_waypoint": (1.1, 1.35),
    },
    "corridor_b": {
        "start": (0.0, -2.2),
        "operation_region": (0.0, 0.0),
        "water_source_region": (0.0, 2.2),
        "obstacle_center": (0.0, 1.1),
        "detour_waypoint": (1.35, 1.1),
    },
}


@dataclass
class RouteResult:
    outcome: str
    route_kind: str
    contact_observed: bool
    samples_checked: int


class MujocoEmbodiedAdapter:
    """Headless physics boundary. Absolute poses never leave this adapter."""

    def __init__(self, layout_id: str, executor_type: str, obstacle: str = "none") -> None:
        if layout_id not in LAYOUTS:
            raise ValueError(f"unknown layout: {layout_id}")
        if executor_type not in EXECUTOR_CAPABILITIES:
            raise ValueError(f"unknown executor: {executor_type}")
        self.layout_id = layout_id
        self.executor_type = executor_type
        self.obstacle = obstacle
        self.layout = LAYOUTS[layout_id]
        self.model = mujoco.MjModel.from_xml_string(self._build_xml())
        self.data = mujoco.MjData(self.model)
        self.robot_joint = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "robot_free")
        self.obstacle_geom = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "obstacle")

    def report_capabilities(self) -> list[str]:
        return sorted(EXECUTOR_CAPABILITIES[self.executor_type])

    def execute_fill_task(self) -> dict[str, Any]:
        return self.execute_steps(["move_to_counter", "pick_up_cup", "move_to_water_source", "fill_cup_at_water_source"])

    def execute_steps(self, steps: list[str]) -> dict[str, Any]:
        location = "start"
        holding_cup = False
        stage_results: list[dict[str, Any]] = []
        last_route = None
        for step in steps:
            before = {"location": location, "holding_cup": holding_cup}
            required = {
                "move_to_counter": "navigate_to_region",
                "pick_up_cup": "grasp_object",
                "move_to_water_source": "navigate_to_region",
                "fill_cup_at_water_source": "fill_container",
            }.get(step)
            if required and required not in EXECUTOR_CAPABILITIES[self.executor_type]:
                stage_results.append(self._stage(step, "capability_gap", before, before, missing_capabilities=[required]))
                return self._result("capability_gap", stage_results=stage_results, missing_capabilities=[required])
            route = None
            observations: list[dict[str, Any]] = []
            if step == "move_to_counter":
                route = self._navigate(self.layout["start"], self.layout["operation_region"])
                last_route = route
                if route.outcome == "blocked":
                    stage_results.append(self._stage(step, "fact_not_established", before, before, route=route))
                    return self._result("fact_not_established", route=route, stage_results=stage_results)
                location = "operation_region"
            elif step == "pick_up_cup":
                if location != "operation_region":
                    stage_results.append(self._stage(step, "fact_not_established", before, before, reason="executor_not_at_cup"))
                    return self._result("fact_not_established", stage_results=stage_results)
                holding_cup = True
            elif step == "move_to_water_source":
                start = self.layout["operation_region"] if location == "operation_region" else self.layout["start"]
                route = self._navigate(start, self.layout["water_source_region"])
                last_route = route
                if route.outcome == "blocked":
                    stage_results.append(self._stage(step, "fact_not_established", before, before, route=route))
                    return self._result("fact_not_established", route=route, stage_results=stage_results)
                location = "water_source_region"
            elif step == "fill_cup_at_water_source":
                if location != "water_source_region" or not holding_cup:
                    stage_results.append(self._stage(step, "fact_not_established", before, before, reason="fill_prerequisites_missing"))
                    return self._result("fact_not_established", stage_results=stage_results)
                observations = [
                    {"fact_id": "cup_contains_water", "channel_id": "physical_liquid_level", "state": "established"},
                    {"fact_id": "cup_contains_water", "channel_id": "digital_flow_integral", "state": "established"},
                ]
            after = {"location": location, "holding_cup": holding_cup}
            stage_results.append(self._stage(step, "fact_established", before, after, route=route, observations=observations))
        return self._result(
            "fact_established",
            route=last_route,
            stage_results=stage_results,
            observations=stage_results[-1].get("observations", []) if stage_results else [],
        )

    @staticmethod
    def _stage(step: str, outcome: str, before: dict[str, Any], after: dict[str, Any], **extra: Any) -> dict[str, Any]:
        route = extra.pop("route", None)
        return {
            "step": step,
            "outcome": outcome,
            "before_state": before,
            "after_state": after,
            "route_evidence": route.__dict__ if route else None,
            "observations": extra.pop("observations", []),
            **extra,
        }

    def _navigate(self, start: tuple[float, float], target: tuple[float, float]) -> RouteResult:
        direct_contact, direct_samples = self._path_contacts([start, target])
        if not direct_contact:
            return RouteResult("reached", "direct", False, direct_samples)
        if self.obstacle != "detourable":
            return RouteResult("blocked", "none", True, direct_samples)
        detour_contact, detour_samples = self._path_contacts([start, self.layout["detour_waypoint"], target])
        if detour_contact:
            return RouteResult("blocked", "none", True, direct_samples + detour_samples)
        return RouteResult("reached", "local_detour", True, direct_samples + detour_samples)

    def _path_contacts(self, points: list[tuple[float, float]]) -> tuple[bool, int]:
        checked = 0
        for start, target in zip(points, points[1:]):
            for ratio in np.linspace(0.0, 1.0, 31):
                x = start[0] + (target[0] - start[0]) * float(ratio)
                y = start[1] + (target[1] - start[1]) * float(ratio)
                address = self.model.jnt_qposadr[self.robot_joint]
                self.data.qpos[address : address + 7] = [x, y, 0.25, 1.0, 0.0, 0.0, 0.0]
                mujoco.mj_forward(self.model, self.data)
                checked += 1
                if self.obstacle_geom >= 0 and any(
                    self.obstacle_geom in (self.data.contact[index].geom1, self.data.contact[index].geom2)
                    for index in range(self.data.ncon)
                ):
                    return True, checked
        return False, checked

    def _result(self, outcome: str, **extra: Any) -> dict[str, Any]:
        route = extra.pop("route", None)
        return {
            "engine": "mujoco",
            "layout_id": self.layout_id,
            "executor_type": self.executor_type,
            "outcome": outcome,
            "missing_capabilities": extra.pop("missing_capabilities", []),
            "route_evidence": route.__dict__ if route else None,
            "observations": extra.pop("observations", []),
            "experience_writeback_policy": "topology_and_fact_outcome_only_no_absolute_pose",
            **extra,
        }

    def _build_xml(self) -> str:
        center = self.layout["obstacle_center"]
        if self.obstacle == "none":
            obstacle = ""
        else:
            half_y = 0.5 if self.obstacle == "detourable" else 4.0
            obstacle = (
                f'<geom name="obstacle" type="box" pos="{center[0]} {center[1]} 0.35" '
                f'size="0.3 {half_y} 0.35" rgba="0.8 0.2 0.2 1"/>'
            )
        return f"""
<mujoco model="rell_minimal_physics">
  <option gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="6 6 0.1"/>
    {obstacle}
    <body name="executor" pos="{self.layout['start'][0]} {self.layout['start'][1]} 0.25">
      <freejoint name="robot_free"/>
      <geom name="executor_body" type="cylinder" size="0.24 0.25" mass="20"/>
    </body>
  </worldbody>
</mujoco>
"""
