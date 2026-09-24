"""Execution failures must never become observations about task difficulty."""
from pathlib import Path
import json


class RolloutInfrastructureError(RuntimeError):
    pass


def invalid_row(row):
    return (row.get('execution_ok') is False or row.get('agent_ok') is False
            or str(row.get('fail_reason', '')).startswith('rollout error:')
            or bool(row.get('api_failures')))


def require_valid_rows(rows, evidence_dir=None):
    failures = [row for row in rows if invalid_row(row)]
    if failures:
        if evidence_dir:
            path = Path(evidence_dir) / 'execution_failure.json'
            path.write_text(json.dumps({'rows': rows, 'failures': failures}, ensure_ascii=False, indent=2))
        raise RolloutInfrastructureError(
            f'{len(failures)}/{len(rows)} rollouts have execution errors; '
            'checkpoint retained, no quality/update decision may use this batch'
        )
