## Contextual abstract
This skill guides an agent in solving multi-step embodied household tasks by translating natural language goals into formal Planning Domain Definition Language (PDDL) plans. The agent must navigate simulated environments, manipulate objects, and track state changes across sequential steps. Success requires strict subgoal sequencing, intermediate state verification, and persistent execution until the final goal condition is fully satisfied without premature termination.

## Successful experiences
1. **Parse PDDL specifications:** Extract the initial state, goal conditions, and action schemas with their preconditions and effects from the provided domain and problem files.
2. **Decompose into linear subgoals:** Break the high-level instruction into an ordered chain of atomic subgoals. For example, translate "clean and place the mug" into: navigate to mug → pick up mug → navigate to sink → clean mug → navigate to cabinet → place mug.
3. **Verify intermediate preconditions:** Before executing any action, explicitly check that its preconditions are met in the current state. Confirm the object is clean before navigating to the target receptacle, or confirm it is cooled before placing it in the coffee machine.
4. **Execute sequentially and persistently:** Generate and execute the action sequence step-by-step. Maintain the active plan in memory and only terminate when the final goal condition is demonstrably achieved in the environment state.

## Failure lessons
* **Partial-completion trap:**
  *Signal:* The episode terminates with the task objective unfulfilled because the agent stopped after handling just one component (e.g., picking up an object but failing to place it, or cleaning it but leaving it on the counter).
  *Counter-action:* Treat intermediate milestones as incomplete. Force the planner to append all remaining dependency steps to the action queue before outputting the final termination command.
* **Initialization freezing:**
  *Signal:* Zero or no meaningful reasoning tokens and action outputs are generated, causing immediate environment termination without attempting any interaction or exploration.
  *Counter-action:* Mandate a fallback initialization routine. If the primary parsing step stalls, immediately output a minimal valid plan structure (e.g., `[navigate, pick, modify, place]`) to ensure the environment always receives at least one executable action.