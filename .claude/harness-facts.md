# 하네스 상태 — SessionStart 자동 주입

이 파일은 `harness/hooks/gate.py` 가 매 세션·매 서브에이전트 시작 시 컨텍스트에 넣는다.
설명을 다시 요청받지 않으려고 두는 것이다. 상태가 바뀌면 **이 파일을 같이 고쳐라.**

## 지금 켜져 있는 것

`.claude/settings.json` 이 `harness/hooks/gate.py` 를 6개 이벤트에 배선한다.
`.claude/harness.json` 이 `enforce: true` 다 — 아래는 **실제로 막는다.**

| 걸리는 일 | 결과 |
| --- | --- |
| 메인 스레드가 한 턴에 산출물 파일 3개째 수정 | `PreToolUse` exit 2 로 차단 |
| 메인 스레드가 Bash(`sed -i`·리다이렉트·`tee`)로 산출물 수정 | 차단 |
| 승인(`ExitPlanMode` 수락) 없이 `maker` 스폰 | 차단 |
| 위임이 일어난 턴에 `critic` 없이 종료 | `Stop` 차단, **2회 상한 후 통과** |

산출물 = `base/**` · `docs/**` · `harness/**` (`docs/DECISIONS.md` 제외).
`.claude/**` 는 산출물이 아니라 게이트 밖이다.

**막히면 우회하지 말고 규칙대로 하라.** 3개 이상이면 계획을 제시하고 승인받아 maker 에 위임한다.
게이트가 잘못됐다고 판단되면 `.claude/harness.json` 에서 끄고 그 사실을 사용자에게 보고한다 —
조용히 우회하는 것이 이 하네스가 막으려는 바로 그 행동이다.

## 규칙 본문

[`harness/CORE.md`](../harness/CORE.md) 가 전부다. 80줄이고 규칙마다 `기계`/`조언` 이 붙어 있다.
`기계` 는 어길 수 없고, `조언` 은 아무것도 확인하지 않는다. 그 구분이 이 하네스의 설계 원칙이다.

역할 정의는 [`harness/agents/`](../harness/agents/) 5개이며 `.claude/agents/` 에 **심링크**돼 있다
(사본이 아니라 드리프트가 원리적으로 불가능).

## 고칠 때

게이트를 건드리면 반드시:

```bash
python3 harness/tests/test_gate.py     # 49 tests
```

양방향이 다 통과해야 한다 — 메인을 막는 것과 서브에이전트를 **막지 않는** 것.
한 방향만 보면 "무용한 게이트"와 "마비된 세션"이 둘 다 성공처럼 보인다.

## 미완 (이어서 할 일)

1. **`effort` 키 수정 12곳이 미검증이다.** `base/agents/*.md` 와 `~/.claude/agents/*.md` 의
   `reasoning_effort:` → `effort:` 치환. Critic 호출이 중단돼 판정을 못 받았다.
2. **서브에이전트 내부 비용에 상한이 없다.** 이번 세션에 scout 하나가 116K 토큰·26분을 썼다.
   전체 툴 호출 계측은 켜 뒀으니(`harness-metrics.jsonl`), 데이터가 쌓이면 문턱을 근거로 정할 것.
3. **`base/` 옛 하네스가 그대로 있다.** 새 하네스가 실사용 검증되면 삭제 대상.
4. **배포 경로가 없다.** 새 하네스를 다른 프로젝트에 설치하는 스크립트를 아직 안 만들었다.

## 배경

`base/` 옛 하네스는 규범 183개 중 기계 집행이 10%뿐이었고, 게이트의 30%는 구속 대상이 스스로
집행했으며, 5개 역할의 추론 예산이 무효 키(`reasoning_effort`) 때문에 전부 무시되고 있었다.
그래서 "집행할 수 없는 규칙은 쓰지 않는다"를 원칙으로 새로 만들었다.
경위는 [`docs/PLAN_HARNESS_REDESIGN.md`](../docs/PLAN_HARNESS_REDESIGN.md).
