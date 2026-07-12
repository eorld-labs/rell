from __future__ import annotations

import json
import sys

from physics_mujoco_adapter import MujocoEmbodiedAdapter


def main() -> None:
    request = json.loads(sys.stdin.read())
    adapter = MujocoEmbodiedAdapter(
        request.get("layout_id", "kitchen_a"),
        request.get("executor_type", "mobile_manipulator"),
        request.get("obstacle", "none"),
    )
    steps = request.get("steps")
    result = adapter.execute_steps(steps, request.get("initial_state")) if steps else adapter.execute_fill_task()
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
