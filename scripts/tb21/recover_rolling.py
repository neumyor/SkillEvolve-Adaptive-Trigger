#!/usr/bin/env python3
"""Rolling single-trial recovery feeder (2026-10-10 redesign).

Instead of grouped Harbor runs, the exact 50 missing trials form one flat
queue, longest-expected first.  Two trials are launched per minute (no
concurrency cap); each trial is its own runner invocation with its own
RUN_ID, so no cold-start burst ever happens.  A manifest maps every
recovery arm back to its task and model.

Run detached:  cd ~/niuyiming/SkillExpand-tbeval && . ./env.sh && \
               python3 /data2/niuyiming/scripts/recover_rolling.py <queue.tsv>
"""
import os
import subprocess
import sys
import time

RUNNER = "/data2/niuyiming/scripts/run_tencent_tb21_smoke_niuyiming.sh"
JOBS_DIR = "/data2/niuyiming/e1_recover/jobs"
LOGS = os.path.expanduser("~/niuyiming/SkillExpand-tbeval/logs")


def main() -> int:
    os.makedirs(JOBS_DIR, exist_ok=True)
    queue_path = sys.argv[1]
    rows = [line.rstrip("\n").split("\t") for line in open(queue_path) if line.strip()]
    print(f"[{time.strftime('%F %T')}] queue: {len(rows)} trials, 2 per minute", flush=True)
    manifest = open(os.path.join(os.path.dirname(JOBS_DIR), "manifest.tsv"), "a")
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
                "TBENCH_MAX_TRIAL_RETRIES": "1",
                "TBENCH_VERIFIER_OVERRIDE": "7200.0",
                "TBENCH_REASONING_EFFORT": effort,
                "RUN_ID": run_id,
                "JOBS_DIR": JOBS_DIR,
                "DRY_RUN": "0",
            })
            log = open(f"{LOGS}/{run_id}.log", "ab")
            proc = subprocess.Popen(["bash", RUNNER], env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
            procs.append((proc, run_id))
            manifest.write(f"{run_id}\t{model}\t{effort or 'default'}\t{task}\t"
                           f"{time.strftime('%F %T')}\n")
            manifest.flush()
            print(f"[{time.strftime('%F %T')}] launched {run_id} ({model}, {task})", flush=True)
        if i + 2 < len(rows):
            time.sleep(60)
    manifest.close()
    failed = [rid for proc, rid in ((p, r) for p, r in procs) if proc.wait() != 0]
    for proc, rid in procs:
        proc.wait()
    print(f"[{time.strftime('%F %T')}] ALL DONE, {len(procs)} trials, "
          f"{len(failed)} runner call(s) nonzero: {failed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
