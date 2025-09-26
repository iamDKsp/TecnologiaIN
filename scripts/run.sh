#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
cd "${REPO_ROOT}"

echo "Using repo root: ${REPO_ROOT}" >&2
if [[ "${1:-}" != "--skip-install" ]]; then
  echo "Installing dependencies defined in requirements.txt..." >&2
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo "Starting Flask development server..." >&2
exec python -m flask --app webapp.app run
