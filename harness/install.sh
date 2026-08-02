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
cleanup_tmp() {
    local f
    for f in "${TMP_FILES[@]:-}"; do
        [ -n "$f" ] && rm -f "$f" "$f.next"
    done
}
trap cleanup_tmp EXIT

usage() {
    cat <<'EOF'
Usage:
  harness/install.sh <target-project-dir>
  harness/install.sh --uninstall <target-project-dir>
EOF
}

log() { printf '%s\n' "$*" >&2; }

epoch_now() { date +%s; }

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

# EN: Copy a source file over a target path, snapshotting any pre-existing target
#     file to <path>.bak-<epoch> first. The installer must never silently destroy
#     something the project already had there.
# KO: 소스 파일을 대상 경로에 복사하되, 기존 파일이 있으면 먼저 <path>.bak-<epoch>
#     로 떠 둔다. 설치기가 프로젝트에 이미 있던 것을 조용히 없애서는 안 된다.
copy_with_backup() {
    local src="$1" dst="$2" epoch="$3"
    if [ -e "$dst" ] || [ -L "$dst" ]; then
        if ! cmp -s "$src" "$dst" 2>/dev/null; then
            cp -P "$dst" "$dst.bak-$epoch"
            log "backed up existing $dst -> $dst.bak-$epoch"
        fi
    fi
    rm -f "$dst"
    cp "$src" "$dst"
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
    cat >"$dst" <<'EOF'
{
  "enforce": false,
  "product": ["docs/**", "harness/**"],
  "exempt": []
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
    if [ "${1:-}" = "--uninstall" ]; then
        [ -n "${2:-}" ] || { usage; exit 1; }
        do_uninstall "$2"
        exit 0
    fi

    [ -n "${1:-}" ] || { usage; exit 1; }
    do_install "$1"
}

main "$@"
