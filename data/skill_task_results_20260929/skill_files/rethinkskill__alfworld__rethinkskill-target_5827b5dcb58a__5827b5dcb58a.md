---
name: "rethinkskill-target"
description: "Dynamic skill for native ALFWorld interaction."
---

# ALFWorld Embodied Agent Skill

## Overview
This skill guides agents operating in the ALFWorld text-based embodied environment.
The agent must complete household tasks by navigating rooms, interacting with objects,
and using appliances. Actions must be chosen from the admissible action list provided
at each step.

**Output format**: Always output `<think>...<\/think>` for reasoning, then `<action>...<\/action>` for the chosen action.

---

## Task Types & Command Templates

| Type | Goal | Key Steps & Command Pattern |
|------|------|-----------------------------|
| Pick & Place | Put object X in/on receptacle Y | Find X -> take X from loc -> go to Y -> put X in/on Y |
| Pick Two & Place | Put two instances of X in/on Y | Find X1 -> take -> place -> find X2 -> take -> place |
| Examine in Light | Examine object X under desklamp | Find X -> take X -> find desklamp -> use desklamp on X |
| Clean & Place | Clean object X and put in/on Y | Find X -> take X -> go to sink -> clean X with sink -> go to Y -> put X |
| Heat & Place | Heat object X and put in/on Y | Find X -> take X -> go to microwave -> open microwave -> put X in microwave -> close microwave -> wait/heat -> open microwave -> take X -> go to Y -> put X on/in Y |
| Cool & Place | Cool object X and put in/on Y | Find X -> take X -> go to fridge -> open fridge -> put X in fridge -> close fridge -> wait/cool -> open fridge -> take X -> go to Y -> put X on/in Y |

---

## General Principles

1. **Parse goal precisely**: Extract the exact target object, destination receptacle, and required state transformation from the instruction. Match it to the appropriate task template.
2. **Structured State Declaration**: Begin every `<think>` block with a machine-readable state snapshot: `[LOC: x] [HOLDING: y|null] [FREE: bool]`. This prevents state drift and grounds all subsequent reasoning.
3. **Strict Inventory Discipline**: You cannot `take` unless `FREE=true`. You cannot `put` unless holding an item. If switching targets, you MUST `put` the current item down before executing the next `take`. Update mental tracking immediately after every swap.
4. **World State Memory**: Continuously maintain a mental map of explored locations, container statuses (closed/open/empty), and item positions. Do not rely solely on the immediate observation; recall previously gathered context to avoid redundant searches.
5. **Systematic Exploration**: Execute breadth-first or depth-first search within the current room. Open every container and inspect surfaces. Upon opening, verify contents. If the target is absent, mark the container as `checked` and proceed. Once exhausted, move to connected rooms. Never jump randomly; prioritize logically adjacent rooms based on known layouts.
6. **Immediate Acquisition**: When a required object is visible and reachable, `take` it immediately before navigating elsewhere.
7. **Appliance Interaction Cycle**: For cleaning/heating/cooling, strictly follow the full sequence: locate appliance -> `open` -> `place` item -> `close` -> `wait` -> **verify transformation via observation** -> `open` -> retrieve -> proceed. Never skip intermediate steps or assume transformation succeeded without checking.
8. **Transformation Before Delivery**: If the task requires cleaning, heating, or cooling, perform the state change at the correct appliance BEFORE heading to the final destination. Placing an untransformed object fails the goal.
9. **Direct Delivery & Preposition Strictness**: Once holding the transformed (or untransformed) goal object, navigate straight to the target receptacle and place it. Respect `in` vs `on` prepositions exactly as specified in the goal. Mismatched prepositions silently fail the verifier.
10. **Step Budget Awareness**: Episodes are step-limited. Minimize backtracking. If an intended action is not in the admissible list, diagnose why (wrong location, closed container, hands full, distance mismatch) and execute the first valid corrective action. Do not retry blocked commands.
11. **Admissible List Supremacy & Blocking Resolution**: BEFORE emitting `<action>`, cross-reference your plan against the provided `admissible_action_list`. If the desired action is missing, immediately pivot to a valid workaround from the list. Blindly proposing unavailable actions wastes turns and triggers verification failures.
12. **Continuous Goal Verification**: Treat the task as incomplete until **external observations confirm** all goal conditions. Re-check the environment state after every major step. If observations contradict your expectation, adjust immediately. Never halt action generation or assume success based on internal confidence alone; extend the plan until verified.
13. **Post-Action State Sync**: After every successful action, instantly update your mental model. Remove items from sources, add them to destinations, and update container contents to prevent phantom searches and state corruption.
14. **Location Awareness**: Track your current room explicitly. Use `go_to <room_name>` to transition between rooms. Only search a room if you have a hypothesis or logical reason; otherwise, explore sequentially.
15. **Observation Grounding & Conflict Resolution**: If observation text contradicts your mental state (e.g., forgotten holding status, changed container state), **prioritize the observation text**. Update your mental map instantly to reflect ground truth.
16. **Pre-Action Container Verification**: Never `take` from or `put` into a container without confirming it is `open`. If closed, prioritize `open <container>`. If the container isn't visible, `look_around` or navigate to it. Blind attempts break interaction pipelines.
17. **Canonical Object Names**: Use the exact object identifiers reported by the environment. Avoid inferred modifiers, synonyms, or pronouns unless explicitly confirmed. Mismatched names cause silent action failures.
18. **Stuck Detection and Action Diversification**: If identical observations or rejected actions repeat for 3+ turns, you are likely stuck. Immediately diversify: toggle a nearby item's state, move to a different surface, or navigate to an unvisited adjacent room. Exhaust `look_around` only once per stationary phase.
19. **Mandatory Pre-Action Validation Checklist**: Inside `<think>`, explicitly run this check before outputting `<action>`:
    a) Is the action present in the `admissible_action_list`?
    b) Does my declared state support it (e.g., free hands for take, holding for put, correct room)?
    c) Are all physical preconditions met (object visible/reachable, container open)?
    d) **Is the action necessary given current observations?** Avoid redundant moves.
    e) Will this action advance the goal or fix a blocker?
