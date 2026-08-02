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

## 다음 세션에서 먼저 할 것 — 사용자 손이 필요한 것 하나

**Claude Code 를 업데이트해야 한다.** 설치본이 `2.1.128`, npm 최신이 `2.1.220` (92 버전 뒤).
`npm install -g` 가 `EACCES` 로 실패한다 — `/usr/local/lib/node_modules/` 쓰기 권한이 없다.
에이전트는 `sudo` 를 실행할 수 없으므로 **사용자가 터미널에서 직접** 돌려야 한다:

```bash
sudo npm install -g @anthropic-ai/claude-code@latest
```

**업데이트가 하네스 동작을 바꾼다.** `prompt_id` 는 `2.1.196` 부터 훅 페이로드에 실린다
(2.1.128 에는 없다). 지금은 `turn_key()` 가 항상 `None` 이고 턴 경계가 `Stop` 의 카운터 파일
삭제 하나뿐이다. 업데이트하면 `prompt_id` 경로가 살아난다 — **업데이트 직후
`python3 harness/tests/test_gate.py` 를 다시 돌리고, 쓰기 예산이 턴마다 리셋되는지
실제 세션에서 확인하라.**

## 미완 (이어서 할 일)

1. **서브에이전트 내부 비용에 문턱을 만들지 않기로 결정했다(D-006).** 546런 실측으로 scout
   중앙값은 90,062 — 이전에 적었던 "scout 하나가 116K 토큰" 이상치 진술은 반증됐다.
   근거는 `docs/DECISIONS.md` D-006.
2. **lint 게이트는 만들지 않기로 했다 (2026-08-03 사용자 결정).** 옛 하네스의 lint 훅은
   대체하지 않는다. lint 는 `조언` 으로만 남는다 — 전역 `CLAUDE.md` 의 Lint 처리 정책.
3. **close 게이트가 백그라운드 서브에이전트 실행 중에 발동한다. 고치지 않기로 했다
   (2026-08-03 사용자 결정).** 서브에이전트가 도는 중에 메인 턴이 끝나면 "미검증"으로
   차단되지만 **2회 후 통과하는 유한 동작**이라 피해가 턴 2개다.
   `SubagentStart` − `SubagentStop` 카운트로 유예하는 안을 구현했다가(`7fb4f1f`)
   **critic FAIL 로 되돌렸다(`8f43661`)** — 무한 유예로 바뀌어 턴 경계가 소멸하고 승인
   게이트가 무력화됐다. 판정 근거는 아래 "critic 이 남긴 것". **다시 손대지 마라.**
4. **`install.sh --global` 주변 미처리 4건** (critic 2026-08-03, 전부 데이터 손실 없음):
   `~/.claude/agents` 가 심링크일 때 `cp -R` 백업이 심링크만 복사(W3) ·
   `~/.claude/CLAUDE.md` 가 심링크면 조용히 실파일로 대체(W4) ·
   `--global` 에 `python3` 사전 확인 없음, 없으면 오안내 + 반쪽 설치(W5) ·
   내용이 같아도 매번 `.bak-<epoch>` 생성해 무한 누적(N4).

## critic 이 남긴 것 (2026-08-03, opus)

`7fb4f1f` 에 **FAIL**. BLOCKER 4건 중 3건이 부모 커밋 대비 회귀였다. 되돌린 이유다.

- **B1** `SubagentStop` 이 안 오면 `agents_running` 이 1 에 고정 → 그 세션의 모든 `Stop`
  무한 유예 → 턴 경계 소멸 → 승인 게이트 무력화 + 쓰기 예산이 "세션당 2개"가 됨.
- **W1** 실제 프로덕션 순서에서 수정이 작동하지 않았다. 메트릭 로그상 `Stop` 이
  `SubagentStart` 9초 뒤에 돌아 서브에이전트가 쓰기 전에 카운터를 지운다.
- **B2** 모든 `SubagentStop` 이 카운터를 쓰는데 원자적이지 않아 경합 (6-way 2/5 시행 소실).
- **B3** 늦게 온 `SubagentStop(critic)` 의 `verified:true` 가 다음 턴에 상속.
- **B4** `install.sh --global` 이 마커를 인용한 문서의 사용자 본문 삭제 → **`57913c6` 에서 고침.**

## 저장소 상태 (2026-08-03 세션 종료 시점)

브랜치 `harness-v2`, 커밋 17개, **미푸시. `main` 병합 미결정. PR 없음.**
워킹트리 clean. 테스트 152 passed / 0 failed. HEAD `57913c6`.

## 배경

옛 하네스(삭제됨)는 규범 183개 중 기계 집행이 10%뿐이었고, 게이트의 30%는 구속 대상이
스스로 집행했으며, 5개 역할의 추론 예산이 무효 키(`reasoning_effort`) 때문에 전부 무시되고
있었다. 그래서 "집행할 수 없는 규칙은 쓰지 않는다"를 원칙으로 새로 만들었다.
경위는 [`docs/PLAN_HARNESS_REDESIGN.md`](../docs/PLAN_HARNESS_REDESIGN.md).
