import json, glob
from collections import defaultdict

TARGETS = {"q": 2, "d": 5}
MAIN = {"q": "/data2/niuyiming/e1_full_q36flash_2att/jobs/e1_full_q36flash_2att",
        "d": "/data2/niuyiming/e1_full_dsv4max_5att/jobs/e1_full_dsv4max_5att"}
REC = {"q": sorted(glob.glob("/data2/niuyiming/e1_recover/jobs/e1rec_q_*")),
       "d": sorted(glob.glob("/data2/niuyiming/e1_recover/jobs/e1rec_d_*"))}

for tag, label in (("q", "qwen(目标2臂)"), ("d", "dpsk(目标5臂)")):
    target = TARGETS[tag]
    stats = defaultdict(lambda: {"valid": 0, "succ": 0, "verto": 0, "other_exc": 0, "running": 0})
    files = glob.glob(MAIN[tag] + "/*__*/result.json")
    for rid_dir in REC[tag]:
        files += glob.glob(rid_dir + "/*__*/result.json")
        if not glob.glob(rid_dir + "/*__*/result.json"):
            task = rid_dir.split("/")[-1].split("_", 2)[2].rsplit("_", 1)[0]
            stats[task]["running"] += 1
    for f in files:
        name = f.split("/")[-2].rsplit("__", 1)[0]
        data = json.load(open(f))
        reward = (data.get("verifier_result") or {}).get("rewards", {}).get("reward")
        etype = (data.get("exception_info") or {}).get("exception_type") or ""
        if reward is not None:
            stats[name]["valid"] += 1
            stats[name]["succ"] += int(reward in (1, 1.0, True))
        elif etype == "VerifierTimeoutError":
            stats[name]["verto"] += 1
        else:
            stats[name]["other_exc"] += 1
    tasks = stats
    n = len(tasks)
    any_succ = sum(1 for s in tasks.values() if s["succ"])
    full = sum(1 for s in tasks.values() if s["valid"] >= target)
    verto_trials = sum(s["verto"] for s in tasks.values())
    verto_tasks = sum(1 for s in tasks.values() if s["verto"])
    other = sum(s["other_exc"] for s in tasks.values())
    running = sum(s["running"] for s in tasks.values())
    print(f"===== {label}: 共 {n} 个任务 =====")
    print(f"至少一次成功: {any_succ}")
    print(f"有效臂已补齐(>={target}): {full}")
    print(f"verifier超时: {verto_trials} trial / {verto_tasks} 任务")
    print(f"其他异常臂: {other}; 正在跑: {running}")
    for name in sorted(tasks):
        s = tasks[name]
        if s["valid"] < target:
            print(f"  未补齐: {name} 有效{s['valid']}/{target} 超时{s['verto']} 其他异常{s['other_exc']} 在跑{s['running']}")
