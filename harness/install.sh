#!/usr/bin/env bash
# EN: Installer for the enforcement-first harness into a target project P.
#     Copies the 9 source files (CORE.md, gate.py, test_gate.py,
#     subagent_cost.py, 5 agent roles), symlinks the 5 role definitions into
#     P/.claude/agents/, merges the 6 hook entries into P/.claude/settings.json,
#     and creates P/.claude/harness.json (enforce: false) if absent.
#     See docs/PLAN_HARNESS_REDESIGN.md Phase 4 for the design rationale.
# KO: 집행 우선 하네스를 대상 프로젝트 P 에 설치한다. 소스 파일 9개(CORE.md·
#     gate.py·test_gate.py·subagent_cost.py·역할 5개)를 복사하고, 역할 정의 5개를
#     P/.claude/agents/ 에 심링크로 걸고, 훅 6개를 P/.claude/settings.json 에
#     병합하고, P/.claude/harness.json 이 없을 때만 만든다(enforce: false).
#     설계 근거는 docs/PLAN_HARNESS_REDESIGN.md Phase 4.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_SRC="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT_NAMES=(scout architect maker critic referee)
HOOK_EVENTS=(PreToolUse PostToolUse Stop SubagentStop SessionStart SubagentStart)

# EN: Every file this installer creates under <target>/harness, relative to that
#     directory. Uninstall removes exactly these — never the whole tree, which
#     may hold files the target project put there itself.
# KO: 이 설치기가 <target>/harness 아래 만드는 파일 전부(그 디렉터리 기준 상대경로).
#     언인스톨은 정확히 이것만 지운다 — 트리 통째로 지우지 않는다. 거기에 대상
#     프로젝트가 스스로 넣어둔 파일이 있을 수 있다.
HARNESS_FILES=(
    CORE.md
    hooks/gate.py
    tests/test_gate.py
    tools/subagent_cost.py
    agents/scout.md
    agents/architect.md
    agents/maker.md
    agents/critic.md
    agents/referee.md
)

# EN: Temp files created during a settings merge, cleaned up on any exit path so
#     a failed install does not leave .tmp-* litter in the target's .claude/.
# KO: 설정 병합 중 만든 임시 파일. 어떤 경로로 끝나든 정리한다 — 설치가 실패해도
#     대상의 .claude/ 에 .tmp-* 쓰레기를 남기지 않으려는 것이다.
TMP_FILES=()
# EN: The trailing `return 0` is load-bearing. An EXIT trap's final status becomes
#     the script's exit status, and with TMP_FILES empty the loop ends on a failed
#     `[ -n "" ]` — so every run that created no temp file reported failure while
#     having succeeded. `--global --uninstall` exited 1 every single time.
# KO: 끝의 `return 0` 이 핵심이다. EXIT 트랩의 마지막 상태가 스크립트 종료 코드가 되는데,
#     TMP_FILES 가 비면 루프가 실패한 `[ -n "" ]` 로 끝난다 — 임시 파일을 안 만든 실행은
#     성공하고도 실패로 보고됐다. `--global --uninstall` 은 매번 exit 1 이었다.
cleanup_tmp() {
    local f
    for f in "${TMP_FILES[@]:-}"; do
        [ -n "$f" ] && rm -f "$f" "$f.next"
    done
    return 0
}
trap cleanup_tmp EXIT

usage() {
    cat <<'EOF'
Usage:
  harness/install.sh <target-project-dir>
  harness/install.sh --uninstall <target-project-dir>
  harness/install.sh --global              # 설치·갱신
  harness/install.sh --global --uninstall  # 제거
EOF
}

log() { printf '%s\n' "$*" >&2; }

epoch_now() { date +%s; }

# EN: The literal marker lines in ~/.claude/CLAUDE.md that bracket the
#     harness-managed block. Everything outside them is the user's own
#     personal instructions and must never be touched.
# KO: ~/.claude/CLAUDE.md 에서 하네스가 관리하는 블록을 감싸는 마커 줄 그대로.
#     그 밖은 사용자가 직접 쓴 개인 지침이므로 절대 건드리지 않는다.
MARKER_BEGIN='<!-- HARNESS:BEGIN -->'
MARKER_END='<!-- HARNESS:END -->'

