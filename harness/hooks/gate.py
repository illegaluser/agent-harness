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
import importlib.util
import json
import os
import re
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

# EN: Writers whose target is an argument, not a redirect. A segment matching one
#     of these makes every path-shaped token *in that segment* a candidate target.
#     `\b`, not `(?:^|\s)` — the latter missed absolute invocations (`/usr/bin/sed`,
#     `/bin/rm`) because the character right before the word is `/`, not whitespace
#     or start-of-segment. `\b` matches both `/usr/bin/sed` (boundary at `/`) and
#     still excludes `used`/`confirm` (no boundary between two word characters).
# KO: 대상이 리다이렉트가 아니라 인자인 쓰기 명령. 세그먼트가 이 중 하나에 매치되면
#     그 세그먼트 안의 경로 모양 토큰 전부가 후보 대상이 된다.
#     `(?:^|\s)` 가 아니라 `\b` 를 쓴다 — 전자는 단어 앞이 `/`인 절대경로 호출
#     (`/usr/bin/sed`, `/bin/rm`)을 놓쳤다. `\b` 는 `/usr/bin/sed` 도 매치하면서
#     (`/` 에서 경계 성립) `used`/`confirm` 은 여전히 제외한다(단어 문자끼리는 경계가 없다).
#     `(?<!-)` keeps a flag from being read as the command: `docker run --rm` names
#     no file to delete, and blocking it blocked ordinary container work.
# KO(cont): `(?<!-)` 는 플래그가 명령으로 읽히지 않게 한다 — `docker run --rm` 은 지울
#     파일을 지목하지 않는데, 이것을 막으면 평범한 컨테이너 작업이 막혔다.
#     `rm` is exempted when it is `git rm --cached`: that stages a removal in the
#     index and leaves the working tree file alone, so blocking it blocked
#     ordinary un-tracking. Plain `git rm` (no --cached) does delete the file and
#     stays blocked. `docker` is excluded outright — `docker rm docs` names a
#     container, not a path, and there is no container subcommand that writes a
#     host path we can see from the command line alone.
# KO(cont): `git rm --cached` 는 인덱스에만 삭제를 올리고 워킹트리 파일은 그대로 두므로
#     예외로 둔다 — 막으면 평범한 추적 해제가 막혔다. `--cached` 없는 `git rm` 은 파일을
#     실제로 지우므로 계속 막는다. `docker` 는 통째로 제외한다 — `docker rm docs` 의
#     `docs` 는 컨테이너 이름이지 경로가 아니고, 명령줄만 보고 호스트 경로를 쓴다고
#     판정할 수 있는 컨테이너 하위명령이 없다.
ARG_WRITE_MARKERS = (
    r"(?<!-)\bsed\s+[^\n]*-\w*i",
    r"(?<!-)\bperl\s+[^\n]*-\w*i",
    r"(?<!-)\bawk\s+[^\n]*-i\s*inplace",
    r"(?<!-)\bed\s",
    r"(?<!-)\bex\s+[^\n]*-\w*s",
    r"(?<!-)\btee\b",
    r"(?<!-)\btruncate\b",
    r"(?<!-)\brm\b",
    r"(?<!-)\brmdir\b",
    r"\bgit\b[^\n]*\b(?:checkout|restore|apply)\b",
)

# EN: Segments that look like a write marker but are not. Checked before the
#     markers, so a match here means "not a target segment" outright.
# KO: 쓰기 마커처럼 보이지만 아닌 세그먼트. 마커보다 먼저 검사하며, 여기 걸리면
#     대상 세그먼트가 아닌 것으로 확정한다.
WRITE_MARKER_EXEMPTIONS = (
    r"\bgit\b[^\n]*\brm\b[^\n]*--cached\b",
    r"\bdocker\b",
)

