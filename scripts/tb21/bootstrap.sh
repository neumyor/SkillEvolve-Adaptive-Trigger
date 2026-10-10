#!/usr/bin/env bash
# Recreate the Harbor venv the runner expects (layer 3).  Run once per machine:
#   ./bootstrap.sh                     # venv at <bundle>/.venv
#   TBENCH_VENV_DIR=/somewhere ./.     # or elsewhere
# Requires python3.12 on PATH (the original node29 venv is 3.12).
set -euo pipefail

BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="${TBENCH_VENV_DIR:-${BUNDLE}/.venv}"

if ! command -v python3.12 >/dev/null 2>&1; then
  printf 'python3.12 not found on PATH (the original venv is 3.12)\n' >&2
  exit 2
fi

python3.12 -m venv "${VENV}"
"${VENV}/bin/pip" install -r "${BUNDLE}/vendor/requirements.txt"
# harbor 0.2.0 is NOT on PyPI: installed from the vendored source tree
# (claw-harbor, main @ 37a234f8de64243e675254d14264c39363692483).
"${VENV}/bin/pip" install "${BUNDLE}/vendor/claw-harbor"
"${VENV}/bin/harbor" --version
printf 'venv ready: %s\n' "${VENV}"
