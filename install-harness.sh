#!/usr/bin/env bash
# EN: Receiving-side installer for the multi-agent harness bundle. Placed at
#     the bundle root by package-harness.sh (sibling of base/), it copies
#     base/agents, base/settings.harness.json, base/hooks, base/docs/harness
#     and base/templates into either the global layer (~/.claude/) or a
#     project layer (<repo>/.claude/, <repo>/docs/), following the 2-layer
#     model in base/docs/harness/03-adoption.md A0. It is the only place the
#     merge invariants from docs/PLAN_HARNESS_PORTABILITY.md are enforced:
#     backup-before-overwrite, skip+warn on customized files, JSON union for
#     settings.json, marker-scoped merge for CLAUDE.md, and fail-loud restore
#     on write validation failure. --uninstall reverses the same operations
#     using the same shipped base/ files as the source of truth for what
#     "unmodified" looks like.
# KO: 하네스 번들의 받는 쪽 인스톨러. package-harness.sh 가 번들 최상위에
#     배치하며(base/ 와 형제), base/agents, base/settings.harness.json,
#     base/hooks, base/docs/harness, base/templates 를 글로벌 층(~/.claude/)
#     또는 프로젝트 층(<repo>/.claude/, <repo>/docs/)으로 복사한다
#     (base/docs/harness/03-adoption.md A0 의 2계층 모델). PLAN_HARNESS_PORTABILITY.md
#     의 병합 불변식 — 덮어쓰기 전 백업, 커스터마이즈 파일 skip+경고,
#     settings.json JSON union, CLAUDE.md 마커 범위 병합, 쓰기 검증 실패 시
#     백업 복원 — 을 실제로 강제하는 유일한 곳이다. --uninstall 은 같은
#     shipped base/ 파일을 "미변경 여부" 판정 기준으로 삼아 정확히 역순 처리한다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$SCRIPT_DIR/base"

MODE=""
PROJECT_ARG=""
DRY_RUN=0
FORCE=0
UNINSTALL=0

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
install-harness.sh — 멀티 에이전트 하네스 인스톨러 (harness-dist)

사용법:
  install-harness.sh --global [--dry-run] [--force] [--uninstall]
  install-harness.sh --project <repo-path> [--dry-run] [--force] [--uninstall]

옵션:
  --global            글로벌 층(~/.claude/)에 설치
  --project <path>    프로젝트 층(<repo>/.claude/, <repo>/docs/)에 설치.
                       <path>는 git 저장소 내부 아무 경로나 가능(자동으로 루트를 찾는다)
  --dry-run           실제 쓰기 없이 무엇을 할지만 출력. 파일시스템 무변화
  --force             이미 커스터마이즈된(내용이 다른) 파일도 백업 후 덮어쓴다
  --uninstall         관리블록·이 스크립트가 배치한 스캐폴드 제거 (.bak-* 백업은 보존)
  -h, --help          이 도움말 출력

자세한 안내: base/INSTALL.md
USAGE
}

# EN: Parses argv into the MODE/PROJECT_ARG/DRY_RUN/FORCE/UNINSTALL globals
#     that every do_install_*/do_uninstall_* function below reads. Called
#     once from main() as the very first step; everything else depends on
#     its output. Rejects unknown flags and requires exactly one of
#     --global / --project <path> so a typo never silently falls through to
#     the wrong target.
# KO: argv 를 파싱해 아래 모든 do_install_*/do_uninstall_* 함수가 읽는
#     MODE/PROJECT_ARG/DRY_RUN/FORCE/UNINSTALL 전역변수를 채운다. main() 의
#     첫 단계로 한 번 호출되며 이후 모든 로직이 이 결과에 의존한다. 알 수
#     없는 플래그는 거부하고, --global / --project <path> 중 정확히 하나를
#     요구해 오타로 엉뚱한 대상에 설치되는 것을 막는다.
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --global)
        MODE="global"
        shift
        ;;
      --project)
        MODE="project"
        PROJECT_ARG="${2:-}"
        [[ -n "$PROJECT_ARG" ]] || die "--project requires a path argument"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --force)
        FORCE=1
        shift
        ;;
      --uninstall)
        UNINSTALL=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        die "unknown argument: $1"
        ;;
    esac
  done
  if [[ -z "$MODE" ]]; then
    usage
    die "one of --global or --project <path> is required"
  fi
}

