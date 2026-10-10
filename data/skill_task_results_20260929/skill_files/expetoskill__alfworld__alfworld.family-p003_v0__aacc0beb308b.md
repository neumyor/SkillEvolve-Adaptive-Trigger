1. Identify the target object specified in the goal (e.g., alarmclock, cd, pillow) and the required light source (e.g., desklamp).
2. Locate the target object by navigating to its known receptacle or searching unvisited locations if necessary.
3. Take the target object from its current receptacle using the command: `take <object_id> from <receptacle_id>`.
4. Navigate to the location of the lamp using: `go to <lamp_receptacle_id>`.
5. Verify you are holding the target object by checking inventory if uncertain, though the system state usually implies possession after a successful take.
6. Execute the illumination action using: `use <lamp_id>`.
7. Confirm task completion via environment feedback (e.g., 'Task is SOLVED').
8. If the initial attempt fails due to syntax or prerequisites, re-verify the exact IDs of the object and lamp from observations before retrying.
9. Do not place the object in any receptacle after using the lamp unless explicitly required by a different task type.
10. Reserve steps for navigation and retrieval; avoid redundant examinations of empty containers.