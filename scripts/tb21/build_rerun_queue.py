#!/usr/bin/env python3
"""Build the rerun queue from audit_trials.py's per-task gaps.

Reads <audit.json>, writes a TSV (run_id, model, effort, task) for
recover_rolling.py.  Longest-expected tasks first, so the slowest trials start
earliest.  run_id = e1fix_<q|d>_<task>_<n> (distinct from the earlier e1rec_*
recovery arms so the two generations stay separable).
"""
import json
import sys

MODELS = {"qwen": ("q", "qwen3.6-flash-distill", ""),
          "dpsk": ("d", "DEEPSEEK_up5zdj", "max")}
# Verifiers that install torch / heavy deps or boot QEMU: slowest, start first.
HEAVY = {"torch-pipeline-parallelism", "torch-tensor-parallelism", "pytorch-model-recovery",
         "mteb-retrieve", "qemu-startup", "qemu-alpine-ssh", "pytorch-model-cli", "sam-cell-seg"}


def main() -> int:
    audit, out = json.load(open(sys.argv[1])), sys.argv[2]
    rows = []
    for key, gap in audit["per_task"].items():
        label, task = key.split(":", 1)
        tag, model, effort = MODELS[label]
        for n in range(1, gap["rerun"] + 1):
            rows.append((task not in HEAVY, label != "dpsk", task, n,
                         (f"e1fix_{tag}_{task}_{n}", model, effort, task)))
    rows.sort(key=lambda r: r[:4])
    with open(out, "w") as f:
        for *_, row in rows:
            f.write("\t".join(row) + "\n")
    print(f"{len(rows)} trials -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
