#!/usr/bin/env bash
set -euo pipefail
ENABLEMENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ENABLEMENT_ROOT/.venv/bin/python" "$ENABLEMENT_ROOT/backend/scripts/enablement_environment.py" "${1:-status}"
