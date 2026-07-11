#!/usr/bin/env bash
# EN: Mechanical lint gate wired to two different Claude Code hook events via
#     a --mode flag: PostToolUse (Write|Edit) calls it with --mode posttool
#     (advisory, never blocks) and Stop/SubagentStop call it with --mode stop
#     (can block, bounded). It lints only files that are currently dirty in
#     the git working tree (never a full-repo sweep) and only two
#     extensions: *.py via `ruff check`, *.md via `markdownlint-cli2` — the
#     same two linter families CLAUDE.md's "Lint 오류 — NON-NEGOTIABLE" rule
#     already requires a human/agent to fix by hand. It self-degrades to a
#     silent pass whenever a linter binary is not on PATH (this repo
#     deliberately does not bundle ruff/markdownlint-cli2 per the "inert
#     gate" decision — see .claude/hooks/README.md) or when there are no
#     dirty matching files. In --mode stop it keeps a small counter file
#     under .claude/state/ so a persistently-broken lint state cannot hang
#     the session forever: it blocks at most 3 consecutive times (a self
#     cap sitting below Claude Code's own hard stop-hook cap) and then lets
#     the session end regardless; the counter resets to 0 the moment lint
#     comes back clean.
# KO: 하나의 --mode 플래그로 서로 다른 두 Claude Code 훅 이벤트에 배선되는
#     기계적 lint 게이트다: PostToolUse(Write|Edit) 는 --mode posttool(참고용,
#     절대 차단 안 함)로, Stop/SubagentStop 은 --mode stop(차단 가능, 유한)으로
#     호출한다. git 워킹트리에서 현재 dirty 한 파일만(전체 저장소 스윕 아님)
#     그리고 두 확장자만 검사한다 — *.py 는 `ruff check`, *.md 는
#     `markdownlint-cli2`. CLAUDE.md의 "Lint 오류 — NON-NEGOTIABLE" 규칙이
#     이미 사람/에이전트에게 수동 처리를 요구하는 바로 그 두 린터 계열이다.
#     린터 바이너리가 PATH 에 없으면(이 저장소는 "inert 게이트" 결정에 따라
#     ruff/markdownlint-cli2 를 의도적으로 번들하지 않는다 — .claude/hooks/README.md
#     참조) 또는 dirty 대상 파일이 없으면 조용히 통과(self-degrade)한다.
#     --mode stop 에서는 .claude/state/ 아래 작은 카운터 파일을 유지해 lint
#     상태가 계속 깨져 있어도 세션이 영원히 멈추지 않게 한다 — 최대 3회
#     연속으로만 차단하고(Claude Code 자체 stop-hook 하드캡보다 낮은 자체
#     상한) 그 이후엔 세션 종료를 허용한다. lint 가 다시 클린해지는 순간
#     카운터는 0으로 리셋된다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
STATE_DIR="$REPO_ROOT/.claude/state"
COUNTER_FILE="$STATE_DIR/lint-stop-block-count"
MAX_BLOCKS=3

MODE="posttool"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

mkdir -p "$STATE_DIR"

# EN: Collects paths (relative to repo root) of *.py and *.md files that are
#     currently dirty (modified/staged/untracked) in the git working tree.
#     Called once at the top of this script; feeds the two lint blocks
#     below. Guards every array expansion behind a length check so it stays
#     safe under `set -u` on macOS's stock bash 3.2 (empty-array expansion
#     is unsafe there), and skips anything that isn't a real readable file
#     (e.g. the composite "old -> new" path git prints for renames).
# KO: git 워킹트리에서 현재 dirty(수정/스테이지/미추적) 상태인 *.py, *.md
#     파일의 경로(저장소 루트 기준 상대경로)를 모은다. 이 스크립트 맨 위에서
#     한 번 호출되며, 아래 두 lint 블록이 그 결과를 소비한다. macOS 기본
#     bash 3.2 에서 빈 배열 확장이 `set -u` 하에 안전하지 않으므로 모든 배열
#     확장을 길이 체크로 감쌌고, 실제 읽을 수 있는 파일이 아닌 것(예: git 이
#     rename 에 출력하는 "old -> new" 합성 경로)은 건너뛴다.
collect_dirty_files() {
  DIRTY_PY=()
  DIRTY_MD=()

  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi

  local line path
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    path="${line:3}"
    [[ -f "$REPO_ROOT/$path" ]] || continue
    case "$path" in
      *.py) DIRTY_PY+=("$path") ;;
      *.md) DIRTY_MD+=("$path") ;;
    esac
  done < <(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)
}

collect_dirty_files

cd "$REPO_ROOT"
LINT_ERRORS=""

if [[ ${#DIRTY_PY[@]} -gt 0 ]] && command -v ruff >/dev/null 2>&1; then
  if ! OUT="$(ruff check "${DIRTY_PY[@]}" 2>&1)"; then
    LINT_ERRORS+="$OUT"$'\n'
  fi
fi

if [[ ${#DIRTY_MD[@]} -gt 0 ]] && command -v markdownlint-cli2 >/dev/null 2>&1; then
  if ! OUT="$(markdownlint-cli2 "${DIRTY_MD[@]}" 2>&1)"; then
    LINT_ERRORS+="$OUT"$'\n'
  fi
fi

if [[ -z "$LINT_ERRORS" ]]; then
  # Clean — covers "no lint errors", "no dirty matching files", and
  # "linter(s) missing from PATH" (self-degrade) all the same way.
  # 클린 — "오류 없음", "dirty 대상 파일 없음", "린터 부재(self-degrade)"
  # 세 경우 모두 동일하게 처리한다.
  echo 0 > "$COUNTER_FILE"
  exit 0
fi

if [[ "$MODE" == "posttool" ]]; then
  # PostToolUse is advisory only per this hardening pass's decision — it
  # must never block, only surface the finding to the transcript.
  # PostToolUse 는 이번 강화 결정상 참고용일 뿐 — 절대 차단하지 않고 발견만
  # transcript 에 표면화한다.
  {
    echo "lint-gate (posttool, non-blocking) — dirty *.py/*.md lint findings:"
    echo "$LINT_ERRORS"
  } >&2
  exit 0
fi

# --mode stop: bounded blocking. Read the current block count (defaulting to
# 0 on any parse trouble) so a corrupted counter file can't wedge the gate.
# --mode stop: 유한 차단. 카운터 파일이 깨져 있어도 게이트가 멈추지 않도록
# 파싱 실패 시 0으로 기본값 처리한다.
COUNT=0
if [[ -f "$COUNTER_FILE" ]]; then
  COUNT="$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)"
  [[ "$COUNT" =~ ^[0-9]+$ ]] || COUNT=0
fi

if [[ "$COUNT" -ge "$MAX_BLOCKS" ]]; then
  # Self cap reached — stop blocking so the session can end even though
  # lint is still dirty. Counter is left as-is; it only resets on a clean run.
  # 자체 상한 도달 — lint 가 아직 안 깨끗해도 세션 종료를 허용한다. 카운터는
  # 그대로 두고, 클린한 실행에서만 리셋된다.
  exit 0
fi

echo $((COUNT + 1)) > "$COUNTER_FILE"

python3 - "$LINT_ERRORS" <<'PYEOF'
import json
import sys

errors = sys.argv[1]
print(json.dumps({
    "decision": "block",
    "reason": "lint-gate: dirty *.py/*.md lint errors found, fix before stopping:\n" + errors,
}))
PYEOF