# EN: Copies a single-source-of-truth backup of an existing file to
#     "<path>.bak-<timestamp>-<pid>" before it gets overwritten. Called from
#     sync_protected_file's forced-overwrite branch; the JSON/CLAUDE.md
#     merge helpers below do their own equivalent backup in python3 so they
#     can back up only when content actually changes. No-op (and no
#     filesystem write) if the path does not exist yet, or if DRY_RUN is set.
# KO: 기존 파일을 덮어쓰기 직전 "<경로>.bak-<타임스탬프>-<pid>" 로 백업한다.
#     sync_protected_file 의 강제 덮어쓰기 분기에서 호출된다. 아래
#     JSON/CLAUDE.md 병합 헬퍼는 실제 내용이 바뀔 때만 백업하도록 python3
#     안에서 동등한 백업을 자체적으로 수행한다. 경로가 아직 없거나
#     DRY_RUN 이면 아무 것도 쓰지 않고 조용히 넘어간다.
backup_path() {
  local path="$1"
  [[ -e "$path" ]] || return 0
  [[ "$DRY_RUN" -eq 1 ]] && { log "WOULD_BACKUP $path"; return 0; }
  local bak
  bak="${path}.bak-$(date +%Y%m%dT%H%M%S)-$$"
  cp -p "$path" "$bak"
  log "BACKUP  $path -> $bak"
}

# EN: The single install-time protection rule used for every "install once,
#     don't clobber later customization" target: agent files (--global),
#     spec docs / hooks / decision-log seed (--project). If the destination
#     is absent it is created fresh. If present and byte-identical to the
#     shipped source it is a no-op (this is what makes repeated installs
#     idempotent — diff 0). If present and different, it is assumed
#     hand-customized and left alone with a warning unless --force is set,
#     in which case it is backed up first via backup_path. Shell scripts get
#     their exec bit re-applied after every copy, compensating for exec-bit
#     loss some zip toolchains introduce (Q5 in the plan).
# KO: "한 번 설치하고 이후 커스터마이즈는 건드리지 않는다" 대상 전부가
#     공유하는 단일 설치 보호 규칙 — agent 파일(--global), 스펙 문서/훅/
#     결정로그 시드(--project). 대상이 없으면 새로 만든다. 있고 shipped
#     원본과 바이트 단위로 동일하면 아무 것도 안 한다(반복 설치가
#     멱등·diff 0 이 되는 이유). 있고 다르면 손으로 커스터마이즈된 것으로
#     간주해 경고만 남기고 건드리지 않는다 — 단 --force 면 backup_path 로
#     먼저 백업한 뒤 덮어쓴다. 셸 스크립트는 복사할 때마다 exec bit 를
#     재적용해 일부 zip 툴체인의 exec-bit 손실(계획의 Q5)을 보완한다.
sync_protected_file() {
  local src="$1" dst="$2" label="$3"
  [[ -e "$src" ]] || die "internal: missing shipped source for $label: $src"

  if [[ ! -e "$dst" ]]; then
    log "CREATE  $label -> $dst"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
      case "$dst" in
        *.sh) chmod +x "$dst" ;;
      esac
    fi
    return 0
  fi

  if cmp -s "$src" "$dst"; then
    log "OK      $label already in sync"
    return 0
  fi

  if [[ "$FORCE" -eq 1 ]]; then
    log "OVERWRITE $label (forced) -> $dst"
    backup_path "$dst"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      cp "$src" "$dst"
      case "$dst" in
        *.sh) chmod +x "$dst" ;;
      esac
    fi
  else
    warn "$label at $dst differs from the shipped version — assumed customized, skipping (rerun with --force to overwrite)"
  fi
}

# EN: Uninstall counterpart of sync_protected_file. Removes the destination
#     only if it is byte-identical to the shipped source (proof that it was
#     never customized after install); otherwise it warns and leaves the
#     file in place rather than risk deleting real project content (e.g. an
#     accumulated docs/DECISIONS.md). Never touches .bak-* files.
# KO: sync_protected_file 의 uninstall 대응 함수. 대상이 shipped 원본과
#     바이트 단위로 동일할 때만(=설치 후 한 번도 커스터마이즈되지 않았다는
#     증거) 제거한다. 다르면 경고만 남기고 그대로 둔다 — 누적된 실제
#     프로젝트 내용(예: docs/DECISIONS.md)을 잘못 지우는 위험을 피한다.
#     .bak-* 백업 파일은 절대 건드리지 않는다.
remove_if_matches_shipped() {
  local src="$1" dst="$2" label="$3"
  if [[ ! -e "$dst" ]]; then
    log "SKIP    $label not present at $dst"
    return 0
  fi
  if cmp -s "$src" "$dst"; then
    log "REMOVE  $label -> $dst"
    [[ "$DRY_RUN" -eq 0 ]] && rm -f "$dst"
  else
    warn "$label at $dst differs from the shipped version — assumed customized, leaving in place"
  fi
}

