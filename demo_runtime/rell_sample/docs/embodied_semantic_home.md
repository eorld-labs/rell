# Embodied semantic home benchmark

This benchmark grounds the existing P010 semantic topology and P008 body portrait in a visible 3D household instance. It does not replace either layer or claim a new numbered technical-scheme identifier.

## Contract

- Semantic regions bind to scene volumes and affordances.
- Objects bind stable semantic ids to current scene instances.
- The executor body portrait supplies collision radius, height, turning radius, arm reach, gripper span, and supported actions.
- Relative language such as `往前走一点` is resolved in the executor heading frame, not as an absolute world coordinate.
- Front, back, left, and right are body-frame concepts. The current differential-drive portrait realizes a side target by turning then driving and realizes backward motion by reversing; it never claims lateral translation.
- Animation frames are transient execution feedback. They are never admitted into a reusable experience.
- A detour is accepted only when the body envelope has clearance. Otherwise the executor explains the blocker and asks whether the movable obstacle may be removed.
- A local detour must pass the obstacle's full combined envelope before returning to the original travel axis. Every segment and the terminal pose are collision-checked; a short language distance may be extended only to satisfy this safety boundary, with the extension recorded as route evidence.
- Fixed furniture and room boundaries participate in swept body-envelope collision checks. Continuous movement terminates at the last safe pose before contact and repeated commands cannot penetrate the collider.

## Current benchmark

The first home contains connected living-room, corridor, and kitchen regions plus an operation counter, water dispenser, cup, apple, and dynamic stool. The browser scene is available at `/embodied`.

The first command benchmark covers direct relative movement, a detourable stool, and a stool in a narrow transition. The next expansion should connect teaching confirmation to a learned relative-motion concept and add a second home layout for zero-trajectory migration.
