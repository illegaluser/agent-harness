#!/usr/bin/env bash
# EN: Regression tests for harness/install.sh's --global path (W3/W4/W5/N4 fix).
#     Every case runs the real installer against a throwaway $HOME made with
#     mktemp -d — the actual $HOME is never touched. Run:
#       bash harness/tests/test_install_global.sh
# KO: harness/install.sh 의 --global 경로 회귀 테스트 (W3/W4/W5/N4 수정 검증).
#     각 케이스는 mktemp -d 로 만든 일회용 $HOME 을 대상으로 실제 설치기를
#     돌린다 — 실제 $HOME 은 절대 건드리지 않는다. 실행:
#       bash harness/tests/test_install_global.sh
set -u

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL="$HARNESS_DIR/install.sh"

MARKER_BEGIN='<!-- HARNESS:BEGIN -->'
MARKER_END='<!-- HARNESS:END -->'
AGENT_NAMES=(scout architect maker critic referee)

failures=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s — %s\n' "$1" "$2"; failures=$((failures + 1)); }

new_home() { mktemp -d; }

# Run the installer with $HOME=$1 and the given args; stdout+stderr go to
# $1/.install-out, exit code is echoed.
run_install() {
    local h="$1"
    shift
    env HOME="$h" bash "$INSTALL" "$@" >"$h/.install-out" 2>&1
    echo "$?"
}

count_direct() {
    # Count entries directly inside dir $1 whose name matches glob $2
    # (mindepth/maxdepth 1 — direct children only, excludes $1 itself and
    # anything nested deeper).
    find "$1" -mindepth 1 -maxdepth 1 -name "$2" 2>/dev/null | wc -l | tr -d ' '
}

agents_match_source() {
    local dir="$1" name
    for name in "${AGENT_NAMES[@]}"; do
        cmp -s "$HARNESS_DIR/agents/$name.md" "$dir/$name.md" || return 1
    done
    return 0
}

