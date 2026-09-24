import json
from pathlib import Path

import pytest

from controller_v3.audit import audit_run
from controller_v3.validity import RolloutInfrastructureError, require_valid_rows


def test_execution_errors_are_not_model_failures(tmp_path):
    require_valid_rows([{'id': 'hard-task', 'hard': 0, 'n_turns': 50, 'fail_reason': 'environment_done'}])
    for row in [
        {'id': 'env', 'hard': 0, 'fail_reason': 'rollout error: IndexError: pop from empty list'},
        {'id': 'api', 'hard': 0, 'agent_ok': False},
        {'id': 'env', 'hard': None, 'execution_ok': False},
    ]:
        with pytest.raises(RolloutInfrastructureError):
            require_valid_rows([row], tmp_path)
        assert json.loads((tmp_path / 'execution_failure.json').read_text())['failures'] == [row]


def test_audit_detects_heldout_errors_even_with_complete_ids(tmp_path):
    (tmp_path / 'progress.jsonl').write_text(json.dumps({'task_id': 'train', 'row': {'hard': 1}})+'\n')
    (tmp_path / 'heldout.json').write_text(json.dumps({'rows': [{'id': 'test', 'agent_ok': False, 'hard': 0}]}))
    assert audit_run(tmp_path)['quality_usable'] is False


def test_searchqa_error_stops_before_decision(tmp_path):
    from controller_v3.native_bridges import BaseNativeBridge
    from controller_v3.usage import TokenLedger
    from types import SimpleNamespace
    bridge = BaseNativeBridge(SimpleNamespace(ledger=TokenLedger(condition='original', method='test')))
    bridge.evidence_dir = tmp_path
    with pytest.raises(RolloutInfrastructureError):
        bridge._parallel_rollout([{'id': 'a'}], lambda item: {'id': item['id'], 'agent_ok': False})
    assert (tmp_path / 'tokens.json').exists()


def environment_probe(gamefile):
    from alfworld_eval.env import AlfworldTextEnv, split_for_gamefile
    config = Path(__file__).resolve().parents[2] / 'benchmark/alfworld-eval/configs/textworld.yaml'
    with AlfworldTextEnv(config_path=config, split=split_for_gamefile(gamefile), gamefiles=[gamefile]) as env:
        obs = env.reset()
        stepped = env.step('look')
        return obs.text, obs.admissible_commands, stepped.observation.text


@pytest.mark.skipif(__import__('os').environ.get('RUN_ALFWORLD_INTEGRATION') != '1', reason='requires benchmark venv and real ALFWorld data')
def test_real_environment_spawn_matches_serial():
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    root = Path(__file__).resolve().parents[2]
    items = json.loads((root / 'repos/pulled/SkillOpt/data/alfworld_path_split/val/items.json').read_text())[:8]
    games = [row['gamefile'] for row in items]
    serial = [environment_probe(game) for game in games]
    with ProcessPoolExecutor(max_workers=8, mp_context=multiprocessing.get_context('spawn')) as pool:
        parallel = list(pool.map(environment_probe, games))
        repeated = list(pool.map(environment_probe, games))
    assert serial == parallel == repeated


def test_stale_preflight_cannot_launch(tmp_path):
    from controller_v3.preflight import validate_report
    p = tmp_path / 'report.json'
    p.write_text(json.dumps({'fingerprint': 'old'}))
    with pytest.raises(ValueError, match='stale'):
        validate_report(p, ['alfworld'], 512)


def test_full_run_refuses_without_preflight(tmp_path, monkeypatch):
    import sys
    from controller_v3 import full_campaign
    monkeypatch.setattr(sys, 'argv', ['full_campaign', '--domains', 'alfworld', '--out-root', str(tmp_path)])
    with pytest.raises(SystemExit):
        full_campaign.main()
    assert not (tmp_path / 'status.json').exists()


