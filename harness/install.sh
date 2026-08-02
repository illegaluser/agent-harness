#!/usr/bin/env bash
# EN: Installer for the enforcement-first harness (CORE.md + gate.py + 5 agent
#     roles) into a target project P. Copies the 7 source files, symlinks the
#     5 agent role definitions into P/.claude/agents/, merges the 6 hook
#     entries into P/.claude/settings.json, and creates P/.claude/harness.json
#     (enforce: false) if it does not already exist. See docs/PLAN_HARNESS_
#     REDESIGN.md Phase 4 for the design rationale.
# KO: 집행 우선 하네스(CORE.md·gate.py·역할 5개)를 대상 프로젝트 P 에 설치한다.
#     소스 파일 7개를 복사하고, 역할 정의 5개를 P/.claude/agents/ 에 심링크로
#     걸고, 훅 6개를 P/.claude/settings.json 에 병합하고, P/.claude/harness.json
#     이 없을 때만 만든다(enforce: false). 설계 근거는
#     docs/PLAN_HARNESS_REDESIGN.md Phase 4.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_SRC="$SCRIPT_DIR"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT_NAMES=(scout architect maker critic referee)
HOOK_EVENTS=(PreToolUse PostToolUse Stop SubagentStop SessionStart SubagentStart)

usage() {
    cat <<'EOF'
Usage:
  harness/install.sh <target-project-dir>
  harness/install.sh --uninstall <target-project-dir>
EOF
}

log() { printf '%s\n' "$*" >&2; }

# EN: Fail fast and loud if jq is missing — never edit JSON with sed.
# KO: jq 가 없으면 즉시 중단 — JSON 을 sed 로 편집하지 않는다.
require_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        log "ERROR: jq is required and was not found on PATH."
        log ""
        log "수동 설치 절차 (jq 없이):"
        log "  1. cp -R \"$HARNESS_SRC/CORE.md\" \"$HARNESS_SRC/hooks\" \"$HARNESS_SRC/tests\" \"$HARNESS_SRC/agents\" <target>/harness/"
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

install_files() {
    local target="$1"
    mkdir -p "$target/harness/hooks" "$target/harness/tests" "$target/harness/agents"
    mkdir -p "$target/.claude/agents"

    cp "$HARNESS_SRC/CORE.md" "$target/harness/CORE.md"
    cp "$HARNESS_SRC/hooks/gate.py" "$target/harness/hooks/gate.py"
    chmod 0755 "$target/harness/hooks/gate.py"
    cp "$HARNESS_SRC/tests/test_gate.py" "$target/harness/tests/test_gate.py"

    local drift_off=0
    for name in "${AGENT_NAMES[@]}"; do
        cp "$HARNESS_SRC/agents/$name.md" "$target/harness/agents/$name.md"
        local link="$target/.claude/agents/$name.md"
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
    local src_settings="$REPO_ROOT/.claude/settings.json"
    local dst_settings="$target/.claude/settings.json"

    mkdir -p "$target/.claude"
    if [ ! -f "$dst_settings" ]; then
        echo '{"hooks":{}}' >"$dst_settings"
    else
        local epoch
        epoch="$(date +%s)"
        cp "$dst_settings" "$dst_settings.bak-$epoch"
    fi

    local merged="$dst_settings.tmp-$$"
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
        log "검증 1/4 OK: test_gate.py exit 0"
    else
        log "검증 1/4 FAIL: test_gate.py"
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
        log "검증 2/4 OK: 에이전트 링크 5개가 전부 존재하는 파일로 풀린다"
    else
        log "검증 2/4 FAIL: 에이전트 링크 중 최소 1개가 풀리지 않는다"
        failed=1
    fi

    local event_count
    event_count="$(jq '.hooks | keys | length' "$target/.claude/settings.json")"
    if [ "$event_count" -ge 6 ]; then
        log "검증 3/4 OK: settings.json 에 훅 이벤트 $event_count 개"
    else
        log "검증 3/4 FAIL: settings.json 에 훅 이벤트 $event_count 개 (< 6)"
        failed=1
    fi

    local enforce_val
    enforce_val="$(jq -r '.enforce' "$target/.claude/harness.json")"
    if [ "$enforce_val" = "false" ]; then
        log "검증 4/4 OK: enforce == false. 실사용 1세션 후 true 로 바꾸라."
    else
        log "검증 4/4 FAIL: enforce == $enforce_val (expected false)"
        failed=1
    fi

    return "$failed"
}

run_shellcheck_self() {
    if command -v shellcheck >/dev/null 2>&1; then
        shellcheck "$SCRIPT_DIR/install.sh" || true
    fi
}

do_install() {
    local target="$1"
    require_jq
    install_files "$target"
    merge_settings "$target"
    create_harness_json "$target"
    verify_install "$target"
}

do_uninstall() {
    local target="$1"
    for name in "${AGENT_NAMES[@]}"; do
        rm -f "$target/.claude/agents/$name.md"
    done
    rm -rf "$target/harness"

    local dst_settings="$target/.claude/settings.json"
    # EN: Backup names are settings.json.bak-<epoch> — epoch is a fixed-width
    #     decimal for the foreseeable future, so a lexicographic sort is also
    #     a chronological sort. No `ls`, per SC2012.
    # KO: 백업 이름은 settings.json.bak-<epoch> — epoch 는 당분간 자릿수가
    #     고정된 십진수이므로 사전순 정렬이 곧 시간순 정렬이다. SC2012 에 따라
    #     `ls` 대신 `find` 를 쓴다.
    local latest_bak
    latest_bak="$(find "$(dirname "$dst_settings")" -maxdepth 1 -name "$(basename "$dst_settings").bak-*" 2>/dev/null \
        | sort | tail -1)"
    if [ -n "$latest_bak" ]; then
        cp "$latest_bak" "$dst_settings"
        log "settings.json restored from $latest_bak"
    else
        log "WARNING: no settings.json.bak-* found — settings.json left as-is."
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