# EN: Creates the empty .claude/state/.gitkeep marker a fresh project needs
#     so lint-gate.sh has somewhere to write its runtime counter file (see
#     base/hooks/README equivalent notes). A trivial always-idempotent
#     create-if-absent; paired with remove_state_gitkeep for --uninstall.
# KO: 신규 프로젝트가 필요로 하는 빈 .claude/state/.gitkeep 마커를 만든다 —
#     lint-gate.sh 가 런타임 카운터 파일을 쓸 자리다.
#     항상 멱등한 "없으면 생성" 뿐인 사소한 함수. --uninstall 용
#     remove_state_gitkeep 과 짝이다.
ensure_state_gitkeep() {
  local project_root="$1"
  local dst="$project_root/.claude/state/.gitkeep"
  if [[ -e "$dst" ]]; then
    log "OK      .claude/state/.gitkeep already present"
    return 0
  fi
  log "CREATE  .claude/state/.gitkeep -> $dst"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$(dirname "$dst")"
    : > "$dst"
  fi
}

# EN: Uninstall counterpart of ensure_state_gitkeep. Removes the marker and,
#     best-effort, rmdir's .claude/state/ if that leaves it empty (never
#     touches it if other runtime files are still sitting there).
# KO: ensure_state_gitkeep 의 uninstall 대응. 마커를 지우고, best-effort로
#     .claude/state/ 가 비면 rmdir 한다(다른 런타임 파일이 남아 있으면
#     건드리지 않는다).
remove_state_gitkeep() {
  local project_root="$1"
  local dst="$project_root/.claude/state/.gitkeep"
  local state_dir="$project_root/.claude/state"
  if [[ -f "$dst" ]]; then
    log "REMOVE  .claude/state/.gitkeep -> $dst"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      rm -f "$dst"
      rmdir "$state_dir" 2>/dev/null || true
    fi
  fi
}

