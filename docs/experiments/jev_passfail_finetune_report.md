# Jev Skill–Task Pass/Fail Probability Fine-Tuning

**Run:** `20260929_caps6144x6144/full_train_20260929_v1`<br>
**Status:** Complete; test evaluated once after checkpoint freeze.<br>
**Objective:** Estimate `P(pass | dataset, target LLM, complete skill text, task text)` as Jev's `[P(fail), P(pass)]` distribution.

## Result

The frozen epoch-1 model has lower trial-weighted test NLL, Brier score, and ECE than the original Jev checkpoint overall and on each dataset. At the fixed `P(pass) >= 0.5` diagnostic threshold, fail recall is lower, so the probability-quality improvement does not imply that this threshold is suitable for fail detection.

Each cell gives the point estimate and its 95% percentile interval from 2,000 task-group bootstrap replicates (seed `20260929`). Overall bootstrap replicates preserve the observed test trial weight within each dataset.

### Overall

| Metric | Original Jev | Fine-tuned epoch 1 |
|---|---:|---:|
| Trial-weighted NLL | 0.7082 [0.6644, 0.7529] | 0.5094 [0.4481, 0.5678] |
| Brier | 0.2418 [0.2228, 0.2609] | 0.1547 [0.1313, 0.1771] |
| 10-bin ECE | 0.2419 [0.2033, 0.2844] | 0.0621 [0.0416, 0.0997] |
| Balanced accuracy | 0.5065 [0.4599, 0.5576] | 0.5422 [0.5109, 0.5750] |
| Fail recall | 0.3724 [0.2854, 0.4696] | 0.1466 [0.0897, 0.2140] |
| Expected macro-F1 | 0.4885 [0.4501, 0.5284] | 0.5412 [0.4984, 0.5859] |

### SearchQA

Test coverage is 1,602 unique inputs, 1,620 trials and 280 task groups.

| Metric | Original Jev | Fine-tuned epoch 1 |
|---|---:|---:|
| Trial-weighted NLL | 0.7053 [0.6599, 0.7529] | 0.5090 [0.4449, 0.5708] |
| Brier | 0.2442 [0.2247, 0.2643] | 0.1586 [0.1337, 0.1824] |
| 10-bin ECE | 0.2409 [0.2011, 0.2865] | 0.0611 [0.0410, 0.1017] |
| Balanced accuracy | 0.5046 [0.4563, 0.5578] | 0.5357 [0.5021, 0.5716] |
| Fail recall | 0.3616 [0.2683, 0.4628] | 0.1352 [0.0755, 0.2066] |
| Expected macro-F1 | 0.4880 [0.4482, 0.5299] | 0.5328 [0.4868, 0.5815] |

### ALFWorld

Test coverage is 62 unique inputs, 101 trials and 8 task groups. The small number of groups makes these intervals substantially less precise than SearchQA.

| Metric | Original Jev | Fine-tuned epoch 1 |
|---|---:|---:|
| Trial-weighted NLL | 0.7556 [0.6444, 0.8387] | 0.5161 [0.3392, 0.7010] |
| Brier | 0.2040 [0.1504, 0.2673] | 0.0925 [0.0653, 0.1252] |
| 10-bin ECE | 0.2690 [0.1935, 0.3799] | 0.1122 [0.0746, 0.2037] |
| Balanced accuracy | 0.5237 [0.4226, 0.6878] | 0.6329 [0.5667, 0.7211] |
| Fail recall | 0.5217 [0.3529, 0.8333] | 0.3043 [0.2000, 0.4615] |
| Expected macro-F1 | 0.4821 [0.3862, 0.5822] | 0.6559 [0.5696, 0.7703] |

## Data and Split

The source has 17,572 six-tuple observations: 16,543 SearchQA and 1,029 ALFWorld. Resolution found 46 skill artifacts and produced 16,994 unique serialized states while retaining all 17,572 trials. The 242 mixed-target states remain soft probability targets; no exact duplicate source rows were removed. Task resolution and skill hashes passed independent audits. All complete inputs fit the final limits with no overflow or truncation.

The input contains dataset, target-agent model, the complete Markdown skill, and task text. Skill-evolve method, pass/fail source label, IDs, paths, and gold answers are excluded. State, causal row, and packed-record limits are 6,144, 6,144, and 6,400 tokens. The longest causal row is 5,730 tokens.

| Split | SearchQA inputs / trials / groups | ALFWorld inputs / trials / groups | Total inputs / trials / groups |
|---|---:|---:|---:|
| Train | 13,190 / 13,305 / 2,240 | 470 / 799 / 62 | 13,660 / 14,104 / 2,302 |
| Validation | 1,608 / 1,618 / 280 | 62 / 129 / 8 | 1,670 / 1,747 / 288 |
| Test | 1,602 / 1,620 / 280 | 62 / 101 / 8 | 1,664 / 1,721 / 288 |

Task groups were deterministically assigned within each dataset using seed `20260929`; all observations for a task remain in one split. The test set was not opened until training audit and checkpoint freeze passed. The pre-existing `validation_eval.json` SearchQA Jev check is historical prior use, not a separate holdout result.

## Training

Training started from the remote MiniCPM5-2B Jev checkpoint and updated only the rank-16 LoRA adapter. The eight-GPU DDP run used BF16, AdamW, learning rate `1e-5`, weight decay `0.01`, global effective batch 32, gradient clipping 1.0, and seed `20260929`. It was capped at 10 epochs with patience 2 and minimum validation-NLL improvement `1e-6`.

| Epoch | Validation NLL | SearchQA NLL | ALFWorld NLL | Selection state |
|---:|---:|---:|---:|---|
| 1 | 0.522975 | 0.521300 | 0.543984 | Selected; best |
| 2 | 0.588447 | 0.589200 | 0.578999 | Not selected; stale 1 |
| 3 | 0.699723 | 0.711463 | 0.552464 | Not selected; stale 2; early stop |

The original Jev validation NLL was 0.693381 overall (SearchQA 0.683349; ALFWorld 0.819213). The registered primary selection metric remained validation trial-weighted soft-label NLL. The whole-run auditor passed all three epoch checkpoints, validation predictions, metrics, data/code hashes and selection records. The frozen checkpoint is `epoch_01`; its adapter and Jev readout were hashed before test evaluation.

## Evaluation and Limits

The test evaluator ran once and exited successfully. It wrote one probability distribution per unique input for both original Jev and the frozen model. An independent post-run audit matched test state hashes, dataset/task-group/count provenance, row alignment, checkpoint hashes, all six metrics, and all bootstrap intervals to the saved prediction files.

The principal result is probability quality under trial-weighted soft-label metrics. Fail recall at the fixed 0.5 threshold declines, so this model should not be described as a better fail detector without a separately registered thresholding study. The ALFWorld estimate is especially uncertain with only eight test task groups. This is one task-group split and does not establish performance under distribution shift. The historical SearchQA Jev check is not an independent holdout.

## Artifacts

Compact logs, manifests, per-input validation/test predictions, metrics, bootstrap intervals, and audit reports are mirrored under `tmp/jev_passfail_remote/20260929_caps6144x6144/`. The full run remains on the remote server at `~/niuyiming/SkillEvolvePaperList/tmp/jev_passfail/20260929_caps6144x6144/`; model weight files were not copied locally.
