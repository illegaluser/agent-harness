#!/usr/bin/env python3
"""
gate.py — the harness's single enforcement point.

EN: One hook script wired to every event we care about; it dispatches on
    `hook_event_name` from the payload rather than on a `--mode` flag, so
    adding an event never means adding a file. Three jobs:
      1. write gate   (PreToolUse)  — the main thread may not freely edit
                                      product files; subagents may.
      2. close gate   (Stop/SubagentStop) — resets the per-turn counter, and
                                      is the place a completion check will hang.
      3. metrics      (every event) — one JSON line per event, events only,
                                      never prompt or file content.
    Everything fails open: a bug here must never wedge a session.

KO: 우리가 신경 쓰는 모든 훅 이벤트에 하나로 배선되는 스크립트다. `--mode` 플래그가 아니라
    페이로드의 `hook_event_name` 으로 분기하므로 이벤트가 늘어도 파일이 늘지 않는다. 하는 일 셋:
      1. write 게이트  (PreToolUse) — 메인 스레드는 산출물 파일을 자유롭게 못 고친다.
                                      서브에이전트는 통과한다.
      2. close 게이트  (Stop/SubagentStop) — 턴 카운터를 리셋하고, 완료 검사가 걸릴 자리다.
      3. 계측          (모든 이벤트) — 이벤트당 JSON 한 줄. 이벤트만 남기고
                                      프롬프트·파일 내용은 절대 안 남긴다.
    전부 fail-open 이다. 여기 버그가 세션을 멈추게 해서는 안 된다.

Runtime facts this relies on (verified against the official hooks reference and
the installed Claude Code binary, 2026-08-02):
  - `agent_id` is present ONLY when the hook fires inside a subagent, and is
    absent on the main thread even in `--agent` sessions. `agent_type` is NOT a
    reliable discriminator (it can appear on a main thread started with --agent).
  - PreToolUse blocks via exit code 2 with the message on stderr.
  - Stop/SubagentStop block via {"decision":"block","reason":...} on stdout.
  - `prompt_id` requires Claude Code >= 2.1.196; we use it when present and fall
    back to resetting the counter on Stop, which is the same turn boundary.
"""

import fnmatch
import json
import os
import sys
import time

CONFIG_REL = ".claude/harness.json"
STATE_REL = ".claude/state"
METRICS_NAME = "harness-metrics.jsonl"
FACTS_REL = ".claude/harness-facts.md"

# EN: Safe defaults — an empty product list means the write gate matches nothing,
#     so an unconfigured install is inert rather than obstructive.
# KO: 안전한 기본값 — product 가 비면 write 게이트가 아무것도 안 잡는다.
#     설정 안 된 설치는 방해가 아니라 무동작이 된다.
DEFAULTS = {
    "enforce": False,
    "product": [],
    "exempt": [],
    "main_thread_file_limit": 2,
    "verifiers": ["critic"],
    "close_gate": True,
    "max_close_blocks": 2,
    "approval_gate": True,
    "write_agents": ["maker"],
    "metrics": True,
}

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SPAWN_TOOLS = ("Agent", "Task")

# EN: Bash escape hatches that write files without going through Write/Edit.
# KO: Write/Edit 를 거치지 않고 파일을 쓰는 Bash 우회 경로.
BASH_WRITE_MARKERS = (
    r"\bsed\s+[^|;&]*-\w*i",
    r"\bperl\s+[^|;&]*-\w*i",
    r"\btee\b",
    r">>?",
)


def repo_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def load_config(root):
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(root, CONFIG_REL), encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return cfg


def state_dir(root):
    d = os.path.join(root, STATE_REL)
    os.makedirs(d, exist_ok=True)
    return d


def emit_metric(root, cfg, record):
    """
    EN: Append one event line. Events only — no prompt text, no file contents.
        Metrics must never be the reason a hook fails, hence the bare except.
    KO: 이벤트 한 줄 append. 이벤트만 — 프롬프트 텍스트도 파일 내용도 안 남긴다.
        계측이 훅 실패의 원인이 되면 안 되므로 예외를 통째로 삼킨다.
    """
    if not cfg.get("metrics", True):
        return
    try:
        record["ts"] = int(time.time())
        with open(os.path.join(state_dir(root), METRICS_NAME), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def rel_path(root, path):
    try:
        return os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    except (OSError, ValueError):
        return path


def matches_any(rel, patterns):
    """
    EN: fnmatch's `*` crosses `/`, which is what we want: "base/**" and "base/*"
        both mean "anything under base/". We normalize `**` to `*` so config
        files can be written either way.
    KO: fnmatch 의 `*` 는 `/` 를 넘는다 — "base/**" 든 "base/*" 든 "base/ 아래 전부"가 된다.
        설정 파일을 어느 쪽으로 쓰든 되도록 `**` 를 `*` 로 정규화한다.
    """
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat.replace("**", "*")):
            return True
    return False


