#!/usr/bin/env bash
set -euo pipefail

# Run this script from the tb21 bundle (any machine with the vendor/ tree and a
# venv from bootstrap.sh). It only keeps the Harbor process alive; E2B owns the
# task sandbox and its persistent snapshot.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# All external trees default to locations inside the bundle; override any of
# them with env vars to reuse a live tree elsewhere instead.
SKILL_ROOT="${TBENCH_TB21_TENCENT_SKILL_ROOT:-${SCRIPT_DIR}/vendor/tb21-tencent-skill}"

# Load credentials into this process only. The file is never copied to the
# sandbox or interpolated into the generated Harbor configuration.
ENV_FILE="${TBENCH_TENCENT_ENV_FILE:-${SCRIPT_DIR}/secrets.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

: "${TBENCH_VENV_DIR:=${SCRIPT_DIR}/.venv}"
: "${HARBOR_BIN:=${TBENCH_VENV_DIR}/bin/harbor}"
: "${PYTHON_BIN:=${TBENCH_VENV_DIR}/bin/python}"
: "${TENCENT_ADAPTER_PYTHON:=${SCRIPT_DIR}/vendor/framework-python}"
: "${DATASET_PATH:=${SCRIPT_DIR}/vendor/tasks}"
: "${TBENCH_EVAL_MODE:=bare}"
# Only read when TBENCH_EVAL_MODE=skills; skill packs are not vendored.
: "${TBENCH_SKILL_ROOT:=${SCRIPT_DIR}/vendor/skills}"
: "${TBENCH_RUN_MODE:=smoke}"
: "${TBENCH_N_ATTEMPTS:=1}"
TBENCH_N_CONCURRENT_EXPLICIT=0
if [[ "${TBENCH_N_CONCURRENT+x}" == "x" ]]; then
  TBENCH_N_CONCURRENT_EXPLICIT=1
fi
: "${TBENCH_N_CONCURRENT:=1}"
: "${TBENCH_MAX_TRIAL_RETRIES:=1}"
: "${TBENCH_VERIFIER_MULTIPLIER:=2}"
: "${TBENCH_SETUP_MULTIPLIER:=3}"
: "${TBENCH_VERIFIER_OVERRIDE:=null}"
: "${TBENCH_VPC_DNS:=}"
: "${TBENCH_APT_INTRANET_MIRROR:=0}"
: "${TBENCH_APT_SNAPSHOT_BULLSEYE:=0}"
REASONING_EFFORT_LINE=""
SANDBOX_ENV_BLOCK=""
if [[ -n "${TBENCH_PYPI_MIRROR:-}" ]]; then
  SANDBOX_ENV_BLOCK="  env:
    PIP_INDEX_URL: \"${TBENCH_PYPI_MIRROR}\"
    UV_INDEX_URL: \"${TBENCH_PYPI_MIRROR}\""
fi
if [[ -n "${TBENCH_REASONING_EFFORT:-}" ]]; then
  REASONING_EFFORT_LINE="          reasoning_effort: ${TBENCH_REASONING_EFFORT}"
fi
: "${TASK_NAME:=fix-git}"
: "${TBENCH_TASK_NAMES:=}"
: "${RUN_ID:=tb21_tencent_${TBENCH_RUN_MODE}_$(date +%Y%m%d_%H%M%S)}"
: "${MODEL_API_BASE:=https://llm-center.modelbest.co/v1}"
: "${MODEL_NAME:=qwen3.6-flash-distill}"
: "${E2B_DOMAIN:=ap-beijing.tencentags.com}"
: "${SNAPSHOT_RETRIES:=3}"
# Task sandboxes are ephemeral; only the experiment's relay sandbox persists.
# Keep trajectories, logs, and verifier artifacts on the host for audit.
: "${TBENCH_PERSIST_SANDBOXES:=0}"
: "${TBENCH_E2B_START_CONCURRENCY:=4}"
: "${TBENCH_E2B_RPC_CONCURRENCY:=12}"
: "${TBENCH_FAIL_FAST_CONNECTION_ERRORS:=0}"
: "${DRY_RUN:=0}"

