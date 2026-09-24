# SkillEvolve Adaptive Trigger

Controller V3 is a host-side plugin for self-evolving LLM agent methods. It
decides when a host should wait for more execution evidence and when it should
invoke its native optimizer. The host continues to own proposal, reflection,
mutation, validation, selection, rollback, and skill storage.

This makes the central experiment direct: compare an unchanged host schedule
with the same host plus Controller V3, using the same tasks, model, skill
state, and evaluation harness. The target is lower LLM token cost at
comparable quality.

## Repository layout

```text
controller_v3/          Controller core, host bridges, ledgers, runners, audits
controller_v3/tests/    Unit and integration-oriented tests
benchmark/              Evaluation setup documentation (upstream checkouts are separate)
docs/                   Method, evidence, and reproduction notes
tests/                  Project-level smoke tests
```

This repository does not vendor private API keys, downloaded benchmark data,
virtual environments, paper PDFs, experiment caches, or upstream research
checkouts. Those are installed separately and ignored by Git.

## Architecture

The Controller interface is intentionally small:

1. A host emits rollout records containing task IDs, success, failure reason,
   and optional execution-health metadata.
2. `ControllerV3` accumulates evidence and returns `WAIT` or `UPDATE`.
3. On `UPDATE`, the host executes its native optimization path unchanged.
4. The host writes the candidate, validation result, checkpoint, and token
   ledger before moving to the next window.

The adapters cover SkillOpt, GEPA, EvoSkill, and Trace2Skill. The ALFWorld
bridge uses the official `benchmark/alfworld-eval` runner and starts one
isolated environment process per active episode. Infrastructure failures are
retried in fresh processes and are never silently scored as model failures.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Install the upstream method repositories under `repos/pulled/` for the
integration you need. The `benchmark/` directory in this repository contains
setup documentation only; the official benchmark environments are intentionally
not vendored. Clone or install them separately at `benchmark/alfworld-eval`
and `benchmark/searchqa-eval`, each with its own virtual environment. Keep
credentials in the ignored local file
`benchmark/llm_config.json`:

```json
{
  "alfworld-eval": {
    "base_url": "https://your-openai-compatible-endpoint/v1",
    "model": "your-model",
    "api_key": "your-key"
  },
  "searchqa-eval": {
    "base_url": "https://your-openai-compatible-endpoint/v1",
    "model": "your-model",
    "api_key": "your-key"
  }
}
```

## Quick checks

Run the deterministic tests first:

```bash
PYTHONPATH=. pytest -q controller_v3/tests tests/test_controller_v3_smoke.py
ruff check controller_v3
```

Run a real SearchQA smoke test after configuring an endpoint and data split:

```bash
PYTHONPATH=. python -m controller_v3.real_smoke \
  --limit 2 \
  --out-dir tmp/controller_v3_real_smoke
```

The output contains raw evidence per host and a summary with native update
calls, Controller actions, scores, and token usage.

## Paired experiments

The paired runner persists every task window and resumes from the existing
manifest, Controller state, candidate skill, and token ledger:

```bash
PYTHONPATH=. python -m controller_v3.paired_experiment \
  --method skillopt \
  --condition controller \
  --train-path path/to/train/items.json \
  --heldout-path path/to/val/items.json \
  --out-dir tmp/paired/skillopt/controller \
  --batch-size 4 \
  --api-workers 4
```

Run the matching `original` condition with the same task manifest and model
configuration. The runner writes `progress.jsonl`, `result.json`,
`tokens.json`, `audit.json`, and raw per-task evidence after each window.

```bash
PYTHONPATH=. python -m controller_v3.campaign_audit tmp/paired
```

Token comparisons are usable only when both conditions expose complete usage
records. Missing usage remains explicitly marked in the ledger.

## Official ALFWorld environment

Use the environment from this repository, not a separately implemented game
loop:

```bash
export ALFWORLD_DATA="$PWD/benchmark/alfworld-eval/.data/alfworld"
export ALFWORLD_CONFIG="$PWD/benchmark/alfworld-eval/configs/textworld.yaml"
export ALFWORLD_BENCH_SRC="$PWD/benchmark/alfworld-eval/src"

PYTHONPATH=. benchmark/alfworld-eval/.venv/bin/python \
  -m controller_v3.skillopt_native_alfworld \
  --condition controller \
  --out tmp/skillopt-alfworld/controller \
  --env-workers 4
```

The native SkillOpt path keeps its original reflection, aggregation,
selection, patch, gate, slow-update, and meta-skill operations. Controller V3
only changes their timing. For long runs, use a supervisor, flush evidence
after every unit, and validate the final 134-task test split before
interpreting quality or cost.

## Reproducibility rules

- Declare the primary metric before looking at test results.
- Keep train, validation, and test task IDs separate and verify paired IDs.
- Record raw task-level evidence, not only aggregate scores.
- Treat environment or API failures as infrastructure evidence; do not score
  them as model failures.
- Preserve cumulative token totals across resume and disclose unknown usage.
- Never commit `benchmark/llm_config.json` or downloaded benchmark data.

## License and upstream code

Controller V3 code is released for research use. Benchmark environments and
upstream methods retain their own licenses. Consult each upstream repository
before redistributing its source or data.
