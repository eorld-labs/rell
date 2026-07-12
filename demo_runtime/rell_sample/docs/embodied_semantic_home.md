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

A confirmation never disables the protection overlay. It creates a one-use authorization bound to the exact command hash, current world revision, declaration identity/version, and policy revision. Starting that execution consumes the authorization; command changes, world changes, policy replacement, policy removal, denial, or prior consumption make it unusable. The policy runtime separately records its application revision and active/revoked state. An active motion job is bound to both world and policy revisions, so a mid-motion policy change invalidates the old job and forces a fresh decision from the last verified pose.

## Task-conditioned concept perception

The first perception slice handles `去桌子上拿杯子` without allowing the concept grounder to read scene truth. Object concepts activate a target container, support surface, pickup action, and required `target_on_top_of_support` relation. A simulated RGB-D adapter reads the scene and emits a restricted observation DTO containing category candidates, estimated geometry, and relation candidates. The grounder receives only that DTO and the activated concept contract.

The cup/support binding reaches `spatially_grounded`, not `runtime_verified`. It remains `candidate_only=true`, commits no runtime fact, and produces only a causal preview for navigation, alignment, grasping, and post-grasp verification. Removing support-relation evidence forces the result back to active observation instead of allowing the grounder to reconstruct the answer from scene configuration. Irrelevant object semantics are suppressed, while active obstacles and other safety channels remain always on.

The runtime scene can now switch among a single clear cup, two compatible cups, front-view occlusion, and a relocated cup. Two cups produce `perception_disambiguation_required` with both candidates preserved and no selected binding. `拿白色杯子` or `拿浅蓝色杯子` starts a new observation interpretation, filters by an observed attribute, preserves the rejected alternative and its reason, and stales the preceding ambiguous result. It does not use screen-left or screen-right as an implicit spatial reference.

Front-view occlusion produces explicit occlusion evidence. When the executor portrait exposes a panning head RGB-D frame, the perception loop selects an allowed alternate viewpoint and retries without moving the chassis. A successful second observation still yields only a candidate. Relocation increments the world revision, stales the old observation, moves the rendered instance, and requires a new observation id and position binding.

## Current benchmark

The first home contains connected living-room, corridor, and kitchen regions plus an operation counter, water dispenser, cup, apple, and dynamic stool. The browser scene is available at `/embodied`.

The command benchmark covers task-conditioned cup/support perception, multi-instance disambiguation, active observation under occlusion, relocation and rebinding, direct relative movement, a detourable stool, and a stool in a narrow transition. The next boundary is to submit a uniquely grounded target and its causal preview back through orchestration into actual navigation and grasp execution, while retaining per-step world-revision and P016 fact-verification gates.
