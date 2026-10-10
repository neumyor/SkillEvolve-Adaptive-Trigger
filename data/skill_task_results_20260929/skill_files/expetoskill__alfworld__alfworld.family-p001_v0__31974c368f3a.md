1. Identify the target object and its required final location from the task description.
2. Locate the target object by navigating to likely sources (countertops, tables, shelves, drawers, stoveburners, fridges) and checking observations for the specific object ID.
3. If the object is inside a closed container (drawer, cabinet, fridge), open it first before attempting to take the object.
4. Take the target object from its current location using 'take <object> from <receptacle>'.
5. Check if the task requires a state transformation (e.g., 'clean', 'heat', 'cool').
6. If cleaning is required: navigate to the sinkbasin and execute 'clean <object> with <sinkbasin>'.
7. If heating is required: navigate to the microwave. Note that some instances require opening the microwave ('open microwave') before heating, while others allow implicit interaction. Attempt to heat; if rejected, check if opening is needed. Execute 'heat <object> with <microwave>'.
8. If cooling is required: navigate to the fridge. The fridge does not need to be opened for the 'cool' action on a held object. Execute 'cool <object> with <fridge>'.
9. Navigate to the target destination receptacle specified in the goal.
10. Place the object using 'move <object> to <receptacle>'.
11. If the destination is a closed container (drawer, cabinet), open it before moving the object inside.
12. Verify success via environment feedback; do not assume completion based on observation alone.