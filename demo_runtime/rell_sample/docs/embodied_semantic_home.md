# Embodied semantic home benchmark

This benchmark grounds the existing P010 semantic topology and P008 body portrait in a visible 3D household instance. It does not replace either layer or claim a new numbered technical-scheme identifier.

## Contract

- Semantic regions bind to scene volumes and affordances.
- Objects bind stable semantic ids to current scene instances.
- The executor body portrait supplies collision radius, height, turning radius, arm reach, gripper span, and supported actions.
- Relative language such as `往前走一点` is resolved in the executor heading frame, not as an absolute world coordinate.
- Front, back, left, and right are body-frame concepts. The current differential-drive portrait realizes a side target by turning then driving and realizes backward motion by reversing; it never claims lateral translation.
- Body directions are invariant under camera movement. The semantic ground frame uses `+x=forward`, `+y=left`, and counterclockwise positive yaw; the Three.js adapter maps semantic `+y` to negative render `z` to preserve handedness. Screen-left and screen-right never define body-left and body-right.
- Animation frames are transient execution feedback. They are never admitted into a reusable experience.
- A detour is accepted only when the body envelope has clearance. Otherwise the executor explains the blocker and asks whether the movable obstacle may be removed.
- A local detour must pass the obstacle's full combined envelope before returning to the original travel axis. Every segment and the terminal pose are collision-checked; a short language distance may be extended only to satisfy this safety boundary, with the extension recorded as route evidence.
- Fixed furniture and room boundaries participate in swept body-envelope collision checks. Continuous movement terminates at the last safe pose before contact and repeated commands cannot penetrate the collider.
- Browser motion is a server-verified frame job, not a precomputed animation. Every frame is committed against the latest world revision; a new obstacle invalidates the old job and replans from the last verified pose.

## Body truth, P6 policy, and P2 control boundary

The intrinsic executor profile remains stable body truth. An optional P6 protection declaration is stored as a revocable overlay and can only narrow speed, contact force, avoidance distance, confirmation, or stop boundaries. The derived effective execution envelope records both sources and never writes policy values back into the body profile.

Continuous or otherwise high-risk physical controls enter a P2-style causal control decision. A policy-required confirmation blocks execution before frames are generated. When a safety stop is issued, actual stopped/non-penetrating state is compared with the expected safe state; failure would require upgraded protection. P6 execution receipts and P2 safety self-proof records are distinct outputs.

## Current benchmark

The first home contains connected living-room, corridor, and kitchen regions plus an operation counter, water dispenser, cup, apple, and dynamic stool. The browser scene is available at `/embodied`.

The first command benchmark covers direct relative movement, a detourable stool, and a stool in a narrow transition. The next expansion should connect teaching confirmation to a learned relative-motion concept and add a second home layout for zero-trajectory migration.
