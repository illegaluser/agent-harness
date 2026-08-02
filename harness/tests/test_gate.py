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


def spawn(root, subagent_type, tool="Agent"):
    return run(root, {
        "hook_event_name": "PreToolUse", "session_id": "sess-1", "prompt_id": "t1",
        "cwd": root, "tool_name": tool, "tool_use_id": "tu-1",
        "tool_input": {"subagent_type": subagent_type, "prompt": "..."},
    })


def approve(root):
    return run(root, {
        "hook_event_name": "PostToolUse", "session_id": "sess-1", "prompt_id": "t1",
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
