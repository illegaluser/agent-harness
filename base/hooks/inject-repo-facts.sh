#!/usr/bin/env bash
# EN: SessionStart/SubagentStart hook that injects the repo-facts sheet
#     (.claude/agents/_repo-facts.md) into the new session's context as
#     additionalContext, so port/launcher/topology/version-pin facts survive
#     even when an agent's own self-reported "REPO_FACTS_LOADED" marker
#     (scout.md S0 / architect.md A0 / maker.md M0 / critic.md C0) is
#     skipped or forgotten. Wired from .claude/settings.json
#     hooks.SessionStart and hooks.SubagentStart with the same command — the
#     hookEventName in the output simply mirrors whichever event triggered
#     it. It is read-only and never blocks anything: if the facts file is
#     missing it exits 0 with no output, matching the "self-reported marker
#     stays the primary source of truth, this hook is a mechanical backup"
#     design decided for this hardening pass.
# KO: SessionStart/SubagentStart 훅으로, _repo-facts.md 전문을 새 세션의
#     additionalContext 로 주입해 에이전트의 자기신고 "REPO_FACTS_LOADED"
#     마커(scout.md S0 / architect.md A0 / maker.md M0 / critic.md C0)가
#     생략되거나 누락돼도 포트/런처/토폴로지/버전핀 사실이 살아남게 한다.
#     .claude/settings.json 의 hooks.SessionStart 와 hooks.SubagentStart 가
#     같은 커맨드로 이 스크립트를 호출하며, 출력의 hookEventName은 실제 발동한
#     이벤트를 그대로 반영한다. read-only 이며 절대 무언가를 차단하지 않는다 —
#     사실 시트가 없으면 조용히 exit 0 (자기신고 마커가 여전히 1차 진실 소스,
#     이 훅은 기계적 백업이라는 이번 하네스 강화의 설계와 일치).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
FACTS_FILE="$REPO_ROOT/.claude/agents/_repo-facts.md"

# Self-degrade: no facts file (e.g. a project without this repo's agent
# setup) → nothing to inject, allow session start silently and cheaply.
# 자기-강등: 사실 시트가 없으면(예: 이 에이전트 세팅이 없는 프로젝트) 주입할
# 게 없다 — 조용히, 저비용으로 세션 시작을 허용한다.
if [[ ! -f "$FACTS_FILE" ]]; then
  exit 0
fi

# Read the hook's stdin (Claude Code pipes a JSON payload describing the
# triggering event) once into a variable so it can be handed to python3 as
# an argv string rather than re-read from a pipe.
# 훅의 stdin(Claude Code 가 트리거 이벤트를 담아 파이프하는 JSON)을 한 번만
# 읽어 변수에 담고, 파이프 재읽기 대신 python3 에 argv 문자열로 넘긴다.
INPUT_JSON="$(cat)"

python3 - "$FACTS_FILE" "$INPUT_JSON" <<'PYEOF'
import json
import sys

facts_path, input_json = sys.argv[1], sys.argv[2]

try:
    hook_input = json.loads(input_json) if input_json.strip() else {}
except json.JSONDecodeError:
    hook_input = {}

# Whichever event fired (SessionStart or SubagentStart) is reported back so
# the output stays honest about what triggered the injection.
event_name = hook_input.get("hook_event_name", "SessionStart")

with open(facts_path, "r", encoding="utf-8") as f:
    facts_text = f.read()

output = {
    "hookSpecificOutput": {
        "hookEventName": event_name,
        "additionalContext": facts_text,
    }
}
print(json.dumps(output))
PYEOF