# EN: Writers whose target is the LAST path-shaped argument in the segment —
#     cp/mv/install take source(s) then destination; only the destination is
#     a target, so the source is not falsely flagged as being overwritten.
# KO: 대상이 세그먼트의 '마지막' 경로 모양 인자인 쓰기 명령. cp/mv/install 은
#     원본(들) 다음에 목적지가 오므로 목적지만 대상이다 — 원본을 덮어쓴다고
#     오판하지 않는다.
#     `install` is anchored to the start of the segment and must be the whole word:
#     coreutils `install` is the command itself, whereas `pip install` / `npm install`
#     are subcommands that write nothing here, and `bash harness/install.sh` merely
#     *runs* a file named install.sh. Both were blocked — the second made the
#     harness's own installer unrunnable from a main thread.
# KO(cont): `install` 은 세그먼트 맨 앞에 오고 낱말 전체여야 한다. coreutils 의
#     `install` 은 명령 자신이지만 `pip install`·`npm install` 은 여기서 아무것도 쓰지
#     않는 하위명령이고, `bash harness/install.sh` 는 install.sh 라는 파일을 *실행*할
#     뿐이다. 둘 다 막혔었다 — 뒤엣것 때문에 하네스 자기 설치기를 메인 스레드에서
#     돌릴 수 없었다.
LAST_TOKEN_WRITE_MARKERS = (
    r"(?<!-)\bcp\b",
    r"(?<!-)\bmv\b",
    r"(?<!-)\bln\b",
    r"^\s*(?:\S*/)?install(?=\s|$)",
)

# EN: `>`/`>>` with an optional fd number or `&`, optional `|` (noclobber override)
#     and optional opening quote, capturing only the target word. `2>&1` cannot
#     match — `&` is not in the target class, so it names no file. The lookbehind
#     excludes only `>` and `&` (not `<`): `<` blocked no real false positive
#     (heredocs/`<`/`<<<` never reach here because REDIRECT_RE itself requires a
#     literal `>`) but did block `exec 3<> file` (read-write open), a real miss.
# KO: 앞에 fd 번호나 `&`, 뒤에 `|`(noclobber)·따옴표가 붙을 수 있는 `>`/`>>` 와 그 대상.
#     `2>&1` 은 매치되지 않는다 — `&` 가 대상 문자 집합에 없어 파일을 지목하지 않는다.
#     lookbehind 는 `>`·`&` 만 제외한다(`<` 는 제외 안 함) — `<` 를 제외해도 실제
#     오탐은 안 막았다(heredoc·`<`·`<<<` 는 REDIRECT_RE 자체가 리터럴 `>` 를 요구해
#     애초에 안 걸린다) 반면 `exec 3<> file`(읽기-쓰기 오픈)은 실제 미탐이었다.
REDIRECT_RE = re.compile(r"(?<![>&])(?:[0-9]+|&)?>>?\|?\s*[\"']?([A-Za-z0-9_./~-]+)")

# EN: Command separators. A `|` right after `>` is the noclobber form, not a pipe.
# KO: 명령 구분자. `>` 바로 뒤의 `|` 는 파이프가 아니라 noclobber 표기다.
SEGMENT_RE = re.compile(r"\|\||&&|(?<!>)[|;&\n]")

PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_./~-]+")

# EN: A `cd` segment with a literal argument (not `-`, not empty). Option flags
#     (-L/-P/-e/-@) and the `--` end-of-options marker are skipped so `cd -P base`
#     tracks like `cd base`; a trailing `# comment` is ignored. The argument keeps
#     its quotes here and is unquoted at use — `cd "base"` must track exactly like
#     `cd base`, since quoting a path is the ordinary way to write it. We deliberately
#     do not try to resolve `cd $VAR` correctly — its target segment still gets
#     tracked as a literal (bogus) directory, which never matches a real product
#     glob, i.e. it degrades to a miss rather than a false block.
# KO: 리터럴 인자를 가진 `cd` 세그먼트(`-`도 빈 인자도 아님). 옵션 플래그(-L/-P/-e/-@)와
#     옵션 종료 표시 `--` 를 건너뛰어 `cd -P base` 가 `cd base` 와 같이 추적되게 하고,
#     끝의 `# 주석` 은 무시한다. 인자는 따옴표를 단 채로 잡아 쓰는 자리에서 벗긴다 —
#     경로에 따옴표를 씌우는 것은 평범한 표기이므로 `cd "base"` 는 `cd base` 와 정확히
#     같이 추적돼야 한다. `cd $VAR` 를 올바르게 풀려고 하지 않는다 — 대상 세그먼트가
#     리터럴(가짜) 디렉터리로 추적되는데, 이는 실제 product 글롭에 매치되지 않으므로
#     오차단이 아니라 미탐으로 완화된다.
CD_RE = re.compile(r"^\s*cd\b(.*)$")
CD_FLAGS = ("-L", "-P", "-e", "-@", "-LP", "-PL", "--")


