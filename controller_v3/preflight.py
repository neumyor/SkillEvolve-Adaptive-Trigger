"""Small real-rollout acceptance report, bound to the exact code and configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    files = sorted((ROOT / 'controller_v3').rglob('*.py'))
    for domain in ('alfworld', 'searchqa'):
        files += sorted((ROOT / f'benchmark/{domain}-eval/src').rglob('*.py'))
    files += [ROOT / 'benchmark/alfworld-eval/configs/textworld.yaml', ROOT / 'benchmark/llm_config.json']
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_report(path, domains, max_tokens, *, llm_names=None, enable_thinking=False, max_steps=50):
    report = json.loads(Path(path).read_text())
    if report.get('fingerprint') != fingerprint():
        raise ValueError('Preflight is stale: code/config changed; run controller_v3.preflight again')
    for domain in domains:
        result = report.get('domains', {}).get(domain, {})
        if result.get('status') != 'passed' or result.get('max_tokens') != max_tokens or result.get('llm_name') != (llm_names or {}).get(domain, f'{domain}-eval') or result.get('enable_thinking') != enable_thinking or result.get('max_steps') != max_steps:
            raise ValueError(f'Missing matching real-rollout preflight for {domain}')
    return report


def main():
    from .llm import build_llm
    from .usage import LedgerLLM, TokenLedger
    from .validity import require_valid_rows
    from .native_bridges import _run_searchqa_benchmark
    from .alfworld_bridges import ALFWorldBaseBridge
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--domains', nargs='+', default=['alfworld', 'searchqa'])
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--llm-name-alfworld', default='alfworld-eval')
    parser.add_argument('--llm-name-searchqa', default='searchqa-eval')
    parser.add_argument('--enable-thinking', action='store_true')
    parser.add_argument('--max-steps', type=int, default=50)
    parser.add_argument('--api-timeout', type=float, default=120)
    parser.add_argument('--api-attempts', type=int, default=2)
    parser.add_argument('--retry-backoff', type=float, default=0)
    parser.add_argument('--allow-cost-uncertainty', action='store_true', help='Permit execution-valid recovery checks with explicitly unknown timeout usage')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'fingerprint': fingerprint(), 'domains': {}}
    for domain in args.domains:
        out = args.out / domain
        out.mkdir(exist_ok=True)
        ledger = TokenLedger(condition='preflight', method='shared_rollout')
        llm_name = getattr(args, f'llm_name_{domain}')
        llm = LedgerLLM(build_llm(llm_name, max_tokens=args.max_tokens, enable_thinking=args.enable_thinking), ledger)
        llm.client.timeout = args.api_timeout
        llm.client.retries = args.api_attempts
        llm.client.retry_backoff = args.retry_backoff
        if domain == 'alfworld':
            os.environ.setdefault('ALFWORLD_DATA', str(ROOT / 'benchmark/alfworld-eval/.data/alfworld'))
            items = json.loads((ROOT / 'repos/pulled/SkillOpt/data/alfworld_path_split/val/items.json').read_text())[:2]
            bridge = ALFWorldBaseBridge.__new__(ALFWorldBaseBridge)
            bridge.llm = llm
            bridge.benchmark_env = True
            bridge.env_batch_size = 2
            bridge.max_api_workers = 2
            bridge.max_steps = args.max_steps
            bridge.evidence_dir = out
            rows = bridge._rollout(items, 'Use the observation and choose a valid action to finish the task.')
            before = ledger.summary()
            bridge.rollout_call_index = 0
            resumed = bridge._rollout(items, 'Use the observation and choose a valid action to finish the task.')
            assert rows == resumed and before == ledger.summary(), 'Resume repeated billable calls'
        else:
            items = json.loads((ROOT / 'benchmark/searchqa-eval/data/searchqa_split/val/items.json').read_text())[:2]
            with ThreadPoolExecutor(max_workers=2) as pool:
                rows = list(pool.map(lambda item: _run_searchqa_benchmark(llm, item, 'Answer from context with <answer> tags.'), items))
        require_valid_rows(rows, out)
        assert [row['id'] for row in rows] == [item['id'] for item in items]
        assert ledger.summary()['api_calls'] > 0
        assert ledger.summary()['cost_usable'] or args.allow_cost_uncertainty, 'Execution passed but retry usage is unknown; explicit recovery cost-uncertainty policy required'
        (out / 'rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        ledger.save(out / 'tokens.json')
        report['domains'][domain] = {'status': 'passed', 'tasks': len(rows), 'max_tokens': args.max_tokens, 'llm_name': llm_name, 'enable_thinking': args.enable_thinking, 'max_steps': args.max_steps, 'tokens': ledger.summary(), 'cost_uncertainty_allowed': args.allow_cost_uncertainty, 'warnings': [] if ledger.summary()['cost_usable'] else ['Timeout attempt usage unknown; execution checks passed, exact costs unavailable']}
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))
        print(domain, 'passed', flush=True)


if __name__ == '__main__':
    main()