# EN: JSON-unions base/settings.harness.json into a target settings.json:
#     permissions.allow/deny are set-unioned for every scope, while hooks
#     are unioned per event with duplicate detection by command substring
#     (so slightly different absolute paths to the same hook script still
#     count as a duplicate) ONLY when scope != "global" — hooks reference
#     "$CLAUDE_PROJECT_DIR"-relative scripts that a global-only install never
#     places, so a global merge must leave the target's "hooks" key exactly
#     as it found it (absent stays absent). Every other top-level key (e.g.
#     enabledPlugins) is left completely untouched regardless of scope. If
#     the target file exists but is not valid JSON before the merge even
#     starts, no backup/write is attempted at all and the python helper
#     exits 2 (PRECORRUPT) so the caller can report "skipped, left
#     untouched" instead of the misleading "restored from backup". For an
#     already-valid target, backs it up only when the merge actually changes
#     something, writes, reloads to validate the JSON, and restores the
#     backup + exits 1 if that reload fails (fail-loud, per the plan's merge
#     invariants). Called from do_install_global (scope="global") and
#     do_install_project (scope="project").
# KO: base/settings.harness.json 을 대상 settings.json 에 JSON union 한다:
#     permissions.allow/deny 는 모든 scope 에서 집합 union 하지만, hooks 는
#     scope != "global" 일 때만 이벤트별 union + command 문자열 substring
#     중복 판정(같은 훅 스크립트를 가리키는 약간 다른 절대경로도 중복으로
#     잡는다)을 수행한다 — 훅은 글로벌 설치가 배치하지 않는
#     "$CLAUDE_PROJECT_DIR" 상대경로 스크립트를 참조하므로, 글로벌 병합은
#     대상의 "hooks" 키를 발견한 그대로 둬야 한다(없던 건 계속 없어야
#     한다). enabledPlugins 등 그 외 top-level 키는 scope 와 무관하게 전혀
#     건드리지 않는다. 대상 파일이 존재하는데 병합 시작 전부터 유효한
#     JSON이 아니면 백업·쓰기를 아예 시도하지 않고 python 헬퍼가 exit 2
#     (PRECORRUPT)로 끝나 호출부가 "복원됨"이 아니라 "건너뜀·원본 유지"로
#     정확히 보고할 수 있게 한다. 처음부터 유효한 대상이면 실제 내용이
#     바뀔 때만 백업 후 쓰고, 재-load 로 JSON 유효성을 검증해 실패하면
#     백업을 복원하고 exit 1(계획의 병합 불변식 — fail-loud). do_install_global
#     (scope="global")과 do_install_project(scope="project")에서 호출된다.
merge_settings_json() {
  local base="$1" target="$2" scope="${3:-project}" out rc=0
  out="$(python3 - "$base" "$target" "$DRY_RUN" "$scope" <<'PYEOF'
import json
import os
import shutil
import sys
import time

base_path, target_path, dry_run_flag, scope = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
dry_run = dry_run_flag == "1"

with open(base_path, encoding="utf-8") as f:
    base = json.load(f)

existed = os.path.exists(target_path)
if existed:
    try:
        with open(target_path, encoding="utf-8") as f:
            target = json.load(f)
    except Exception:
        print("PRECORRUPT", file=sys.stderr)
        sys.exit(2)
    original_text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"
else:
    target = {}
    original_text = ""

perms = target.setdefault("permissions", {})
for key in ("allow", "deny"):
    base_list = base.get("permissions", {}).get(key, [])
    merged = list(perms.get(key, []))
    for item in base_list:
        if item not in merged:
            merged.append(item)
    perms[key] = merged


def is_dup(new_cmd, existing_cmds):
    return any(new_cmd in e or e in new_cmd for e in existing_cmds)


if scope != "global":
    hooks = target.setdefault("hooks", {})
    for event, entries in base.get("hooks", {}).items():
        cur_entries = hooks.get(event, [])
        existing_cmds = []
        for group in cur_entries:
            for h in group.get("hooks", []):
                existing_cmds.append(h.get("command", ""))
        merged_entries = list(cur_entries)
        for group in entries:
            new_hooks = [h for h in group.get("hooks", []) if not is_dup(h.get("command", ""), existing_cmds)]
            if new_hooks:
                new_group = dict(group)
                new_group["hooks"] = new_hooks
                merged_entries.append(new_group)
                existing_cmds.extend(h.get("command", "") for h in new_hooks)
        hooks[event] = merged_entries

new_text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"

if new_text == original_text:
    print("UNCHANGED")
    sys.exit(0)

if dry_run:
    print("WOULD_WRITE")
    sys.exit(0)

backup = None
if existed:
    backup = target_path + ".bak-" + time.strftime("%Y%m%dT%H%M%S") + "-" + str(os.getpid())
    shutil.copy2(target_path, backup)

os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_text)

try:
    with open(target_path, encoding="utf-8") as f:
        json.load(f)
except Exception:
    if backup:
        shutil.copy2(backup, target_path)
    print("FAILED_RESTORED", file=sys.stderr)
    sys.exit(1)

print("WRITTEN" + (" backup=" + backup if backup else ""))
PYEOF
  )" || rc=$?
  if [[ "$rc" -eq 2 ]]; then
    warn "$target is not valid JSON — merge skipped, existing file left untouched"
    return 0
  elif [[ "$rc" -ne 0 ]]; then
    die "settings.json merge failed and was restored from backup: $target"
  fi
  log "settings.json: $out"
}