def is_product(root, cfg, path):
    if not path:
        return False
    rel = rel_path(root, path)
    if rel.startswith(".."):
        return False  # outside the repo — not our product
    if matches_any(rel, cfg.get("exempt", [])):
        return False
    return matches_any(rel, cfg.get("product", []))


def turn_key(payload):
    """
    EN: prompt_id changes once per user prompt and is the exact turn boundary.
        Below 2.1.196 it is absent — we return None and rely on the Stop event
        to clear the counter, which is the same boundary. Returning None rather
        than falling back to session_id matters: if some events carried a
        prompt_id and others didn't, a session_id fallback would read as a
        *different* turn and silently split the turn's state in two.
    KO: prompt_id 는 사용자 프롬프트마다 바뀌는 정확한 턴 경계다. 2.1.196 미만에는
        없으므로 None 을 돌려주고 Stop 이벤트가 같은 경계를 만든다. session_id 로
        대체하지 않는 것이 중요하다 — 일부 이벤트에만 prompt_id 가 실리면 그 대체값이
        '다른 턴'으로 읽혀 한 턴의 상태가 조용히 둘로 쪼개진다.
    """
    return payload.get("prompt_id")


def counter_file(root, payload):
    sid = "".join(c for c in str(payload.get("session_id", "nosession")) if c.isalnum() or c == "-")
    return os.path.join(state_dir(root), "gate-%s.json" % (sid or "nosession"))


