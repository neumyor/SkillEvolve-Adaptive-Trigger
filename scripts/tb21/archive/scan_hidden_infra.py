"""Scan every completed verifier log for setup/download failures that ended as
reward 0 (no exception raised), i.e. infra failures disguised as model failures."""
import glob, json, re

PATTERNS = {
    "uv下载失败": re.compile(r"Failed to (download|fetch|build|resolve)|Could not find EOCD|Invalid zip|error decoding|Failed to extract", re.I),
    "网络错误": re.compile(r"Connection (reset|refused|timed out)|Temporary failure in name resolution|Could not resolve host|Network is unreachable|Read timed out", re.I),
    "git失败": re.compile(r"fatal: (unable to access|could not read)|RPC failed|early EOF", re.I),
    "pip失败": re.compile(r"ERROR: Could not (install|find a version)|No matching distribution", re.I),
    "apt失败": re.compile(r"E: (Unable to locate|Failed to fetch|Could not get lock)", re.I),
}
ROOTS = {
    "qwen": "/data2/niuyiming/e1_full_q36flash_2att/jobs/e1_full_q36flash_2att/*__*",
    "dpsk": "/data2/niuyiming/e1_full_dsv4max_5att/jobs/e1_full_dsv4max_5att/*__*",
    "补跑": "/data2/niuyiming/e1_recover/jobs/*/*__*",
}
for label, pat in ROOTS.items():
    total = zero = 0
    flagged = []
    for d in sorted(glob.glob(pat)):
        try:
            r = json.load(open(d + "/result.json"))
        except Exception:
            continue
        reward = (r.get("verifier_result") or {}).get("rewards", {}).get("reward")
        if reward is None:
            continue
        total += 1
        if reward not in (0, 0.0):
            continue
        zero += 1
        try:
            log = open(d + "/verifier/test-stdout.txt", errors="replace").read()
        except Exception:
            continue
        # Did pytest actually run any test?
        ran = bool(re.search(r"(passed|failed|error)[^\n]* in [0-9.]+s|collected [0-9]+ item", log))
        hits = [k for k, rx in PATTERNS.items() if rx.search(log)]
        if hits and not ran:
            task = d.rsplit("/", 1)[1].rsplit("__", 1)[0]
            line = next((l for l in log.splitlines() if any(rx.search(l) for rx in PATTERNS.values())), "")
            flagged.append((task, hits, line.strip()[:140]))
    print(f"===== {label}: 有结论的评测 {total} 条, 其中 0 分 {zero} 条, 疑似「评测没跑起来」的 0 分 {len(flagged)} 条")
    for task, hits, line in flagged:
        print(f"  {task}: {hits} | {line}")