# EN: Reverses merge_settings_json using the same base/settings.harness.json
#     as the source of truth for "what did the harness add" — it subtracts
#     exactly the allow/deny entries (every scope) and, ONLY when
#     scope != "global", the hook commands (same substring match) that base
#     would have contributed, leaving anything the user added independently
#     untouched. The hooks subtraction is skipped entirely for scope
#     "global" for the same reason merge_settings_json skips adding them
#     there: a global install/uninstall must be a no-op with respect to the
#     "hooks" key either way, since it never wired them in the first place.
#     No-op if target settings.json does not exist. If the target file exists
#     but is not valid JSON before the unmerge even starts, no backup/write is
#     attempted at all and the python helper exits 2 (PRECORRUPT), mirroring
#     merge_settings_json's pre-corruption guard exactly, so the caller can
#     report "unmerge skipped, left untouched" instead of the misleading
#     "restored from backup" — and, critically, continue with the rest of
#     uninstall (hooks/state/DECISIONS/CLAUDE managed block removal) instead
#     of aborting into a partial uninstall. For an already-valid target,
#     backs it up before writing, same fail-loud reload check as the merge
#     direction (restore + exit 1 on reload failure). Called from
#     do_uninstall_global (scope="global") and do_uninstall_project
#     (scope="project").
# KO: merge_settings_json 의 역방향. 같은 base/settings.harness.json 을
#     "하네스가 무엇을 추가했었나"의 기준으로 삼아, allow/deny 항목(모든
#     scope)과, scope != "global" 일 때만 훅 커맨드(같은 substring 매칭)를
#     정확히 빼고 사용자가 독립적으로 추가한 것은 건드리지 않는다. "global"
#     scope 는 훅 제거 로직 자체를 건너뛴다 — merge_settings_json 이 글로벌에
#     훅을 애초에 추가하지 않는 것과 같은 이유로, 글로벌 install/uninstall
#     은 "hooks" 키에 대해 어느 방향이든 no-op 이어야 한다. 대상
#     settings.json 이 없으면 아무 것도 안 한다. 대상 파일이 존재하는데 해제
#     시작 전부터 유효한 JSON이 아니면 백업·쓰기를 아예 시도하지 않고
#     python 헬퍼가 merge_settings_json 과 정확히 대칭으로 exit 2
#     (PRECORRUPT)로 끝나 호출부가 "복원됨"이 아니라 "해제 건너뜀·원본 유지"로
#     정확히 보고하고 — 무엇보다 — uninstall 의 나머지 단계(hooks/state/
#     DECISIONS/CLAUDE 관리블록 제거)를 계속 진행해 부분 uninstall 로 중단되지
#     않게 한다. 처음부터 유효한 대상이면 쓰기 전 백업, merge 방향과 동일한
#     fail-loud 재-load 검증(실패 시 복원 + exit 1)을 수행한다.
#     do_uninstall_global(scope="global")과 do_uninstall_project
#     (scope="project")에서 호출된다.
unmerge_settings_json() {
  local base="$1" target="$2" scope="${3:-project}" out rc=0
  out="$(python3 - "$base" "$target" "$DRY_RUN" "$scope" <<'PYEOF'
import json
import os
import shutil
import sys
import time

base_path, target_path, dry_run_flag, scope = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
dry_run = dry_run_flag == "1"

if not os.path.exists(target_path):
    print("NOOP")
    sys.exit(0)

with open(base_path, encoding="utf-8") as f:
    base = json.load(f)
try:
    with open(target_path, encoding="utf-8") as f:
        target = json.load(f)
except Exception:
    print("PRECORRUPT", file=sys.stderr)
    sys.exit(2)
original_text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"

changed = False

perms = target.get("permissions", {})
for key in ("allow", "deny"):
    base_set = set(base.get("permissions", {}).get(key, []))
    cur_list = perms.get(key, [])
    new_list = [x for x in cur_list if x not in base_set]
    if len(new_list) != len(cur_list):
        changed = True
    perms[key] = new_list


def matches_any(cmd, cmd_set):
    return any(cmd in c or c in cmd for c in cmd_set)


if scope != "global":
    hooks = target.get("hooks", {})
    for event, entries in base.get("hooks", {}).items():
        base_cmds = set()
        for group in entries:
            for h in group.get("hooks", []):
                base_cmds.add(h.get("command", ""))
        cur_entries = hooks.get(event, [])
        new_entries = []
        for group in cur_entries:
            remaining = [h for h in group.get("hooks", []) if not matches_any(h.get("command", ""), base_cmds)]
            if len(remaining) != len(group.get("hooks", [])):
                changed = True
            if remaining:
                new_group = dict(group)
                new_group["hooks"] = remaining
                new_entries.append(new_group)
        if new_entries:
            hooks[event] = new_entries
        elif event in hooks:
            del hooks[event]
            changed = True

if not changed:
    print("UNCHANGED")
    sys.exit(0)

new_text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"

if dry_run:
    print("WOULD_WRITE")
    sys.exit(0)

backup = target_path + ".bak-" + time.strftime("%Y%m%dT%H%M%S") + "-" + str(os.getpid())
shutil.copy2(target_path, backup)

with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_text)

