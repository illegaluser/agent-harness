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
import shutil
import subprocess
import sys
import tempfile

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


def stop(root, event="Stop", agent_type=None, agent_id=None):
    p = {"hook_event_name": event, "session_id": "sess-1", "cwd": root}
    if agent_id:
        p["agent_id"] = agent_id
    if agent_type:
        p["agent_type"] = agent_type
    return run(root, p)


def blocked(out):
    return '"decision": "block"' in out


def test_close_gate_blocks_unverified_delegation():
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


def spawn(root, subagent_type, tool="Agent", session="sess-1"):
    return run(root, {
        "hook_event_name": "PreToolUse", "session_id": session, "prompt_id": "t1",
        "cwd": root, "tool_name": tool, "tool_use_id": "tu-1",
        "tool_input": {"subagent_type": subagent_type, "prompt": "..."},
    })


def approve(root, session="sess-1"):
    return run(root, {
        "hook_event_name": "PostToolUse", "session_id": session, "prompt_id": "t1",
        "cwd": root, "tool_name": "ExitPlanMode", "tool_input": {}, "tool_response": {},
    })


def test_approval_gate_blocks_unapproved_maker():
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
        rows = [json.loads(l) for l in
                open(os.path.join(root, ".claude", "state", "harness-metrics.jsonl"),
                     encoding="utf-8") if l.strip()]
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
    EN: The facts file is how a fresh session inherits the harness state without
        a human re-explaining it. If injection silently stops working, every
        later session starts blind — and nothing else would reveal that.
    KO: 새 세션이 사람의 재설명 없이 하네스 상태를 물려받는 경로가 이 파일이다.
        주입이 조용히 멎으면 이후 모든 세션이 눈먼 채로 시작하는데, 그걸 드러내는
        다른 장치가 없다.
    """
    root = make_repo(ENFORCING)
    try:
        code, out, _ = session_start(root)
        check("no facts file → silent no-op", code == 0 and out.strip() == "", repr(out[:60]))

        with open(os.path.join(root, ".claude", "harness-facts.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("ENFORCE_IS_ON")
        code, out, _ = session_start(root)
        payload = json.loads(out)["hookSpecificOutput"]
        check("facts file is injected as additionalContext",
              payload["additionalContext"] == "ENFORCE_IS_ON", repr(out[:80]))
        check("injection echoes the firing event name",
              payload["hookEventName"] == "SessionStart", str(payload))

        code, out, _ = session_start(root, event="SubagentStart")
        check("subagents receive the same facts",
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
