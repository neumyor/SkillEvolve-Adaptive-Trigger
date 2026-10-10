import json, glob, sys
from collections import defaultdict

root = sys.argv[1]
trials = defaultdict(list)
fails = defaultdict(int)
for f in sorted(glob.glob(root + "/*__*/result.json")):
    name = f.split("/")[-2].rsplit("__", 1)[0]
    data = json.load(open(f))
    reward = (data.get("verifier_result") or {}).get("rewards", {}).get("reward")
    exc = data.get("exception_info") or {}
    trials[name].append((reward, exc.get("exception_type") if exc else None))

valid = {n: [r for r, _ in rs if r is not None] for n, rs in trials.items()}
n_tasks = len(trials)
full = sum(1 for n in trials if len(trials[n]) == len(trials[n]) and None not in [r for r, _ in trials[n]])
per_task_ok = {n: len(trials[n]) for n in trials if len(trials[n]) < len(trials[n])}
scored = {n: sum(v) / len(v) for n, v in valid.items() if v}
avg = sum(scored.values()) / n_tasks if n_tasks else 0
# pass@N: at least one success among the trials the task actually ran
pass_at = sum(1 for v in valid.values() if any(v)) / n_tasks if n_tasks else 0
incomplete = {n: len(rs) for n, rs in trials.items()
              if len(rs) < max(len(t) for t in trials.values())
              or any(r is None for r, _ in rs)}
exc_types = defaultdict(int)
for n, rs in trials.items():
    for r, e in rs:
        if r is None and e:
            exc_types[e] += 1
        elif r is None:
            exc_types["unknown/none"] += 1

total = sum(len(rs) for rs in trials.values())
print(f"任务数: {n_tasks}, trial总数: {total}")
print(f"avg@N(每任务先平均再对任务平均): {avg:.4f}")
print(f"pass@N(至少一次成功): {pass_at:.4f}  ({sum(1 for v in valid.values() if any(v))}/{n_tasks})")
print(f"带异常的任务数: {len(incomplete)}")
print("异常类型分布:", dict(exc_types))
for n in sorted(incomplete):
    rs = trials[n]
    print(f"  {n}: {len(rs)}个trial, rewards={[r for r, _ in rs]}")
