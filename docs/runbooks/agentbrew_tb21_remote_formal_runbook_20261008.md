# AgentBrew TB2.1 remote formal runbook

> **Deprecated protocol (2026-10-26):** 本文档记录旧的 41/20/28 切分。当前 AgentBrew TB2.1 使用 25/64，见 `benchmark/terminalbench-eval/docs/AGENTBREW.md`。

The formal run is hosted at `/home/xinhaidong/agentbrew-tb21` on `10.31.112.40`
and writes to `outputs/agentbrew_tb21_formal_20261008`. It uses the frozen
TB2.1 contract: 41 evolve tasks, then a frozen pool, then 28 test tasks and 28
matched vanilla controls. The student is `qwen3.6-plus-distill`; the teacher is
`deepseek-v4-flash-0731-tencent`.

Use the exact SSH key login configured for this run and inspect exact recorded
PIDs and `run.lock`; do not use `pgrep -f`. A completed `rollout.json` and its
independent evidence audit are immutable. Resume only with the same contract
and `--resume`. Preserve infrastructure failures, pending request records,
unknown usage and raw artifacts. Never retry a valid reward result as if it
were infrastructure failure.

Before any repair, save logs and check path existence, source/config hashes,
task snapshot hashes, duplicate writers and child process identity. Repairs are
limited to transport, dependency, or process failures; method prompts,
budgets, task order, split membership and memory semantics remain fixed.

## Launch and monitoring

SSH independently with:

```sh
ssh -S none -o BatchMode=yes -i /Users/yimingniu/.ssh/id_ed25519 xinhaidong@10.31.112.40
```

The server uses its own `.venv/bin/python`, `.env`, task symlink, harness and
embedding assets. Host paths were resolved and checked on the server; no local
`/Users/...` dependency is carried into its configuration or output artifacts.
The loopback teacher URL `http://127.0.0.1:18132/v1` is a relay owned by the
remote driver; it is not an SSH tunnel. Preserve port 18132 on resume because
the provider URL is part of teacher request signatures.

The detached launch is recorded in `<output>/launch.json`. The first supervisor
PID was 2738702 (session 2738702); the first relay driver PID was 2738718
(session 2738718). Read current pidfiles rather than assuming these remain
valid. The supervisor only waits and records exit status; it does not watch or
restart experiments. **No server watchdog or server cron job is deployed.**
The user explicitly rejected a server watchdog. The Codex thread heartbeat
`agentbrew-tb2-1` is active every two hours and is allowed to repair and resume.
It executes from the local Codex app and needs that host to be available.

For a stopped campaign, the replayable launch command is stored in
`launch.json`. Verify both driver and child are gone and that `run.lock` is
unlocked before replaying it from a remote `subprocess.Popen` with
`start_new_session=True`, `stdin=DEVNULL`, and log-file stdout/stderr. It already
contains `--resume`, `--with-vanilla`, and port 18132. Record every replacement
PID and start time separately; never launch a second writer while a tracked
child is running. Credentials are read from the remote ignored `.env`.

## Evidence and recovery boundaries

Final registered code passed 37 AgentBrew/TB2.1/job-configuration checks locally
and remotely. Broader remote tests additionally failed on uninstalled, unrelated
SkillOpt and Trace2Skill checkouts; this is an AgentBrew environment, not a
working installation of those methods. The 89 task/harness hashes passed.
The completed remote `fix-git` initial rollout passed independent request,
trajectory, checksum and verifier evidence checks (reward 1). The partial
smoke serve was interrupted during transition and is excluded from formal
results; do not claim the whole smoke report completed.

Teacher Draft/Curator schema probes are synthetic health-only requests outside
the scientific run and do not write the pool. Their evidence is in
`teacher_schema_preflight`. Curator JSON schema now publishes the already
enforced append/merge/reject invariants. HTTP 429 retains the original two
attempts and waits 60 seconds between attempts. Neither change adds Ralph
rounds, expands output/context budgets, or changes the method's control flow.
Earlier preflight contracts are archived under `preflight_run_001/002`; only
`run/contract.json` defines the formal campaign.

Inspect `run/brew/*/state.json`, `run/serve/progress.json`,
`run/vanilla/progress.json`, `run/**/physical_*/result.json`, and the durable
teacher `run/brew/**/http_*.json` records. A successful exit must also have
`run/audit.json` with `passed=true` and the full report. Reward=0 is a legitimate
result and must be retained.

When all physical attempts for an unfinished unit have failed with
`infra=true`, the adapter's original per-invocation infrastructure budget can
be exhausted. After diagnosis and repair, archive those *failed-only* physical
directories under that same unit's `infra_recovery/<timestamp>/physical_*`
and record the reason, old paths, request hash and tracked PID in a repair
receipt. Leave completed `rollout.json` and request payloads untouched. This
retains failed result records in the recursive cost scan, while allowing
`--resume` to make a fresh infrastructure attempt at the same logical unit.
First validate any raw result from an interrupted physical attempt: if it is
valid, adopt it instead of retrying. Check that every associated child is dead
and remove only its own leftover E2B sandbox, using the exact trial metadata.

For exhausted teacher HTTP transport attempts, archive *failed retryable* or
lost pending request records under the same draft/curator directory's
`transport_recovery/<timestamp>/http_*.json`, preserving unknown usage and
costs. Never archive successful raw responses or invalid completed content to
silently sample a more favorable answer. Validation errors, missing references,
source/config contract mismatch or inconsistent memory require actual diagnosis,
not blind retries. Do not edit a frozen source contract to conceal a change.
Repair infrastructure outside the frozen method when possible; if implementation
changes are needed, record the old evidence and explain their effect on validity
before applying a reviewed recovery strategy. If safe continuation is impossible,
notify the user promptly with the blocking evidence.

After completion, run the independent audit before quoting scores. Require
41 completed brew states, 28 serve and 28 vanilla results, distinct raw trial
identities, frozen/current pool equality, zero teacher calls during serve,
correct cumulative cost evidence, and the preregistered paired task metric.
Synchronize artifacts locally without secrets, then pause the heartbeat.