If any check fails, abort and execute the necessary prerequisite step instead.

---

## Common Mistakes to Avoid

- **Revisiting searched locations**: Keep track of checked surfaces/containers; do not re-examine them.
- **Ignoring visible objects**: If the target object appears in the observation, pick it up immediately.
- **Skipping state changes**: Do not place an object at the destination without first cleaning/heating/cooling it when required.
- **Premature termination**: Do not stop the episode until all goal conditions are verified as met.
- **Action loops & Stagnation**: Repeatedly toggling or examining the same object wastes steps. Diversify interactions or relocate instead.
- **Inventory mismanagement**: Forgetting you are already holding an object leads to invalid `take` or `put` attempts. Confirm hands-free before picking up new items, and always clear inventory when needing to switch targets.
- **Container assumptions**: Never assume a container holds a specific item without opening and observing. Conversely, do not abandon a search prematurely if an item is not immediately visible upon opening.
- **Preposition errors**: Placing an item `in` when the goal says `on`, or vice versa, breaks the success condition. Follow the goal's preposition exactly.
- **Blocking constraint violation**: Attempting an action not present in the admissible list is invalid. Always filter candidates through the provided list and fix preconditions if the action is unavailable.
- **Aimless navigation**: Moving between rooms without a plan wastes steps. Verify the current room's exhaustiveness before leaving.
- **Incomplete appliance cycles**: Skipping open/close/wait/retrieve steps during heat/cool/clean operations causes state mismatches and verifier failures. Always complete the full interaction sequence.
- **Name/Hallucination Errors**: Inventing object descriptions or using aliases instead of canonical IDs leads to unrecognized interactions. Trust the environment's exact labels.
- **State Drift**: Failing to update your mental map after taking/placing leads to searching for items you've already handled. Sync immediately after every interaction.
