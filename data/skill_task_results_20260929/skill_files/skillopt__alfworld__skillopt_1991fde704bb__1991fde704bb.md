# ALFWorld Embodied Agent Skill

## Overview
This skill guides agents operating in the ALFWorld text-based embodied environment.
The agent must complete household tasks by navigating rooms, interacting with objects,
and using appliances. Actions must be chosen from the admissible action list provided
at each step.

**Output format**: Always output `<think>...</think>` for reasoning, then `<action>...</action>` for the chosen action.

---

## Task Types

| Type | Goal | Key Steps |
|------|------|-----------|
| Pick & Place | Put object X in/on receptacle Y | Find X -> take X -> go to Y -> put X in/on Y |
| Pick Two & Place | Put two instances of X in/on Y | Find X1 -> take -> place -> find X2 -> take -> place |
| Examine in Light | Examine object X under desklamp | Find X -> take X -> find desklamp -> use desklamp |
| Clean & Place | Clean object X and put in/on Y | Find X -> take X -> go to sink -> clean X -> go to Y -> put X |
| Heat & Place | Heat object X and put in/on Y | Find X -> take X -> go to microwave -> (open/put/close if needed) -> heat X (may require taking out and using 'heat X with microwave') -> go to Y -> put X |
| Cool & Place | Cool object X and put in/on Y | Find X -> take X -> go to fridge -> cool X -> go to Y -> put X |

---

## General Principles

1. **Decompose the task**: Parse the goal into ordered sub-goals (locate, acquire, transform, deliver). Complete each before moving to the next.
2. **Semantic prioritization**: When searching for an object, first check locations where that object type is commonly stored (e.g., fridge/countertops for food, cabinets/drawers for dishes/cutlery, desks/shelves for electronics/books) before checking less likely areas.
3. **Search order efficiency**: Prioritize checking open surfaces (countertops, tables, shelves) before opening closed containers. However, when you do approach a closed container (cabinet, drawer, fridge), always open it to check inside before judging it empty or moving on.
4. **Leverage Direct Admissible Actions**: Always scan the admissible action list for direct interaction commands like `take <object> from <location>`, `heat/cool <object> with <appliance>`, or `put <object> to <receptacle>`. If these specific actions are available, execute them immediately. You often do not need to navigate to the source location or manually open/close appliances if the direct interaction command is provided.
5. **Verify object identity**: Ensure the object name in the `take` action exactly matches the task goal (e.g., do not take a 'pan' if the goal is 'pot'). If you accidentally pick up the wrong item, put it back immediately to free your hands.
6. **Grab immediately**: When a required object is visible in the current observation, `take` it immediately. Do not navigate away or search other locations while the target object is in view.
7. **Transform before placing & Explicit Commands**: 
   - **Priority on Direct Actions**: ALWAYS scan for and prioritize explicit single-step commands like `heat <object> with <appliance>`, `clean <object> with <sink>`, or `cool <object> with <fridge>`. These commands handle both the state change and often the interaction logic, bypassing the need to manually open, place, close, and toggle appliances. Only use manual multi-step sequences if the explicit command is missing from the admissible list.
   - **Sequence**: Perform the state change at the appliance *before* navigating to the final destination.
   - **Examine in Light Exception**: For 'Examine in Light' tasks, do NOT transform the object. Instead, find the object, take it, find the desklamp, and execute `use <desklamp>` while holding the object.
8. **Direct delivery**: Once holding the transformed (or untransformed) goal object, navigate straight to the target receptacle and place it.
9. **Place-first strategy for multiple items**: When tasked with moving multiple items (e.g., 'pick two'), place the first acquired item at the destination immediately, then return to search for the remaining items. Do not attempt to hold multiple items simultaneously. This prevents inventory errors and simplifies state tracking.
   - **Strict Loop**: Find Item 1 -> Take Item 1 -> Go to Destination -> Place Item 1 -> Find Item 2 -> Take Item 2 -> Go to Destination -> Place Item 2. Never search for Item 2 while holding Item 1.