# --- Case 1: fresh empty $HOME -------------------------------------------
case1() {
    local label='1 빈 HOME 설치'
    local h rc
    h="$(new_home)"
    rc="$(run_install "$h" --global)"

    if [ "$rc" != "0" ]; then
        fail "$label" "exit $rc, expected 0: $(cat "$h/.install-out")"
        rm -rf "$h"
        return
    fi
    local begin_n end_n
    begin_n="$(grep -c -F "$MARKER_BEGIN" "$h/.claude/CLAUDE.md")"
    end_n="$(grep -c -F "$MARKER_END" "$h/.claude/CLAUDE.md")"
    if [ "$begin_n" != "1" ] || [ "$end_n" != "1" ]; then
        fail "$label" "marker counts begin=$begin_n end=$end_n"
    elif ! agents_match_source "$h/.claude/agents"; then
        fail "$label" "agent files do not byte-match source"
    elif [ "$(count_direct "$h/.claude" '*.bak-*')" != "0" ]; then
        fail "$label" "unexpected .bak-* on a fresh install"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 2: run twice — second run makes no new backups (N4) ------------
case2() {
    local label='2 연속 2회 — N4'
    local h
    h="$(new_home)"
    run_install "$h" --global >/dev/null
    run_install "$h" --global >/dev/null
    if [ "$(count_direct "$h/.claude" '*.bak-*')" != "0" ]; then
        fail "$label" "second run created a backup when nothing changed"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 3a: one agent file corrupted, then reinstalled ------------------
case3a() {
    local label='3a 에이전트 1개 훼손 후 재실행'
    local h
    h="$(new_home)"
    run_install "$h" --global >/dev/null
    printf '\nCORRUPTED\n' >>"$h/.claude/agents/scout.md"
    run_install "$h" --global >/dev/null

    if [ "$(count_direct "$h/.claude" 'agents.bak-*')" != "1" ]; then
        fail "$label" "expected exactly 1 agents.bak-*, got $(count_direct "$h/.claude" 'agents.bak-*')"
    elif ! cmp -s "$HARNESS_DIR/agents/scout.md" "$h/.claude/agents/scout.md"; then
        fail "$label" "scout.md was not restored to source"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 3b: content inside markers corrupted, then reinstalled ---------
case3b() {
    local label='3b 마커 안쪽 훼손 후 재실행'
    local h
    h="$(new_home)"
    run_install "$h" --global >/dev/null
    local first_line
    first_line="$(head -n 1 "$HARNESS_DIR/global/CLAUDE.harness.md")"
    python3 - "$h/.claude/CLAUDE.md" "$first_line" <<'PYEOF'
import sys
target, first_line = sys.argv[1:3]
with open(target, "r", encoding="utf-8") as f:
    text = f.read()
text = text.replace(first_line, "CORRUPTED LINE", 1)
with open(target, "w", encoding="utf-8") as f:
    f.write(text)
PYEOF
    run_install "$h" --global >/dev/null

    if [ "$(count_direct "$h/.claude" 'CLAUDE.md.bak-*')" != "1" ]; then
        fail "$label" "expected exactly 1 CLAUDE.md.bak-*, got $(count_direct "$h/.claude" 'CLAUDE.md.bak-*')"
    elif grep -q 'CORRUPTED LINE' "$h/.claude/CLAUDE.md"; then
        fail "$label" "corrupted content still present after reinstall"
    elif ! grep -q -F "$first_line" "$h/.claude/CLAUDE.md"; then
        fail "$label" "block was not restored to source"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 4: CLAUDE.md is a symlink into a dotfiles dir (W4) --------------
case4() {
    local label='4 CLAUDE.md 심링크 (W4)'
    local h
    h="$(new_home)"
    mkdir -p "$h/dotfiles" "$h/.claude"
    printf 'my own notes\nmore notes\n' >"$h/dotfiles/CLAUDE.md"
    ln -s "$h/dotfiles/CLAUDE.md" "$h/.claude/CLAUDE.md"

    local rc
    rc="$(run_install "$h" --global)"
    if [ "$rc" != "0" ]; then
        fail "$label" "exit $rc: $(cat "$h/.install-out")"
    elif [ ! -L "$h/.claude/CLAUDE.md" ]; then
        fail "$label" "symlink was replaced with a real file"
    elif [ "$(grep -c -F "$MARKER_BEGIN" "$h/dotfiles/CLAUDE.md")" != "1" ]; then
        fail "$label" "block did not land in the dotfiles real file"
    elif ! grep -q 'my own notes' "$h/dotfiles/CLAUDE.md"; then
        fail "$label" "user prose outside the markers was lost"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 5: agents dir is a symlink into a dotfiles dir (W3) -------------
case5() {
    local label='5 agents 심링크 (W3)'
    local h
    h="$(new_home)"
    mkdir -p "$h/dotfiles/agents" "$h/.claude"
    printf 'my custom agent\n' >"$h/dotfiles/agents/myagent.md"
    ln -s "$h/dotfiles/agents" "$h/.claude/agents"

    local rc
    rc="$(run_install "$h" --global)"
    if [ "$rc" != "0" ]; then
        fail "$label" "exit $rc: $(cat "$h/.install-out")"
    elif [ ! -L "$h/.claude/agents" ]; then
        fail "$label" "symlink was replaced with a real directory"
    elif ! agents_match_source "$h/dotfiles/agents"; then
        fail "$label" "the 5 role files are not in the dotfiles real dir"
    elif [ "$(cat "$h/dotfiles/agents/myagent.md")" != "my custom agent" ]; then
        fail "$label" "user's own myagent.md was altered"
    else
        local bak_n bak_dir
        bak_n="$(count_direct "$h/dotfiles" 'agents.bak-*')"
        bak_dir="$(find "$h/dotfiles" -mindepth 1 -maxdepth 1 -name 'agents.bak-*' | head -n 1)"
        if [ "$bak_n" != "1" ]; then
            fail "$label" "expected 1 agents.bak-* next to the resolved dir, got $bak_n"
        elif [ -L "$bak_dir" ]; then
            fail "$label" "backup is itself a symlink"
        elif [ ! -f "$bak_dir/myagent.md" ]; then
            fail "$label" "backup does not contain a copy of myagent.md"
        else
            pass "$label"
        fi
    fi
    rm -rf "$h"
}

# --- Case 6: CLAUDE.md is a dangling symlink ------------------------------
case6() {
    local label='6 끊긴 CLAUDE.md 심링크'
    local h
    h="$(new_home)"
    mkdir -p "$h/.claude"
    ln -s "$h/does-not-exist/CLAUDE.md" "$h/.claude/CLAUDE.md"

    local rc
    rc="$(run_install "$h" --global)"
    if [ "$rc" = "0" ]; then
        fail "$label" "expected non-zero exit on a dangling symlink"
    elif [ -d "$h/.claude/agents" ] && [ "$(count_direct "$h/.claude/agents" '*')" != "0" ]; then
        fail "$label" "agent files were written despite the abort"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 7: agents dir is a dangling symlink -----------------------------
case7() {
    local label='7 끊긴 agents 심링크'
    local h
    h="$(new_home)"
    mkdir -p "$h/.claude"
    printf 'user prose only\n' >"$h/.claude/CLAUDE.md"
    ln -s "$h/does-not-exist/agents" "$h/.claude/agents"

    local rc
    rc="$(run_install "$h" --global)"
    if [ "$rc" = "0" ]; then
        fail "$label" "expected non-zero exit on a dangling symlink"
    elif [ "$(cat "$h/.claude/CLAUDE.md")" != "user prose only" ]; then
        fail "$label" "CLAUDE.md was touched despite the abort"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

# --- Case 8: uninstall from the case-4 (symlinked CLAUDE.md) state -------
case8() {
    local label='8 케이스4 상태에서 --global --uninstall'
    local h
    h="$(new_home)"
    mkdir -p "$h/dotfiles" "$h/.claude"
    printf 'my own notes\nmore notes\n' >"$h/dotfiles/CLAUDE.md"
    ln -s "$h/dotfiles/CLAUDE.md" "$h/.claude/CLAUDE.md"
    run_install "$h" --global >/dev/null

    local rc
    rc="$(run_install "$h" --global --uninstall)"
    if [ "$rc" != "0" ]; then
        fail "$label" "exit $rc: $(cat "$h/.install-out")"
    elif [ ! -L "$h/.claude/CLAUDE.md" ]; then
        fail "$label" "symlink was replaced with a real file"
    elif grep -q -F "$MARKER_BEGIN" "$h/dotfiles/CLAUDE.md"; then
        fail "$label" "marker block was not removed"
    elif ! grep -q 'my own notes' "$h/dotfiles/CLAUDE.md"; then
        fail "$label" "user prose outside the markers was lost"
    else
        local name still_there=0
        for name in "${AGENT_NAMES[@]}"; do
            [ -f "$h/.claude/agents/$name.md" ] && still_there=1
        done
        if [ "$still_there" = "1" ]; then
            fail "$label" "not all 5 agent files were removed"
        else
            pass "$label"
        fi
    fi
    rm -rf "$h"
}

# --- Case 9: python3 missing from PATH (W5) -------------------------------
case9() {
    local label='9 python3 없는 PATH (W5)'
    local h bash_bin rc out
    h="$(new_home)"
    bash_bin="$(command -v bash)"
    out="$(env -i HOME="$h" PATH="" "$bash_bin" "$INSTALL" --global 2>&1)"
    rc=$?

    if [ "$rc" = "0" ]; then
        fail "$label" "expected non-zero exit without python3"
    elif ! printf '%s' "$out" | grep -qi 'python3'; then
        fail "$label" "stderr did not mention python3: $out"
    elif [ -d "$h/.claude/agents" ] && [ "$(count_direct "$h/.claude/agents" '*')" != "0" ]; then
        fail "$label" "agent files were written before the python3 check"
    elif [ "$(count_direct "$h/.claude" '*.bak-*')" != "0" ]; then
        fail "$label" "a backup was made before the python3 check"
    else
        pass "$label"
    fi
    rm -rf "$h"
}

case1
case2
case3a
case3b
case4
case5
case6
case7
case8
case9

printf '\n%d failure(s)\n' "$failures"
[ "$failures" -eq 0 ]