# EN: Replace (or, if absent, append) the HARNESS:BEGIN/END block in $target
#     with the contents of $src_block, writing the result to $out. $target is
#     never modified in place — the caller decides whether to mv $out over it.
#     Exits 3 if only one marker is present, or if BEGIN comes after END.
# KO: $target 의 HARNESS:BEGIN/END 블록을 $src_block 내용으로 치환(없으면
#     append)해 $out 에 쓴다. $target 자체는 건드리지 않는다 — 덮어쓸지는
#     호출자가 mv 로 결정한다. 마커가 한쪽만 있거나 BEGIN 이 END 뒤에 있으면
#     exit 3.
merge_marker_block() {
    local target="$1" src_block="$2" out="$3"
    python3 - "$target" "$src_block" "$out" "$MARKER_BEGIN" "$MARKER_END" <<'PYEOF'
import sys

target, src_block, out, begin, end = sys.argv[1:6]

try:
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()
except FileNotFoundError:
    text = ""

with open(src_block, "r", encoding="utf-8") as f:
    block = f.read()

# EN: Count, don't just test presence. `text.index()` finds the FIRST marker, so
#     a file that merely *quotes* the marker in prose above the real block would
#     have everything between the quote and the real END deleted. Counting here —
#     before anything is written — is what makes the "we never touch anything
#     outside the markers" contract true. The post-hoc count in
#     verify_install_global runs after the mv, i.e. after the damage.
# KO: 존재 여부가 아니라 개수를 센다. `text.index()` 는 **첫** 마커를 찾으므로, 진짜
#     블록 위 산문에서 마커를 단지 *인용*한 파일은 그 인용부터 진짜 END 까지가 통째로
#     지워진다. 아무것도 쓰기 전에 여기서 세는 것이 "마커 밖은 절대 건드리지 않는다"는
#     계약을 참으로 만든다. verify_install_global 의 사후 개수 검사는 mv 뒤에,
#     즉 이미 지워진 뒤에 돈다.
n_begin = text.count(begin)
n_end = text.count(end)

if n_begin != n_end:
    sys.stderr.write(
        "ERROR: %s has %d %s and %d %s — they must be paired. "
        "Aborting without touching the file; fix it by hand.\n"
        % (target, n_begin, begin, n_end, end)
    )
    sys.exit(3)

if n_begin > 1:
    sys.stderr.write(
        "ERROR: %s has %d harness blocks (or quotes the markers in its text). "
        "Aborting without touching the file — leave exactly one pair, or remove "
        "the quoted occurrences, then re-run.\n" % (target, n_begin)
    )
    sys.exit(3)

has_begin = n_begin == 1
has_end = n_end == 1

new_block = begin + "\n" + block.rstrip("\n") + "\n" + end

if has_begin and has_end:
    start = text.index(begin)
    finish = text.index(end) + len(end)
    if start > finish:
        sys.stderr.write(
            "ERROR: %s has BEGIN after END. Aborting — fix by hand.\n" % target
        )
        sys.exit(3)
    text = text[:start] + new_block + text[finish:]
else:
    if text:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + new_block + "\n"
    else:
        text = new_block + "\n"

with open(out, "w", encoding="utf-8") as f:
    f.write(text)
PYEOF
}

# EN: Fail fast and loud if jq is missing — never edit JSON with sed.
# KO: jq 가 없으면 즉시 중단 — JSON 을 sed 로 편집하지 않는다.
require_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        log "ERROR: jq is required and was not found on PATH."
        log ""
        log "수동 설치 절차 (jq 없이):"
        log "  1. cp -R \"$HARNESS_SRC/CORE.md\" \"$HARNESS_SRC/hooks\" \"$HARNESS_SRC/tests\" \\"
        log "        \"$HARNESS_SRC/tools\" \"$HARNESS_SRC/agents\" <target>/harness/"
        log "  2. chmod 755 <target>/harness/hooks/gate.py"
        log "  3. for n in scout architect maker critic referee; do"
        log "       ln -s ../../harness/agents/\$n.md <target>/.claude/agents/\$n.md"
        log "     done"
        log "  4. Manually merge the 6 hook entries from"
        log "     $REPO_ROOT/.claude/settings.json into <target>/.claude/settings.json"
        log "     (PreToolUse, PostToolUse, Stop, SubagentStop, SessionStart, SubagentStart),"
        log "     each running: \$CLAUDE_PROJECT_DIR/harness/hooks/gate.py"
        log "  5. Create <target>/.claude/harness.json with:"
        log '     {"enforce": false, "product": ["docs/**","harness/**"], "exempt": []}'
        exit 1
    fi
}

# EN: Refuse to start unless the target's settings.json is valid JSON. Validating
#     up front is the only way to avoid a half-installed target: by the time jq
#     fails mid-merge, files and symlinks are already in place.
# KO: 대상의 settings.json 이 올바른 JSON 이 아니면 시작하지 않는다. 미리 검사하는
#     것만이 반쯤 설치된 대상을 피하는 방법이다 — 병합 도중 jq 가 실패할 때쯤이면
#     파일과 심링크는 이미 깔려 있다.
require_valid_target_settings() {
    local dst_settings="$1/.claude/settings.json"
    [ -f "$dst_settings" ] || return 0
    if ! jq empty "$dst_settings" 2>/dev/null; then
        log "ERROR: $dst_settings is not valid JSON. Nothing was installed."
        log "       Fix or move that file, then re-run the installer."
        exit 1
    fi
}

