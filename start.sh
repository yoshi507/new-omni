#!/usr/bin/env bash
# OmniBot launcher — works with flat layout OR GitHub zip nested folder.
set -euo pipefail

cd "${PWD}"

find_root() {
  if [[ -f main.py && -d omnibot ]]; then
    pwd
    return 0
  fi
  for d in new-omni-main new-omni ./*/; do
    if [[ -f "${d}/main.py" && -d "${d}/omnibot" ]]; then
      (cd "${d}" && pwd)
      return 0
    fi
  done
  # Search one level deeper
  for d in ./*/*/; do
    if [[ -f "${d}/main.py" && -d "${d}/omnibot" ]]; then
      (cd "${d}" && pwd)
      return 0
    fi
  done
  return 1
}

ROOT="$(find_root || true)"
if [[ -z "${ROOT}" ]]; then
  echo "[start.sh] ERROR: could not find main.py + omnibot/ under $(pwd)"
  ls -la
  exit 1
fi

cd "${ROOT}"
echo "[start.sh] project root: ${ROOT}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

PY="${PYTHON:-}"
if [[ -z "${PY}" ]]; then
  for c in /usr/local/bin/python python3 python; do
    if command -v "${c}" >/dev/null 2>&1; then
      PY="${c}"
      break
    fi
  done
fi
if [[ -z "${PY}" ]]; then
  echo "[start.sh] ERROR: python not found"
  exit 1
fi

if [[ -f requirements.txt ]]; then
  "${PY}" -m pip install -U --prefix .local -r requirements.txt 2>/dev/null \
    || "${PY}" -m pip install -U -r requirements.txt 2>/dev/null \
    || true
  for sp in "${ROOT}"/.local/lib/python*/site-packages; do
    [[ -d "${sp}" ]] && export PYTHONPATH="${sp}:${PYTHONPATH}"
  done
  export PATH="${ROOT}/.local/bin:${PATH:-}"
fi

exec "${PY}" "${ROOT}/main.py"