case "${TBENCH_RUN_MODE}" in
  smoke|full|selected) ;;
  *) printf 'TBENCH_RUN_MODE must be smoke, selected, or full\n' >&2; exit 2 ;;
esac

case "${TBENCH_EVAL_MODE}" in
  bare)
    : "${JOBS_DIR:=${SCRIPT_DIR}/jobs/tb21_tencent_smoke}"
    : "${RETRY_ARCHIVE_ROOT:=${SCRIPT_DIR}/jobs/tb21_tencent_retry_archives}"
    : "${E2B_ENVIRONMENT_IMPORT:=tencent_vpc_dns_env:TencentVpcDnsE2BEnvironment}"
    : "${AGENT_IMPORT:=tencent_sandbox_terminus:TencentSandboxTerminus2}"
    SKILL_AGENT_KWARGS=""
    SKILL_ENV_KWARGS=""
    ;;
  skills)
    : "${JOBS_DIR:=${SCRIPT_DIR}/jobs/tb21_tencent_skill_eval}"
    : "${RETRY_ARCHIVE_ROOT:=${SCRIPT_DIR}/jobs/tb21_tencent_skill_retry_archives}"
    : "${E2B_ENVIRONMENT_IMPORT:=tencent_tb2_skill_env:TencentTaskSkillE2BEnvironment}"
    : "${AGENT_IMPORT:=tencent_sandbox_terminus:TencentSkillTerminus2}"
    if [[ ! -f "${TBENCH_SKILL_ROOT}/${TASK_NAME}/SKILL.md" && "${TBENCH_RUN_MODE}" == "smoke" ]]; then
      printf 'task skill is missing: %s/%s/SKILL.md\n' "${TBENCH_SKILL_ROOT}" "${TASK_NAME}" >&2
      exit 2
    fi
    SKILL_AGENT_KWARGS='      skills_dir: "/opt/openclaw-skills"'
    SKILL_ENV_KWARGS="    skill_root: \"${TBENCH_SKILL_ROOT}\""
    ;;
  *) printf 'TBENCH_EVAL_MODE must be bare or skills\n' >&2; exit 2 ;;
esac

if [[ "${TBENCH_EVAL_MODE}" == "skills" && "${TBENCH_RUN_MODE}" == "full" && "${TBENCH_N_CONCURRENT_EXPLICIT}" == "0" ]]; then
  TBENCH_N_CONCURRENT=100
fi

for value in "${TBENCH_N_ATTEMPTS}" "${TBENCH_N_CONCURRENT}"; do
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    printf 'attempts and concurrency must be positive integers\n' >&2
    exit 2
  fi
done
if [[ ! "${TBENCH_MAX_TRIAL_RETRIES}" =~ ^[0-9]+$ ]]; then
  printf 'TBENCH_MAX_TRIAL_RETRIES must be a non-negative integer\n' >&2
  exit 2
fi
if [[ "${TBENCH_PERSIST_SANDBOXES}" != "0" && "${TBENCH_PERSIST_SANDBOXES}" != "1" ]]; then
  printf 'TBENCH_PERSIST_SANDBOXES must be 0 or 1\n' >&2
  exit 2