# EN: Fail fast and loud if python3 is missing — it merges/verifies the marker
#     block and, after this fix, resolves symlinks too. Global install/uninstall
#     both depend on it before touching anything.
# KO: python3 이 없으면 즉시 중단 — 마커 블록 병합·검증에 쓰이고, 이 수정 이후로는
#     심링크 해석에도 쓰인다. 전역 설치·제거 둘 다 아무것도 건드리기 전에 확인한다.
require_python3() {
    if ! command -v python3 >/dev/null 2>&1; then
        log "ERROR: python3 is required and was not found on PATH."
        log "       It is used to merge/verify the HARNESS:BEGIN/END block in"
        log "       ~/.claude/CLAUDE.md. Install python3, or edit that block by hand."
        exit 1
    fi
}

# EN: If $1 is a symlink, follow it to its physical target and print that path
#     (a dangling symlink — -L and not -e — logs and exits 1, since the user's
#     own config is already broken and we should not create files under an
#     unmounted path). If $1 is not a symlink, print it unchanged. This makes a
#     dotfiles-managed ~/.claude/CLAUDE.md or ~/.claude/agents symlink resolve
#     to its real backing file/dir, so install writes land there instead of
#     silently replacing the symlink with a plain file/dir.
#     ~/.claude itself being a symlink is out of scope — not handled here.
# KO: $1 이 심링크면 물리 경로로 따라가 출력한다(끊긴 심링크 — -L 이면서 !-e —
#     면 log 후 exit 1: 사용자 설정이 이미 깨져 있으므로 마운트 안 된 경로에
#     파일을 만들지 않는다). 심링크가 아니면 그대로 출력한다. dotfiles 로 관리되는
#     ~/.claude/CLAUDE.md 나 ~/.claude/agents 심링크가 실제 백업 파일/디렉터리로
#     풀리게 해서, 설치 결과가 심링크를 실파일/실디렉터리로 조용히 대체하지 않게 한다.
#     ~/.claude 디렉터리 자신이 심링크인 경우는 범위 밖이며 여기서 다루지 않는다.
# EN: $2 = "tolerate-dangling" makes a broken link resolve to the link itself
#     instead of aborting. Uninstall passes it: aborting there was a dead end,
#     because the way to fix a broken harness link is to remove the harness, and
#     removal was the thing being blocked (N-5). Install still aborts — writing
#     through a broken link would create a file at an unmounted path.
# KO: $2 가 "tolerate-dangling" 이면 끊긴 링크가 중단이 아니라 링크 자신으로 해석된다.
#     제거 경로가 이것을 넘긴다 — 거기서 중단하는 것은 막다른 길이었다. 깨진 하네스
#     링크를 고치는 방법이 하네스를 제거하는 것인데 그 제거가 막혀 있었다(N-5).
#     설치는 여전히 중단한다 — 끊긴 링크로 쓰면 마운트되지 않은 경로에 파일이 생긴다.
resolve_if_symlink() {
    local p="$1" mode="${2:-strict}"
    if [ ! -L "$p" ]; then
        printf '%s\n' "$p"
        return 0
    fi
    if [ -e "$p" ]; then
        python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$p"
        return 0
    fi
    if [ "$mode" = "tolerate-dangling" ]; then
        log "NOTE: $p is a dangling symlink — removing the link itself."
        printf '%s\n' "$p"
        return 0
    fi
    log "ERROR: $p is a symlink but its target does not exist (dangling)."
    log "       Fix or remove the symlink, then re-run the installer."
    exit 1
}

# EN: Copy a source file over a target path, snapshotting any pre-existing target
#     file to <path>.bak-<epoch> first. The installer must never silently destroy
#     something the project already had there. If $dst is itself a symlink (e.g.
#     an individual role file routed through a dotfiles repo), it is resolved to
#     its physical target via resolve_if_symlink() first (D1) — the write lands
#     on the real file and the symlink itself is never touched, so it survives.
#     A dangling symlink aborts inside resolve_if_symlink(), matching D1.
# KO: 소스 파일을 대상 경로에 복사하되, 기존 파일이 있으면 먼저 <path>.bak-<epoch>
#     로 떠 둔다. 설치기가 프로젝트에 이미 있던 것을 조용히 없애서는 안 된다. $dst
#     자체가 심링크(예: dotfiles 저장소로 흘려보내는 개별 역할 파일)면 먼저
#     resolve_if_symlink() 로 물리 경로를 구한다(D1) — 쓰기는 실파일에 떨어지고
#     심링크 자신은 건드리지 않아 그대로 남는다. 끊긴 심링크는 resolve_if_symlink()
#     안에서 중단된다(D1 과 동일).
copy_with_backup() {
    local src="$1" dst="$2" epoch="$3"
    local resolved
    resolved="$(resolve_if_symlink "$dst")"
    if [ -e "$resolved" ]; then
        if ! cmp -s "$src" "$resolved" 2>/dev/null; then
            cp -P "$resolved" "$resolved.bak-$epoch"
            log "backed up existing $resolved -> $resolved.bak-$epoch"
        fi
    fi
    rm -f "$resolved"
    cp "$src" "$resolved"
}

