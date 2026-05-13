#!/usr/bin/env bash
set -euo pipefail

# Verify websocket handshake endpoints return 101 (Switching Protocols).
# Usage:
#   scripts/check_lastmile_ws.sh <base_url> <user_id> <store_subentity_id>
# Example:
#   scripts/check_lastmile_ws.sh https://lastmile.fainzy.tech 37 7

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <base_url> <user_id> <store_subentity_id>" >&2
  exit 2
fi

BASE_URL="${1%/}"
USER_ID="$2"
STORE_ID="$3"

KEY="dGhlIHNhbXBsZSBub25jZQ==" # RFC sample

check_ws() {
  local url="$1"
  local name="$2"
  local out

  out="$(curl -sS -i --http1.1 \
    -H "Connection: Upgrade" \
    -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" \
    -H "Sec-WebSocket-Key: ${KEY}" \
    "${url}" || true)"

  local status_line
  status_line="$(printf '%s\n' "${out}" | head -n 1)"

  if printf '%s\n' "${status_line}" | rg -q " 101 "; then
    echo "[OK] ${name} ${url} -> ${status_line}"
    return 0
  fi

  echo "[FAIL] ${name} ${url} -> ${status_line}" >&2
  printf '%s\n' "${out}" | head -n 20 >&2
  return 1
}

fail=0
check_ws "${BASE_URL}/ws/soc/${USER_ID}/" "user_orders" || fail=1
check_ws "${BASE_URL}/ws/soc/store_${STORE_ID}/" "store_orders" || fail=1
check_ws "${BASE_URL}/ws/soc/store_statistics_${STORE_ID}/" "store_stats" || fail=1

if [[ "${fail}" -ne 0 ]]; then
  echo "One or more websocket handshake checks failed." >&2
  exit 1
fi

echo "All websocket handshake checks returned 101."
