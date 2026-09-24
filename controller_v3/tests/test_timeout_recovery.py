import json
from concurrent.futures import Future

from controller_v3.alfworld_bridges import ALFWorldBaseBridge
from controller_v3.llm import build_llm
from controller_v3.usage import LedgerLLM, TokenLedger


def test_cached_successes_skipped_and_failed_attempt_usage_retained(
    tmp_path, monkeypatch
):
    import controller_v3.alfworld_bridges as module
    import controller_v3.alfworld_worker as worker

    class Pool:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, fn, job):
            f = Future()
            f.set_result(fn(job))
            return f

    monkeypatch.setattr(module, "ProcessPoolExecutor", Pool)
    calls = []
    fail = True

    def job(args):
        item = args[0]
        calls.append(item["id"])
        ledger = TokenLedger(condition="original", method="gepa")
        ledger.add({"total_tokens": 10})
        ok = not (item["id"] == "bad" and fail)
        if not ok:
            ledger.mark_untracked("api", "timeout")
        return {"id": item["id"], "execution_ok": ok}, ledger.to_dict()

    monkeypatch.setattr(worker, "run_episode_job", job)
    bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
    bridge.llm = LedgerLLM(
        build_llm("alfworld-eval"), TokenLedger(condition="original", method="gepa")
    )
    bridge.benchmark_env = True
    bridge.env_batch_size = 1
    bridge.max_api_workers = 128
    # Keep this cache accounting test focused on resume behavior; retry policy
    # is exercised by the real rollout smoke and can be disabled here.
    bridge.rollout_retries = 0
    bridge.evidence_dir = tmp_path
    bridge.defer_execution_errors = True
    items = [{"id": "good"}, {"id": "bad"}]
    bridge._rollout(items, "skill")
    assert (tmp_path / "episode_failures").exists()
    fail = False
    bridge.rollout_call_index = 0
    bridge.llm.client.timeout = 300
    bridge.llm.client.retries = 4
    bridge.llm.client.retry_backoff = 2
    bridge.llm.ledger = TokenLedger.from_dict(
        json.loads((tmp_path / "tokens.json").read_text())
    )
    assert all(r["execution_ok"] for r in bridge._rollout(items, "skill"))
    assert calls == ["good", "bad", "bad"]
    assert bridge.llm.ledger.summary()["total_tokens"] == 30
    assert not bridge.llm.ledger.summary()["cost_usable"]
    before = bridge.llm.ledger.to_dict()
    bridge.rollout_call_index = 0
    bridge._rollout(items, "skill")
    assert bridge.llm.ledger.to_dict() == before


def test_timeout_backoff_and_unknown_usage_on_successful_retry(monkeypatch):
    import searchqa_eval.agent as module

    delays = []
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"total_tokens": 5},
                }
            ).encode()

    def request(*args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) < 3:
            raise TimeoutError("read timed out")
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", request)
    monkeypatch.setattr(module.time, "sleep", delays.append)
    client = module.OpenAIChatAgent(
        base_url="https://example.invalid",
        api_key="test",
        model="test",
        timeout=300,
        retries=4,
        retry_backoff=2,
    )
    ledger = TokenLedger(condition="test", method="test")
    assert LedgerLLM(client, ledger).respond("s", "u")[0] == "ok"
    assert calls == [300, 300, 300] and delays == [2, 4]
    assert ledger.summary()["untracked_calls"] == 2
