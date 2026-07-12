# P020 minimal physics loop

This phase replaces logical obstacle assertions with headless MuJoCo contact evidence while preserving the P016/P017/P019 boundaries.

## Boundary

- MuJoCo poses, geometry dimensions, and route samples remain private to `MujocoEmbodiedAdapter`.
- Experience writeback contains topology, required capabilities, route outcome, and terminal facts only.
- A successful fill task requires both `physical_liquid_level` and `digital_flow_integral` to establish `cup_contains_water`.
- Contact with the floor is support state, not obstacle evidence. Only contact with the named obstacle geometry can block or detour navigation.
- Capability admission happens before physics execution. A mobile base cannot grasp or fill; a fixed arm cannot navigate.

## Current pressure matrix

| Dimension | Cases |
| --- | --- |
| Layout | `kitchen_a`, `corridor_b` |
| Executor | mobile manipulator, mobile base, fixed arm |
| Obstacle | none, detourable local obstacle, non-detourable wall |
| Fact result | established through two channels, not established, capability gap |

The liquid event is deliberately low-dimensional. This phase validates causal termination and observation routing, not computational fluid dynamics.

## Run

```powershell
$env:RELL_PHYSICS_PYTHON = "C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"
python .\demo_runtime\rell_sample\run_all_checks.py
```

Install the isolated physics dependencies with `requirements-physics.txt`. The Web runtime remains on the default Python interpreter and does not import MuJoCo.
