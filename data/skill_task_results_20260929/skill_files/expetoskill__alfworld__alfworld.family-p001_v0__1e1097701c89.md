1. Identify the target object and its required destination receptacle from the task description.
2. Navigate to potential source locations to locate the specific object instance. Use 'go to <receptacle>' to arrive at a location.
3. If the source is a closed container (e.g., drawer, cabinet), use 'open <receptacle>' before attempting to take the object.
4. Verify the object is present in the current observation. Use exact IDs observed (e.g., 'object_1').
5. Retrieve the object using 'take <object> from <receptacle>'. This places the item in inventory.
6. Navigate to the destination receptacle using 'go to <destination_receptacle>'.
7. If the destination is a closed container, ensure it is open ('open <destination_receptacle>') if necessary for placement, though some surfaces accept items directly.
8. Place the object using 'move <held_object> to <destination_receptacle>'.
9. Confirm success via environment feedback ('Task is SOLVED'). Do not assume success based on action execution alone.
10. If the object is not found in the first visited location, return to step 2 and check other unvisited receptacles. Avoid consecutive identical actions.