"""Audit every trial of the qwen / dpsk TB2.1 campaign and decide which need a rerun.

Pre-registered rules (fixed before looking at the data):
  VALID         reward present AND pytest collected tests ("collected N item")
  RERUN_INFRA   no reward, exception is infrastructure
                (AgentSetupTimeoutError, VerifierTimeoutError, SandboxException,
                 AddTestsDirError, transport/RPC errors, unknown/no exception)
  RERUN_FAKE0   reward present but pytest never collected anything
                (verifier setup / download failed -> fake model failure)
  KEEP_MODEL    no reward, exception is the model's own doing
                (AgentTimeoutError, tmux keystroke errors, context/parse errors)
  RUNNING       launched recovery trial without result.json

Targets: qwen 2 valid trials per task, dpsk 5.
"""
import collections, glob, json, os, re, sys

MAIN = {
    "q": "/data2/niuyiming/e1_full_q36flash_2att/jobs/e1_full_q36flash_2att",
    "d": "/data2/niuyiming/e1_full_dsv4max_5att/jobs/e1_full_dsv4max_5att",
}
# Every recovery generation, in launch order: e1_recover (e1rec_*, old network),
# then e1_fix (e1fix_*, VPC DNS + intranet mirrors).  Add new generations here.
REC_GLOBS = ("/data2/niuyiming/e1_recover/jobs/e1rec_{tag}_*",
             "/data2/niuyiming/e1_fix/jobs/e1fix_{tag}_*")
TARGET = {"q": 2, "d": 5}
TASKS_DIR = "/data2/liyishan/tbench2-openclaw-min/sources/terminal-bench-2-1-modelbest/tasks"

INFRA_EXC = {"AgentSetupTimeoutError", "VerifierTimeoutError", "SandboxException",
             "AddTestsDirError", "EnvironmentStartTimeoutError", "DownloadVerifierDirError",
             "RewardFileNotFoundError"}
MODEL_EXC = {"AgentTimeoutError", "ContextLengthExceededError", "OutputLengthExceededError"}
COLLECTED = re.compile(r"collected [0-9]+ item")
SETUP_FAIL = [
    ("uv下载失败(PyPI包)", re.compile(r"Failed to download `")),
    ("GitHub下载失败(uv/Python)", re.compile(r"Failed to download https://github\.com|failed to download https://github\.com")),
    ("apt包404(Debian下架)", re.compile(r"404\s+Not Found")),
    ("apt锁冲突", re.compile(r"Could not get lock")),
    ("uvx不存在", re.compile(r"uvx: command not found")),
    ("zip损坏", re.compile(r"Could not find EOCD|Invalid zip")),
]


def classify_exception(etype, emsg):
    if not etype:
        return "RERUN_INFRA", "无异常也无reward"
    if etype in INFRA_EXC:
        return "RERUN_INFRA", etype
    if etype in MODEL_EXC:
        return "KEEP_MODEL", etype
    if etype == "RuntimeError" and ("send" in emsg and "keys" in emsg or "tmux" in emsg):
        return "KEEP_MODEL", "tmux按键失败(" + ("tmux未安装" if "command not found" in emsg else "命令解析") + ")"
    if "model request failed" in emsg.lower() or "context deadline" in emsg.lower():
        return "RERUN_INFRA", etype + "(LLM请求)"
    if etype in ("InvalidArgumentException", "TimeoutException"):
        return "RERUN_INFRA", etype + "(沙箱RPC)"
    if etype == "CancelledError":
        return "RERUN_INFRA", "CancelledError(我方手动停止补跑器)"
    return "RERUN_INFRA", etype + "(未识别,按基础设施)"


def audit_trial(tdir):
    try:
        r = json.load(open(tdir + "/result.json"))
    except FileNotFoundError:
        return "RUNNING", "无result.json", None
    reward = (r.get("verifier_result") or {}).get("rewards", {}).get("reward")
    exc = r.get("exception_info") or {}
    etype, emsg = exc.get("exception_type") or "", str(exc.get("exception_message") or "")
    if reward is None:
        status, why = classify_exception(etype, emsg)
        return status, why, None
    try:
        log = open(tdir + "/verifier/test-stdout.txt", errors="replace").read()
    except FileNotFoundError:
        log = ""
    if COLLECTED.search(log):
        return "VALID", "", float(reward)
    why = [name for name, rx in SETUP_FAIL if rx.search(log)] or ["pytest未运行(原因未识别)"]
    return "RERUN_FAKE0", "+".join(why), float(reward)


def task_of(tdir):
    return os.path.basename(tdir.rstrip("/")).rsplit("__", 1)[0]


