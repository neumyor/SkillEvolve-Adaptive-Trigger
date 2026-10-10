import json, glob
from collections import defaultdict

for label, root, target in (
        ("qwen", "/data2/niuyiming/e1_full_q36flash_2att/jobs/e1_full_q36flash_2att", 2),
        ("dpsk", "/data2/niuyiming/e1_full_dsv4max_5att/jobs/e1_full_dsv4max_5att", 5)):
    seen, valid = set(), defaultdict(int)
    for f in glob.glob(root + "/*__*/result.json"):
        name = f.split("/")[-2].rsplit("__", 1)[0]
        seen.add(name)
        reward = (json.load(open(f)).get("verifier_result") or {}).get("rewards", {}).get("reward")
        if reward is not None:
            valid[name] += 1
    need = defaultdict(list)
    for name in sorted(seen):
        missing = target - valid[name]
        if missing > 0:
            need[missing].append(name)
    print(f"===== {label} (目标每任务 {target} 条有效轨迹) =====")
    total = 0
    for missing in sorted(need):
        tasks = need[missing]
        total += missing * len(tasks)
        print(f"缺 {missing} 条的 {len(tasks)} 个任务: {' '.join(tasks)}")
    print(f"合计需补 {total} 个 trial\n")
