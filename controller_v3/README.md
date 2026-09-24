# Controller V3 adapters

This package is a host-side timing plugin. It owns the decision to wait for
more execution evidence or invoke a host optimizer, while each upstream method
keeps its native proposal, mutation, validation, and selection semantics.
The real smoke run uses temporary directories or branches for filesystem and
Git side effects.

## Host mapping

| Host method | Rollout callback | UPDATE callback | Existing host operation preserved |
|---|---|---|---|
| SkillOpt | `SearchQAAdapter.rollout` / equivalent | native reflect → aggregate → select → patch → gate | reflect → aggregate → select → update → gate |
| GEPA | `GEPAAdapter.evaluate` batch wrapper | `optimize_anything` / engine proposal | evaluator, ASI reflection, candidate acceptance |
| EvoSkill | harness task execution and verifier | `SelfImprovingLoop._mutate` + `ProgramManager.update_frontier` | frontier selection and held-out scoring |
| Trace2Skill | benchmark runner result row | `SkillEvolver.run_evolution` in a temporary skill directory | patch validation and rollback; consolidation is disabled in smoke |

The four named classes in `adapters.py` deliberately have the same API. A
host integration passes its native rollout and update functions through
`controller_v3.integrations.make_hooks`, then calls `adapter.run(...)`.

## Real SearchQA smoke test

The real smoke entrypoint reads the released SearchQA train split and uses the
endpoint configured in `benchmark/llm_config.json` (the key is never logged):

```bash
python3 -m controller_v3.real_smoke \
  --start 100 --limit 4 \
  --out-dir tmp/controller_v3_real_smoke
```

Each method receives real SearchQA responses and writes raw responses, scores,
Controller action, native API, update result, and token usage to its own JSON.
The four native insertion paths are SkillOpt's reflect/aggregate/select/gate
stages, GEPA's `EvalServer`/`optimize_anything`, EvoSkill's `_mutate` and
frontier update, and Trace2Skill's `SkillEvolver.run_evolution`.

The older `smoke_searchqa` command remains an offline lifecycle test. Neither
command is a full experiment.

## Paired evidence runner

`controller_v3.paired_experiment` writes each task to
`<out>/<method>/<condition>/progress.jsonl` and flushes `result.json`,
`tokens.json`, and `audit.json` after every window. Re-running the same output
directory skips task IDs already present and merges the previous token ledger;
it restores `state.json` (current skill, Controller evidence state, and attempt
history) and does not reset cost totals. Accepted native candidate skills are
passed to the next window for both conditions. `summary.json` contains raw
condition records and a paired per-task comparison.

For a validation split, pass `--heldout-path` and `--heldout-limit`. Held-out
rows are evaluation-only and are kept separately from update evidence. Token
comparisons are usable only when both conditions have complete usage records.
Native calls that do not expose usage remain in the evidence but set
`cost_comparison_usable=false`.

GEPA candidate validation uses the complete paired window. ALFWorld forwards
accepted candidate skills and applies `--max-tokens` to the native rollout
bridge; API timeouts remain task evidence and invalidate only cost comparison
when response usage cannot be recovered.

After a paired campaign, run the campaign-level integrity audit:

```bash
python3 -m controller_v3.campaign_audit tmp/controller_v3_searchqa_all4_real
```

It checks task populations, manifest hashes, per-task evidence, paired IDs,
held-out artifacts, and token-ledger completeness.

## ALFWorld paired smoke

Use the official ALFWorld environment and the dedicated `alfworld-eval` LLM
configuration:

```bash
ALFWORLD_DATA="$PWD/benchmark/alfworld-eval/.data/alfworld" \
ALFWORLD_WORKER_START_METHOD=fork \
PYTHONPATH="$PWD:$PWD/benchmark/searchqa-eval/src:$PWD/repos/SkillOptETE:$PWD/repos/pulled/GEPA/src:$PWD/repos/pulled/EvoSkill:$PWD/repos/pulled/Trace2Skill" \
benchmark/alfworld-eval/.venv/bin/python -m controller_v3.alfworld_paired_experiment \
  --methods skillopt gepa evoskill trace2skill --limit 2 --batch-size 2 \
  --max-steps 50 --api-timeout 120 \
  --out-dir tmp/controller_v3_alfworld_paired
```

For a reproducible task population, use explicit IDs. The order is preserved
and unknown or duplicate IDs fail before any model call:

```bash
... -m controller_v3.alfworld_paired_experiment \
  --item-ids train:0001 train:0006 \
  --heldout-item-ids val:0001 val:0004
```

The ALFWorld bridge uses `benchmark/alfworld-eval`'s `AlfworldTextEnv` and
`run_unified_episode`; the host-specific update API remains recorded in
`equivalence_scope`. The official environment config supplies the episode
step budget, while API timeouts and malformed actions are handled by the
benchmark runner's correction/fallback protocol. Each environment process is
limited to one gamefile at a time, matching the benchmark's shard runner.

The native Trace2Skill client forwards OpenAI usage into the shared ledger.
Campaign audit therefore permits a strict cost comparison whenever both
conditions report no untracked calls; it does not infer missing usage.