def read_counter(path, turn):
    """
    EN: A stored turn is only invalidated when we can *prove* the turn changed —
        i.e. this payload carries a turn id and it differs. An absent turn id is
        not evidence of a new turn, so it inherits the stored state.
    KO: 저장된 턴은 바뀌었다는 것이 **증명될 때만** 무효화한다 — 이 페이로드에 턴 id 가
        있고 그것이 다를 때. 턴 id 가 없는 것은 새 턴이라는 증거가 아니므로 기존 상태를
        그대로 물려받는다.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        if turn is None or saved.get("turn") == turn:
            return saved
    except (OSError, ValueError):
        pass
    return {"turn": turn, "files": []}


def write_counter(path, data):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def allow():
    sys.exit(0)


def deny(message):
    """EN/KO: PreToolUse blocks with exit code 2; stderr goes back to the model."""
    sys.stderr.write(message)
    sys.exit(2)


def bash_targets(command, root, cfg):
    """
    EN: Cheap, deliberately conservative: only if the command looks like it
        writes at all do we bother extracting path-shaped tokens and testing
        them against the product globs. Misses exotic bypasses by design —
        this is a runaway guard, not a sandbox.
    KO: 일부러 보수적이고 싸게 만들었다. 쓰기처럼 보이는 명령일 때만 경로 모양 토큰을 뽑아
        product 글롭에 대본다. 별난 우회는 놓친다 — 이건 샌드박스가 아니라 폭주 방지 장치다.
    """
    import re

    if not any(re.search(m, command) for m in BASH_WRITE_MARKERS):
        return []
    hits = []
    for token in re.findall(r"[A-Za-z0-9_./~-]+", command):
        if "." in token or "/" in token:
            if is_product(root, cfg, os.path.join(root, token.lstrip("./"))):
                hits.append(rel_path(root, os.path.join(root, token.lstrip("./"))))
    return hits


def load_turn(root, payload):
    """EN/KO: (path, state) for this turn. `wrote` feeds the close gate."""
    cpath = counter_file(root, payload)
    state = read_counter(cpath, turn_key(payload))
    state.setdefault("files", [])
    state.setdefault("wrote", [])
    state.setdefault("delegated", False)
    state.setdefault("verified", False)
    state.setdefault("approved", False)
    state.setdefault("close_blocks", 0)
    return cpath, state


def bash_gate(root, cfg, payload, base):
    """EN/KO: Main thread must not edit product files through the shell."""
    hits = bash_targets((payload.get("tool_input") or {}).get("command", ""), root, cfg)
    if not hits:
        allow()
    emit_metric(root, cfg, dict(base, decision="deny" if cfg["enforce"] else "observe",
                                reason="bash-bypass", paths=hits[:5]))
    if cfg["enforce"]:
        deny(
            "[harness] 메인 스레드는 Bash 로 산출물 파일을 수정할 수 없다: %s\n"
            "Edit/Write 를 쓰거나 maker 서브에이전트에 위임하라.\n" % ", ".join(hits[:5])
        )
    allow()


def write_gate(root, cfg, payload, base, actor, rel):
    """
    EN: Every product write is recorded (both actors) so the close gate knows
        the turn changed something. Only the main thread is rate-limited —
        delegation is the sanctioned path, and which subagents may write at all
        is already fixed by their `tools:` frontmatter.
    KO: 산출물 쓰기는 양쪽 다 기록한다 — close 게이트가 "이번 턴에 뭔가 바뀌었다"를
        알아야 하기 때문이다. 개수 제한은 메인 스레드에만 건다. 위임이 정규 경로이고,
        어느 서브에이전트가 쓸 수 있는지는 이미 각자의 `tools:` 가 정한다.
    """
    cpath, state = load_turn(root, payload)
    if rel not in state["wrote"]:
        state["wrote"].append(rel)

    if actor == "sub":
        state["delegated"] = True
        write_counter(cpath, state)
        emit_metric(root, cfg, dict(base, decision="allow", reason="subagent", path=rel))
        allow()

    if rel in state["files"]:
        write_counter(cpath, state)
        emit_metric(root, cfg, dict(base, decision="allow", reason="same-file", path=rel))
        allow()

    limit = int(cfg.get("main_thread_file_limit", 2))
    if len(state["files"]) < limit:
        state["files"].append(rel)
        write_counter(cpath, state)
        emit_metric(root, cfg, dict(base, decision="allow", reason="under-limit",
                                    path=rel, count=len(state["files"]), limit=limit))
        allow()

    write_counter(cpath, state)
    emit_metric(root, cfg, dict(base, decision="deny" if cfg["enforce"] else "observe",
                                reason="over-limit", path=rel,
                                count=len(state["files"]), limit=limit))
    if cfg["enforce"]:
        deny(
            "[harness] 이번 턴에 메인 스레드가 직접 고친 산출물 파일이 이미 %d 개다 (%s).\n"
            "3 개째부터는 계획이 필요하다 — maker 서브에이전트에 위임하라.\n"
            % (limit, ", ".join(state["files"]))
        )
    allow()


def spawn_gate(root, cfg, payload, base):
    """
    EN: Spawning the write-capable role is the moment the approval gate has to
        hold — it is the last observable point before a plan becomes edits.
        The only user approval a hook can actually *see* is an accepted
        ExitPlanMode; anything else would be the orchestrator certifying its own
        authorization, which is exactly what this gate exists to prevent.
    KO: 쓰기 권한 역할을 띄우는 순간이 승인 게이트가 서야 할 자리다 — 계획이 편집으로
        바뀌기 직전의 마지막 관측 지점이다. 훅이 실제로 **볼 수 있는** 사용자 승인은
        수락된 ExitPlanMode 뿐이다. 그 외는 오케스트레이터가 자기 권한을 스스로
        인증하는 것이고, 이 게이트는 바로 그걸 막으려고 있다.
    """
    sub = (payload.get("tool_input") or {}).get("subagent_type", "")
    base = dict(base, subagent_type=sub)
    if sub not in cfg.get("write_agents", []):
        emit_metric(root, cfg, dict(base, decision="allow", reason="spawn"))
        allow()

    _, state = load_turn(root, payload)
    if state["approved"]:
        emit_metric(root, cfg, dict(base, decision="allow", reason="spawn-approved"))
        allow()

    enforcing = cfg.get("approval_gate") and cfg.get("enforce")
    emit_metric(root, cfg, dict(base, decision="deny" if enforcing else "observe",
                                reason="spawn-unapproved"))
    if enforcing:
        deny(
            "[harness] '%s' 는 쓰기 권한 역할이라 사용자 승인 없이 띄울 수 없다.\n"
            "계획을 제시하고 승인(ExitPlanMode)을 받은 뒤 다시 호출하라.\n" % sub
        )
    allow()


def handle_pretooluse(root, cfg, payload):
    tool = payload.get("tool_name", "")
    actor = "sub" if payload.get("agent_id") else "main"
    base = {
        "event": "PreToolUse",
        "session": payload.get("session_id"),
        "actor": actor,
        "agent_type": payload.get("agent_type"),
        "tool": tool,
    }

    if tool in SPAWN_TOOLS:
        spawn_gate(root, cfg, payload, base)

    if tool == "Bash" and actor == "main":
        bash_gate(root, cfg, payload, base)

    if tool in WRITE_TOOLS:
        tool_input = payload.get("tool_input") or {}
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if is_product(root, cfg, path):
            write_gate(root, cfg, payload, base, actor, rel_path(root, path))
        emit_metric(root, cfg, dict(base, decision="allow", reason="not-product"))
        allow()

    # EN/KO: Everything else is observed only — this is where per-role tool-call
    #        cost comes from. Nothing is gated here.
    emit_metric(root, cfg, dict(base, decision="allow", reason="observe"))
    allow()


def handle_posttooluse(root, cfg, payload):
    """
    EN: PostToolUse only fires when the tool actually ran, so seeing it for
        ExitPlanMode means the user accepted the plan — a rejected plan is
        denied at PreToolUse and never reaches here. That asymmetry is what
        makes this a trustworthy approval signal rather than a self-report.
    KO: PostToolUse 는 툴이 실제로 실행됐을 때만 발화한다. 그래서 ExitPlanMode 에서
        이게 보이면 사용자가 계획을 수락한 것이다 — 거절된 계획은 PreToolUse 에서
        막혀 여기까지 오지 않는다. 이 비대칭이 자기 보고가 아닌 신뢰 가능한 승인
        신호를 만든다.
    """
    if payload.get("tool_name") == "ExitPlanMode":
        cpath, state = load_turn(root, payload)
        state["approved"] = True
        write_counter(cpath, state)
        emit_metric(root, cfg, {
            "event": "PostToolUse",
            "session": payload.get("session_id"),
            "actor": "main",
            "tool": "ExitPlanMode",
            "decision": "allow",
            "reason": "approval-recorded",
        })
    allow()


def handle_subagent_stop(root, cfg, payload):
    """
    EN: A verifier finishing is what satisfies the close gate. Note this must
        NOT clear the turn counter — a subagent ending is not a turn boundary,
        and clearing here would hand the main thread a fresh write budget.
    KO: 검증자가 끝나는 것이 close 게이트의 충족 조건이다. 여기서 턴 카운터를 비우면
        안 된다 — 서브에이전트 종료는 턴 경계가 아니고, 비우면 메인 스레드가
        쓰기 예산을 새로 받는다.
    """
    agent_type = payload.get("agent_type")
    if agent_type in cfg.get("verifiers", []):
        cpath, state = load_turn(root, payload)
        state["verified"] = True
        write_counter(cpath, state)
    emit_metric(root, cfg, {
        "event": "SubagentStop",
        "session": payload.get("session_id"),
        "actor": "sub",
        "agent_type": agent_type,
        "decision": "allow",
        "reason": "verified" if agent_type in cfg.get("verifiers", []) else "subagent-stop",
    })
    allow()


def handle_stop(root, cfg, payload):
    """
    EN: The turn boundary — and the close gate. If the turn changed product
        files but no verifier ran, block once so the verdict happens before the
        turn ends. Bounded: after `max_close_blocks` it releases regardless, so
        a stuck verification can never wedge the session.
        Clearing the counter is also what gives per-turn semantics on Claude
        Code builds older than 2.1.196, which have no `prompt_id`.
    KO: 턴 경계이자 close 게이트다. 이번 턴에 산출물이 바뀌었는데 검증자가 안 돌았으면
        한 번 차단해 판정을 턴 종료 전으로 당긴다. 유한하다 — `max_close_blocks` 회
        이후엔 무조건 통과시켜, 검증이 막혀도 세션이 영영 멈추지 않는다.
        카운터를 비우는 것이 `prompt_id` 없는 구버전에서 턴 단위 동작을 만든다.
    """
    cpath, state = load_turn(root, payload)
    base = {
        "event": "Stop",
        "session": payload.get("session_id"),
        "actor": "main",
        "wrote": len(state["wrote"]),
    }

    # EN: Verification is owed by turns that crossed into delegation — a
    #     subagent wrote, or the direct-handling budget was exceeded. A turn the
    #     main thread handled inside its budget is the "small enough to do
    #     directly" band and does not owe a critic round trip; demanding one
    #     there would make the cheap path cost the same as the expensive one.
    #     This is a threshold, not a judgment call — it reuses the write gate's
    #     own limit rather than introducing a second number.
    # KO: 검증 의무는 위임 영역으로 넘어간 턴에 생긴다 — 서브에이전트가 썼거나, 직접
    #     처리 예산을 넘겼거나. 메인이 예산 안에서 끝낸 턴은 "직접 해도 되는" 구간이라
    #     critic 왕복을 지지 않는다. 거기까지 강제하면 싼 경로가 비싼 경로와 같아진다.
    #     재량이 아니라 문턱이며, 새 숫자가 아니라 write 게이트의 한도를 그대로 쓴다.
    limit = int(cfg.get("main_thread_file_limit", 2))
    owes_verification = state["delegated"] or len(state["wrote"]) > limit
    base["delegated"] = state["delegated"]

    blocking = (
        cfg.get("close_gate")
        and cfg.get("enforce")
        and owes_verification
        and not state["verified"]
        and state["close_blocks"] < int(cfg.get("max_close_blocks", 2))
    )
    if blocking:
        state["close_blocks"] += 1
        write_counter(cpath, state)
        emit_metric(root, cfg, dict(base, decision="block", reason="unverified",
                                    blocks=state["close_blocks"]))
        print(json.dumps({
            "decision": "block",
            "reason": (
                "[harness] 이번 턴에 산출물이 바뀌었는데 검증자가 돌지 않았다: %s\n"
                "critic 서브에이전트로 판정을 받고 끝내라."
                % ", ".join(state["wrote"][:5])
            ),
        }, ensure_ascii=False))
        allow()

    try:
        os.remove(cpath)
    except OSError:
        pass
    emit_metric(root, cfg, dict(base, decision="allow",
                                reason="verified" if state["verified"] else "turn-reset"))
    allow()


def sweep_stale_turns(root, keep_hours=24):
    """
    EN: Turn state is keyed by session id and normally deleted at Stop. A session
        that dies mid-turn leaves its file behind forever, so sweep old ones at
        session start. A turn never spans a day, so anything older than 24h is
        certainly dead — this is not a tunable threshold, it is a wide margin
        over a bound the data cannot cross.
    KO: 턴 상태는 세션 id 로 키를 잡고 보통 Stop 에서 지워진다. 턴 도중에 죽은 세션은
        파일을 영영 남기므로 세션 시작 때 오래된 것을 쓸어낸다. 턴이 하루를 넘길 수는
        없으니 24시간 초과는 확실히 죽은 것이다 — 조율 대상 문턱이 아니라, 데이터가
        넘을 수 없는 경계에 넉넉히 얹은 값이다.
    """
    try:
        d = state_dir(root)
        cutoff = time.time() - keep_hours * 3600
        for name in os.listdir(d):
            if name.startswith("gate-") and name.endswith(".json"):
                p = os.path.join(d, name)
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
    except OSError:
        pass


def handle_session_start(root, cfg, payload):
    """EN/KO: Inject repo facts if the project wrote any. Silent no-op otherwise."""
    sweep_stale_turns(root)
    emit_metric(root, cfg, {
        "event": payload.get("hook_event_name", "SessionStart"),
        "session": payload.get("session_id"),
        "actor": "sub" if payload.get("agent_id") else "main",
        "decision": "allow",
        "reason": "start",
    })
    facts = os.path.join(root, FACTS_REL)
    if not os.path.isfile(facts):
        allow()
    try:
        with open(facts, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        allow()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": payload.get("hook_event_name", "SessionStart"),
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    allow()


HANDLERS = {
    "PreToolUse": handle_pretooluse,
    "PostToolUse": handle_posttooluse,
    "Stop": handle_stop,
    "SubagentStop": handle_subagent_stop,
    "SessionStart": handle_session_start,
    "SubagentStart": handle_session_start,
}


def main():
    payload = json.load(sys.stdin)
    root = repo_root()
    cfg = load_config(root)
    handler = HANDLERS.get(payload.get("hook_event_name", ""))
    if handler is None:
        allow()
    handler(root, cfg, payload)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # EN/KO: fail-open — a broken gate must not be able to wedge a session.
        sys.exit(0)
