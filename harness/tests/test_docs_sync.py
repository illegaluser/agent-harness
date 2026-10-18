#!/usr/bin/env python3
"""
test_docs_sync.py — machine cross-check between gate.py, CORE.md, agents/*.md,
and the files that must never duplicate them.

EN: Catches exactly the two documented failures by diffing the DEFINING side
    (gate.py's DEFAULTS, agents/*.md frontmatter) against the REFERENCING side
    (CORE.md's role table) and the three files that must not carry a copy of a
    config key at all (README.md, the always-injected block, harness-facts.md).
    Pure string comparison — no markdown parser, no yaml parser, so it runs
    without any dependency beyond the standard library.
KO: 문서화된 실패 두 가지를 정의하는 쪽(gate.py 의 DEFAULTS, agents/*.md 의
    frontmatter)과 참조하는 쪽(CORE.md 역할 표), 그리고 설정 키의 복사본을 아예
    가지면 안 되는 파일 셋(README.md, 상시 주입 블록, harness-facts.md)을 대조해
    잡는다. 순수 문자열 비교다 — markdown 파서도 yaml 파서도 안 쓰므로 표준
    라이브러리 밖의 의존성 없이 돈다.

Run: python3 harness/tests/test_docs_sync.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_DIR = os.path.normpath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.normpath(os.path.join(HARNESS_DIR, ".."))
GATE = os.path.join(HARNESS_DIR, "hooks", "gate.py")
CORE = os.path.join(HARNESS_DIR, "CORE.md")

AGENT_NAMES = ("scout", "architect", "maker", "critic", "referee")

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  — " + detail) if detail and not cond else ""))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_frontmatter(agent_path):
    """EN/KO: 아주 좁은 frontmatter 파서 — `tools:`/`description:` 한 줄짜리 값만 뽑는다."""
    text = read(agent_path)
    block = text.split("---", 2)[1] if text.startswith("---") else ""
    tools = re.search(r"^tools:\s*(.+)$", block, re.M)
    desc = re.search(r"^description:\s*(.+)$", block, re.M)
    return (tools.group(1).strip() if tools else None,
            desc.group(1).strip() if desc else None)


def first_sentence(desc):
    """
    EN/KO: 첫 `.` 까지(포함)를 첫 문장으로 본다. 이 저장소의 모든 agents/*.md
    description 은 그 전에 약어(`.` 를 포함하는 축약)를 쓰지 않는다 — 단순 분할로
    충분하다.
    """
    idx = desc.find(".")
    return desc[: idx + 1].strip() if idx != -1 else desc.strip()


def core_role_rows():
    """EN/KO: CORE.md '## 2. 역할' 표의 5행을 (역할, 도구칸, 하는일칸) 으로 뽑는다."""
    text = read(CORE)
    rows = re.findall(
        r"^\|\s*`(\w+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", text, re.M
    )
    return {name: (tools, did) for name, tools, did in rows if name in AGENT_NAMES}


def defaults_block():
    return re.search(r"DEFAULTS = \{(.*?)\n\}", read(GATE), re.S).group(1)


def test_numeric_defaults_are_in_core():
    """EN/KO: DEFAULTS 의 수치 키는 전부 CORE.md 본문에 설명돼 있어야 한다 (근거 없는 숫자 금지)."""
    block = defaults_block()
    core_text = read(CORE)
    numeric = re.findall(r'"(\w+)":\s*-?\d+', block)
    missing = [k for k in numeric if k not in core_text]
    check("every numeric DEFAULTS key is named in CORE.md", not missing, str(missing))


def test_role_table_tools_match_frontmatter():
    """EN/KO: 손으로 쓴 게이트 표가 DEFAULTS·frontmatter 와 어긋났던 불일치(#1)의 재발을 막는다."""
    rows = core_role_rows()
    for name in AGENT_NAMES:
        tools, _ = parse_frontmatter(os.path.join(HARNESS_DIR, "agents", "%s.md" % name))
        core_tools = rows.get(name, (None, None))[0]
        check("CORE.md tools cell for %s matches frontmatter" % name,
              core_tools == tools, "core=%r frontmatter=%r" % (core_tools, tools))


def test_role_table_description_matches_frontmatter_first_sentence():
    """EN/KO: 역할 표 서술이 낡는(#1) 재발 경로를 닫는다 — frontmatter 의 첫 문장과 글자 그대로 맞춘다."""
    rows = core_role_rows()
    for name in AGENT_NAMES:
        _, desc = parse_frontmatter(os.path.join(HARNESS_DIR, "agents", "%s.md" % name))
        expected = first_sentence(desc)
        core_did = rows.get(name, (None, None))[1]
        check("CORE.md 하는일 cell for %s matches frontmatter's first sentence" % name,
              core_did == expected, "core=%r expected=%r" % (core_did, expected))


# EN: Files that must never carry a copy of a DEFAULTS key — the documented
#     failure was exactly a hand-written table of these going stale against
#     DEFAULTS. `exceptions` names, per file, the one key the canonical global
#     block deliberately references by name as a single inline pointer (not a
#     copied key:value table) — see the Maker report for the two exact lines
#     ("`.claude/harness.json` 이 없거나 `enforce: false` 면 ..." and
#     "없으면 프로젝트가 선언한 `verify_commands` 를 ...").
# KO: DEFAULTS 키의 복사본을 절대 가지면 안 되는 파일들 — 문서화된 실패가 바로
#     이런 손으로 쓴 표가 DEFAULTS 와 어긋나는 것이었다. `exceptions` 는 정본
#     전역 블록이 일부러 이름으로 참조하는 키 하나씩을 파일별 예외로 둔다
#     (key:value 표 복사가 아니라 문장 속 단일 참조) — 정확한 두 줄은 Maker 보고에
#     있다.
NO_COPY_FILES = {
    "README.md": set(),
    os.path.join("harness", "global", "CLAUDE.harness.md"): {"enforce", "verify_commands"},
    os.path.join(".claude", "harness-facts.md"): set(),
}


def test_config_keys_are_not_copied_into_prose():
    """EN/KO: 설정 키가 README·전역 블록·facts 로 복사돼 DEFAULTS 와 갈라지는(#2) 재발을 막는다."""
    keys = re.findall(r'"(\w+)":', defaults_block())
    for rel, exceptions in NO_COPY_FILES.items():
        path = os.path.join(REPO_ROOT, rel)
        text = read(path)
        leaked = [k for k in keys
                  if k not in exceptions and re.search(r"\b%s\b" % re.escape(k), text)]
        check("%s does not copy a DEFAULTS key" % rel, not leaked, str(leaked))


ALLOWED_MODEL_ALIASES = {"haiku", "sonnet", "opus", "inherit"}


def test_agent_frontmatter_model_is_an_alias():
    """EN/KO: agents/*.md 의 model: 값이 별칭 집합(haiku/sonnet/opus/inherit)인지 본다 — 정확한 모델
    ID 를 적으면 세대 교체 후에도 낡은 ID 로 실행되는 결함(D-015)의 재발을 막는다."""
    for name in AGENT_NAMES:
        path = os.path.join(HARNESS_DIR, "agents", "%s.md" % name)
        text = read(path)
        block = text.split("---", 2)[1] if text.startswith("---") else ""
        m = re.search(r"^model:\s*(.+)$", block, re.M)
        value = m.group(1).strip() if m else None
        check("agents/%s.md model: is an alias" % name,
              value in ALLOWED_MODEL_ALIASES, "model=%r" % value)


EXACT_MODEL_ID_FILES = [
    CORE,
    os.path.join(HARNESS_DIR, "global", "CLAUDE.harness.md"),
    os.path.join(HARNESS_DIR, "agents", "scout.md"),
    os.path.join(HARNESS_DIR, "agents", "architect.md"),
    os.path.join(HARNESS_DIR, "agents", "maker.md"),
    os.path.join(HARNESS_DIR, "agents", "critic.md"),
    os.path.join(HARNESS_DIR, "agents", "referee.md"),
    os.path.join(REPO_ROOT, "README.md"),
]

EXACT_MODEL_ID_PATTERN = re.compile(r"claude-(opus|sonnet|haiku|fable)-[0-9]")


def test_no_exact_model_ids_outside_decisions_log():
    """EN/KO: CORE.md·전역 블록·agents/*.md·README.md 에 정확한 모델 ID
    (`claude-(opus|sonnet|haiku|fable)-[0-9]`) 가 남아있지 않은지 본다. docs/DECISIONS.md
    는 이력 기록이라 제외한다."""
    for path in EXACT_MODEL_ID_FILES:
        text = read(path)
        hits = EXACT_MODEL_ID_PATTERN.findall(text)
        check("%s has no exact model IDs" % os.path.relpath(path, REPO_ROOT),
              not hits, str(hits))


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
