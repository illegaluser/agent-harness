# 하네스 상태 — SessionStart 자동 주입

이 파일은 `harness/hooks/gate.py` 가 매 세션·매 서브에이전트 시작 시 컨텍스트에 넣는다.
설명을 다시 요청받지 않으려고 두는 것이다. 상태가 바뀌면 **이 파일을 같이 고쳐라.**

## 지금 켜져 있는 것

`.claude/settings.json` 이 `harness/hooks/gate.py` 를 6개 이벤트에 배선한다.
`.claude/harness.json` 이 `enforce: true` 다 — 아래는 **실제로 막는다.**

| 걸리는 일 | 결과 |
| --- | --- |
| 메인 스레드가 한 턴에 산출물 파일 3개째 수정 | `PreToolUse` exit 2 로 차단 |
| 메인 스레드가 Bash(`sed -i`·`perl -i`·리다이렉트·`tee`·`rm`·`rmdir`·`cp`·`mv`·`install`)로 산출물 수정 | 차단 (알려진 미탐 있음 — `gate.py` 의 `bash_targets` docstring) |
| 승인(`ExitPlanMode` 수락) 없이 `maker` 스폰 | 차단 |
| 위임이 일어난 턴에 `critic` 없이 종료 | `Stop` 차단, **2회 상한 후 통과** |

산출물 = `docs/**` · `harness/**` (`docs/DECISIONS.md` 제외).
`.claude/**` 는 산출물이 아니라 게이트 밖이다.

**막히면 우회하지 말고 규칙대로 하라.** 3개 이상이면 계획을 제시하고 승인받아 maker 에 위임한다.
게이트가 잘못됐다고 판단되면 `.claude/harness.json` 에서 끄고 그 사실을 사용자에게 보고한다 —
조용히 우회하는 것이 이 하네스가 막으려는 바로 그 행동이다.

## 규칙 본문

[`harness/CORE.md`](../harness/CORE.md) 가 전부다. 규칙마다 `기계`/`조언` 이 붙어 있다.
`기계` 는 어길 수 없고, `조언` 은 아무것도 확인하지 않는다. 그 구분이 이 하네스의 설계 원칙이다.

역할 정의는 [`harness/agents/`](../harness/agents/) 5개이며 `.claude/agents/` 에 **심링크**돼 있다
(사본이 아니라 드리프트가 원리적으로 불가능).

## 전역 설정도 하네스가 관리한다

`~/.claude/CLAUDE.md` 의 `HARNESS:BEGIN`/`END` 블록과 `~/.claude/agents/` 5개는
[`harness/global/CLAUDE.harness.md`](../harness/global/CLAUDE.harness.md) 와
[`harness/agents/`](../harness/agents/) 가 정본이다.

**손으로 고치지 마라.** 정본을 고치고 아래로 반영한다:

```bash
bash harness/install.sh --global              # 전역 설치·갱신
bash harness/install.sh --global --uninstall  # 전역 제거
bash harness/install.sh <프로젝트경로>          # 대상 프로젝트에 설치
```

## 고칠 때

게이트를 건드리면 반드시:

```bash
python3 harness/tests/test_gate.py     # 152 tests
```

양방향이 다 통과해야 한다 — 메인을 막는 것과 서브에이전트를 **막지 않는** 것.
한 방향만 보면 "무용한 게이트"와 "마비된 세션"이 둘 다 성공처럼 보인다.

## 미완 (이어서 할 일)

1. **서브에이전트 내부 비용에 문턱을 만들지 않기로 결정했다(D-006).** 546런 실측으로 scout
   중앙값은 90,062 — 이전에 적었던 "scout 하나가 116K 토큰" 이상치 진술은 반증됐다.
   근거는 `docs/DECISIONS.md` D-006.
2. **lint 게이트는 만들지 않기로 했다 (2026-08-03 사용자 결정).** 옛 하네스의 lint 훅은
   대체하지 않는다. lint 는 `조언` 으로만 남는다 — 전역 `CLAUDE.md` 의 Lint 처리 정책.
3. **close 게이트가 백그라운드 서브에이전트 실행 중에 발동한다.** 서브에이전트가 아직
   도는데 메인 턴이 끝나면 "미검증"으로 차단된다 — 게이트가 서브에이전트 생사를 모른다.
   `SubagentStart` − `SubagentStop` 카운트로 유예하는 안이 있으나 미구현.

## 배경

옛 하네스(삭제됨)는 규범 183개 중 기계 집행이 10%뿐이었고, 게이트의 30%는 구속 대상이
스스로 집행했으며, 5개 역할의 추론 예산이 무효 키(`reasoning_effort`) 때문에 전부 무시되고
있었다. 그래서 "집행할 수 없는 규칙은 쓰지 않는다"를 원칙으로 새로 만들었다.
경위는 [`docs/PLAN_HARNESS_REDESIGN.md`](../docs/PLAN_HARNESS_REDESIGN.md).