try:
    with open(target_path, encoding="utf-8") as f:
        json.load(f)
except Exception:
    shutil.copy2(backup, target_path)
    print("FAILED_RESTORED", file=sys.stderr)
    sys.exit(1)

print("WRITTEN backup=" + backup)
PYEOF
  )" || rc=$?
  if [[ "$rc" -eq 2 ]]; then
    warn "$target is not valid JSON — unmerge skipped, existing file left untouched"
    return 0
  elif [[ "$rc" -ne 0 ]]; then
    die "settings.json unmerge failed and was restored from backup: $target"
  fi
  log "settings.json: $out"
}

# EN: Inserts or refreshes the <!-- HARNESS:BEGIN --> ... <!-- HARNESS:END
#     --> managed block inside a CLAUDE.md file, using block_file's full
#     content as the block (both base/templates/CLAUDE.harness-*.md files
#     already start/end with those exact markers). If the markers already
#     exist, only the text between them is replaced — everything else in the
#     file, including all user prose, is byte-for-byte preserved. If the
#     markers are absent, the block is appended after a blank-line
#     separator, again leaving existing content untouched. If the target
#     file does not exist yet it is created containing only the block. Backs
#     up only when content actually changes, so repeated installs stay diff
#     0.
# KO: CLAUDE.md 안의 `<!-- HARNESS:BEGIN -->` ~ `<!-- HARNESS:END -->`
#     관리블록을 삽입하거나 갱신한다. block_file 전체 내용을 블록으로 쓴다
#     (base/templates/CLAUDE.harness-*.md 두 파일 모두 이미 그 정확한
#     마커로 시작·끝난다). 마커가 이미 있으면 그 사이만 교체하고, 파일의
#     나머지(사용자 본문 전부)는 바이트 단위로 보존한다. 마커가 없으면
#     빈 줄 구분자 뒤에 블록을 덧붙인다(기존 내용은 역시 그대로). 대상
#     파일이 아직 없으면 블록만 담아 새로 만든다. 실제 내용이 바뀔 때만
#     백업해 반복 설치가 diff 0 을 유지하게 한다.
merge_claude_md() {
  local block_file="$1" target="$2" out
  if ! out="$(python3 - "$block_file" "$target" "$DRY_RUN" <<'PYEOF'
import os
import shutil
import sys
import time

block_path, target_path, dry_run_flag = sys.argv[1], sys.argv[2], sys.argv[3]
dry_run = dry_run_flag == "1"

BEGIN = "<!-- HARNESS:BEGIN -->"
END = "<!-- HARNESS:END -->"

with open(block_path, encoding="utf-8") as f:
    block = f.read().strip("\n") + "\n"

existed = os.path.exists(target_path)
content = ""
if existed:
    with open(target_path, encoding="utf-8") as f:
        content = f.read()

b = content.find(BEGIN)
e = content.find(END)
if b != -1 and e != -1 and e > b:
    before = content[:b].rstrip("\n")
    after = content[e + len(END):].lstrip("\n")
    if before and after:
        new_content = before + "\n\n" + block + "\n" + after
    elif after:
        new_content = block + "\n" + after
    elif before:
        new_content = before + "\n\n" + block
    else:
        new_content = block
elif content:
    new_content = content.rstrip("\n") + "\n\n" + block
else:
    new_content = block

if new_content == content:
    print("UNCHANGED")
    sys.exit(0)

if dry_run:
    print("WOULD_WRITE")
    sys.exit(0)

backup = None
if existed:
    backup = target_path + ".bak-" + time.strftime("%Y%m%dT%H%M%S") + "-" + str(os.getpid())
    shutil.copy2(target_path, backup)

os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("WRITTEN" + (" backup=" + backup if backup else ""))
PYEOF
  )"; then
    die "CLAUDE.md merge failed: $target"
  fi
  log "CLAUDE.md ($target): $out"
}