10. **Track progress**: Maintain an internal count of how many objects still need to be found and placed. Only stop searching when the count reaches zero.
11. **Avoid loops**: Never repeat the same action more than twice in a row. If stuck, move to a different unexplored location. **Crucially**, if you are holding the goal object and at the target receptacle, do not loop on `look` or `inventory`; execute the placement action immediately.
12. **Only choose admissible actions**: Always pick an action from the admissible action list. Do not invent actions.
13. **Track visited locations**: Maintain a mental list of locations you have already searched. If you find yourself returning to a previously visited location without having found the target object, you MUST navigate to a new, unvisited location from the admissible actions. Do not revisit the same location more than once unless retrieving an object placed there.
14. **Break navigation loops**: If you perform the same `go to` action twice or return to a location you just left, you are in a loop. Immediately choose a different, unvisited location from the admissible actions to break the cycle.

14b. **Track Visited Locations**: Maintain an internal list of locations you have explicitly searched (checked contents). Do not revisit a location unless retrieving an item placed there. If you find yourself returning to a previously searched location, you MUST choose a new, unvisited location.
14c. **Strict Search Strategy Switch**: If you have checked **3** locations of the same type (e.g., 3 empty drawers, 3 empty shelves, or 3 cabinets with wrong items) without finding the target, you **MUST** immediately switch to a different category of location (e.g., from drawers to countertops, or from shelves to cabinets). 
   - **Crucial**: Do NOT return to a previously checked location of the *same* type if you have already failed there. 
   - **Loop Prevention**: If you find yourself navigating between the same 2-3 locations for more than 3 steps, you are in a loop. Immediately force a switch to a completely unvisited location type (e.g., if stuck on cabinets, go to a countertop or drawer you haven't touched yet).
15. **Verify Placement Actions**: When holding the goal object and standing at the target receptacle, check the admissible action list for `put <object> in/on <receptacle>`. 
   - **If available**: Execute it immediately.
   - **If MISSING**: Do NOT loop on `look` or `inventory`. The absence of the action usually indicates one of three issues: (1) You are holding the wrong object type (e.g., holding a 'cup' when the task requires a 'mug'); (2) The receptacle needs a specific interaction (like `open` or `examine`) before placing; or (3) The object name in your inventory does not match the expected syntax. 
   - **Action**: If `put` is missing, first `examine` the held object to verify its type. If it doesn't match the goal (e.g., Cup vs Mug), put it back and search for the correct object. If it matches, try `examine`ing the receptacle to reveal hidden placement options.
16. **Explicit Appliance Usage & Receptacle Interaction**: 
   - **Heating/Cooling**: Always look for explicit `heat <object> with <appliance>` or `cool <object> with <appliance>` actions. If unavailable, try `use` or `toggle`.
   - **Open Before Placing**: When placing an object into a closed container (fridge, drawer, cabinet), you MUST `open` it first. Do not attempt to `move` or `put` an object into a closed receptacle; the action will likely fail or be unavailable until the container is open.

---

## Common Mistakes to Avoid

- **Revisiting searched locations**: Keep track of which surfaces/containers have been checked; do not re-examine them.
- **Ignoring visible objects**: If the target object appears in the observation, pick it up immediately.
- **Skipping state changes**: Do not place an object at the destination without first cleaning/heating/cooling it when required.
- **Premature termination**: Do not stop the episode until all goal conditions are verified as met.
- **Action loops**: Repeatedly toggling or examining the same object wastes steps. Move on to new locations instead.

## Emergency Loop Breaking
If you find yourself navigating between the same 2-3 locations for more than 5 steps without progress:
1. **Stop** moving between these locations.
2. **List** all unvisited locations of a *different* type than the ones you are stuck on.
3. **Move** to the most semantically relevant unvisited location from that new list.
4. If no unvisited locations remain, re-examine the contents of previously visited locations using `examine` or `look` actions, as objects may have been missed.

## Emergency Search Reset
If you have taken more than 20 steps and have not yet found the goal object:
1. **Stop** your current search pattern.
2. **List** all location types you have NOT yet visited (e.g., if you've only checked cabinets, list drawers, shelves, countertops, tables).
3. **Move** to the most semantically relevant UNVISITED location type.
4. Do not revisit any location you have already fully searched (opened/examined) unless you are retrieving an item you placed there.