install_files() {
    local target="$1"
    local epoch="$2"
    mkdir -p "$target/harness/hooks" "$target/harness/tests" \
        "$target/harness/tools" "$target/harness/agents"
    mkdir -p "$target/.claude/agents"

    copy_with_backup "$HARNESS_SRC/CORE.md" "$target/harness/CORE.md" "$epoch"
    copy_with_backup "$HARNESS_SRC/hooks/gate.py" "$target/harness/hooks/gate.py" "$epoch"
    chmod 0755 "$target/harness/hooks/gate.py"
    copy_with_backup "$HARNESS_SRC/tests/test_gate.py" \
        "$target/harness/tests/test_gate.py" "$epoch"
    # EN: gate.py loads this by relative path on SubagentStop to record cost.
    #     Without it every installed project records cost_resolved: false.
    # KO: gate.py 가 SubagentStop 에서 비용을 남길 때 상대경로로 이 파일을 읽는다.
    #     빠지면 설치된 모든 프로젝트가 cost_resolved: false 만 기록하게 된다.
    copy_with_backup "$HARNESS_SRC/tools/subagent_cost.py" \
        "$target/harness/tools/subagent_cost.py" "$epoch"

    local drift_off=0
    for name in "${AGENT_NAMES[@]}"; do
        copy_with_backup "$HARNESS_SRC/agents/$name.md" \
            "$target/harness/agents/$name.md" "$epoch"
        local link="$target/.claude/agents/$name.md"
        # EN: A project-level agent definition outranks the global one, so an
        #     existing real file here is authoritative for that project — snapshot
        #     it before replacing it with our symlink.
        # KO: 프로젝트 수준 에이전트 정의가 전역보다 우선하므로, 여기 있는 실파일은
        #     그 프로젝트의 정본이다 — 심링크로 바꾸기 전에 떠 둔다.
        if [ -f "$link" ] && [ ! -L "$link" ]; then
            cp "$link" "$link.bak-$epoch"
            log "backed up project agent definition $link -> $link.bak-$epoch"
        fi
        rm -f "$link"
        if ! ln -s "../../harness/agents/$name.md" "$link" 2>/dev/null; then
            cp "$HARNESS_SRC/agents/$name.md" "$link"
            drift_off=1
        fi
    done
    if [ "$drift_off" -eq 1 ]; then
        log "WARNING: symlink creation failed for one or more agent files — fell back to a copy. 드리프트 방지가 꺼졌다."
    fi
}

