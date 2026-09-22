#!/usr/bin/env bash
# OmniBot — Pterodactyl / VPS friendly launcher
# Finds main.py even if the GitHub zip left a nested folder, then runs the bot.
set -euo pipefail

ROOT="${PWD}"

# If main.py is not here, look one level down (new-omni-main/, new-omni/, etc.)
if [[ ! -f "${ROOT}/main.py" ]]; then
  for d in "${ROOT}"/new-omni-main "${ROOT}"/new-omni "${ROOT}"/new-omni-* "${ROOT}"/*/; do
    if [[ -f "${d}/main.py" ]]; then
      echo "[start.sh] Found project in ${d} — using that as root"
      cd "${d}"
      ROOT="$(pwd)"
      break
    fi
  done
fi

if [[ ! -f "${ROOT}/main.py" ]]; then
  echo "[start.sh] ERROR: main.py not found under ${PWD}"
  echo "[start.sh] Upload the full repo so main.py and omnibot/ sit together."
  ls -la "${PWD}" || true
  exit 1
fi

if [[ ! -d "${ROOT}/omnibot" ]]; then
  echo "[start.sh] ERROR: omnibot/ folder missing next to main.py"
  ls -la "${ROOT}" || true
  exit 1
fi

cd "${ROOT}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Prefer system python; fall back to common paths
PY="${PYTHON:-python3}"
command -v "${PY}" >/dev/null 2>&1 || PY="python"
command -v "${PY}" >/dev/null 2>&1 || PY="/usr/local/bin/python"

echo "[start.sh] cwd=${ROOT}"
echo "[start.sh] python=$(command -v "${PY}" || echo missing)"

if [[ -f requirements.txt ]]; then
  "${PY}" -m pip install -U --prefix .local -r requirements.txt 2>/dev/null \
    || "${PY}" -m pip install -U -r requirements.txt 2>/dev/null \
    || true
  export PATH="${ROOT}/.local/bin:${PATH:-}"
  export PYTHONPATH="${ROOT}/.local/lib/python*/site-packages:${PYTHONPATH}"
  # Expand glob for site-packages if present
  for sp in "${ROOT}"/.local/lib/python*/site-packages; do
    [[ -d "${sp}" ]] && export PYTHONPATH="${sp}:${PYTHONPATH}"
  done
fi

exec "${PY}" main.py
