# P021 embodied semantic home benchmark

P021 grounds the existing P010 semantic topology and P008 body portrait in a visible 3D household instance. It does not replace either layer.

## Contract

- Semantic regions bind to scene volumes and affordances.
- Objects bind stable semantic ids to current scene instances.
- The executor body portrait supplies collision radius, height, turning radius, arm reach, gripper span, and supported actions.
- Relative language such as `往前走一点` is resolved in the executor heading frame, not as an absolute world coordinate.
- Animation frames are transient execution feedback. They are never admitted into a reusable experience.
- A detour is accepted only when the body envelope has clearance. Otherwise the executor explains the blocker and asks whether the movable obstacle may be removed.

## Current benchmark

The first home contains connected living-room, corridor, and kitchen regions plus an operation counter, water dispenser, cup, apple, and dynamic stool. The browser scene is available at `/embodied`.

The first command benchmark covers direct relative movement, a detourable stool, and a stool in a narrow transition. The next expansion should connect teaching confirmation to a learned relative-motion concept and add a second home layout for zero-trajectory migration.
