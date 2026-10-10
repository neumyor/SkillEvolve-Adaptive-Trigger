#!/usr/bin/env python3
"""Rolling single-trial launcher for TB2.1 on Tencent E2B.

Every line of the queue (TSV: run_id, model, effort, task) becomes one
independent runner invocation with N_ATTEMPTS=1 and its own RUN_ID.  Two
trials start per minute with no concurrency cap, so sandboxes never cold-start
in a burst (the cause of the AgentSetupTimeoutError / tmux-not-installed
failures of the first full runs).

Campaign settings (network, retries, verifier ceiling) come from the caller's
environment -- source campaign.env first -- and are written next to every
trial in manifest.tsv, so each trial's conditions stay traceable.

Run detached:
  cd ~/niuyiming/SkillExpand-tbeval && . ./env.sh && . /data2/niuyiming/scripts/campaign.env
  python3 /data2/niuyiming/scripts/recover_rolling.py <queue.tsv> <jobs_dir>
"""
import os
import subprocess
import sys
import time

RUNNER = "/data2/niuyiming/scripts/run_tencent_tb21_smoke_niuyiming.sh"
LOGS = os.path.expanduser("~/niuyiming/SkillExpand-tbeval/logs")
# Recorded per trial; all are read by the runner / environment class.
RECORDED = ("TBENCH_VPC_DNS", "TBENCH_PYPI_MIRROR", "TBENCH_APT_SNAPSHOT_BULLSEYE",
            "TBENCH_APT_INTRANET_MIRROR", "TBENCH_MAX_TRIAL_RETRIES",
            "TBENCH_VERIFIER_OVERRIDE", "TBENCH_VERIFIER_MULTIPLIER",
            "TBENCH_SETUP_MULTIPLIER")


def main() -> int:
    queue_path, jobs_dir = sys.argv[1], sys.argv[2]
    os.makedirs(jobs_dir, exist_ok=True)
    rows = [line.rstrip("\n").split("\t") for line in open(queue_path) if line.strip()]
    settings = {k: os.environ.get(k, "") for k in RECORDED}
    print(f"[{time.strftime('%F %T')}] queue: {len(rows)} trials, 2 per minute; {settings}", flush=True)
    manifest_path = os.path.join(os.path.dirname(jobs_dir.rstrip("/")), "manifest.tsv")
    new_manifest = not os.path.exists(manifest_path)
    manifest = open(manifest_path, "a")
    if new_manifest:
        manifest.write("\t".join(("run_id", "model", "effort", "task", "launched_at") + RECORDED) + "\n")
    procs = []
    for i in range(0, len(rows), 2):
        for run_id, model, effort, task in rows[i:i + 2]:
            env = dict(os.environ)
            env.update({
                "MODEL_NAME": model,
                "TBENCH_RUN_MODE": "selected",
                "TBENCH_TASK_NAMES": task,
                "TBENCH_N_ATTEMPTS": "1",
                "TBENCH_N_CONCURRENT": "1",
                "TBENCH_REASONING_EFFORT": effort,
                "RUN_ID": run_id,
                "JOBS_DIR": jobs_dir,
                "DRY_RUN": "0",
            })
            log = open(f"{LOGS}/{run_id}.log", "ab")
            procs.append((subprocess.Popen(["bash", RUNNER], env=env,
                                           stdout=log, stderr=subprocess.STDOUT), run_id))
            manifest.write("\t".join([run_id, model, effort or "default", task,
                                      time.strftime("%F %T")] + [settings[k] for k in RECORDED]) + "\n")
            manifest.flush()
            print(f"[{time.strftime('%F %T')}] launched {run_id} ({model}, {task})", flush=True)
        if i + 2 < len(rows):
            time.sleep(60)
    manifest.close()
    failed = [rid for proc, rid in procs if proc.wait() != 0]
    print(f"[{time.strftime('%F %T')}] ALL DONE, {len(procs)} trials, "
          f"{len(failed)} runner call(s) nonzero: {failed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