# EN: Strips the <!-- HARNESS:BEGIN --> ... <!-- HARNESS:END --> managed
#     block back out of a CLAUDE.md file, restoring the surrounding user
#     content exactly (collapsed to a single blank-line join where the block
#     used to sit). If removing the block leaves the file blank, the file
#     itself is deleted (it only ever existed to hold the block). No-op if
#     the target file or the markers are absent. Always backs up before
#     mutating.
# KO: CLAUDE.md 에서 `<!-- HARNESS:BEGIN -->` ~ `<!-- HARNESS:END -->`
#     관리블록만 도려내 주변 사용자 본문을 그대로 복원한다(블록이 있던
#     자리는 빈 줄 하나로 합쳐진다). 블록 제거 후 파일이 비면 파일 자체를
#     지운다(블록만 담으려고 만들어진 파일이었다는 뜻이므로). 대상 파일이나
#     마커가 없으면 아무 것도 안 한다. 변경 전 항상 백업한다.
unmerge_claude_md() {
  local target="$1" out
  if ! out="$(python3 - "$target" "$DRY_RUN" <<'PYEOF'
import os
import shutil
import sys
import time

target_path, dry_run_flag = sys.argv[1], sys.argv[2]
dry_run = dry_run_flag == "1"

BEGIN = "<!-- HARNESS:BEGIN -->"
END = "<!-- HARNESS:END -->"

if not os.path.exists(target_path):
    print("NOOP")
    sys.exit(0)

with open(target_path, encoding="utf-8") as f:
    content = f.read()

b = content.find(BEGIN)
e = content.find(END)
if b == -1 or e == -1 or e < b:
    print("NOOP")
    sys.exit(0)

before = content[:b].rstrip("\n")
after = content[e + len(END):].lstrip("\n")
if before and after:
    new_content = before + "\n\n" + after
elif after:
    new_content = after
elif before:
    new_content = before + "\n"
else:
    new_content = ""

if dry_run:
    print("UNCHANGED" if new_content == content else "WOULD_WRITE")
    sys.exit(0)

backup = target_path + ".bak-" + time.strftime("%Y%m%dT%H%M%S") + "-" + str(os.getpid())
shutil.copy2(target_path, backup)

if new_content.strip() == "":
    os.remove(target_path)
    print("REMOVED_EMPTY backup=" + backup)
    sys.exit(0)

with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_content)
print("WRITTEN backup=" + backup)
PYEOF
  )"; then
    die "CLAUDE.md unmerge failed: $target"
  fi
  log "CLAUDE.md ($target): $out"
}

# EN: Resolves a --project <path> argument to the actual git repository
#     root via `git rev-parse --show-toplevel`, so passing a subdirectory
#     never causes the installer to write .claude/docs scaffolding into the
#     wrong (non-root) location — the exact "루트 오탐" guard the plan calls
#     for. Dies loudly if the path is missing or not inside a git repo.
# KO: --project <path> 인자를 `git rev-parse --show-toplevel` 로 실제
#     저장소 루트로 해석한다 — 서브디렉터리를 넘겨도 .claude/docs 스캐폴딩이
#     엉뚱한(루트가 아닌) 위치에 쓰이지 않게 하는, 계획서가 요구한 "루트
#     오탐" 가드 그 자체다. 경로가 없거나 git 저장소 밖이면 즉시 실패한다.
resolve_project_root() {
  local input_path="$1"
  [[ -d "$input_path" ]] || die "--project path does not exist or is not a directory: $input_path"
  local abs_input toplevel
  abs_input="$(cd "$input_path" && pwd)"
  toplevel="$(cd "$abs_input" && git rev-parse --show-toplevel 2>/dev/null)" || die "--project path is not inside a git repository: $input_path"
  if [[ "$toplevel" != "$abs_input" ]]; then
    # NOTE: this function's stdout is captured via command substitution by
    # callers ("project_root=$(resolve_project_root ...)"), so informational
    # output must go to stderr — anything on stdout here would corrupt the
    # captured path.
    printf 'INFO    resolved --project path to repo root: %s\n' "$toplevel" >&2
  fi
  printf '%s\n' "$toplevel"
}

# EN: Implements Q1 of the plan (project CLAUDE.md target selection) — a
#     root CLAUDE.md wins if present, otherwise .claude/CLAUDE.md under it.
#     Called once by both do_install_project and do_uninstall_project so
#     install and uninstall always agree on which file they mean.
# KO: 계획서의 Q1(프로젝트 CLAUDE.md 대상 선택)을 구현한다 — 루트에
#     CLAUDE.md 가 있으면 그것, 없으면 그 아래 .claude/CLAUDE.md. install과
#     uninstall이 항상 같은 파일을 가리키도록 두 함수가 이 함수 하나를
#     공유한다.
claude_md_target_for_project() {
  local project_root="$1"
  if [[ -f "$project_root/CLAUDE.md" ]]; then
    printf '%s\n' "$project_root/CLAUDE.md"
  else
    printf '%s\n' "$project_root/.claude/CLAUDE.md"
  fi
}

