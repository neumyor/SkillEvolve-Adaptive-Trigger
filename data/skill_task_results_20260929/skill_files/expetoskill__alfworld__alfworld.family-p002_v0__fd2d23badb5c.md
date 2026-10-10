1. Identify the target object and its required final state (clean, cool, or heat) from the task description.
2. Locate the target object in the environment. Navigate to its current receptacle or surface. Check closed containers (cabinets, drawers, fridge) if not immediately visible on open surfaces.
3. Retrieve the object using `take <object> from <receptacle>`. Verify possession via `inventory` if needed.
4. Navigate to the appropriate processing station:
   - For 'clean': go to a sinkbasin.
   - For 'cool': go to a fridge.
   - For 'heat': go to a microwave.
5. Apply the state modification:
   - Use `clean <held object> with <sinkbasin>`.
   - Use `cool <held object> with <fridge>`. Note: The fridge does not strictly need to be opened before cooling, but opening it may be necessary if the agent needs to verify contents or if specific environmental constraints require it.
   - Use `heat <held object> with <microwave>`. Note: The microwave usually needs to be opened before heating.
6. Navigate to the final destination receptacle specified in the goal.
7. If the destination is a closed container (cabinet, drawer, fridge, microwave), open it first using `open <receptacle>`.
8. Place the processed object using `move <held object> to <receptacle>`.
9. Confirm task completion only upon receiving explicit success feedback from the environment.