def cd_target(rest):
    """
    EN: The directory a `cd` segment lands in, or None to reset to the repo root.
        `rest` is everything after the `cd` word. Parsed in code, not in the regex,
        so no nested quantifier can backtrack on a long command line.
    KO: `cd` 세그먼트가 도착하는 디렉터리. None 이면 저장소 루트로 되돌린다는 뜻이다.
        `rest` 는 `cd` 낱말 뒤 전부다. 정규식이 아니라 코드로 파싱한다 — 중첩 수량자가
        긴 명령줄에서 백트래킹하지 않게 하려는 것이다.
    """
    words = rest.split("#", 1)[0].split()
    while words and words[0] in CD_FLAGS:
        words.pop(0)
    if not words or words[0] == "-":
        return None
    return words[0].strip("\"'")


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


def rel_path_logical(root, path):
    """
    EN: The path as *written*, resolved against the repo root but WITHOUT
        following symlinks. realpath() alone let a symlink inside a product
        directory point outside the repo; the resolved path then started with
        ".." and is_product() called it foreign, so the write gate and the bash
        gate both waved it through. The name the caller used is `docs/link.md`,
        and that is a product path no matter where the inode lives.
        This also fixes relative file_path: the write gate never resolved
        against the root the way bash_targets does, so `docs/a.md` (relative)
        was judged against the process cwd.
    KO: **쓰인 그대로**의 경로를 저장소 루트 기준으로 풀되 심링크는 따라가지 않는다.
        realpath() 만 쓰면 산출물 디렉터리 안의 심링크가 저장소 밖을 가리킬 때 해석
        결과가 ".." 로 시작해 is_product() 가 남의 것으로 판정했고, 쓰기 게이트와 bash
        게이트가 둘 다 통과시켰다. 호출자가 쓴 이름은 `docs/link.md` 이고, inode 가
        어디에 있든 그것은 산출물 경로다.
        상대경로 file_path 도 여기서 같이 고쳐진다 — 쓰기 게이트는 bash_targets 와
        달리 루트 기준으로 풀지 않아 `docs/a.md` 를 프로세스 cwd 기준으로 판정했다.
    """
    try:
        if not os.path.isabs(path):
            path = os.path.join(root, path)
        return os.path.relpath(os.path.normpath(path), os.path.normpath(root))
    except (OSError, ValueError):
        return path


def matches_any(rel, patterns):
    """
    EN: fnmatch's `*` crosses `/`, which is what we want: "base/**" and "base/*"
        both mean "anything under base/". We normalize `**` to `*` so config
        files can be written either way.
        The second test makes a *directory itself* match the glob that covers its
        contents: rel_path()/realpath() strip trailing slashes, so `rm -rf base/`
        arrives here as "base", which "base/*" does not match — the token that
        destroys every product file under it would otherwise be the one token the
        gate ignores. Appending a sentinel child ("base" -> "base/\x00") asks the
        real question: "does this glob cover anything inside this path?" \x00 is
        used because no filesystem allows it in a name, so it can never collide
        with a real child.
    KO: fnmatch 의 `*` 는 `/` 를 넘는다 — "base/**" 든 "base/*" 든 "base/ 아래 전부"가 된다.
        설정 파일을 어느 쪽으로 쓰든 되도록 `**` 를 `*` 로 정규화한다.
        두 번째 검사는 **디렉터리 자체**가 그 내용물을 덮는 글롭에 매치되게 한다.
        rel_path()/realpath() 가 끝 슬래시를 지우므로 `rm -rf base/` 는 여기에 "base"
        로 도착하는데 "base/*" 는 그것과 매치되지 않는다 — 아래 산출물을 전부 파괴하는
        바로 그 토큰만 게이트가 무시하게 된다. 센티넬 자식을 붙여("base" -> "base/\x00")
        "이 글롭이 이 경로 안의 무언가를 덮는가"를 묻는다. \x00 을 쓰는 이유는 어떤
        파일시스템도 이름에 허용하지 않아 실제 자식과 충돌할 수 없기 때문이다.
    """
    for pat in patterns:
        norm = pat.replace("**", "*")
        if fnmatch.fnmatch(rel, norm) or fnmatch.fnmatch(rel + "/\x00", norm):
            return True
    return False