fi
if [[ ! "${TBENCH_E2B_START_CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'TBENCH_E2B_START_CONCURRENCY must be a positive integer\n' >&2
  exit 2
fi
if [[ ! "${TBENCH_E2B_RPC_CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
  printf 'TBENCH_E2B_RPC_CONCURRENCY must be a positive integer\n' >&2
  exit 2
fi
if [[ "${TBENCH_FAIL_FAST_CONNECTION_ERRORS}" != "0" && "${TBENCH_FAIL_FAST_CONNECTION_ERRORS}" != "1" ]]; then
  printf 'TBENCH_FAIL_FAST_CONNECTION_ERRORS must be 0 or 1\n' >&2
  exit 2
fi

if [[ -z "${OPENAI_API_KEY:-}" && "${DRY_RUN}" != "1" ]]; then
  printf 'OPENAI_API_KEY must be loaded in the live shell\n' >&2
  exit 2
fi
if [[ -z "${E2B_API_KEY:-}" && "${DRY_RUN}" != "1" ]]; then
  printf 'E2B_API_KEY must be loaded in the live shell\n' >&2
  exit 2
fi

if [[ "${E2B_API_KEY:-}" == ark_* ]]; then
  export E2B_VALIDATE_API_KEY=false
fi

if [[ ! -f "${TENCENT_ADAPTER_PYTHON}/harbor_e2b_modelbest/__init__.py" ]]; then
  printf 'Tencent enterprise Harbor adapter not found under %s\n' "${TENCENT_ADAPTER_PYTHON}" >&2
  exit 2
fi

export PYTHONPATH="${SCRIPT_DIR}/python:${SKILL_ROOT}/python:${TENCENT_ADAPTER_PYTHON}${PYTHONPATH:+:${PYTHONPATH}}"
export TBENCH_VPC_DNS TBENCH_APT_INTRANET_MIRROR TBENCH_APT_SNAPSHOT_BULLSEYE
export E2B_DOMAIN SNAPSHOT_RETRIES TBENCH_EVAL_MODE TBENCH_SKILL_ROOT
export TBENCH_PERSIST_SANDBOXES TBENCH_E2B_START_CONCURRENCY TBENCH_E2B_RPC_CONCURRENCY
export TBENCH_FAIL_FAST_CONNECTION_ERRORS

CONFIG_DIR="${JOBS_DIR%/}/../configs"
CONFIG_PATH="${CONFIG_DIR}/${RUN_ID}.yaml"
mkdir -p "${CONFIG_DIR}"

if [[ "${TBENCH_RUN_MODE}" == "smoke" ]]; then
  TASK_FILTER=$(printf '    task_names:\n      - "%s"\n' "${TASK_NAME}")
elif [[ "${TBENCH_RUN_MODE}" == "selected" ]]; then
  if [[ -z "${TBENCH_TASK_NAMES}" ]]; then
    printf 'TBENCH_TASK_NAMES is required for selected mode\n' >&2
    exit 2
  fi
  TASK_FILTER="    task_names:"
  read -r -a selected_tasks <<< "${TBENCH_TASK_NAMES}"
  for task_name in "${selected_tasks[@]}"; do
    TASK_FILTER+=$'\n      - "'"${task_name}"'"'
  done
else
  TASK_FILTER=""
fi

cat > "${CONFIG_PATH}" <<YAML
job_name: "${RUN_ID}"
jobs_dir: "${JOBS_DIR}"
n_attempts: ${TBENCH_N_ATTEMPTS}
verifier_timeout_multiplier: ${TBENCH_VERIFIER_MULTIPLIER}
agent_setup_timeout_multiplier: ${TBENCH_SETUP_MULTIPLIER}
verifier:
  override_timeout_sec: ${TBENCH_VERIFIER_OVERRIDE}
orchestrator:
  type: local
  n_concurrent_trials: ${TBENCH_N_CONCURRENT}
  retry:
    max_retries: ${TBENCH_MAX_TRIAL_RETRIES}
    include_exceptions:
      - AgentSetupTimeoutError
      - SandboxException
      - AddTestsDirError
    exclude_exceptions: []
    wait_multiplier: 2
    min_wait_sec: 5
    max_wait_sec: 60
agents:
  - import_path: "${AGENT_IMPORT}"
    model_name: "openai/${MODEL_NAME}"
    override_timeout_sec: 7200
    kwargs:
      api_base: "${MODEL_API_BASE}"
      interleaved_thinking: true
      store_all_messages: true
${SKILL_AGENT_KWARGS}
      trajectory_config:
        raw_content: false
        linear_history: false
      llm_call_kwargs:
        top_p: 0.95
        max_tokens: 65536
        extra_body:
          top_k: 20
          enable_thinking: true
${REASONING_EFFORT_LINE}
          chat_template_kwargs:
            preserve_thinking: true
environment:
  import_path: "${E2B_ENVIRONMENT_IMPORT}"
  delete: true
${SANDBOX_ENV_BLOCK}
  kwargs:
    snapshot_retries: ${SNAPSHOT_RETRIES}
${SKILL_ENV_KWARGS}
datasets:
  - path: "${DATASET_PATH}"
${TASK_FILTER}
YAML

if [[ "${DRY_RUN}" == "1" ]]; then
  "${PYTHON_BIN}" - "${CONFIG_PATH}" <<'PY'
from pathlib import Path
import os
import sys
import yaml
from harbor.models.job.config import JobConfig

path = Path(sys.argv[1])
config = yaml.safe_load(path.read_text(encoding="utf-8"))
validated = JobConfig.model_validate(config)
task_count = len(validated.datasets[0].get_task_configs())
eval_mode = os.environ["TBENCH_EVAL_MODE"]
print(f"run_mode={'full' if not validated.datasets[0].task_names else 'selected'}")
print(f"eval_mode={eval_mode}")
print(f"tasks={task_count}")
print(f"n_attempts={validated.n_attempts}")
print(f"formal_trials={task_count * validated.n_attempts}")
print(f"n_concurrent={validated.orchestrator.n_concurrent_trials}")
print(f"max_trial_retries={validated.orchestrator.retry.max_retries}")
print(f"persist_sandboxes={os.environ['TBENCH_PERSIST_SANDBOXES']}")
print(f"e2b_start_concurrency={os.environ['TBENCH_E2B_START_CONCURRENCY']}")
print(f"e2b_rpc_concurrency={os.environ['TBENCH_E2B_RPC_CONCURRENCY']}")
print(f"fail_fast_connection_errors={os.environ['TBENCH_FAIL_FAST_CONNECTION_ERRORS']}")
print(f"task_filter={bool(validated.datasets[0].task_names)}")
if eval_mode == "skills":
    skill_root = Path(os.environ["TBENCH_SKILL_ROOT"])
    skill_directory_overrides = {"install-windows-3.11": "install-windows-3-11"}
    dataset_root = Path(config["datasets"][0]["path"])
    selected_names = validated.datasets[0].task_names
    task_names = selected_names or sorted(
        path.name for path in dataset_root.iterdir() if path.is_dir()
    )
    missing = [
        name for name in task_names
        if not (skill_root / skill_directory_overrides.get(name, name) / "SKILL.md").is_file()
    ]
    print(f"skill_root={skill_root}")
    print(f"task_skills={len(task_names)}")
    print(f"missing_task_skills={len(missing)}")
    if missing:
        raise SystemExit(f"missing task skills: {', '.join(missing)}")
print(f"validated_config={path}")
PY
  exit 0
fi

mkdir -p "${JOBS_DIR}"
mkdir -p "${RETRY_ARCHIVE_ROOT}"
RUNNER_ARGS=()
if [[ "${TBENCH_EVAL_MODE}" == "skills" && ( "${TBENCH_RUN_MODE}" == "full" || "${TBENCH_ENABLE_FAIL_FAST:-0}" == "1" ) ]]; then
  RUNNER_ARGS+=(--fail-fast)
fi
exec "${PYTHON_BIN}" "${SKILL_ROOT}/python/run_tencent_job.py" \
  --config "${CONFIG_PATH}" \
  --retry-archive-root "${RETRY_ARCHIVE_ROOT}" \
  "${RUNNER_ARGS[@]}"
