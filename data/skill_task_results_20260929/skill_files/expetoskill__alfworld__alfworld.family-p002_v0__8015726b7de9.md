1. **Locate Target Object**: Identify the specific object mentioned in the goal (e.g., alarmclock, cd, pillow). Navigate to its observed location and take it from the receptacle using `take <object> from <receptacle>`. Ensure the object is in inventory.
2. **Locate Lamp**: Identify the lamp specified in the goal (e.g., desklamp). Navigate to the receptacle containing the lamp. If the lamp is on a surface (desk, shelf, dresser), you must arrive at that specific receptacle.
3. **Verify State**: Confirm you are holding the target object and standing at the location of the lamp. The environment requires physical presence at the lamp's location to activate it.
4. **Execute Activation**: Use the command `use <lamp>` while holding the target object. Do not place the object down before this step. The action must be performed at the lamp's location.
5. **Handle Constraints**: 
   - If the lamp is closed, open it first (`open <lamp_receptacle>` if applicable, though desklamps are typically always accessible once located).
   - If the target object is not found in initial observations, systematically check other receptacles (drawers, beds, shelves) until found.
   - Do not assume the lamp is at the same location as the object; they are often in different rooms or on different furniture.
   - Verify success only via the environment feedback ('Task is SOLVED'), not by thought or placement alone.