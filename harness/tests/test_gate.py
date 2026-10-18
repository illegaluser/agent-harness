#!/usr/bin/env python3
"""
test_gate.py — end-to-end tests for the write gate.

EN: The gate is only finished when BOTH sides are proven: that it blocks the
    main thread, and that it does NOT block delegated subagents. Proving one
    without the other yields either a useless gate or a paralyzed session, and
    both failures look like success if you only test one direction.
    The hook is a plain stdin/stdout JSON filter, so every test runs the real
    script as a subprocess against a throwaway repo — no mocking, no imports.

KO: 게이트는 양쪽이 다 증명돼야 완성이다 — 메인 스레드를 막는 것과, 위임된 서브에이전트를
    막지 '않는' 것. 한쪽만 증명하면 각각 "무용한 게이트"와 "마비된 세션"이 되는데,
    한 방향만 보면 둘 다 성공처럼 보인다.
    훅은 순수 stdin/stdout JSON 필터이므로, 모든 테스트가 임시 저장소를 대상으로 실제
    스크립트를 서브프로세스로 돌린다 — 목도 임포트도 없다.

Run: python3 harness/tests/test_gate.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "gate.py")
GATE = os.path.normpath(GATE)

PASSED = []
FAILED = []


def make_repo(config):
    root = tempfile.mkdtemp(prefix="gate-test-")
    os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
    os.makedirs(os.path.join(root, "base"), exist_ok=True)
    with open(os.path.join(root, ".claude", "harness.json"), "w", encoding="utf-8") as fh:
        json.dump(config, fh)
    return root


def run(root, payload, raw=None):
    """EN/KO: Returns (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, GATE],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root),
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_payload(root, path, actor="main", turn="t1", tool="Write", agent_type=None):
    p = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess-1",
        "prompt_id": turn,
        "cwd": root,
        "tool_name": tool,
        "tool_input": {"file_path": os.path.join(root, path)},
        "tool_use_id": "tu-1",
    }
    if actor == "sub":
        p["agent_id"] = "agent-abc"
        p["agent_type"] = agent_type or "maker"
    elif agent_type:
        p["agent_type"] = agent_type  # main thread started with --agent
    return p


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  — " + detail) if detail and not cond else ""))


ENFORCING = {"enforce": True, "product": ["base/**"], "exempt": ["base/EXEMPT.md"],
             "main_thread_file_limit": 2, "metrics": True}


def test_main_thread_blocked_over_limit():
    root = make_repo(ENFORCING)
    try:
        for i in (1, 2):
            code, _, _ = run(root, write_payload(root, "base/f%d.md" % i))
            check("main thread allowed under limit (file %d)" % i, code == 0)
        code, _, err = run(root, write_payload(root, "base/f3.md"))
        check("main thread DENIED on 3rd product file", code == 2, "exit=%d" % code)
        check("deny message reaches the model via stderr", "harness" in err, repr(err[:80]))
    finally:
        shutil.rmtree(root)


def test_subagent_never_blocked():
    """EN/KO: The delegation path must survive; this is the other half of the proof."""
    root = make_repo(ENFORCING)
    try:
        codes = []
        for i in range(1, 7):
            code, _, _ = run(root, write_payload(root, "base/s%d.md" % i, actor="sub"))
            codes.append(code)
        check("subagent allowed for 6 product files (limit is 2)", codes == [0] * 6, str(codes))
    finally:
        shutil.rmtree(root)


