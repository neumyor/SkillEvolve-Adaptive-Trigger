# Benchmark-Specific Jev Fine-Tuning Plan

**Experiment:** Train two independent MiniCPM5-2B-Jev LoRA adapters, one using SearchQA only and one using ALFWorld only.  
**Plan registered:** 2026-09-30 (Asia/Shanghai).  
**Status:** Protocol registration and second review complete; data filtering and independent audit are the next gate.  
**Execution rule:** This is a new experiment. After context compaction, read this document first and continue from the first unchecked gate. Do not use the mixed-benchmark model's test results to choose settings or thresholds.

## Objective and comparison

Estimate `P(pass | complete skill, task, target LLM)` with two separate models:

1. `searchqa_only`: train and validate only on SearchQA examples; evaluate only on the SearchQA test groups.
2. `alfworld_only`: train and validate only on ALFWorld examples; evaluate only on the ALFWorld test groups.

Both models start from the untouched remote MiniCPM5-2B-Jev checkpoint and update their own rank-16 LoRA adapter. The original Jev checkpoint is evaluated on each corresponding test split as a baseline. No input from the other benchmark enters either model's train, validation, or test evaluation.

The source, task reconstruction, complete Markdown skills, soft targets, serialization, token limits, calibration, optimizer settings, metrics, and bootstrap definitions remain those fixed in the completed mixed-benchmark protocol. This experiment does not revise those choices after seeing results.

## Fixed data construction

The immutable source is the audited remote preparation under `20260929_caps6144x6144/data` and `splits`. For each benchmark, create a fresh experiment directory by filtering only rows whose `dataset` equals the benchmark, then independently verify:

- every retained example has the original complete serialized state, skill hash, task group, pass/fail counts, and target distribution;
- filtered row resolution contains exactly the source rows for that benchmark, with no cross-benchmark rows;
- task groups are assigned independently within the selected benchmark with `SHA-256("20260929|{dataset}|{task_group}")`, 10% test and 10% validation using the registered Python-round rule;
- train, validation, and test task groups are disjoint and the filtered manifests reproduce the expected subset of the audited assignment;
- all source counts, pass/fail mass, mixed-target counts, repeated trials, and token audits reconcile;
- no filtered input is overflowed or silently truncated.

The complete input remains:

```text
Dataset: {dataset}
Target agent model: {llm}

Skill:
{complete skill Markdown body}

Task:
{complete task text}
```

Conflicting observations remain soft targets `[n_fail/n_trials, n_pass/n_trials]`. The training loss is trial-weighted soft-label cross-entropy. The question is fixed to the `noul` type with options `[false, true]` and the saved Jev `noul` bias/temperature.

## Fixed training and evaluation

- Remote root: `~/niuyiming/SkillEvolvePaperList/tmp/jev_passfail/20260930_benchmark_specific/`.
- Each model uses 8-GPU DDP, BF16, AdamW, learning rate `1e-5`, weight decay `0.01`, global effective batch 32, gradient clipping 1.0, seed `20260929`, maximum 10 epochs, patience 2, and minimum validation-NLL improvement `1e-6`.
- Only LoRA parameters are trainable; the base model and Jev readout buffers are frozen. Calibration is fixed identically in train and inference.
- Primary checkpoint selection is minimum validation trial-weighted soft-label NLL; ties within `1e-6` choose the earlier epoch. Brier, ECE, balanced accuracy, fail recall, and expected macro-F1 are diagnostics.
- Threshold diagnostics use the fixed `P(pass) >= 0.5` rule for the primary report. Any later threshold sweep is a separate post-hoc analysis and cannot change checkpoint selection or the registered test result.
- Test remains unopened until that benchmark's training integrity audit and checkpoint freeze pass. Each benchmark test is evaluated exactly once for original Jev and its selected specialist checkpoint.
- Test confidence intervals use 2,000 task-group bootstrap replicates, seed `20260929`, preserving the observed benchmark test trial mass.

## Stages and gates

| Stage | Work | Pass condition | State |
|---|---|---|---|
| 0 | Register protocol and perform a second review against `AGENTS.md` and the completed mixed-benchmark plan. | Scope, split, metrics, checkpoint rule, test lock, and recovery procedure are fixed before specialist results. | [x] |
| 1 | Remote preflight. | Original Jev checkpoint is unchanged; service is stopped; all eight GPUs are idle; remote environment imports the exact model. | [ ] |
| 2 | Build fresh SearchQA-only and ALFWorld-only data/split directories from immutable audited data. | Counts and checksums reconcile; no cross-benchmark examples or task-group leakage. | [ ] |
| 3 | Independent filtered-data, token, metric, and split audit. | Both benchmark directories pass all checks and support binary metrics in every split. | [ ] |
| 4 | Run one-input-per-specialist smoke and one optimizer step on 8 GPUs; verify calibration, LoRA gradients, save/reload, and DDP agreement. | Both smoke runs pass; no specialist settings are changed based on test data. | [ ] |
| 5 | Train SearchQA-only and ALFWorld-only models under separate PID-tracked supervisors, sequentially on the same eight GPUs. | Every epoch is atomically checkpointed and audited; early stopping or completion is clean; no concurrent trainer. | [ ] |
| 6 | Audit each complete run and freeze each best checkpoint. | Data/code/source checksums, epoch metrics, predictions, selection flags, and checkpoint state all reconcile. | [ ] |
| 7 | Evaluate each specialist and original Jev once on its untouched test split; bootstrap by task group. | Predictions, metrics, bootstrap reports, and checkpoint hashes reconcile; no test-driven choices. | [ ] |
| 8 | Write the comparative report. | Report distinguishes specialist-vs-baseline results from the prior mixed-benchmark experiment and records limitations. | [ ] |

## Recovery and storage

Keep `searchqa/` and `alfworld/` data, splits, runs, evaluations, and jobs separate under the new remote root. Use independent run and job names, for example `searchqa_full_v1` and `alfworld_full_v1`. Every long process must use the PID-tracked supervisor and a new shell watcher that checks recorded PIDs and artifact files; never use `pgrep -f`. If a trainer exits unexpectedly, confirm its recorded supervisor and child PIDs are gone, reconcile the existing run, and resume only that run. Never start a second trainer for the same output directory.

Before each costly stage, repeat the required small-sample, invariant, matched-condition, fixed-metric, statistical, and resume checks. Audit every completed specialist run before reading its test results.

## Double-review checklist

- [x] Separate benchmark scope, independent models, and no cross-benchmark training inputs are explicit.
- [x] Soft-label aggregation, complete skill/task input, answer-leakage exclusion, and task-level grouping are inherited without alteration.
- [x] Specialist split rule, validation checkpoint selection, untouched test policy, and bootstrap rule are fixed.
- [x] Training settings, Jev calibration, LoRA-only updates, 8-GPU smoke, atomic checkpoints, supervisor/PID recovery, and audit gates are fixed.
- [x] Primary and diagnostic metrics are fixed before specialist results.
- [x] The distinction between this specialist experiment and the prior mixed-benchmark experiment is explicit.

## Progress log

- 2026-09-30: New specialist experiment registered after the mixed-benchmark run completed. The prior model and its test results are comparison context only; no specialist data, threshold, or checkpoint choice has been inspected.