# EN: Merge the 6 hook entries from this repo's settings.json into the
#     target's settings.json. For each event: if an entry already references
#     harness/hooks/gate.py, replace it in place; otherwise append it. Other
#     hooks in the target are left untouched.
# KO: 이 저장소 settings.json 의 훅 6개를 대상 settings.json 에 병합한다.
#     이벤트마다: harness/hooks/gate.py 를 참조하는 기존 항목이 있으면 치환,
#     없으면 append. 대상의 다른 훅은 건드리지 않는다.
merge_settings() {
    local target="$1"
    local epoch="$2"
    local src_settings="$REPO_ROOT/.claude/settings.json"
    local dst_settings="$target/.claude/settings.json"

    mkdir -p "$target/.claude"
    if [ ! -f "$dst_settings" ]; then
        echo '{"hooks":{}}' >"$dst_settings"
    else
        cp "$dst_settings" "$dst_settings.bak-$epoch"
    fi

    local merged="$dst_settings.tmp-$$"
    TMP_FILES+=("$merged")
    cp "$dst_settings" "$merged"

    for event in "${HOOK_EVENTS[@]}"; do
        # EN: src_entries is the array of hook-entry objects for this event in
        #     this repo's own settings.json (normally one entry). Drop any
        #     existing target entry whose command already references
        #     harness/hooks/gate.py (replace-in-place semantics), then append
        #     the source entries (covers both replace and first-time append).
        # KO: src_entries 는 이 저장소 settings.json 에서 이 이벤트의 훅 항목
        #     배열이다(보통 1개). 대상에 이미 harness/hooks/gate.py 를 참조하는
        #     항목이 있으면 제거한 뒤(치환 의미) 소스 항목을 append 한다
        #     (치환과 최초 append 둘 다 이 한 연산으로 처리된다).
        local src_entries
        src_entries="$(jq -c --arg ev "$event" '.hooks[$ev]' "$src_settings")"
        local tmp2="$merged.next"
        jq --arg ev "$event" --argjson src "$src_entries" '
            ((.hooks[$ev] // []) | map(
                select((.hooks // []) | any(.command // "" | contains("harness/hooks/gate.py")) | not)
            )) as $kept
            | .hooks[$ev] = ($kept + $src)
        ' "$merged" >"$tmp2"
        mv "$tmp2" "$merged"
    done

    mv "$merged" "$dst_settings"
}

create_harness_json() {
    local target="$1"
    local dst="$target/.claude/harness.json"
    if [ -f "$dst" ]; then
        log "$dst already exists — leaving it untouched."
        return
    fi
    mkdir -p "$target/.claude"
    # EN: Write every key gate.py reads, even where the value equals the built-in
    #     default. A three-key file left approval_gate, close_gate, verifiers and
    #     write_agents to silently fall back — and their falsy defaults mean the
    #     approval and close gates were OFF while the file said nothing about it.
    #     Reading this file has to answer "which gates are live?" on its own.
    # KO: gate.py 가 읽는 키를 전부 쓴다. 값이 내장 기본값과 같아도 쓴다. 세 키만 쓰던
    #     파일은 approval_gate·close_gate·verifiers·write_agents 를 조용히 기본값에
    #     맡겼고, 그 기본값이 falsy 라서 승인 게이트와 close 게이트가 꺼진 채였는데
    #     파일에는 그런 말이 한 줄도 없었다. 이 파일만 읽고 "어떤 게이트가 살아 있나"에
    #     답할 수 있어야 한다.
    cat >"$dst" <<'EOF'
{
  "enforce": false,
  "product": ["docs/**", "harness/**"],
  "exempt": [],
  "main_thread_file_limit": 2,
  "verifiers": ["critic"],
  "write_agents": ["maker"],
  "approval_gate": true,
  "close_gate": true,
  "max_close_blocks": 2,
  "metrics": true
}
EOF
}

verify_install() {
    local target="$1"
    local failed=0

    if python3 "$target/harness/tests/test_gate.py"; then
        log "검증 1/5 OK: test_gate.py exit 0"
    else
        log "검증 1/5 FAIL: test_gate.py"
        failed=1
    fi

    local link_fail=0
    for name in "${AGENT_NAMES[@]}"; do
        local link="$target/.claude/agents/$name.md"
        if [ ! -e "$link" ]; then
            link_fail=1
        fi
    done
    if [ "$link_fail" -eq 0 ]; then
        log "검증 2/5 OK: 에이전트 링크 5개가 전부 존재하는 파일로 풀린다"
    else
        log "검증 2/5 FAIL: 에이전트 링크 중 최소 1개가 풀리지 않는다"
        failed=1
    fi

    local event_count
    event_count="$(jq '.hooks | keys | length' "$target/.claude/settings.json")"
    if [ "$event_count" -ge 6 ]; then
        log "검증 3/5 OK: settings.json 에 훅 이벤트 $event_count 개"
    else
        log "검증 3/5 FAIL: settings.json 에 훅 이벤트 $event_count 개 (< 6)"
        failed=1
    fi

    local enforce_val
    enforce_val="$(jq -r '.enforce' "$target/.claude/harness.json")"
    if [ "$enforce_val" = "false" ]; then
        log "검증 4/5 OK: enforce == false. 실사용 1세션 후 true 로 바꾸라."
    else
        log "검증 4/5 FAIL: enforce == $enforce_val (expected false)"
        failed=1
    fi

    # EN: Every file the installer claims to place must actually be there — a
    #     missing one is silent until some later hook needs it.
    # KO: 설치기가 놓는다고 한 파일이 전부 실제로 있어야 한다 — 하나가 빠지면
    #     나중에 어떤 훅이 그것을 필요로 할 때까지 드러나지 않는다.
    local missing=0 rel
    for rel in "${HARNESS_FILES[@]}"; do
        [ -f "$target/harness/$rel" ] || { log "  missing: harness/$rel"; missing=1; }
    done
    if [ "$missing" -eq 0 ]; then
        log "검증 5/5 OK: 소스 파일 ${#HARNESS_FILES[@]} 개가 전부 자리에 있다"
    else
        log "검증 5/5 FAIL: 설치돼야 할 파일이 빠졌다"
        failed=1
    fi

    return "$failed"
}

# EN: Verify the result of do_install_global (exit != 0 on any failure):
#     both markers appear exactly once, the block byte-matches the source, and
#     all 5 role files under ~/.claude/agents byte-match harness/agents/*.md.
# KO: do_install_global 결과를 검증한다(실패 시 exit != 0): 마커 2개가 각각
#     정확히 1번, 블록이 소스와 바이트 동일, ~/.claude/agents 의 역할 5개가
#     harness/agents/*.md 와 바이트 동일.
verify_install_global() {
    # EN/KO: 설치·제거와 같은 경로를 봐야 한다 (N-3). 심링크 구성에서 이 함수만 링크
    #        경로를 쓰면, 검증이 방금 쓴 파일이 아닌 다른 것을 볼 수 있다.
    local target
    target="$(resolve_if_symlink "$HOME/.claude/CLAUDE.md")"
    local failed=0

    local begin_count end_count
    begin_count="$(grep -c -F "$MARKER_BEGIN" "$target" || true)"
    end_count="$(grep -c -F "$MARKER_END" "$target" || true)"
    if [ "$begin_count" -eq 1 ] && [ "$end_count" -eq 1 ]; then
        log "검증 OK: 마커가 각각 정확히 1개"
    else
        log "검증 FAIL: BEGIN $begin_count 개, END $end_count 개 (기대: 각 1개)"
        failed=1
    fi

    local extracted="$target.extract-$$"
    TMP_FILES+=("$extracted")
    python3 - "$target" "$MARKER_BEGIN" "$MARKER_END" "$extracted" <<'PYEOF'
import sys

target, begin, end, out = sys.argv[1:5]
with open(target, "r", encoding="utf-8") as f:
    text = f.read()
start = text.index(begin) + len(begin)
finish = text.index(end)
block = text[start:finish].strip("\n") + "\n"
with open(out, "w", encoding="utf-8") as f:
    f.write(block)
PYEOF
    if cmp -s "$extracted" "$HARNESS_SRC/global/CLAUDE.harness.md"; then
        log "검증 OK: 블록 내용이 소스와 바이트 동일"
    else
        log "검증 FAIL: 블록 내용이 소스와 다르다"
        failed=1
    fi

    local name
    local agents_ok=1
    for name in "${AGENT_NAMES[@]}"; do
        if ! cmp -s "$HARNESS_SRC/agents/$name.md" "$HOME/.claude/agents/$name.md"; then
            log "검증 FAIL: $name.md 가 소스와 다르다"
            failed=1
            agents_ok=0
        fi
    done
    if [ "$agents_ok" -eq 1 ]; then
        log "검증 OK: 에이전트 5개가 소스와 바이트 동일"
    fi

    return "$failed"
}

# EN: True (exit 0) only if all 5 agent role files under $1 already byte-match
#     this repo's source — i.e. this install would not change anything there.
#     Reuses the cmp -s predicate from copy_with_backup rather than diff -r,
#     which always reports a difference here: the target directory may hold
#     the user's own extra agent files that the source never has (D3).
# KO: $1 아래 에이전트 역할 파일 5개가 전부 이 저장소 소스와 바이트 동일할 때만
#     참(exit 0) — 즉 이번 설치가 거기서 아무것도 바꾸지 않는다는 뜻이다.
#     copy_with_backup 의 cmp -s 선례를 재사용한다 — diff -r 은 항상 다르다고
#     답한다: 대상 디렉터리엔 사용자 자신의 다른 에이전트 파일이 있을 수 있고
#     소스에는 정확히 5개뿐이기 때문이다(D3).
agents_dir_unchanged() {
    local dir="$1" name
    for name in "${AGENT_NAMES[@]}"; do
        if ! cmp -s "$HARNESS_SRC/agents/$name.md" "$dir/$name.md" 2>/dev/null; then
            return 1
        fi
    done
    return 0
}

# EN: Install/update the harness-managed block of the user's global
#     ~/.claude/CLAUDE.md and the 5 role definitions under ~/.claude/agents/,
#     as real files (not symlinks — a global setting must survive this repo
#     moving or changing branch). If either path is itself a symlink (e.g. a
#     dotfiles setup), it is resolved to its physical target first, so writes
#     land there instead of silently replacing the symlink. A backup is made
#     only when the install would actually change something, and only right
#     before the mutation that would change it.
# KO: 사용자 전역 ~/.claude/CLAUDE.md 의 하네스 관리 블록과 ~/.claude/agents/
#     아래 역할 정의 5개를 실파일로(심링크 아님 — 전역 설정은 이 저장소가
#     옮겨지거나 브랜치가 바뀌어도 살아남아야 한다) 설치·갱신한다. 둘 중 하나가
#     심링크(예: dotfiles 구성)면 먼저 물리 경로로 해석해 그 경로에 쓴다 —
#     심링크를 조용히 실파일/실디렉터리로 대체하지 않는다. 백업은 이번 설치가
#     실제로 뭔가를 바꿀 때만, 그 변형 직전에만 만든다.
do_install_global() {
    require_python3
    local epoch
    epoch="$(epoch_now)"
    local global_claude="$HOME/.claude/CLAUDE.md"
    local global_agents_dir="$HOME/.claude/agents"
    global_claude="$(resolve_if_symlink "$global_claude")"
    global_agents_dir="$(resolve_if_symlink "$global_agents_dir")"

    # EN/KO: 해석된 경로의 부모를 만든다 (N-4). $HOME/.claude 를 무조건 만들면, 두 경로가
    #        모두 dotfiles 로 해석된 구성에서는 아무 일도 하지 않으면서 정작 필요한
    #        디렉터리는 안 만들어진다.
    mkdir -p "$(dirname "$global_claude")" "$(dirname "$global_agents_dir")"

    # 1. Backup the agents directory, but only if this install would actually
    #    change something under it (N4) — per-file backups in step 2 already
    #    cover byte-identical files individually.
    if [ -d "$global_agents_dir" ] && ! agents_dir_unchanged "$global_agents_dir"; then
        cp -R "$global_agents_dir" "$global_agents_dir.bak-$epoch" || {
            log "ERROR: backup of $global_agents_dir failed. Aborting — nothing changed."
            exit 1
        }
        log "backed up existing $global_agents_dir -> $global_agents_dir.bak-$epoch"
    fi

    # 2. Copy the 5 role definitions as real files.
    mkdir -p "$global_agents_dir"
    local name
    for name in "${AGENT_NAMES[@]}"; do
        copy_with_backup "$HARNESS_SRC/agents/$name.md" "$global_agents_dir/$name.md" "$epoch"
    done

    # 3. Merge the HARNESS marker block into a tmp file. $global_claude itself
    #    is untouched until the mv below.
    local merged="$global_claude.tmp-$$"
    TMP_FILES+=("$merged")
    if ! merge_marker_block "$global_claude" "$HARNESS_SRC/global/CLAUDE.harness.md" "$merged"; then
        log ""
        log "수동 절차: $global_claude 에서 $MARKER_BEGIN / $MARKER_END 마커를 직접 확인해 고치세요."
        log "           (한쪽만 있거나 순서가 뒤집혀 있으면 자동 병합을 하지 않습니다.)"
        exit 1
    fi
    # Backup right before the only mutation of $global_claude, and only if it
    # would actually change (N4).
    if [ -f "$global_claude" ] && ! cmp -s "$merged" "$global_claude"; then
        cp "$global_claude" "$global_claude.bak-$epoch" || {
            log "ERROR: backup of $global_claude failed. Aborting — nothing changed."
            exit 1
        }
        log "backed up existing $global_claude -> $global_claude.bak-$epoch"
    fi
    mv "$merged" "$global_claude"

    # 4. Verify.
    verify_install_global
}

# EN: Remove the HARNESS marker block (markers included) from ~/.claude/CLAUDE.md,
#     leaving everything outside it byte-for-byte intact, and delete only the
#     role files under ~/.claude/agents that still byte-match this repo's
#     source — a file the user hand-edited stays. Backups are never deleted.
#     If either path is itself a symlink (e.g. a dotfiles setup), it is
#     resolved to its physical target first, so the edit lands there instead
#     of silently replacing the symlink with a plain file.
# KO: ~/.claude/CLAUDE.md 에서 HARNESS 마커 블록을 마커 줄 포함 제거하고 그
#     밖은 그대로 두며, ~/.claude/agents 아래 역할 파일 중 이 저장소 소스와
#     여전히 바이트 동일한 것만 지운다 — 사용자가 손으로 고친 파일은 남는다.
#     백업은 지우지 않는다. 둘 중 하나가 심링크(예: dotfiles 구성)면 먼저 물리
#     경로로 해석해 그 경로를 고친다 — 심링크를 조용히 실파일로 대체하지 않는다.
do_uninstall_global() {
    require_python3
    local global_claude="$HOME/.claude/CLAUDE.md"
    local global_agents_dir="$HOME/.claude/agents"
    global_claude="$(resolve_if_symlink "$global_claude" tolerate-dangling)"
    global_agents_dir="$(resolve_if_symlink "$global_agents_dir" tolerate-dangling)"

    # EN/KO: 끊긴 링크는 하네스가 남긴 잔해다. 제거가 그것을 치우는 자리다 (N-5).
    local dead
    for dead in "$global_claude" "$global_agents_dir"; do
        if [ -L "$dead" ] && [ ! -e "$dead" ]; then
            rm -f "$dead"
            log "removed dangling symlink $dead"
        fi
    done

    if [ -f "$global_claude" ]; then
        local begin_count end_count
        begin_count="$(grep -c -F "$MARKER_BEGIN" "$global_claude" || true)"
        end_count="$(grep -c -F "$MARKER_END" "$global_claude" || true)"
        if [ "$begin_count" -eq 1 ] && [ "$end_count" -eq 1 ]; then
            local out="$global_claude.tmp-$$"
            TMP_FILES+=("$out")
            python3 - "$global_claude" "$MARKER_BEGIN" "$MARKER_END" "$out" <<'PYEOF'
import sys

target, begin, end, out = sys.argv[1:5]
with open(target, "r", encoding="utf-8") as f:
    text = f.read()
start = text.index(begin)
finish = text.index(end) + len(end)
before = text[:start].rstrip("\n")
after = text[finish:]
if after.startswith("\n"):
    after = after[1:]
if before and after:
    text = before + "\n\n" + after
elif before:
    text = before + "\n"
else:
    text = after
with open(out, "w", encoding="utf-8") as f:
    f.write(text)
PYEOF
            mv "$out" "$global_claude"
            log "removed HARNESS marker block from $global_claude (content outside markers preserved)"
        elif [ "$begin_count" -eq 0 ] && [ "$end_count" -eq 0 ]; then
            log "$global_claude has no HARNESS marker block — nothing to remove."
        else
            log "ERROR: $global_claude has BEGIN $begin_count / END $end_count — only one marker present."
            log "       Aborting — fix by hand."
            exit 1
        fi
    fi

    local name
    for name in "${AGENT_NAMES[@]}"; do
        local f="$global_agents_dir/$name.md"
        if [ -f "$f" ] && cmp -s "$HARNESS_SRC/agents/$name.md" "$f"; then
            rm -f "$f"
        fi
    done

    log "global harness backups (CLAUDE.md.bak-* / agents.bak-*) left in place."
}

do_install() {
    local target="$1"
    local epoch
    epoch="$(epoch_now)"
    require_jq
    require_valid_target_settings "$target"
    install_files "$target" "$epoch"
    merge_settings "$target" "$epoch"
    create_harness_json "$target"
    verify_install "$target"
}

# EN: Unwire the hooks BEFORE deleting gate.py. A settings.json that still names
#     a deleted gate.py makes PreToolUse exit 2 — the deny signal — so every tool
#     call in that project is refused. Restoring from a .bak is not enough: a
#     project that had no settings.json before install has no .bak at all.
#     So remove our entries surgically with jq, the same selector the merge uses.
# KO: gate.py 를 지우기 전에 훅부터 뗀다. 지워진 gate.py 를 가리키는 settings.json 은
#     PreToolUse 를 exit 2 — 거부 신호 — 로 만들어 그 프로젝트의 모든 툴 호출이
#     거부된다. .bak 복원으로는 부족하다: 설치 전에 settings.json 이 없던 프로젝트는
#     .bak 자체가 없다. 그래서 병합이 쓰는 것과 같은 선택자로 우리 항목만 걷어낸다.
unwire_hooks() {
    local dst_settings="$1"
    [ -f "$dst_settings" ] || return 0
    if ! jq empty "$dst_settings" 2>/dev/null; then
        log "WARNING: $dst_settings is not valid JSON — leaving it untouched."
        log "         Remove the harness/hooks/gate.py entries by hand."
        return 0
    fi
    local tmp="$dst_settings.tmp-$$"
    TMP_FILES+=("$tmp")
    jq '
        .hooks = ((.hooks // {}) | with_entries(
            .value |= map(
                select((.hooks // []) | any(.command // "" | contains("harness/hooks/gate.py")) | not)
            )
        ) | with_entries(select(.value | length > 0)))
    ' "$dst_settings" >"$tmp"
    mv "$tmp" "$dst_settings"
    log "removed harness gate hooks from $dst_settings (other hooks preserved)"
}

do_uninstall() {
    local target="$1"

    unwire_hooks "$target/.claude/settings.json"

    for name in "${AGENT_NAMES[@]}"; do
        local link="$target/.claude/agents/$name.md"
        # EN: Only remove what we created — a symlink into harness/agents, or the
        #     copy we fell back to. A file the project wrote itself stays.
        # KO: 우리가 만든 것만 지운다 — harness/agents 로 가는 심링크, 또는 심링크가
        #     안 될 때 대신 둔 사본. 프로젝트가 스스로 쓴 파일은 남긴다.
        if [ -L "$link" ]; then
            rm -f "$link"
        elif [ -f "$link" ] && cmp -s "$HARNESS_SRC/agents/$name.md" "$link"; then
            rm -f "$link"
        fi
    done

    local rel
    for rel in "${HARNESS_FILES[@]}"; do
        rm -f "$target/harness/$rel"
    done
    # EN: Remove only the directories we created, and only if they are now empty.
    # KO: 우리가 만든 디렉터리만, 그것도 비었을 때만 지운다.
    for rel in hooks tests tools agents; do
        rmdir "$target/harness/$rel" 2>/dev/null || true
    done
    rmdir "$target/harness" 2>/dev/null || true
    if [ -d "$target/harness" ]; then
        log "$target/harness kept — it still holds files this installer did not create."
    fi

    log "harness.json left in place (may hold user settings)."
}

main() {
    if [ "${1:-}" = "--global" ]; then
        if [ "${2:-}" = "--uninstall" ]; then
            do_uninstall_global
            exit 0
        fi
        do_install_global
        exit 0
    fi

    if [ "${1:-}" = "--uninstall" ]; then
        [ -n "${2:-}" ] || { usage; exit 1; }
        do_uninstall "$2"
        exit 0
    fi

    [ -n "${1:-}" ] || { usage; exit 1; }
    do_install "$1"
}

main "$@"