def test_agent_type_alone_is_main_thread():
    """
    EN: A session started with --agent carries agent_type on the MAIN thread with
        no agent_id. Treating agent_type as the discriminator would hand the main
        thread an unlimited write bypass. It must be counted as main.
    KO: --agent 로 시작한 세션은 메인 스레드에 agent_type 만 실리고 agent_id 는 없다.
        agent_type 으로 판별하면 메인 스레드가 무제한 우회 경로를 얻는다. 메인으로 세야 한다.
    """
    root = make_repo(ENFORCING)
    try:
        for i in (1, 2):
            run(root, write_payload(root, "base/a%d.md" % i, agent_type="general-purpose"))
        code, _, _ = run(root, write_payload(root, "base/a3.md", agent_type="general-purpose"))
        check("agent_type without agent_id counts as MAIN (denied)", code == 2, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_non_product_and_exempt_pass():
    root = make_repo(ENFORCING)
    try:
        codes = [run(root, write_payload(root, "README.md"))[0] for _ in range(5)]
        check("non-product files never gated", codes == [0] * 5, str(codes))
        codes = [run(root, write_payload(root, "base/EXEMPT.md"))[0] for _ in range(5)]
        check("exempt path never gated", codes == [0] * 5, str(codes))
    finally:
        shutil.rmtree(root)


def test_same_file_not_double_counted():
    root = make_repo(ENFORCING)
    try:
        codes = [run(root, write_payload(root, "base/same.md"))[0] for _ in range(6)]
        check("re-editing one file does not consume the budget", codes == [0] * 6, str(codes))
    finally:
        shutil.rmtree(root)


def test_turn_boundary_resets():
    root = make_repo(ENFORCING)
    try:
        for i in (1, 2):
            run(root, write_payload(root, "base/t%d.md" % i, turn="turnA"))
        code, _, _ = run(root, write_payload(root, "base/t3.md", turn="turnA"))
        check("budget exhausted within a turn", code == 2, "exit=%d" % code)
        code, _, _ = run(root, write_payload(root, "base/t4.md", turn="turnB"))
        check("new prompt_id restores the budget", code == 0, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_stop_resets_without_prompt_id():
    """
    EN: The fallback path for Claude Code builds older than 2.1.196. Close gate
        off here so the Stop under test is the write-budget reset, not a block.
    KO: 2.1.196 미만 빌드의 대체 경로. 여기서 검사하는 Stop 은 쓰기 예산 리셋이므로
        close 게이트는 꺼 둔다.
    """
    root = make_repo(dict(ENFORCING, close_gate=False))
    try:
        def no_prompt_id(path):
            p = write_payload(root, path)
            del p["prompt_id"]
            return p

        for i in (1, 2):
            run(root, no_prompt_id("base/n%d.md" % i))
        code, _, _ = run(root, no_prompt_id("base/n3.md"))
        check("budget exhausted without prompt_id", code == 2, "exit=%d" % code)
        run(root, {"hook_event_name": "Stop", "session_id": "sess-1", "cwd": root})
        code, _, _ = run(root, no_prompt_id("base/n4.md"))
        check("Stop event restores the budget (prompt_id fallback)", code == 0, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_bash_bypass():
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
            "tool_input": {"command": "sed -i '' 's/a/b/' base/f.md"},
        }
        code, _, err = run(root, p)
        check("main thread Bash in-place edit of a product file DENIED", code == 2, "exit=%d" % code)
        check("bash deny names the offending path", "base/f.md" in err, repr(err[:100]))

        p["tool_input"] = {"command": "grep -rn foo base/"}
        check("read-only Bash on product files allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "sed -i '' 's/a/b/' notes.txt"}
        check("Bash edit of a non-product file allowed", run(root, p)[0] == 0)

        p["agent_id"] = "agent-abc"
        p["tool_input"] = {"command": "sed -i '' 's/a/b/' base/f.md"}
        check("subagent Bash edit of a product file allowed", run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_bash_write_targets_blocked():
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "echo x > base/f.md"}
        check("redirect truncate DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cat a >> base/f.md"}
        check("redirect append DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "tee base/f.md < x"}
        check("tee with stdin redirect DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "python3 -c 'print(1)' > base/f.md"}
        check("python -c into a product file DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cat > base/f.md <<EOF\nhi\nEOF"}
        check("heredoc after redirect DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cat <<'EOF' > base/f.md\nhi\nEOF"}
        check("redirect after heredoc DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": 'echo "$(date)" > base/f.md'}
        check("command substitution in redirect DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": 'echo x > "base/f.md"'}
        check("quoted redirect target DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo hi>base/f.md"}
        check("redirect without space DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "perl -pi -e 's/a/b/' base/f.md"}
        check("perl in-place DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cat x | tee -a base/f.md"}
        check("pipe into tee -a DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo x > ./base/f.md"}
        check("./-prefixed target DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "grep -rn foo . ; echo x > base/f.md"}
        check("write in a later segment DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo x 2> base/f.md"}
        check("fd-numbered redirect DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo x &> base/f.md"}
        check("&> redirect DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo x >| base/f.md"}
        check("noclobber override DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo a > base/f.md; echo b >> base/f.md"}
        code, _, err = run(root, p)
        check("duplicate targets named once (exit)", code == 2, "exit=%d" % code)
        check("duplicate targets named once (dedup)", err.count("base/f.md") == 1,
              repr(err))

        p["tool_input"] = {"command": "rm base/f.md"}
        check("rm on a product file DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "rm -rf base/"}
        check("rm -rf on a product dir DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cp /tmp/x base/f.md"}
        check("cp into a product file DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "mv /tmp/x base/f.md"}
        check("mv into a product file DENIED", run(root, p)[0] == 2)
    finally:
        shutil.rmtree(root)


def test_bash_read_only_allowed():
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {
            "command": 'grep -rn "reasoning_effort:\\|^effort:" base/agents/*.md '
                       'base/x/*.md ~/.claude/agents/*.md 2>/dev/null | sed "s\\|$HOME\\|~\\|"'
        }
        check("real false positive #1", run(root, p)[0] == 0)

        p["tool_input"] = {
            "command": "grep -rn \"reasoning_effort:\" base/agents base/x "
                       "/Users/x/.claude/agents 2>/dev/null"
        }
        check("real false positive #2", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cat base/f.md | head -20"}
        check("cat a product file into a pager", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "python3 base/tests/t.py"}
        check("run a script that lives in a product dir", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "wc -l base/*.md > /tmp/out.txt"}
        check("redirect to a non-product path", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "ls base/ 2>&1 | head"}
        check("stderr merge is not a target", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "diff base/a.md base/b.md > /tmp/d.txt"}
        check("diff of product files to /tmp", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "git diff base/ > /tmp/x.patch"}
        check("git diff to /tmp", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "echo done > /dev/null"}
        check("/dev/null is not a product", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "for f in base/*.md; do echo $f; done"}
        check("glob loop over product files", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "test -f base/f.md && echo yes"}
        check("test -f on a product file", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "echo x > base/EXEMPT.md"}
        check("exempt file may be written", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cp base/f.md /tmp/x"}
        check("cp of a product file to /tmp allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "mv base/f.md /tmp/x"}
        check("mv of a product file to /tmp allowed", run(root, p)[0] == 0)

        p["agent_id"] = "agent-abc"
        p["tool_input"] = {"command": "echo x > base/f.md"}
        check("subagent redirect into a product file allowed", run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_bash_anchor_and_lookbehind_regression():
    """
    EN: Critic's E2E found that `(?:^|\\s)` markers missed absolute invocations
        (`/usr/bin/sed`, `/bin/tee`) because the character before the word is `/`,
        not whitespace or start-of-segment. `\\b` fixes it without reopening the
        `used`/`committee` false positives the old marker was written to avoid.
        Also covers the `exec 3<> file` miss from dropping `<` off the redirect
        lookbehind, and confirms that drop creates no new false positive for
        heredoc/`<`/`<<<` (REDIRECT_RE itself requires a literal `>`, so those
        never reach the lookbehind at all).
    KO: Critic 의 E2E 가 `(?:^|\\s)` 마커의 미탐을 찾아냈다 — 단어 앞 문자가 공백/세그먼트
        시작이 아니라 `/` 인 절대경로 호출(`/usr/bin/sed`, `/bin/tee`)을 놓쳤다. `\\b`
        는 옛 마커가 피하려던 `used`/`committee` 오탐을 다시 열지 않으면서 이를 고친다.
        리다이렉트 lookbehind 에서 `<` 를 뺀 것이 만든 `exec 3<> file` 미탐도 다루고,
        그 제거가 heredoc/`<`/`<<<` 에 새 오탐을 만들지 않음을 확인한다(REDIRECT_RE
        자체가 리터럴 `>` 를 요구하므로 애초에 lookbehind 에 닿지 않는다).
    """
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "/usr/bin/sed -i '' 's/a/b/' base/f.md"}
        check("absolute sed -i DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "echo x | /usr/bin/tee base/f.md"}
        check("absolute tee DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "/bin/rm -rf base/"}
        check("absolute rm DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "grep -rn used base/"}
        check("'used' is not treated as sed (control)", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "grep -rn committee base/"}
        check("'committee' is not treated as tee (control)", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "echo x | sudo tee base/f.md"}
        check("sudo tee DENIED (control, was already caught)", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "exec 3<> base/f.md"}
        check("exec read-write open DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "ls base/ 2>&1 | head"}
        check("2>&1 still not a target (no new false positive)", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cmd < base/f.md"}
        check("plain input redirect is not a target (no new false positive)",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cmd <<< 'x' > /tmp/o"}
        check("here-string redirect to /tmp is not a target (no new false positive)",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cat <<'EOF' > /tmp/o\nhi\nEOF"}
        check("heredoc to /tmp is not a target (no new false positive)",
              run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_bash_cd_tracking():
    """
    EN: Critic's E2E found `cd X && write` resolved the write's relative target
        against the repo root instead of X, so `cd harness/hooks && echo x > gate.py`
        overwrote the gate itself. bash_targets now tracks `cd` across segments,
        accumulating (`cd a && cd b` -> a/b) and resetting to root on `cd -` or a
        bare `cd` rather than guessing.
    KO: Critic 의 E2E 가 `cd X && write` 의 상대 대상이 X 가 아니라 저장소 루트 기준으로
        풀리는 것을 찾아냈다 — `cd harness/hooks && echo x > gate.py` 가 게이트 자신을
        변조했다. bash_targets 는 이제 세그먼트 사이로 `cd` 를 추적하고(누적,
        `cd a && cd b` -> a/b), `cd -` 나 인자 없는 `cd` 에서는 추측하지 않고 루트로
        되돌린다.
    """
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "cd base && echo x > f.md"}
        check("cd into a product dir then relative write DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cd base/sub && echo x > ../f.md"}
        check("cd into a product subdir then ../ write DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cd base; echo x > f.md"}
        check("cd with ; separator is tracked too", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "cd /tmp && echo x > out.txt"}
        check("cd into a non-product dir then write allowed (no new false positive)",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cd .. && ls"}
        check("a harmless cd with no write is unaffected", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "cd - && echo x > f.md"}
        check("cd - gives up tracking and falls back to root (miss, accepted)",
              run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_bash_directory_targets():
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "rm -rf base"}
        check("rm of a product dir without a trailing slash DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "rm -r base/sub"}
        check("rm -r of a product subdir DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "rmdir base/sub"}
        check("rmdir of a product subdir DENIED", run(root, p)[0] == 2)

        p["tool_input"] = {"command": "rm -rf notes"}
        check("rm of a non-product dir allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "rm -rf /tmp/base"}
        check("rm of a same-named dir outside the repo allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "rm -rf base/EXEMPT.md"}
        check("rm of an exempt file allowed", run(root, p)[0] == 0)

        p["agent_id"] = "agent-abc"
        p["tool_input"] = {"command": "rm -rf base/"}
        check("subagent rm of a product dir allowed", run(root, p)[0] == 0)
        del p["agent_id"]

        p["tool_input"] = {"command": "cp -r /tmp/x base/sub"}
        check("cp into a product subdir DENIED", run(root, p)[0] == 2)

        # EN/KO: `git rm --cached` 는 인덱스만 건드리고 워킹트리 파일은 남긴다.
        #        `--cached` 없는 `git rm` 은 실제로 지우므로 계속 막는다.
        p["tool_input"] = {"command": "git rm --cached base/f.md"}
        check("git rm --cached leaves the file, allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "git rm base/f.md"}
        check("git rm without --cached DENIED", run(root, p)[0] == 2)

        # EN/KO: `docker rm base` 의 `base` 는 컨테이너 이름이지 경로가 아니다.
        p["tool_input"] = {"command": "docker rm base"}
        check("docker rm names a container, not a path, allowed", run(root, p)[0] == 0)

        # EN/KO: A4 — 마커 목록에 새로 들어온 쓰기 명령들.
        for cmd in ("awk -i inplace 1 base/f.md", "ed -s base/f.md",
                    "git checkout -- base/f.md", "git restore base/f.md",
                    "git apply p.diff base/f.md", "truncate -s 0 base/f.md",
                    "ln -sf /etc/passwd base/f.md"):
            p["tool_input"] = {"command": cmd}
            check("in-place writer DENIED: %s" % cmd.split()[0], run(root, p)[0] == 2)
    finally:
        shutil.rmtree(root)


def test_bash_known_misses():
    """EN/KO: 미탐을 명시적으로 고정한다 — 조용히 바뀌면 이 테스트가 먼저 드러낸다."""
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "mv base /tmp/base"}
        check("known miss: moving a product dir out of the repo is not caught",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "rm -rf ."}
        check("known miss: `rm -rf .` is not caught (repo root matches no glob)",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "echo${IFS}PWNED${IFS}>${IFS}base/f.md"}
        check("known miss: $IFS in place of spaces breaks the redirect token",
              run(root, p)[0] == 0)

        p["tool_input"] = {"command": "echo base/f.md | xargs -I{} tee {} </dev/null"}
        check("known miss: xargs {} substitution hides the real target from tee",
              run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_bash_marker_is_the_command_not_a_flag():
    """
    EN: A write marker only counts as one when it is the command. `--rm` is a flag,
        `pip install` is a subcommand, and `bash x/install.sh` merely runs a file —
        none of them write to a product path. Blocking them once made the harness's
        own installer unrunnable from a main thread.
    KO: 쓰기 마커는 그것이 명령일 때만 마커다. `--rm` 은 플래그, `pip install` 은
        하위명령, `bash x/install.sh` 는 파일을 실행할 뿐 — 셋 다 산출물에 쓰지 않는다.
        이것들을 막았을 때 하네스 자기 설치기를 메인 스레드에서 돌릴 수 없었다.
    """
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }
        allowed = [
            ("running an install.sh is not installing onto it",
             "bash base/install.sh /tmp/target"),
            ("running install.sh by path is allowed",
             "./base/install.sh /tmp/target"),
            ("--uninstall does not read as the install command",
             "bash base/install.sh --uninstall /tmp/target"),
            ("pip install with a product requirements file allowed",
             "pip install -r base/requirements.txt"),
            ("npm install pointed at a product dir allowed",
             "npm install --prefix base/x"),
            ("a --rm flag is not the rm command",
             "docker run --rm -v ./base:/data img"),
        ]
        for name, command in allowed:
            p["tool_input"] = {"command": command}
            check(name, run(root, p)[0] == 0)

        blocked = [
            ("coreutils install to a product file DENIED",
             "install -m 644 /tmp/x base/f.md"),
            ("coreutils install by absolute path DENIED",
             "/usr/bin/install -m 644 /tmp/x base/f.md"),
            ("rm by absolute path DENIED", "/bin/rm -f base/f.md"),
            ("tee by absolute path DENIED", "echo x | /usr/bin/tee base/f.md"),
        ]
        for name, command in blocked:
            p["tool_input"] = {"command": command}
            check(name, run(root, p)[0] == 2)
    finally:
        shutil.rmtree(root)


def test_bash_cd_argument_forms():
    """
    EN: `cd` tracking must not depend on how the path is spelled. Quoting a path
        is ordinary, so `cd "base"` has to track exactly like `cd base` — when it
        did not, a write to the gate's own source file went through.
    KO: `cd` 추적이 경로 표기 방식에 좌우되면 안 된다. 경로에 따옴표를 씌우는 것은
        평범한 표기이므로 `cd "base"` 는 `cd base` 와 정확히 같이 추적돼야 한다 —
        그렇지 않았을 때 게이트 자기 소스 파일에 대한 쓰기가 통과했다.
    """
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }
        blocked = [
            ("double-quoted cd target tracked", 'cd "base" && echo x > f.md'),
            ("single-quoted cd target tracked", "cd 'base' && echo x > f.md"),
            ("cd past the -- end-of-options marker tracked", "cd -- base && echo x > f.md"),
            ("cd with a -P flag tracked", "cd -P base && echo x > f.md"),
            ("cd with flag, marker and quotes tracked", "cd -L -- 'base' && echo x > f.md"),
            ("cd with a trailing comment tracked", "cd base # go\necho x > f.md"),
            ("cd then a parent-relative write tracked", "cd base/sub && echo x > ../f.md"),
        ]
        for name, command in blocked:
            p["tool_input"] = {"command": command}
            check(name, run(root, p)[0] == 2)

        allowed = [
            ("cd outside the repo then write allowed", "cd /tmp && echo x > out.txt"),
            ("cd with no argument resets to root", "cd && echo x > out.txt"),
            ("cd - resets to root", "cd - && echo x > out.txt"),
            ("cd into a product dir, read-only, allowed", "cd base && grep -rn foo ."),
            ("cd back out before writing allowed", "cd base && cd /tmp && echo x > f.md"),
            ("cd into a non-product dir allowed", "cd notes && echo x > f.md"),
        ]
        for name, command in allowed:
            p["tool_input"] = {"command": command}
            check(name, run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_exempt_subtree_covers_its_directory():
    root = make_repo(dict(ENFORCING, exempt=["base/sub/**"]))
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
        }

        p["tool_input"] = {"command": "rm -rf base/sub/"}
        check("rm of a fully exempt subtree allowed", run(root, p)[0] == 0)

        p["tool_input"] = {"command": "rm -rf base/"}
        check("rm of the parent of an exempt subtree DENIED", run(root, p)[0] == 2)
    finally:
        shutil.rmtree(root)


def test_write_gate_on_directory_path():
    root = make_repo(dict(ENFORCING, close_gate=False))
    try:
        code, _, _ = run(root, write_payload(root, "base"))
        check("Write on a bare product-dir path is counted, not blocked", code == 0)

        code, _, _ = run(root, write_payload(root, "base/a.md"))
        check("second write still under budget", code == 0)

        code, _, _ = run(root, write_payload(root, "base/b.md"))
        check("the directory-path write consumed a budget slot", code == 2)
    finally:
        shutil.rmtree(root)


def test_observe_mode_never_denies():
    """
    EN/KO: `enforce:false` 는 새로 설치한 프로젝트의 기본값이다. 한 세션 굴려보며
           오작동을 확인하는 동안 아무것도 막으면 안 된다 — 관측 단계에서 차단하면
           도입 자체가 위험해지고, 사용자는 켜보기도 전에 게이트를 꺼버린다.
    """
    root = make_repo(dict(ENFORCING, enforce=False))
    try:
        codes = [run(root, write_payload(root, "base/o%d.md" % i))[0] for i in range(1, 7)]
        check("observe mode allows everything", codes == [0] * 6, str(codes))
        line = open(os.path.join(root, ".claude", "state", "harness-metrics.jsonl"),
                    encoding="utf-8").read()
        check("observe mode still records what it would have blocked", '"observe"' in line)
    finally:
        shutil.rmtree(root)


def test_metrics_content():
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/m1.md"))
        path = os.path.join(root, ".claude", "state", "harness-metrics.jsonl")
        rec = json.loads(open(path, encoding="utf-8").read().strip().splitlines()[0])
        check("metrics record the actor", rec.get("actor") == "main", str(rec))
        check("metrics record the decision", rec.get("decision") == "allow", str(rec))
        check("metrics carry a timestamp", isinstance(rec.get("ts"), int), str(rec))
        check("metrics never carry tool_input", "tool_input" not in rec, str(rec))
    finally:
        shutil.rmtree(root)


def test_fail_open():
    root = make_repo(ENFORCING)
    try:
        code, _, _ = run(root, None, raw="{ this is not json")
        check("malformed payload fails open", code == 0, "exit=%d" % code)
        code, _, _ = run(root, {"hook_event_name": "PreToolUse", "tool_name": "Write"})
        check("payload missing every optional field fails open", code == 0, "exit=%d" % code)
        code, _, _ = run(root, {"hook_event_name": "SomeFutureEvent"})
        check("unknown event passes through", code == 0, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_unconfigured_install_is_inert():
    """EN/KO: No config at all must mean no obstruction, not a default guess."""
    root = tempfile.mkdtemp(prefix="gate-test-")
    try:
        codes = [run(root, write_payload(root, "base/u%d.md" % i))[0] for i in range(1, 7)]
        check("no harness.json → gate is inert", codes == [0] * 6, str(codes))
    finally:
        shutil.rmtree(root)


def stop(root, event="Stop", agent_type=None, agent_id=None, prompt_id=None):
    p = {"hook_event_name": event, "session_id": "sess-1", "cwd": root}
    if prompt_id:
        p["prompt_id"] = prompt_id
    if agent_id:
        p["agent_id"] = agent_id
    if agent_type:
        p["agent_type"] = agent_type
    return run(root, p)


def blocked(out):
    return '"decision": "block"' in out


def test_close_gate_blocks_unverified_delegation():
    """
    EN/KO: 위임한 턴은 메인이 직접 감당하지 못한 크기라서 위임한 것이다. 그 결과를
           아무도 안 본 채 턴이 끝나면 검증이 영영 일어나지 않는다 — 다음 턴은 이미
           바뀐 파일 위에서 시작한다. 유한 차단(max_close_blocks)이라 세션은 안 잠긴다.
    """
    root = make_repo(ENFORCING)
    try:
        check("clean turn (no writes) never blocks", not blocked(stop(root)[1]))
        run(root, write_payload(root, "base/c1.md", actor="sub"))
        check("delegated turn BLOCKS on close until verified", blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_direct_handling_owes_no_verification():
    """
    EN: The whole point of the direct-handling band is that it's cheap. If a
        1-file edit still forced a critic round trip, the cheap path would cost
        the same as the expensive one and the routing rule would be pointless.
    KO: 직접 처리 구간의 존재 이유는 싸다는 것이다. 1개 파일 수정에도 critic 왕복을
        강제하면 싼 경로가 비싼 경로와 같아지고 라우팅 규칙이 무의미해진다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/d1.md"))
        check("1 file handled directly does not block the close",
              not blocked(stop(root)[1]))
        root2 = make_repo(ENFORCING)
        for i in (1, 2):
            run(root2, write_payload(root2, "base/d%d.md" % i))
        check("2 files (at the budget) still does not block",
              not blocked(stop(root2)[1]))
        shutil.rmtree(root2)
    finally:
        shutil.rmtree(root)


def test_verifier_satisfies_close_gate():
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v1.md", actor="sub"))
        stop(root, event="SubagentStop", agent_type="critic", agent_id="a1")
        check("a critic subagent finishing satisfies the close gate",
              not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_non_verifier_does_not_satisfy_close_gate():
    """
    EN/KO: maker 가 끝났다는 것은 변경이 생겼다는 뜻이지 검증됐다는 뜻이 아니다.
           아무 서브에이전트나 close 게이트를 풀면, 위임한 턴은 언제나 maker 로
           끝나므로 게이트가 사실상 없는 것이 된다. `verifiers` 목록만 푼다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v2.md", actor="sub"))
        stop(root, event="SubagentStop", agent_type="maker", agent_id="a1")
        check("a maker subagent finishing does NOT satisfy it", blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_subagent_writes_count_for_close_gate():
    """EN/KO: Delegated writes still need a verdict — the gate isn't main-only."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/s1.md", actor="sub"))
        check("a delegated write also requires verification", blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_close_gate_is_bounded():
    """EN/KO: A stuck verification must not be able to wedge the session."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/b1.md", actor="sub"))
        results = [blocked(stop(root)[1]) for _ in range(4)]
        check("close gate blocks at most max_close_blocks times then releases",
              results == [True, True, False, False], str(results))
    finally:
        shutil.rmtree(root)


def test_subagent_stop_does_not_reset_write_budget():
    """
    EN: SubagentStop is not a turn boundary. If it cleared the counter, the main
        thread would earn a fresh budget every time a subagent finished — an
        unlimited bypass of the whole write gate.
    KO: SubagentStop 은 턴 경계가 아니다. 여기서 카운터를 비우면 서브에이전트가 끝날
        때마다 메인 스레드가 예산을 새로 받아 write 게이트 전체가 무력해진다.
    """
    root = make_repo(ENFORCING)
    try:
        for i in (1, 2):
            run(root, write_payload(root, "base/r%d.md" % i))
        stop(root, event="SubagentStop", agent_type="scout", agent_id="a1")
        code, _, _ = run(root, write_payload(root, "base/r3.md"))
        check("SubagentStop does not restore the main thread's budget",
              code == 2, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_close_gate_off_when_not_enforcing():
    root = make_repo(dict(ENFORCING, enforce=False))
    try:
        run(root, write_payload(root, "base/o1.md", actor="sub"))
        check("observe mode never blocks the close", not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def spawn(root, subagent_type, tool="Agent", session="sess-1", prompt=None):
    # EN/KO: 기본 브리프는 실재하는 파일을 가리킨다 — 인수인계 게이트를 통과시켜
    #        다른 게이트를 시험하려는 테스트가 그것 때문에 막히지 않게 한다.
    #        인수인계 게이트 자체는 prompt 를 넘겨 따로 시험한다.
    if prompt is None:
        prompt = "facts: .claude/harness.json"
    return run(root, {
        "hook_event_name": "PreToolUse", "session_id": session, "prompt_id": "t1",
        "cwd": root, "tool_name": tool, "tool_use_id": "tu-1",
        "tool_input": {"subagent_type": subagent_type, "prompt": prompt},
    })


def approve(root, session="sess-1"):
    return run(root, {
        "hook_event_name": "PostToolUse", "session_id": session, "prompt_id": "t1",
        "cwd": root, "tool_name": "ExitPlanMode", "tool_input": {}, "tool_response": {},
    })


def test_approval_gate_blocks_unapproved_maker():
    """
    EN/KO: maker 스폰은 계획이 편집으로 바뀌기 직전의 마지막 관측 지점이다. 훅이
           실제로 볼 수 있는 사용자 승인은 수락된 ExitPlanMode 뿐이고, 오케스트레이터가
           "승인받았다"고 주장하는 것은 자기 인증이라 신호가 아니다.
           단, 승인의 유효 범위는 한 턴이 아니다 — 그렇게 좁히면 막다른 길이 된다
           (test_approval_survives_a_turn_boundary_until_used 참조).
    """
    root = make_repo(ENFORCING)
    try:
        code, _, err = spawn(root, "maker")
        check("spawning maker without approval DENIED", code == 2, "exit=%d" % code)
        check("deny explains the approval requirement", "승인" in err, repr(err[:80]))
    finally:
        shutil.rmtree(root)


def test_approval_gate_allows_read_only_roles():
    """EN/KO: Only write-capable roles are gated; investigation must stay free."""
    root = make_repo(ENFORCING)
    try:
        codes = [spawn(root, r)[0] for r in ("scout", "architect", "critic", "referee")]
        check("read-only roles spawn without approval", codes == [0] * 4, str(codes))
    finally:
        shutil.rmtree(root)


def test_exit_plan_mode_records_approval():
    root = make_repo(ENFORCING)
    try:
        check("maker blocked before approval", spawn(root, "maker")[0] == 2)
        approve(root)
        check("maker allowed after an accepted ExitPlanMode",
              spawn(root, "maker")[0] == 0)
    finally:
        shutil.rmtree(root)


def test_approval_does_not_survive_the_turn():
    """
    EN: Approval authorizes the turn it was given in, not the session. Otherwise
        one approved plan would license every later maker spawn, including for
        work the user never saw.
    KO: 승인은 그 승인이 이뤄진 턴을 인가하는 것이지 세션 전체가 아니다. 아니면 한 번
        승인된 계획이 이후 모든 maker 호출을 — 사용자가 본 적 없는 작업까지 — 인가한다.
    """
    root = make_repo(ENFORCING)
    try:
        approve(root)
        check("approved maker runs in the same turn", spawn(root, "maker")[0] == 0)
        stop(root)  # turn boundary
        check("next turn requires fresh approval", spawn(root, "maker")[0] == 2)
    finally:
        shutil.rmtree(root)


def test_late_verifier_from_another_turn_does_not_verify_this_one():
    """
    EN: A verifier that finishes late must not certify a turn it never inspected.
        Measured on Claude Code 2.1.220: SubagentStop DOES carry prompt_id, so the
        turn key is present and read_counter() rejects the stale state instead of
        inheriting it. This test locks that in — if a future build stops sending
        prompt_id on SubagentStop, the no-turn-id path would inherit the stored
        state and silently mark an uninspected turn verified.
    KO: 늦게 끝난 검증자가 자기가 본 적 없는 턴을 인증하면 안 된다. Claude Code 2.1.220
        에서 실측: SubagentStop 에 prompt_id 가 **실린다.** 그래서 턴 키가 있고
        read_counter() 가 낡은 상태를 물려받지 않고 버린다. 이 테스트가 그것을 고정한다 —
        나중 빌드가 SubagentStop 에 prompt_id 를 안 실으면, 턴 키 없는 경로가 저장 상태를
        물려받아 검사한 적 없는 턴을 조용히 verified 로 만든다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/x.md", actor="sub"))  # turn t1 delegates
        stop(root, event="SubagentStop", agent_type="critic", prompt_id="OTHER-TURN")
        check("a verifier stamped with another turn does not satisfy this close gate",
              blocked(stop(root, prompt_id="t1")[1]))
    finally:
        shutil.rmtree(root)


def test_symlink_out_of_the_repo_is_still_product():
    """
    EN: A symlink inside a product dir pointing outside the repo used to escape
        the gate entirely — realpath() made it start with "..", so is_product()
        called it foreign and BOTH the write budget and the bash gate waved it
        through. The name written is a product name; where the inode lives is
        not the user's declaration of what is protected.
    KO: 산출물 디렉터리 안에서 저장소 밖을 가리키는 심링크가 게이트를 통째로 빠져나갔다 —
        realpath() 때문에 ".." 로 시작해 is_product() 가 남의 것으로 판정했고, 쓰기 예산도
        bash 게이트도 그냥 통과시켰다. 쓰인 이름이 산출물 이름이다. inode 의 위치는
        무엇을 보호할지에 대한 사용자의 선언이 아니다.
    """
    root = make_repo(ENFORCING)
    try:
        outside = tempfile.mkdtemp()
        target = os.path.join(outside, "elsewhere.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("x\n")
        link = os.path.join(root, "base", "link.md")
        os.symlink(target, link)
        try:
            check("a symlink escaping the repo still counts as product",
                  run(root, write_payload(root, link))[0] == 0)
            check("and it consumed a budget slot",
                  run(root, write_payload(root, "base/b.md"))[0] == 0)
            check("so the third write is blocked",
                  run(root, write_payload(root, "base/c.md"))[0] == 2)
        finally:
            shutil.rmtree(outside)
    finally:
        shutil.rmtree(root)


def test_relative_file_path_is_resolved_against_the_repo():
    """
    EN/KO: 상대경로 file_path 는 프로세스 cwd 가 아니라 저장소 루트 기준으로 푼다.
           bash_targets 는 이미 그렇게 하는데 쓰기 게이트만 안 했다.
    """
    root = make_repo(ENFORCING)
    try:
        check("relative product path counted",
              run(root, write_payload(root, "base/r1.md"))[0] == 0)
        check("second relative product path counted",
              run(root, write_payload(root, "base/r2.md"))[0] == 0)
        check("third is blocked, so both were counted",
              run(root, write_payload(root, "base/r3.md"))[0] == 2)
    finally:
        shutil.rmtree(root)


def test_approval_survives_a_turn_boundary_until_used():
    """
    EN: The gate must not strand the main thread. Once the write budget is spent,
        delegation is the only sanctioned way forward — so an approval given in
        one turn has to still be there when the spawn happens, even if the user
        said one more word in between. Scoping approval to a single turn made
        writing and delegating both impossible, and the only escape was turning
        the gate off. Reach changed; strength did not (see the next test).
    KO: 게이트가 메인을 막다른 길에 가두면 안 된다. 쓰기 예산을 다 쓰면 위임이 유일한
        정규 경로인데, 승인과 스폰 사이에 사용자가 한 마디만 더 해도 승인이 사라지면
        쓰기도 위임도 불가능해지고 빠져나갈 길은 게이트를 끄는 것뿐이었다.
        바뀐 것은 유효 범위이고 강도는 그대로다(다음 테스트).
    """
    root = make_repo(ENFORCING)
    try:
        approve(root)
        stop(root)  # turn boundary — and Stop deletes the turn counter
        check("approval carried across the turn boundary", spawn(root, "maker")[0] == 0)
    finally:
        shutil.rmtree(root)


def test_carried_approval_is_single_use():
    """
    EN/KO: 한 번의 승인은 한 번의 스폰만 산다 — 턴을 넘어와도 마찬가지다.
    """
    root = make_repo(ENFORCING)
    try:
        approve(root)
        stop(root)
        check("first spawn consumes the carried approval", spawn(root, "maker")[0] == 0)
        check("second spawn needs a new approval", spawn(root, "maker")[0] == 2)
    finally:
        shutil.rmtree(root)


def test_approval_does_not_leak_across_sessions():
    """
    EN/KO: 승인은 세션 id 로 묶인다. 다른 세션이 남의 승인을 주워 쓸 수 없다.
    """
    root = make_repo(ENFORCING)
    try:
        approve(root, session="sess-a")
        check("another session sees no approval",
              spawn(root, "maker", session="sess-b")[0] == 2)
    finally:
        shutil.rmtree(root)


def test_handoff_gate_blocks_a_brief_that_cites_nothing():
    """
    EN: A subagent starts with an empty context. Whatever the orchestrator already
        established reaches it only if written down, so a prose-only brief makes it
        re-derive everything — three makers burned 12 minutes that way in one
        session. The hook cannot judge a brief's quality, but it can see that the
        brief names no file at all, which is the cheap failure worth blocking.
    KO: 서브에이전트는 빈 컨텍스트로 시작한다. 오케스트레이터가 이미 확인한 것은 적어야만
        전달되므로, 산문뿐인 브리프는 전부 재조사하게 만든다 — 한 세션에서 Maker 셋이
        그렇게 12분을 태웠다. 훅은 브리프의 품질은 못 보지만 **파일을 하나도 안 가리킨다**는
        것은 볼 수 있고, 그것이 막을 가치가 있는 싼 실패다.
    """
    root = make_repo(ENFORCING)
    try:
        approve(root)
        check("a brief citing no file is DENIED",
              spawn(root, "maker", prompt="고쳐라. 알아서 찾아봐라.")[0] == 2)
        approve(root)
        check("a brief citing a real file passes",
              spawn(root, "maker", prompt="사실은 .claude/harness.json 에 있다")[0] == 0)
        approve(root)
        check("a path that does not exist does not count",
              spawn(root, "maker", prompt="사실은 docs/NOPE-does-not-exist.md 에 있다")[0] == 2)
    finally:
        shutil.rmtree(root)


def test_handoff_gate_leaves_other_roles_alone():
    """
    EN/KO: scout 는 조사하러 가는 역할이라 넘겨줄 사실이 아직 없다. 인수인계를
           요구하면 첫 조사 자체가 불가능해진다 — handoff_roles 밖이다.
    """
    root = make_repo(ENFORCING)
    try:
        check("scout spawns with a prose-only brief",
              spawn(root, "scout", prompt="이 저장소를 조사하라")[0] == 0)
    finally:
        shutil.rmtree(root)


def test_sanctioned_path_runs_end_to_end():
    """
    EN: THE dead-end test. Every other test in this file asks "is this blocked
        here?"; only this one asks "does the sanctioned route reach the end?"
        Budget spent -> plan approved -> turn boundary -> maker spawned ->
        subagent writes -> critic finishes -> turn closes. A gate that blocks a
        step of its own prescribed escape route is unusable, and a suite that
        only tests blocking cannot tell the difference. This exact sequence was
        broken in production: approval was scoped to one turn, so the moment the
        user said anything between approving and delegating, writing AND
        delegating were both impossible and the only way out was to switch the
        gate off.
    KO: **막다른 길 테스트.** 이 파일의 다른 모든 테스트는 "여기서 막히는가"를 묻는다.
        이것만이 "규정된 경로가 끝까지 가는가"를 묻는다.
        예산 소진 → 계획 승인 → 턴 경계 → maker 스폰 → 서브에이전트 쓰기 → critic 종료
        → 턴 종료. 자기가 지정한 탈출 경로의 한 단계를 스스로 막는 게이트는 쓸 수 없고,
        차단만 시험하는 슈트는 그 차이를 구분하지 못한다. 실제로 이 시퀀스가 깨져 있었다 —
        승인이 한 턴만 유효해서, 승인과 위임 사이에 사용자가 한 마디만 하면 쓰기도 위임도
        불가능해지고 빠져나갈 길은 게이트를 끄는 것뿐이었다.
    """
    root = make_repo(ENFORCING)
    try:
        # 1. main thread spends its whole write budget
        check("first direct write allowed",
              run(root, write_payload(root, "base/e1.md"))[0] == 0)
        check("second direct write allowed",
              run(root, write_payload(root, "base/e2.md"))[0] == 0)
        check("third is blocked — delegation is now the only way forward",
              run(root, write_payload(root, "base/e3.md"))[0] == 2)

        # 2. the prescribed escape: present a plan, get it accepted
        check("plan approval is recorded", approve(root)[0] == 0)

        # 3. the user says something else; the turn moves on
        stop(root, prompt_id="turn-1")

        # 4. delegation must still be possible in the new turn
        res = spawn(root, "maker", session="sess-1", prompt="계획: .claude/harness.json")
        check("maker still spawnable after the turn boundary", res[0] == 0, str(res[1]))

        # 5. the subagent does the work the main thread could not
        check("subagent writes are not rate-limited",
              run(root, write_payload(root, "base/e3.md", actor="sub"))[0] == 0)

        # 6. verification closes the turn
        stop(root, event="SubagentStop", agent_type="critic")
        check("the turn can now end", not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_limitation_assertions_carry_a_rationale():
    """
    EN: A test that asserts something is forbidden is either encoding a
        requirement or freezing a defect, and the two are indistinguishable
        without a stated reason. test_approval_does_not_survive_the_turn passed
        for weeks while guarding a dead end. Requiring a docstring does not prove
        the reason is good — it forces someone to write one, and the defect
        showed itself the moment anybody tried.
    KO: 무언가를 금지한다고 단언하는 테스트는 요구사항을 담고 있거나 결함을 고정하고
        있는데, 이유가 적혀 있지 않으면 둘을 구분할 수 없다.
        test_approval_does_not_survive_the_turn 은 막다른 길을 지키면서 몇 주를 통과했다.
        docstring 을 요구한다고 이유가 옳아지지는 않는다 — 다만 누군가 이유를 쓰게 만들고,
        쓰려는 순간 그 결함이 스스로 드러났다.
    """
    src = open(__file__, encoding="utf-8").read()
    funcs = re.findall(r'^def (test_\w+)\(\):\n(\s*""")?', src, re.M)
    markers = ("_does_not_", "_never_", "_requires_", "_blocks_", "_is_bounded")
    missing = [n for n, doc in funcs if any(m in n for m in markers) and not doc]
    check("every limitation-asserting test states why", not missing, str(missing))


def test_numeric_thresholds_are_documented():
    """
    EN: main_thread_file_limit was 2 because an older spec said "1-2 directly,
        plan from the third" — a number carried over, never derived, never
        checked against a repo where the product globs cover most of the tree.
        CORE.md forbids exactly that. This test makes the ban observable: a
        numeric knob that CORE.md does not mention cannot ship.
    KO: main_thread_file_limit 이 2였던 이유는 옛 스펙의 "1~2개는 직접, 3개째부터 계획"
        한 문장뿐이었다. 옮겨 적었을 뿐 도출하지 않았고, product 글롭이 트리 대부분을
        덮는 저장소에서 무슨 일이 나는지 확인한 적도 없다. CORE.md 가 금지한 바로 그것이다.
        이 테스트가 그 금지를 관측 가능하게 만든다 — CORE.md 가 언급하지 않는 수치 손잡이는
        나갈 수 없다.
    """
    core = os.path.join(os.path.dirname(GATE), "..", "CORE.md")
    text = open(os.path.normpath(core), encoding="utf-8").read()
    src = open(GATE, encoding="utf-8").read()
    block = re.search(r"DEFAULTS = \{(.*?)\n\}", src, re.S).group(1)
    numeric = re.findall(r'"(\w+)":\s*-?\d+', block)
    missing = [k for k in numeric if k not in text]
    check("every numeric threshold is explained in CORE.md", not missing, str(missing))


def test_task_tool_is_gated_too():
    root = make_repo(ENFORCING)
    try:
        check("Task spawn of maker is gated like Agent",
              spawn(root, "maker", tool="Task")[0] == 2)
    finally:
        shutil.rmtree(root)


def test_approval_gate_off_when_not_enforcing():
    root = make_repo(dict(ENFORCING, enforce=False))
    try:
        check("observe mode never blocks a spawn", spawn(root, "maker")[0] == 0)
    finally:
        shutil.rmtree(root)


def test_all_tools_are_measured():
    """EN/KO: The widened matcher exists to price each role's tool calls."""
    root = make_repo(ENFORCING)
    try:
        for tool in ("Read", "Grep", "WebFetch"):
            run(root, {
                "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
                "cwd": root, "tool_name": tool, "tool_use_id": "tu-1",
                "agent_id": "a1", "agent_type": "scout", "tool_input": {},
            })
        rows = [json.loads(line) for line in
                open(os.path.join(root, ".claude", "state", "harness-metrics.jsonl"),
                     encoding="utf-8") if line.strip()]
        tools = [r["tool"] for r in rows if r.get("reason") == "observe"]
        check("read-only tool calls are recorded", tools == ["Read", "Grep", "WebFetch"],
              str(tools))
        check("the recorded call is attributed to the role",
              all(r.get("agent_type") == "scout" for r in rows), str(rows[:1]))
    finally:
        shutil.rmtree(root)


def session_start(root, event="SessionStart"):
    return run(root, {"hook_event_name": event, "session_id": "sess-1", "cwd": root})


def test_session_start_injects_facts():
    """
    EN: The injected context is how a fresh session inherits the harness state
        without a human re-explaining it. A generated config summary now goes
        out even with no facts file (D3) — if injection silently stops working,
        every later session starts blind, and nothing else would reveal that.
    KO: 주입되는 컨텍스트는 사람의 재설명 없이 하네스 상태를 물려받는 경로다.
        생성된 설정 요약은 이제 facts 파일이 없어도 나간다(D3) — 주입이 조용히
        멎으면 이후 모든 세션이 눈먼 채로 시작하는데, 그걸 드러내는 다른 장치가 없다.
    """
    root = make_repo(ENFORCING)
    try:
        code, out, _ = session_start(root)
        payload = json.loads(out)["hookSpecificOutput"]
        check("generated config summary is injected even with no facts file",
              "[harness]" in payload["additionalContext"]
              and "harness/CORE.md" in payload["additionalContext"],
              repr(out[:160]))

        with open(os.path.join(root, ".claude", "harness-facts.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("ENFORCE_IS_ON")
        code, out, _ = session_start(root)
        payload = json.loads(out)["hookSpecificOutput"]
        check("facts file content is appended after the generated summary",
              payload["additionalContext"].endswith("ENFORCE_IS_ON"), repr(out[:200]))
        check("injection echoes the firing event name",
              payload["hookEventName"] == "SessionStart", str(payload))

        code, out, _ = session_start(root, event="SubagentStart")
        check("subagents receive the same injection",
              json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SubagentStart")
    finally:
        shutil.rmtree(root)


def test_session_start_sweeps_dead_turn_state():
    """EN/KO: A session that dies mid-turn must not leak its state file forever."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/x1.md"))
        sdir = os.path.join(root, ".claude", "state")
        live = [f for f in os.listdir(sdir) if f.startswith("gate-")]
        check("turn state exists while the turn is open", len(live) == 1, str(live))

        dead = os.path.join(sdir, "gate-deadsession.json")
        with open(dead, "w", encoding="utf-8") as fh:
            fh.write("{}")
        os.utime(dead, (0, 0))  # 1970 — far past any real turn
        session_start(root)
        check("stale turn state is swept at session start", not os.path.exists(dead))
        check("live turn state is left alone",
              len([f for f in os.listdir(sdir) if f.startswith("gate-")]) == 1)
    finally:
        shutil.rmtree(root)


def make_run(root, agent_id, text):
    """
    EN/KO: resolve_subagent_jsonl() 이 찾을 수 있는 자리에 런 파일 하나를 만들고
           transcript_path 를 돌려준다. `text` 는 assistant 의 마지막(유일한)
           텍스트 블록이 된다.
    """
    base_dir = os.path.join(root, "proj")
    session_name = "sess-1"
    subagents_dir = os.path.join(base_dir, session_name, "subagents")
    os.makedirs(subagents_dir, exist_ok=True)
    jsonl_path = os.path.join(subagents_dir, "agent-%s.jsonl" % agent_id)
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        rec = {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return os.path.join(base_dir, session_name + ".jsonl")


def make_handback_run(root, agent_id, text_stub, handback_message):
    """
    EN/KO: 실제 환경의 서브에이전트 종료 형태를 흉내낸다 — 마지막 text 블록은 짧은
           안내문이고, 진짜 보고는 그 뒤 SubagentHandback 툴 호출의 input.message 에
           있다(gate.py:read_verdict() 의 두 번째 후보 경로).
    """
    base_dir = os.path.join(root, "proj")
    session_name = "sess-1"
    subagents_dir = os.path.join(base_dir, session_name, "subagents")
    os.makedirs(subagents_dir, exist_ok=True)
    jsonl_path = os.path.join(subagents_dir, "agent-%s.jsonl" % agent_id)
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        text_rec = {"message": {"role": "assistant",
                                 "content": [{"type": "text", "text": text_stub}]}}
        handback_rec = {"message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "SubagentHandback",
             "input": {"message": handback_message}},
        ]}}
        fh.write(json.dumps(text_rec, ensure_ascii=False) + "\n")
        fh.write(json.dumps(handback_rec, ensure_ascii=False) + "\n")
    return os.path.join(base_dir, session_name + ".jsonl")


def stop_verifier(root, agent_type="critic", agent_id="a1", transcript_path=None):
    p = {"hook_event_name": "SubagentStop", "session_id": "sess-1", "cwd": root,
         "agent_type": agent_type, "agent_id": agent_id}
    if transcript_path:
        p["transcript_path"] = transcript_path
    return run(root, p)


def test_close_gate_reads_critic_verdict():
    """
    EN: The close gate must read the VERDICT line itself, not just "a critic
        ran" — a FAIL must NOT release it, exactly like an unverified turn.
    KO: close 게이트는 "critic 이 돌았다"가 아니라 VERDICT 줄 자체를 읽어야 한다 —
        FAIL 은 미검증 턴과 똑같이 게이트를 풀면 안 된다.
    """
    for verdict, should_block in (("PASS", False), ("CONDITIONAL", False), ("FAIL", True)):
        root = make_repo(ENFORCING)
        try:
            run(root, write_payload(root, "base/v.md", actor="sub"))
            tp = make_run(root, "a1", "실측 내용...\nVERDICT: %s\n" % verdict)
            stop_verifier(root, transcript_path=tp)
            check("critic VERDICT %s -> close %s" % (
                verdict, "still blocks" if should_block else "releases"),
                blocked(stop(root)[1]) == should_block)
        finally:
            shutil.rmtree(root)


def test_close_gate_blocks_on_design_only_critic_report():
    """EN/KO: 판정 줄이 없는 보고(설계 단계)는 close 게이트를 풀지 못한다."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        tp = make_run(root, "a1", "API e2e 설계를 제시한다. 승인을 기다린다.")
        stop_verifier(root, transcript_path=tp)
        check("a critic report with no VERDICT line does not satisfy close",
              blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_close_gate_reads_verdict_from_subagent_handback():
    """
    EN: This harness's subagents report through the `SubagentHandback` tool
        call, not the final assistant text block — a real run's last text
        block was a one-line stub ("Everything is clean. Final report
        below.") and the VERDICT line was in the SubagentHandback right after
        it. Before this fix a PASS there still read as "no-verdict" and
        blocked close forever (bounded only by max_close_blocks).
    KO: 이 하네스의 서브에이전트는 최종 assistant text 블록이 아니라
        `SubagentHandback` 툴 호출로 보고한다 — 실제 런의 마지막 text 블록은
        한 줄짜리 안내("Everything is clean. Final report below.")였고 VERDICT
        줄은 그 바로 뒤 SubagentHandback 에 있었다. 이 수정 전에는 거기 PASS 가
        있어도 "no-verdict" 로 읽혀 close 가 (max_close_blocks 로만 유한하게)
        계속 막혔다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        tp = make_handback_run(root, "a1", "Everything is clean. Final report below.",
                                "수행 보고 전문...\nVERDICT: PASS\n")
        stop_verifier(root, transcript_path=tp)
        check("a PASS delivered via SubagentHandback satisfies the close gate",
              not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_close_gate_blocks_fail_delivered_via_subagent_handback():
    """EN/KO: SubagentHandback 로 온 FAIL 도 차단하고, FAIL 전용 메시지를 낸다."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        tp = make_handback_run(root, "a1", "Final report below.",
                                "결함 발견...\nVERDICT: FAIL\n")
        stop_verifier(root, transcript_path=tp)
        code, out, _ = stop(root)
        check("a FAIL delivered via SubagentHandback still blocks close", blocked(out))
        check("the block message names the FAIL case", "FAIL" in out, repr(out[:160]))
    finally:
        shutil.rmtree(root)


def test_fail_after_pass_in_the_same_turn_reverts_verified():
    """
    EN: A second verifier run that returns FAIL must revert an earlier
        PASS/CONDITIONAL in the same turn — otherwise a later FAIL hides
        behind an earlier pass and the close gate lets the turn through.
    KO: 같은 턴에서 두 번째 검증자가 FAIL 을 내면 앞선 PASS/CONDITIONAL 을
        되돌려야 한다 — 안 그러면 나중 FAIL 이 앞선 통과 뒤에 숨어 close 게이트가
        턴을 그냥 통과시킨다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        tp1 = make_run(root, "a1", "VERDICT: PASS\n")
        stop_verifier(root, agent_id="a1", transcript_path=tp1)
        tp2 = make_run(root, "a2", "VERDICT: FAIL\n")
        stop_verifier(root, agent_id="a2", transcript_path=tp2)
        check("a later FAIL in the same turn reverts an earlier PASS",
              blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_unresolvable_run_file_fails_open():
    """
    EN: No transcript_path (or a run file that cannot be found) must fail open —
        the measured resolution rate is 77% overall and 3/3 for critic, but the
        gate cannot assume every run resolves.
    KO: transcript_path 가 없거나(또는 런 파일을 못 찾으면) fail-open 해야 한다 —
        실측 해결률은 전체 77%, critic 은 3/3이지만 게이트가 모든 런이 해결된다고
        가정할 수는 없다.
    """
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        stop_verifier(root)  # no transcript_path at all
        check("an unresolvable run file still satisfies the close gate (fail-open)",
              not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_require_verdict_false_restores_old_behavior():
    """EN/KO: require_verdict:false 는 갈라진 정본(구버전 critic)을 위한 완화다 — 종전처럼 끝나기만 하면 충족."""
    root = make_repo(dict(ENFORCING, require_verdict=False))
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        tp = make_run(root, "a1", "VERDICT 줄이 없는 옛 critic 보고")
        stop_verifier(root, transcript_path=tp)
        check("require_verdict=false satisfies close even without a VERDICT line",
              not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def write_receipt(root, all_ok, ts):
    d = os.path.join(root, ".claude", "state")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "verify-receipt.json"), "w", encoding="utf-8") as fh:
        json.dump({"ts": ts, "commands": [{"cmd": "true", "exit": 0 if all_ok else 1}],
                   "all_ok": all_ok}, fh)


def test_receipt_fresh_and_ok_satisfies_close():
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        write_receipt(root, True, time.time() + 60)
        check("a fresh all_ok receipt satisfies the close gate",
              not blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_receipt_stale_does_not_satisfy_close():
    """EN/KO: 영수증 시각이 마지막 쓰기보다 앞이면(낡음) close 를 못 푼다."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        write_receipt(root, True, 1)  # 1970 — far older than the write just made
        check("a stale receipt does not satisfy close", blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_receipt_all_ok_false_does_not_satisfy_close():
    """EN/KO: 명령 중 하나라도 실패한(all_ok=false) 영수증은 close 를 못 푼다."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        write_receipt(root, False, time.time() + 60)
        check("a receipt with all_ok=false does not satisfy close",
              blocked(stop(root)[1]))
    finally:
        shutil.rmtree(root)


def test_receipt_alone_satisfies_close_without_any_verifier():
    """EN/KO: 검증자를 한 번도 안 띄워도, 영수증 하나만으로 close 가 풀린다 —
    화면·API 가 없는 변경은 critic 을 아예 스폰하지 않는다는 설계(D6)의 핵심."""
    root = make_repo(ENFORCING)
    try:
        run(root, write_payload(root, "base/v.md", actor="sub"))
        write_receipt(root, True, time.time() + 60)
        code, out, _ = stop(root)
        check("a receipt alone closes a delegated turn with zero verifier spawns",
              not blocked(out), repr(out[:120]))
    finally:
        shutil.rmtree(root)


def test_session_start_injects_config_summary():
    """EN/KO: 생성된 설정 요약이 매 세션 주입되고, 손으로 쓴 사본과 달리 cfg 값 그대로다."""
    root = make_repo(ENFORCING)
    try:
        code, out, _ = session_start(root)
        payload = json.loads(out)["hookSpecificOutput"]
        text = payload["additionalContext"]
        check("config summary names enforce and the file-limit from cfg",
              "enforce=True" in text and "main_thread_file_limit=2" in text, repr(text[:200]))
        check("config summary points at CORE.md as the normative source",
              "harness/CORE.md" in text)
    finally:
        shutil.rmtree(root)


def test_claude_state_other_files_still_exempt():
    """
    EN: `.claude/state/` files OTHER than the receipt must never be product,
        even if a project's own config covers everything — the harness's own
        counter/metrics files live there, and gating them would block the
        harness itself. (The receipt file is a separate, narrower case: see
        test_receipt_forgery_* below — D-014.)
    KO: 영수증을 '제외한' `.claude/state/` 파일은 프로젝트 설정이 전부를 덮어도
        절대 산출물이 아니어야 한다 — 하네스 자신의 카운터·계측 파일이 거기
        있고, 막으면 하네스 자체가 막힌다. (영수증 파일은 더 좁은 별개의
        케이스다 — 아래 test_receipt_forgery_* 참고, D-014.)
    """
    root = make_repo(dict(ENFORCING, product=["**"]))
    try:
        check("direct write under .claude/state/ (non-receipt) is not gated",
              run(root, write_payload(root, ".claude/state/foo.json"))[0] == 0)
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
            "tool_input": {"command": "echo x > .claude/state/foo.json"},
        }
        check("bash write under .claude/state/ (non-receipt) is not gated either",
              run(root, p)[0] == 0)
    finally:
        shutil.rmtree(root)


def test_receipt_forgery_blocked_main_write():
    """EN/KO: D-014 — 메인 스레드의 Write 로 영수증을 직접 쓰는 자기 인증을 막는다."""
    root = make_repo(ENFORCING)
    try:
        code, _, err = run(root, write_payload(root, ".claude/state/verify-receipt.json"))
        check("main thread Write to verify-receipt.json is DENIED", code == 2, "exit=%d" % code)
        check("deny message names verify.sh", "verify.sh" in err, repr(err[:120]))
    finally:
        shutil.rmtree(root)


def test_receipt_forgery_blocked_sub_edit():
    """EN/KO: D-014 — 서브에이전트의 Edit 도 영수증 직접 쓰기는 막는다."""
    root = make_repo(ENFORCING)
    try:
        code, _, _ = run(root, write_payload(root, ".claude/state/verify-receipt.json",
                                              actor="sub", tool="Edit"))
        check("subagent Edit to verify-receipt.json is DENIED too", code == 2, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_receipt_forgery_blocked_bash_redirect():
    """EN/KO: D-014 — Bash 리다이렉트로 영수증에 all_ok:true 를 바로 쓰는 것도 막는다."""
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
            "tool_input": {"command":
                            "echo '{\"all_ok\":true}' > .claude/state/verify-receipt.json"},
        }
        code, _, _ = run(root, p)
        check("bash redirect into verify-receipt.json is DENIED", code == 2, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_verify_sh_execution_not_blocked():
    """EN/KO: 영수증을 '쓰는' 유일한 정당한 경로 — verify.sh 실행 자체는 통과한다."""
    root = make_repo(ENFORCING)
    try:
        p = {
            "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
            "cwd": root, "tool_name": "Bash", "tool_use_id": "tu-1",
            "tool_input": {"command": "bash harness/tools/verify.sh"},
        }
        code, _, _ = run(root, p)
        check("running verify.sh itself is allowed", code == 0, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def test_receipt_forgery_observed_only_when_not_enforcing():
    """EN/KO: D-014 — enforce:false 는 다른 게이트와 같이 관측만 하고 막지 않는다."""
    root = make_repo(dict(ENFORCING, enforce=False))
    try:
        code, _, _ = run(root, write_payload(root, ".claude/state/verify-receipt.json"))
        check("non-enforcing config does not block the receipt write",
              code == 0, "exit=%d" % code)
    finally:
        shutil.rmtree(root)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print(fn.__name__)
        fn()
    print("\n%d passed, %d failed" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