def is_product(root, cfg, path):
    """
    EN: A path is product if EITHER the name as written or the inode it resolves
        to lands under a product glob. One-sided judgement leaked both ways: a
        symlink out of the repo escaped the gate entirely (physical-only), and a
        symlink from outside INTO docs/ would escape a name-only check. Exempt is
        checked first and on both forms, so exempting a path cannot be defeated
        by reaching it through the other form.
    KO: 쓰인 이름과 실제 도달하는 inode 중 **하나라도** 산출물 글롭 아래면 산출물이다.
        한쪽만 보면 양방향으로 샜다 — 저장소 밖을 가리키는 심링크는 물리 경로만 볼 때
        게이트를 통째로 빠져나갔고, 밖에서 docs/ 안으로 걸린 심링크는 이름만 볼 때
        빠져나간다. exempt 는 먼저, 그리고 양쪽 형태 모두에 대해 검사한다 — 다른 형태로
        접근해서 면제를 무력화할 수 없게.
    """
    if not path:
        return False
    forms = []
    for rel in (rel_path(root, path), rel_path_logical(root, path)):
        if rel and not rel.startswith(".."):
            forms.append(rel)
    if not forms:
        return False  # outside the repo by both names — not our product
    if any(matches_any(rel, cfg.get("exempt", [])) for rel in forms):
        return False
    return any(matches_any(rel, cfg.get("product", [])) for rel in forms)


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


def stale_turn(root, payload):
    """
    EN: True when this payload carries a turn key that disagrees with the one
        already on disk — i.e. it belongs to a turn that has moved on. Both keys
        must be present to conclude anything: a payload with no turn id is not
        evidence of a different turn, and neither is an absent stored turn.
    KO: 이 페이로드의 턴 키가 디스크에 이미 있는 것과 어긋날 때 참 — 즉 이미 지나간
        턴의 것이다. 결론을 내리려면 양쪽 키가 다 있어야 한다. 턴 id 가 없는 페이로드는
        다른 턴이라는 증거가 아니고, 저장된 턴이 없는 것도 마찬가지다.
    """
    turn = turn_key(payload)
    if turn is None:
        return False
    try:
        with open(counter_file(root, payload), encoding="utf-8") as fh:
            saved = json.load(fh).get("turn")
    except (OSError, ValueError):
        return False
    return saved is not None and saved != turn


def counter_file(root, payload):
    sid = "".join(c for c in str(payload.get("session_id", "nosession")) if c.isalnum() or c == "-")
    return os.path.join(state_dir(root), "gate-%s.json" % (sid or "nosession"))


def approval_file(root, payload):
    """
    EN: Approval lives OUTSIDE the turn counter on purpose. It is not a property
        of a turn — it is the fact that the user authorised delegation in this
        session. The counter is reset on every turn change and deleted at Stop,
        so storing approval there made it evaporate whenever the user said one
        more word between approving a plan and the spawn. That left the main
        thread unable to write (budget) AND unable to delegate (approval gone) —
        a dead end whose only escape was turning the gate off.
        Lifetime is bounded by two real things, not by an invented timeout:
        the session id (a different session cannot see it) and single use
        (spawn_gate deletes it as it consumes it). Cleanup piggybacks on
        sweep_stale_turns()'s existing 24h rule.
    KO: 승인은 일부러 턴 카운터 **밖**에 둔다. 승인은 턴의 속성이 아니라 "사용자가 이
        세션에서 위임을 허가했다"는 사실이다. 카운터는 턴이 바뀔 때마다 리셋되고 Stop
        에서 삭제되므로, 거기 승인을 담으면 계획 승인과 스폰 사이에 사용자가 한 마디만
        더 해도 증발했다. 그러면 메인은 쓰기도(예산) 위임도(승인 소실) 못 하는 막다른
        길에 갇히고, 빠져나갈 길은 게이트를 끄는 것뿐이었다.
        수명은 자작 시간 문턱이 아니라 실재하는 두 가지로만 묶는다 — 세션 id(다른
        세션은 볼 수 없다)와 단일 사용(spawn_gate 가 소비하며 삭제한다).
        청소는 sweep_stale_turns() 의 기존 24시간 규칙에 얹는다.
    """
    sid = "".join(c for c in str(payload.get("session_id", "nosession")) if c.isalnum() or c == "-")
    return os.path.join(state_dir(root), "approval-%s.json" % (sid or "nosession"))


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


