#!/usr/bin/env bash
# EN: Runs this project's declared verify_commands and writes a receipt the
#     close gate (gate.py's receipt_ok()) can read in lieu of a critic
#     verdict — for changes with no UI or API to run an e2e test against
#     (the harness itself, docs, scripts). No jq dependency: unlike
#     install.sh, this must run standalone at any installed project.
# KO: 이 프로젝트가 선언한 verify_commands 를 돌리고, close 게이트
#     (gate.py 의 receipt_ok())가 critic 판정 대신 읽을 영수증을 남긴다 —
#     화면·API 가 없는 변경(하네스 자체·문서·스크립트)을 위한 것이다. jq 의존
#     없음 — install.sh 와 달리 설치된 어떤 프로젝트에서도 단독으로 돌아야 한다.
set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -n "$ROOT" ] || ROOT="$(pwd)"

CONFIG="$ROOT/.claude/harness.json"
STATE_DIR="$ROOT/.claude/state"
RECEIPT="$STATE_DIR/verify-receipt.json"

commands="$(python3 -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except (OSError, ValueError):
    cfg = {}
for cmd in cfg.get("verify_commands", []):
    print(cmd)
' "$CONFIG" 2>/dev/null)"

if [ -z "$commands" ]; then
    echo "[verify.sh] verify_commands 가 비어 있다 — $CONFIG 에 선언하라." >&2
    exit 2
fi

mkdir -p "$STATE_DIR"

all_ok=true
results=""
sep=""
while IFS= read -r cmd; do
    [ -n "$cmd" ] || continue
    ( cd "$ROOT" && bash -c "$cmd" )
    code=$?
    [ "$code" -eq 0 ] || all_ok=false
    esc_cmd="$(printf '%s' "$cmd" | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))')"
    results="${results}${sep}{\"cmd\": ${esc_cmd}, \"exit\": ${code}}"
    sep=","
done <<<"$commands"

ts="$(python3 -c 'import time; print(time.time())')"
printf '{"ts": %s, "commands": [%s], "all_ok": %s}\n' "$ts" "$results" "$all_ok" >"$RECEIPT"

if [ "$all_ok" = "true" ]; then
    exit 0
else
    exit 1
fi
