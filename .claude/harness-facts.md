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
| 승인(`ExitPlanMode` 수락) 없이 `maker` 스폰 | 차단. **승인은 쓰일 때까지 턴을 넘어 유지되고 단 한 번 쓰인다** |
| 위임이 일어난 턴에 `critic` 없이 종료 | `Stop` 차단, **2회 상한 후 통과** |
| `architect`·`maker` 브리프가 **실재하는 파일을 하나도 안 가리킴** | 차단 (`I4` 인수인계 게이트) |

**쓰기 개수 제한은 지금 사실상 꺼져 있다** — `main_thread_file_limit` 이 `999999` 다
(2026-08-05 사용자 지시). 근거 있는 값으로 되살릴지는 계측(`count` 필드)이 쌓인 뒤 정한다.

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

## Claude Code 버전 — 해결됨 (2026-08-03)

**업데이트 완료. `2.1.220` 이고 npm 최신과 같다.** 이 세션은 VS Code 확장의
`2.1.220` 네이티브 바이너리로 돌고 있다.

검증한 것:

- `python3 harness/tests/test_gate.py` → **152 passed / 0 failed**
- 라이브 페이로드에 `prompt_id` 가 **실린다.** 산출물 쓰기 직후 카운터 파일의 `turn` 이
  실제 UUID(`38f76cbb-…`)로 기록됐다. `turn_key()` 가 `None` 을 돌려주던 상태는 끝났고,
  턴 경계가 `Stop` 의 카운터 삭제와 `prompt_id` **양쪽**으로 선다.

버전을 다시 확인해야 하면 문서를 믿지 말고 실측하라 — `claude --version` 과
`.claude/state/gate-<session>.json` 의 `turn` 필드.

## 2026-08-05 에 바뀐 것 — 오케스트레이터 불변식 신설 (D-008)

하네스가 두 방향으로 동시에 실패한 것을 고쳤다. **정상 경로를 막았고**(승인이 턴을 넘으면
증발해 쓰기도 위임도 불가능), **낭비는 못 막았다**(Maker 셋이 Scout 가 이미 측정한 사실을
다시 캐느라 12분 소모). 둘 다 규칙 위반이 아니었다 — 코어가 메인 스레드를 두 줄로만
규정하고 브리프·인수인계·작업 크기에 대해 아무 말이 없었기 때문이다.

- `I4` 신설 — 오케스트레이터는 아는 것을 넘긴다. 브리프가 실재 파일을 안 가리키면 스폰 차단.
- 계측에 `agent_id` 추가 (`관측` 등급의 첫 사례). **무산출 문턱은 안 만들었다** — 도출할
  데이터가 없다. `count` 필드와 함께 쌓이는 중이다.
- **관통 테스트** 신설 — 예산 소진 → 승인 → 턴 경계 → 위임 → 쓰기 → 검증 → 종료를 한 번에
  통과시킨다. 기존 테스트는 전부 "여기서 막히는가"만 물었다.
- 메타 테스트 둘 — 금지 단언에는 이유를, 수치 문턱에는 `CORE.md` 설명을 요구한다.
- 역할 정의 5개: 40줄 넘치는 상세는 **파일로 남기고 경로를 보고에 적는다.**

**주의 — D-007 커밋 메시지에 틀린 서술이 있다.** "키 3개짜리 `harness.json` 이
`approval_gate`·`close_gate` 를 조용히 꺼진 채 둔다"는 거짓이다. `load_config` 가
`DEFAULTS` 를 먼저 깔아 누락 키는 정상값으로 채워진다. 실제 문제는 투명성뿐이었다.
정정은 `docs/DECISIONS.md` D-008 의 `정정` 항에 있다.

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
4. **`install.sh --global` 주변 미처리 4건 — 해결됨 (2026-08-03, D-007).**
   `~/.claude/agents` 가 심링크일 때 `cp -R` 백업이 심링크만 복사(W3) ·
   `~/.claude/CLAUDE.md` 가 심링크면 조용히 실파일로 대체(W4) ·
   `--global` 에 `python3` 사전 확인 없음, 없으면 오안내 + 반쪽 설치(W5) ·
   내용이 같아도 매번 `.bak-<epoch>` 생성해 무한 누적(N4) — 넷 다 고쳤다.
   `resolve_if_symlink()` 가 W3·W4 를 심링크 물리 경로 해석으로, `require_python3()` 가
   W5 를 사전 차단으로, `agents_dir_unchanged()` + 백업을 `mv` 직전으로 이동한 것이 N4 를
   해결한다. 1차 검증에서 Critic(opus)이 CONDITIONAL 을 냈고, 남은 WARNING 4건도
   2차에서 전부 처리했다: `copy_with_backup()` 자체에 `resolve_if_symlink()` 를 적용해
   개별 파일 심링크(디렉터리는 실디렉터리, 파일 5개가 각각 dotfiles 로 흘러가는 구성)도
   백업 없이 사라지지 않게 했다(W-2). 백업이 해석된 물리 경로 옆(dotfiles 디렉터리 안)에
   생긴다는 사실과 `git add -A` 로 통째로 커밋될 수 있다는 함의를 문서화했다(W-3).
   `CORE.md` §6 을 정본 저장소로 한정해 설치된 프로젝트에서 죽은 링크·불가능한 명령을
   지시하던 문제를 고쳤다(W-1, `install.sh` 는 `HARNESS_FILES` 에 없어 설치되지 않는다).
   케이스 7 에 백업 개수 0 단언을 추가해 가짜 통과를 없앴다(W-4). 신규
   `harness/tests/test_install_global.sh` **12 케이스**로 검증(`mktemp -d` `HOME`
   오버라이드만 사용, 실제 `$HOME` 은 안 건드림). 근거는 `docs/DECISIONS.md` D-007.

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

**`main` 에 병합·푸시 완료.** `harness-v2` 22개 커밋을 fast-forward 로 올렸고
`origin/main` 이 `de63431` 이다. 워킹트리 clean, 브랜치 `harness-v2` 는 `main` 과 같다.
병합 상태에서 실측: `test_gate.py` **152 passed / 0 failed**,
`test_install_global.sh` **12 PASS / 0 failure**.

`harness-v2` 는 원격에 없다 — 내용이 `main` 과 같아 푸시하지 않았다. PR 없음.

## 배경

옛 하네스(삭제됨)는 규범 183개 중 기계 집행이 10%뿐이었고, 게이트의 30%는 구속 대상이
스스로 집행했으며, 5개 역할의 추론 예산이 무효 키(`reasoning_effort`) 때문에 전부 무시되고
있었다. 그래서 "집행할 수 없는 규칙은 쓰지 않는다"를 원칙으로 새로 만들었다.
경위는 [`docs/PLAN_HARNESS_REDESIGN.md`](../docs/PLAN_HARNESS_REDESIGN.md).