def resolve_target(cwd, token):
    """EN/KO: token -> absolute path. `~` expands; a relative token resolves under cwd."""
    t = os.path.expanduser(token) if token.startswith("~") else token
    return t if os.path.isabs(t) else os.path.join(cwd, t)


def bash_targets(command, root, cfg):
    """
    EN: Only *targets* count. A redirect names its target; sed -i / perl -i / tee /
        rm / rmdir name theirs as arguments, so for those we test every path-shaped
        token in the same segment (no "looks like a path" pre-filter — a bare word
        can itself be a product directory, e.g. `rm -rf base`; is_product is the
        only thing that decides what is product, non-path words simply miss the
        globs). cp/mv/install take source(s) then destination, so only the last
        path-shaped token in the segment is a target. We track `cd` across
        segments (accumulating, e.g. `cd a && cd b` -> a/b) so relative targets in
        a later segment resolve against the directory the shell would actually be
        in, not always the repo root; `cd -` or a bare `cd` gives up tracking and
        resets to root rather than guessing. Still not a sandbox: writes from
        inside python/git are invisible to a static scan, by design.

        Known misses, accepted on purpose:
        (1) `gsed -i ... base/f.md` — `g` is a word character, so `\\bsed` does not
            match; `ls base/*.md | xargs sed -i ...` and
            `find base -name '*.md' -exec sed -i ... {} +` — the target arrives via
            stdin/substitution, not as a literal word next to the command.
        (2) `(cd base && echo x > f.md)` subshell, `pushd base; ...`, and
            `cd $VAR && ...` — a subshell boundary breaks our segment-based `cd`
            tracking (the `(` prevents CD_RE from matching); `pushd` is not
            tracked; a variable resolves to a literal (bogus) directory that never
            matches a real product glob, so it degrades to a miss, not a block.
        (3) `mv base /tmp/base` — cp/mv/install only name their destination, so
            moving a product tree *out* is invisible; `rm -rf .` — the repo root
            matches no product glob and never should, or every command would be a
            product write; a product glob that demands a file suffix
            ("docs/*.md") does not cover the directory, so `rm -rf docs/` passes
            under that config; `echo${IFS}x${IFS}>${IFS}base/f.md` (IFS in place of
            spaces) — the target after `>` is no longer an unbroken path-shaped
            token; `echo base/f.md | xargs -I{} tee {} </dev/null` — the real
            target reaches `tee` through `{}` substitution, not as a literal word
            in its segment. (A redirect's target word wrapped to the next
            physical line — `echo x >` then a new line `base/f.md`, valid bash —
            is NOT a miss: SEGMENT_RE's own `(?<!>)` keeps a newline right after
            `>` from splitting the segment, so REDIRECT_RE's `\\s*` still reaches
            across it.)

        Over-blocks, accepted: any `<word> rm <name>` (docker/npm/podman) whose
        name equals a top-level product directory, and `git rm --cached
        base/f.md`, which does not delete the file. Static text cannot tell
        `docker rm base` from `rm base`, and the cost of an over-block (use
        Edit, or delegate to a subagent) is not symmetric with the cost of a
        miss (an irreversible tree deletion). Two former over-blocks are gone:
        a marker now has to *be* the command, so `docker run --rm` (a flag),
        `pip install -r base/x.txt` (a subcommand) and `bash base/install.sh`
        (running a file) all pass.
    KO: '대상'만 센다. 리다이렉트는 대상을 지목하고, sed -i·perl -i·tee·rm·rmdir 는
        인자가 대상이라 같은 세그먼트의 경로 모양 토큰을 전부 검사한다("경로처럼
        생겼나" 사전 필터 없음 — 맨 단어가 그 자체로 산출물 디렉터리일 수 있다.
        예: `rm -rf base`; 무엇이 산출물인지는 is_product 만 정하고, 경로가 아닌
        단어는 글롭에 안 걸릴 뿐이다). cp/mv/install 은 원본(들) 다음에 목적지가
        오므로 세그먼트의 마지막 경로 모양 토큰만 대상이다. `cd` 를 세그먼트 사이로
        추적해(누적 적용, 예: `cd a && cd b` -> a/b) 이후 세그먼트의 상대 대상이
        저장소 루트가 아니라 셸이 실제로 있을 디렉터리를 기준으로 풀리게 한다.
        `cd -` 나 인자 없는 `cd` 는 추적을 포기하고 루트로 되돌린다(추측하지 않는다).
        여전히 샌드박스는 아니다 — python/git 내부의 쓰기는 정적 검사로 보이지 않으며
        그것이 설계다.

        의도적으로 수용하는 미탐:
        (1) `gsed -i ... base/f.md` — `g` 가 단어 문자라 `\\bsed` 가 매치되지 않는다.
            `ls base/*.md | xargs sed -i ...` · `find base -name '*.md' -exec sed -i
            ... {} +` — 대상이 명령어 옆 리터럴 단어가 아니라 stdin/치환으로 들어온다.
        (2) `(cd base && echo x > f.md)` 서브셸 · `pushd base; ...` · `cd $VAR && ...`
            — 서브셸 경계가 세그먼트 기반 `cd` 추적을 끊고(`(` 때문에 CD_RE 가
            매치 안 됨), `pushd` 는 추적 대상이 아니며, 변수는 리터럴(가짜) 디렉터리로
            풀려 실제 product 글롭에 매치되지 않으므로 오차단이 아니라 미탐으로
            완화된다.
        (3) `mv base /tmp/base` — cp/mv/install 은 목적지만 지목하므로 산출물 트리를
            밖으로 옮기는 것은 보이지 않는다. `rm -rf .` — 저장소 루트는 어떤 product
            글롭에도 걸리지 않으며 걸려서도 안 된다(걸리면 모든 명령이 산출물 쓰기가
            된다). 파일 접미사를 요구하는 글롭("docs/*.md")은 디렉터리를 덮지 않으므로
            그 설정에서는 `rm -rf docs/` 가 통과한다. `echo${IFS}x${IFS}>${IFS}base/f.md`
            (공백 대신 IFS) — `>` 뒤 대상이 더 이상 끊기지 않은 경로 모양 토큰이 아니다.
            `echo base/f.md | xargs -I{} tee {} </dev/null` — 실제 대상이 `{}` 치환을
            통해 `tee` 에 닿을 뿐 그 세그먼트의 리터럴 단어가 아니다. (리다이렉트 대상
            단어가 다음 물리 줄로 넘어간 경우 — `echo x >` 다음 줄에 `base/f.md`, 유효한
            bash — 는 미탐이 **아니다**: SEGMENT_RE 자신의 `(?<!>)` 가 `>` 바로 뒤
            개행에서는 자르지 않으므로 REDIRECT_RE 의 `\\s*` 가 그 너머까지 닿는다.)

        수용하는 과차단: 이름이 최상위 산출물 디렉터리와 같은 `<word> rm <name>`
        (docker/npm/podman)과, 파일을 지우지 않는 `git rm --cached base/f.md`.
        정적 텍스트로는 `docker rm base` 와 `rm base` 를 구분할 수 없고, 과차단의
        대가(Edit 사용, 또는 서브에이전트 위임)는 미탐의 대가(되돌릴 수 없는 트리
        삭제)와 대칭이 아니다. 과차단 두 건은 없어졌다: 이제 마커는 그것이 명령
        *자신*일 때만 마커이므로 `docker run --rm`(플래그) · `pip install -r
        base/x.txt`(하위명령) · `bash base/install.sh`(파일 실행) 는 전부 통과한다.
    """
    candidates = []
    cwd = root
    for seg in SEGMENT_RE.split(command):
        # EN: A `cd` segment can still carry a redirect, and the shell opens that
        #     redirect in the *current* directory before the cd takes effect — so
        #     scan the segment first, then move cwd for the segments that follow.
        # KO: `cd` 세그먼트도 리다이렉트를 달 수 있고, 셸은 cd 가 적용되기 전 *현재*
        #     디렉터리에서 그 리다이렉트를 연다 — 그래서 세그먼트를 먼저 검사하고
        #     그다음에 이후 세그먼트를 위해 cwd 를 옮긴다.
        cd_match = CD_RE.match(seg)
        if any(re.search(m, seg) for m in WRITE_MARKER_EXEMPTIONS):
            if cd_match:
                arg = cd_target(cd_match.group(1))
                cwd = root if arg is None else resolve_target(cwd, arg)
            continue
        if any(re.search(m, seg) for m in ARG_WRITE_MARKERS):
            candidates.extend((cwd, t) for t in PATH_TOKEN_RE.findall(seg))
        if any(re.search(m, seg) for m in LAST_TOKEN_WRITE_MARKERS):
            path_tokens = [t for t in PATH_TOKEN_RE.findall(seg) if "." in t or "/" in t]
            if path_tokens:
                candidates.append((cwd, path_tokens[-1]))
        candidates.extend((cwd, t) for t in REDIRECT_RE.findall(seg))
        if cd_match:
            arg = cd_target(cd_match.group(1))
            cwd = root if arg is None else resolve_target(cwd, arg)
    hits = []
    for cwd_at, token in candidates:
        path = resolve_target(cwd_at, token)
        if is_product(root, cfg, path):
            rel = rel_path(root, path)
            if rel not in hits:      # dedup here, so bash_gate's join stays 1:1 with files
                hits.append(rel)
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

    # EN: One approval buys exactly one spawn, whichever path recognises it —
    #     the in-turn flag or the standing file. Consuming on both paths is what
    #     keeps the gate exactly as strong as before; only its *reach* changed,
    #     from one turn to until-used.
    # KO: 승인 하나는 스폰 하나를 산다. 턴 내 플래그든 세션 파일이든 인식한 쪽이
    #     소비한다. 양쪽 다 소비해야 게이트 강도가 종전과 같다 — 바뀐 것은 강도가
    #     아니라 **유효 범위**뿐이다(한 턴 → 쓸 때까지).
    apath = approval_file(root, payload)
    _, state = load_turn(root, payload)
    carried = os.path.exists(apath)
    if state["approved"] or carried:
        if carried:
            try:
                os.remove(apath)
            except OSError:
                pass
        emit_metric(root, cfg, dict(
            base, decision="allow",
            reason="spawn-approved" if state["approved"] else "spawn-approved-carried"))
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
        # EN/KO: also record it outside the turn — see approval_file().
        write_counter(approval_file(root, payload), {"approved": True})
        emit_metric(root, cfg, {
            "event": "PostToolUse",
            "session": payload.get("session_id"),
            "actor": "main",
            "tool": "ExitPlanMode",
            "decision": "allow",
            "reason": "approval-recorded",
        })
    allow()


