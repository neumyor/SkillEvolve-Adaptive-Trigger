"""Spawn-safe ALFWorld jobs: only plain configuration and results cross processes."""
import os


def run_episode_job(job):
    from .alfworld_bridges import ALFWorldBaseBridge
    from .llm import OpenAIChatAgent
    from .usage import LedgerLLM, TokenLedger

    item, skill, config, condition, method, max_steps = job
    ledger = TokenLedger(condition=condition, method=method)
    # Do not import/configure any host optimizer in a rollout process.
    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.llm = LedgerLLM(OpenAIChatAgent(**config), ledger)
    bridge.benchmark_env = True
    bridge.max_steps = max_steps
    rows = bridge._rollout_chunk([item], skill)
    rows[0]['worker_pid'] = os.getpid()
    return rows[0], ledger.to_dict()