do_install_global() {
  local target_root="$HOME/.claude"
  log "== install-harness.sh --global -> $target_root =="
  local name
  for name in scout architect maker critic referee; do
    sync_protected_file "$BASE_DIR/agents/$name.md" "$target_root/agents/$name.md" "agent:$name"
  done
  merge_settings_json "$BASE_DIR/settings.harness.json" "$target_root/settings.json" "global"
  merge_claude_md "$BASE_DIR/templates/CLAUDE.harness-global.md" "$target_root/CLAUDE.md"
  log "== done =="
}

do_uninstall_global() {
  local target_root="$HOME/.claude"
  log "== install-harness.sh --uninstall --global -> $target_root =="
  local name
  for name in scout architect maker critic referee; do
    remove_if_matches_shipped "$BASE_DIR/agents/$name.md" "$target_root/agents/$name.md" "agent:$name"
  done
  unmerge_settings_json "$BASE_DIR/settings.harness.json" "$target_root/settings.json" "global"
  unmerge_claude_md "$target_root/CLAUDE.md"
  log "== done (any .bak-* backups were preserved) =="
}

do_install_project() {
  local project_root claude_target
  project_root="$(resolve_project_root "$PROJECT_ARG")"
  claude_target="$(claude_md_target_for_project "$project_root")"
  log "== install-harness.sh --project -> $project_root =="

  local docname
  for docname in 00-definition 01-roles 02-orchestration 03-adoption; do
    sync_protected_file "$BASE_DIR/docs/harness/$docname.md" "$project_root/docs/harness/$docname.md" "spec:$docname"
  done

  local hookname
  for hookname in inject-repo-facts lint-gate; do
    sync_protected_file "$BASE_DIR/hooks/$hookname.sh" "$project_root/.claude/hooks/$hookname.sh" "hook:$hookname"
  done

  merge_settings_json "$BASE_DIR/settings.harness.json" "$project_root/.claude/settings.json" "project"
  ensure_state_gitkeep "$project_root"
  sync_protected_file "$BASE_DIR/templates/DECISIONS.seed.md" "$project_root/docs/DECISIONS.md" "decisions-log"
  merge_claude_md "$BASE_DIR/templates/CLAUDE.harness-project.md.template" "$claude_target"

  log "== done. Remaining manual steps (base/INSTALL.md): _repo-facts.md, agent overrides, VERIFY.md =="
}

do_uninstall_project() {
  local project_root claude_target
  project_root="$(resolve_project_root "$PROJECT_ARG")"
  claude_target="$(claude_md_target_for_project "$project_root")"
  log "== install-harness.sh --uninstall --project -> $project_root =="

  local docname
  for docname in 00-definition 01-roles 02-orchestration 03-adoption; do
    remove_if_matches_shipped "$BASE_DIR/docs/harness/$docname.md" "$project_root/docs/harness/$docname.md" "spec:$docname"
  done

  local hookname
  for hookname in inject-repo-facts lint-gate; do
    remove_if_matches_shipped "$BASE_DIR/hooks/$hookname.sh" "$project_root/.claude/hooks/$hookname.sh" "hook:$hookname"
  done

  unmerge_settings_json "$BASE_DIR/settings.harness.json" "$project_root/.claude/settings.json" "project"
  remove_if_matches_shipped "$BASE_DIR/templates/DECISIONS.seed.md" "$project_root/docs/DECISIONS.md" "decisions-log"
  remove_state_gitkeep "$project_root"
  unmerge_claude_md "$claude_target"

  log "== done (any .bak-* backups were preserved) =="
}

main() {
  parse_args "$@"
  if [[ "$UNINSTALL" -eq 1 ]]; then
    if [[ "$MODE" == "global" ]]; then
      do_uninstall_global
    else
      do_uninstall_project
    fi
  else
    if [[ "$MODE" == "global" ]]; then
      do_install_global
    else
      do_install_project
    fi
  fi
}

main "$@"