def load_cost_module():
    """
    EN: Load harness/tools/subagent_cost.py by path, relative to this file, so
        the SubagentStop cost record reuses the same 545-run-verified parser
        instead of a second implementation that could drift from it. Any
        failure (missing file, import error) yields None — callers must treat
        that as "cost unavailable", never raise.
    KO: `harness/tools/subagent_cost.py` 를 이 파일 기준 상대경로로 로드한다.
        SubagentStop 의 비용 기록이 545런으로 검증된 그 파서를 재사용하게 하려는
        것이다 — 갈라질 수 있는 두 번째 구현을 만들지 않는다. 실패(파일 없음,
        import 오류)하면 None 을 돌려준다 — 호출부는 이를 "비용 조회 불가"로만
        다루고 예외를 올리지 않는다.
    """
    try:
        mod_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "tools", "subagent_cost.py"
        )
        spec = importlib.util.spec_from_file_location("subagent_cost", mod_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def resolve_subagent_jsonl(payload):
    """
    EN: transcript_path -> the sibling subagents/ dir -> the one run file for
        this agent id. Tries `agent-<id>.jsonl` then `<id>.jsonl` because
        whether the payload's agent id already carries the `agent-` prefix
        used in filenames is unconfirmed.
    KO: transcript_path 에서 형제 subagents/ 디렉터리를 만들고 이 agent id 의
        런 파일 하나를 찾는다. `agent-<id>.jsonl` 다음 `<id>.jsonl` 순으로
        시도한다 — payload 의 agent id 가 파일명의 `agent-` 접두사를 이미
        포함하는지 미확인이기 때문이다.
    """
    transcript_path = payload.get("transcript_path")
    agent_id = payload.get("agent_id")
    if not transcript_path or not agent_id:
        return None
    agent_id = os.path.basename(agent_id)
    base_dir = os.path.dirname(transcript_path)
    session_name = os.path.splitext(os.path.basename(transcript_path))[0]
    subagents_dir = os.path.join(base_dir, session_name, "subagents")
    for candidate_name in ("agent-%s.jsonl" % agent_id, "%s.jsonl" % agent_id):
        candidate = os.path.join(subagents_dir, candidate_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def compute_cost(payload):
    """
    EN: Best-effort cost lookup for a SubagentStop event. Every failure mode —
        no transcript_path, unresolvable file, missing module, a parse error —
        is swallowed here so the hook can never die on this path.
    KO: SubagentStop 이벤트의 비용을 최선을 다해 찾는다. transcript_path 없음·
        파일 미해결·모듈 없음·파싱 오류 등 모든 실패 모드를 여기서 삼켜
        훅이 이 경로에서 절대 죽지 않게 한다.
    """
    agent_id_raw = payload.get("agent_id")
    try:
        jsonl_path = resolve_subagent_jsonl(payload)
        if not jsonl_path:
            return None, False, agent_id_raw
        module = load_cost_module()
        if module is None:
            return None, False, agent_id_raw
        metrics, _skipped = module.load_run(jsonl_path)
        if metrics is None:
            return None, False, agent_id_raw
        return metrics, True, agent_id_raw
    except Exception:
        return None, False, agent_id_raw


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
    if agent_type in cfg.get("verifiers", []) and not stale_turn(root, payload):
        # EN: Only stamp the turn this subagent actually belongs to. A verifier
        #     that finishes after the turn moved on used to write the counter
        #     with ITS turn key, which replaced the live turn's record wholesale —
        #     the delegation and write list vanished, so the close gate found
        #     nothing owed and let an uninspected turn end. Skipping the write
        #     entirely is right: a subagent from another turn has nothing to say
        #     about this one, neither "verified" nor "not".
        # KO: 이 서브에이전트가 실제로 속한 턴만 도장 찍는다. 턴이 넘어간 뒤 끝난
        #     검증자가 **자기 턴 키로** 카운터를 써서 살아 있는 턴의 기록을 통째로
        #     갈아치웠다 — 위임 사실과 쓰기 목록이 사라져 close 게이트가 갚을 것이
        #     없다고 보고 검사 안 된 턴을 끝냈다. 아예 쓰지 않는 것이 옳다. 다른 턴의
        #     서브에이전트는 이 턴에 대해 "검증됨"도 "아님"도 말할 자격이 없다.
        cpath, state = load_turn(root, payload)
        state["verified"] = True
        write_counter(cpath, state)
    cost, cost_resolved, agent_id_raw = compute_cost(payload)
    emit_metric(root, cfg, {
        "event": "SubagentStop",
        "session": payload.get("session_id"),
        # EN/KO: turn key, so a later reader can tell whether this event carried
        #        one at all — the whole turn-scoping design depends on it.
        "turn": turn_key(payload),
        "actor": "sub",
        "agent_type": agent_type,
        "agent_id_raw": agent_id_raw,
        "decision": "allow",
        "reason": "verified" if agent_type in cfg.get("verifiers", []) else "subagent-stop",
        "cost": cost,
        "cost_resolved": cost_resolved,
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
            if name.startswith(("gate-", "approval-")) and name.endswith(".json"):
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