rows = []
for tag in ("q", "d"):
    for tdir in sorted(glob.glob(MAIN[tag] + "/*__*")):
        rows.append((tag, "原始", task_of(tdir), tdir) + audit_trial(tdir))
    for rid in [d for g in REC_GLOBS for d in sorted(glob.glob(g.format(tag=tag)))]:
        tds = glob.glob(rid + "/*__*")
        if not tds:
            continue
        for tdir in tds:
            rows.append((tag, "补跑", task_of(tdir), tdir) + audit_trial(tdir))

all_tasks = sorted(d for d in os.listdir(TASKS_DIR) if os.path.isfile(os.path.join(TASKS_DIR, d, "task.toml")))
assert len(all_tasks) == 89, len(all_tasks)
out = {"rules": __doc__, "trials": [], "per_task": {}}
for tag, label in (("q", "qwen"), ("d", "dpsk")):
    mine = [r for r in rows if r[0] == tag]
    print(f"\n==================== {label}（目标每题 {TARGET[tag]} 条有效）====================")
    for src in ("原始", "补跑"):
        c = collections.Counter(r[4] for r in mine if r[1] == src)
        print(f"  {src}: 共 {sum(c.values())} 条  " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print("  无效原因分布:")
    for (st, why), n in collections.Counter((r[4], r[5]) for r in mine if r[4] not in ("VALID",)).most_common():
        print(f"    {st:12s} {why:40s} {n}")
    need = {}
    for t in all_tasks:
        tr = [r for r in mine if r[2] == t]
        valid = sum(1 for r in tr if r[4] == "VALID")
        running = sum(1 for r in tr if r[4] == "RUNNING")
        model_fail = sum(1 for r in tr if r[4] == "KEEP_MODEL")
        # Model failures count toward the sample (they are genuine outcomes, scored 0).
        have = valid + model_fail
        gap = max(0, TARGET[tag] - have - running)
        need[t] = {"valid": valid, "model_fail": model_fail, "running": running,
                   "rerun": gap,
                   "invalid": collections.Counter(r[5] for r in tr if r[4].startswith("RERUN"))}
        out["per_task"][f"{label}:{t}"] = {k: (dict(v) if isinstance(v, collections.Counter) else v)
                                          for k, v in need[t].items()}
    gaps = {t: v for t, v in need.items() if v["rerun"]}
    print(f"  需要重跑: {sum(v['rerun'] for v in gaps.values())} 条, 涉及 {len(gaps)} 题")
    for t, v in sorted(gaps.items(), key=lambda kv: -kv[1]["rerun"]):
        print(f"    {t:36s} 补 {v['rerun']}  (有效{v['valid']} 模型失败{v['model_fail']}) 无效原因: {dict(v['invalid'])}")

for r in rows:
    out["trials"].append({"model": r[0], "source": r[1], "task": r[2], "trial_dir": r[3],
                          "status": r[4], "reason": r[5], "reward": r[6]})
json.dump(out, open("/data2/niuyiming/audit_20261010.json", "w"), ensure_ascii=False, indent=1)
print("\n逐条明细已写入 /data2/niuyiming/audit_20261010.json")


# ---------------------------------------------------------------------------
# Final metrics on VALID + KEEP_MODEL trials only (fake zeros and infra failures
# excluded).  Per task, the first TARGET trials in launch order are used
# (original run first, then recovery generations), so every task has the same
# sample size and extra recovery arms cannot inflate pass@N.
# avg@N  = mean over tasks of (successes / trials used)
# pass@N = share of tasks with at least one success
# Tasks with fewer than TARGET usable trials are reported, not padded.
# ---------------------------------------------------------------------------
print("\n==================== 指标（仅有效轨迹 + 模型自身失败，按目标数截断）====================")
for tag, label in (("q", "qwen"), ("d", "dpsk")):
    mine = [r for r in rows if r[0] == tag and r[4] in ("VALID", "KEEP_MODEL")]
    order = {"原始": 0, "补跑": 1}
    per_task, short = {}, []
    for t in all_tasks:
        tr = sorted((r for r in mine if r[2] == t), key=lambda r: (order[r[1]], r[3]))[:TARGET[tag]]
        if len(tr) < TARGET[tag]:
            short.append((t, len(tr)))
        if tr:
            per_task[t] = [1.0 if (r[6] or 0) >= 1 else 0.0 for r in tr]
    n = len(all_tasks)
    avg = sum(sum(v) / len(v) for v in per_task.values()) / n
    pas = sum(1 for v in per_task.values() if any(v)) / n
    print(f"  {label}: avg@{TARGET[tag]}={avg:.4f}  pass@{TARGET[tag]}={pas:.4f} "
          f"({sum(1 for v in per_task.values() if any(v))}/{n})  样本不足的题 {len(short)} 个: {short}")
    print(f"    （分母固定为 89 题；没有任何可用轨迹的题按 0 计入）")
