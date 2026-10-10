import json, glob, sys, re
from collections import defaultdict

for label, root in (("qwen", "/data2/niuyiming/e1_full_q36flash_2att/jobs/e1_full_q36flash_2att"),
                    ("dpsk", "/data2/niuyiming/e1_full_dsv4max_5att/jobs/e1_full_dsv4max_5att")):
    rows = []
    for f in sorted(glob.glob(root + "/*__*/result.json")):
        name = f.split("/")[-2].rsplit("__", 1)[0]
        data = json.load(open(f))
        reward = (data.get("verifier_result") or {}).get("rewards", {}).get("reward")
        if reward is not None:
            continue
        exc = data.get("exception_info") or {}
        msg = (exc.get("exception_message") or "")[:220].replace("\n", " ")
        msg = re.sub(r"\s+", " ", msg)
        rows.append((name, exc.get("exception_type"), msg))
    print(f"===== {label}: {len(rows)} 个异常trial =====")
    groups = defaultdict(list)
    for name, etype, msg in rows:
        key = None
        if etype == "VerifierTimeoutError":
            key = "verifier超时"
        elif "tmux: command not found" in msg:
            key = "tmux未安装(冷启动竞态)"
        elif "send-keys" in msg or "invalid flag" in msg:
            key = "tmux send-keys解析失败"
        elif etype == "AgentSetupTimeoutError":
            key = "沙箱启动超时"
        elif etype == "AgentTimeoutError" or etype == "TimeoutException":
            key = "agent执行超时"
        elif etype == "SandboxException":
            key = "沙箱异常"
        elif etype == "AddTestsDirError":
            key = "任务测试目录缺失"
        elif etype == "InvalidArgumentException":
            key = "非法参数"
        else:
            key = f"其他({etype})"
        groups[key].append((name, msg[:150]))
    for key in sorted(groups, key=lambda k: -len(groups[k])):
        print(f"\n[{key}] {len(groups[key])} 个:")
        seen = set()
        for name, msg in groups[key]:
            tag = msg[:110]
            dup = " (同类)" if tag in seen else ""
            seen.add(tag)
            print(f"  {name}: {tag}{dup}")