def test_gepa_tuple_rows_preserve_execution_checks(tmp_path):
    from controller_v3.native_bridges import BaseNativeBridge
    from controller_v3.usage import TokenLedger
    from types import SimpleNamespace
    bridge = BaseNativeBridge(SimpleNamespace(ledger=TokenLedger(condition='original', method='gepa')))
    bridge.evidence_dir = tmp_path
    valid = [(0, {'row': {'id': 'a', 'agent_ok': True, 'hard': 0}})]
    assert bridge._checked_rows(valid) == valid
    with pytest.raises(RolloutInfrastructureError):
        bridge._checked_rows([(0, {'row': {'id': 'b', 'agent_ok': False}})])


def test_preflight_rejects_different_generation_settings(tmp_path):
    from controller_v3.preflight import fingerprint, validate_report
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'fingerprint': fingerprint(), 'domains': {'alfworld': {
        'status': 'passed', 'max_tokens': 512, 'max_steps': 50,
        'llm_name': 'alfworld-eval', 'enable_thinking': False,
    }}}))
    validate_report(path, ['alfworld'], 512)
    for kwargs in ({'enable_thinking': True}, {'max_steps': 10}, {'llm_names': {'alfworld': 'other'}}):
        with pytest.raises(ValueError, match='matching'):
            validate_report(path, ['alfworld'], 512, **kwargs)


def test_broken_update_cannot_look_like_candidate_rejection(tmp_path):
    from controller_v3.native_bridges import BaseNativeBridge
    from controller_v3.usage import TokenLedger
    from types import SimpleNamespace
    bridge = BaseNativeBridge(SimpleNamespace(ledger=TokenLedger(condition='original', method='test')))
    bridge.evidence_dir = tmp_path
    with pytest.raises(RolloutInfrastructureError):
        bridge._raise_update_error(RuntimeError('optimizer backend unavailable'))
    assert 'optimizer backend unavailable' in (tmp_path / 'execution_failure.json').read_text()


def test_selected_campaign_methods_and_128_limit(tmp_path, monkeypatch, capsys):
    import sys
    from controller_v3 import full_campaign
    monkeypatch.setattr(sys, 'argv', ['full_campaign', '--domains', 'alfworld',
        '--methods', 'evoskill', 'gepa', '--api-workers', '128', '--max-active-settings', '4',
        '--out-root', str(tmp_path), '--dry-run'])
    assert full_campaign.main() == 0
    commands = capsys.readouterr().out.strip().splitlines()
    assert len(commands) == 4
    assert all('--api-workers 128' in line for line in commands)
    manifest = json.loads((tmp_path / 'campaign_manifest.json').read_text())
    assert manifest['methods'] == ['evoskill', 'gepa']
    assert manifest['total_settings'] == 4
    assert manifest['maximum_total_api_workers'] == 512


def test_alfworld_gepa_budget_reaches_proposal(monkeypatch):
    from controller_v3 import alfworld_bridges as module
    bridge = module.ALFWorldGEPABridge.__new__(module.ALFWorldGEPABridge)
    bridge.llm = object()
    calls = []
    def propose(*args, **kwargs):
        calls.append(kwargs.get('stage'))
        return {'candidate': 'improved'}, {}, '{}'
    monkeypatch.setattr(module, 'call_json', propose)
    bridge.rollout = lambda item, skill: {'id': item['id'], 'score': int('improved' in skill), 'trajectory': 'task evidence'}
    result = bridge._run_update([{'id': 'a', 'score': 0}], [{'id': 'a'}], 'seed')
    assert calls == ['gepa_proposal']
    assert result['accepted'] is True


def test_json_proposal_ignores_reasoning_examples():
    from controller_v3.llm import call_json
    from types import SimpleNamespace
    raw = '<think>Consider {"skill":"draft"}; then choose final JSON.</think>```json\n{"skill":"final"}\n```'
    client = SimpleNamespace(respond=lambda *args, **kwargs: (raw, {'total_tokens': 20}))
    value, usage, evidence = call_json(client, 'system', 'user')
    assert value == {'skill': 'final'}
    assert evidence == raw and usage['total_tokens'] == 20
