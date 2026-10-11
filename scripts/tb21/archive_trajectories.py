#!/usr/bin/env python3
"""Archive the exact trajectories behind the final avg@5 / pass@5 numbers.

Single source of truth is the audit JSON written by audit_trials.py: for every
task we take the SAME trials the metrics used -- status VALID or KEEP_MODEL,
sorted by (source generation, trial dir), truncated to N per task -- and copy
each FULL trial directory (trajectory, recordings, verifier outputs, config,
logs).  Refuses to run while any task is still short of N usable trials unless
--allow-short is given, so a final archive cannot silently miss a trial.

Layout (under TBENCH_ARCHIVE_ROOT, default $TBENCH_RESULTS_ROOT/e1_final_archive):

  <archive>/qwen/<task>/01_<task>__<suffix>/     # rank 01..05 = metric order
  <archive>/dpsk/<task>/03_<task>__<suffix>/
  <archive>/manifest_qwen.tsv                    # rank, source, origin run, reward, original path
  <archive>/manifest_dpsk.tsv
  <archive>/summary.json                         # per-task rewards + recomputed metrics

Naming rules:
  <label>/   qwen | dpsk
  <task>/    the 89 task directory names
  <NN>_      the trial's rank within the task's metric sample, zero-padded,
             identical to the order the metrics truncate to
  <task>__<suffix>/  the original trial directory name, unique across the whole
             campaign, so no origin run id is needed in the path; the manifest
             carries source (原始/canary/补跑), origin run id and original path.
"""
import argparse, collections, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_ROOT = os.environ.get("TBENCH_RESULTS_ROOT", "/data2/niuyiming")
ARCHIVE_ROOT = os.environ.get(
    "TBENCH_ARCHIVE_ROOT", os.path.join(RESULTS_ROOT, "e1_final_archive"))
# Must mirror audit_trials.py's TARGET and the metrics' sort order.
TARGET = {"q": 5, "d": 5}
LABEL = {"q": "qwen", "d": "dpsk"}
ORDER = {"原始": 0, "canary": 1, "补跑": 2}


def select(audit):
    """Per model per task, the trials the metrics counted (audit's own rule)."""
    picked = {}
    for tag in TARGET:
        by_task = collections.defaultdict(list)
        for t in audit["trials"]:
            if t["model"] == tag and t["status"] in ("VALID", "KEEP_MODEL"):
                by_task[t["task"]].append(t)
        for task, rows in by_task.items():
            picked[(tag, task)] = sorted(
                rows, key=lambda r: (ORDER[r["source"]], r["trial_dir"]))[:TARGET[tag]]
    return picked


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("audit_json", help="audit_trials.py output JSON")
    ap.add_argument("--allow-short", action="store_true",
                    help="archive even if some tasks have fewer than N usable trials")
    args = ap.parse_args()

    audit = json.load(open(args.audit_json))
    picked = select(audit)

    short = [(tag, task, len(rows)) for (tag, task), rows in sorted(picked.items())
             if len(rows) < TARGET[tag]]
    all_tasks = sorted({t["task"] for t in audit["trials"]})
    missing = [(tag, task) for tag in TARGET for task in all_tasks
              if (tag, task) not in picked]
    if (short or missing) and not args.allow_short:
        print(f"样本不足，拒绝归档（用 --allow-short 强制）:")
        for tag, task, n in short:
            print(f"  {LABEL[tag]}/{task}: {n}/{TARGET[tag]}")
        for tag, task in missing:
            print(f"  {LABEL[tag]}/{task}: 0/{TARGET[tag]}")
        return 2

    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    header = ["rank", "task", "source", "origin_run", "trial_dir", "reward", "original_path"]
    manifests = {label: [header] for label in LABEL.values()}
    summary = {"tasks": {}}
    n_copied = 0
    for (tag, task), rows in sorted(picked.items()):
        label = LABEL[tag]
        rewards = []
        for rank, row in enumerate(rows, 1):
            src = row["trial_dir"].rstrip("/")
            origin_run = os.path.basename(os.path.dirname(src))
            dest = os.path.join(ARCHIVE_ROOT, label, task,
                                f"{rank:02d}_{os.path.basename(src)}")
            if not os.path.isdir(dest):
                shutil.copytree(src, dest, symlinks=True)
            assert os.path.isfile(os.path.join(dest, "result.json")), dest
            n_copied += 1
            reward = 1.0 if (row["reward"] or 0) >= 1 else 0.0
            rewards.append(reward)
            manifests[label].append([f"{rank:02d}", task, row["source"], origin_run,
                                     os.path.basename(src), str(row["reward"]), src])
        summary["tasks"][f"{label}:{task}"] = {
            "n": len(rows), "rewards": rewards,
            "success_rate": sum(rewards) / len(rewards) if rewards else 0.0,
        }

    for label, rows in manifests.items():
        path = os.path.join(ARCHIVE_ROOT, f"manifest_{label}.tsv")
        with open(path, "w") as f:
            for r in rows:
                f.write("\t".join(r) + "\n")
    for label in ("qwen", "dpsk"):
        tag = [t for t, l in LABEL.items() if l == label][0]
        vals = [v for k, v in summary["tasks"].items() if k.startswith(label + ":")]
        n_tasks = len(all_tasks)
        summary[f"{label}_avg@{TARGET[tag]}"] = sum(
            v["success_rate"] for v in vals) / n_tasks
        summary[f"{label}_pass@{TARGET[tag]}"] = sum(
            1 for v in vals if any(v["rewards"])) / n_tasks
    with open(os.path.join(ARCHIVE_ROOT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)

    print(f"归档完成: {n_copied} 条 trial -> {ARCHIVE_ROOT}")
    for label in ("qwen", "dpsk"):
        print(f"  {label}: avg={summary[f'{label}_avg@5']:.4f} "
              f"pass={summary[f'{label}_pass@5']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
