# 하네스 코어

이 문서가 하네스의 전부다. 여기 없는 것은 하네스가 아니다.
소스 파일은 `CORE.md` · `hooks/gate.py` · `tools/verify.sh` · `tests/test_gate.py` ·
`tests/test_docs_sync.py` · `tests/test_install_global.sh` · `tools/subagent_cost.py` ·
`agents/` 5개 · `global/CLAUDE.harness.md` · `install.sh` 다.

**설계 원칙 — 집행할 수 없는 규칙은 쓰지 않는다.** 못 쓰겠으면 `조언` 으로 표시하고 코어 밖에 둔다.
아래 모든 규칙에는 집행 주체가 붙어 있다. 붙일 수 없으면 그 규칙은 여기 있으면 안 된다.

| 표시 | 뜻 |
| --- | --- |
| `기계` | 훅 또는 `tools:` frontmatter 가 강제한다. 어길 수 없다 |
| `관측` | 훅이 기록만 한다. 아직 막지 않는다 — 문턱을 데이터로 정하는 중 |
| `조언` | 아무것도 확인하지 않는다. 지키면 좋지만 강제되지 않는다 |

## 1. 불변식

### I1. 산출물은 maker 만 쓴다

- `기계` scout · architect · critic · referee 는 `tools:` 에 `Write`/`Edit` 가 없다. 파일을 못 쓴다.
- `기계` 메인 스레드가 한 턴에 직접 고칠 수 있는 산출물 파일은 `main_thread_file_limit` 개까지다.
  초과분은 maker 에 위임해야 한다. 문턱은 "1~2 개는 직접, 3 개째부터는 계획"에서 유도했다.
- `기계` 메인 스레드가 Bash 우회(`sed -i` · `perl -i` · 리다이렉트 · `tee` · `rm` · `rmdir` · `cp` ·
  `mv` · `install`)로 산출물을 고치는 것도 막는다. `tools:` 로는 표현할 수 없는 경로라 훅이 맡는다.
  알려진 미탐이 있다 — 목록은 `gate.py` 의 `bash_targets` docstring.
- 산출물의 정의는 프로젝트가 [`.claude/harness.json`](../.claude/harness.json) 의 `product` 에 선언한다.
  확장자가 아니라 경로다 — 이 저장소의 산출물은 코드가 아니라 문서다.

### I2. 자기가 만든 것을 자기가 검증하지 않는다

- `기계` critic 은 `Write`/`Edit` 가 없어 자기가 만든 변경이 존재할 수 없다.
- `기계` maker 를 띄우려면 이번 턴에 **수락된 `ExitPlanMode`** 가 있어야 한다.
  훅이 볼 수 있는 사용자 승인은 이것뿐이다 — 오케스트레이터가 "승인받았다"고 주장하는 것은
  자기 인증이라 신호로 치지 않는다. 승인은 그 턴에만 유효하다.

### I3. 검증 없이 끝내지 않는다

- `기계` 이번 턴에 **위임이 일어났는데** 검증이 충족되지 않으면 종료가 차단된다. 충족
  조건은 둘 중 하나다 — (1) 검증자(`verifiers`) 보고의 마지막 줄이 `VERDICT: PASS` 또는
  `VERDICT: CONDITIONAL` 이다 (2) `bash harness/tools/verify.sh` 가 쓴
  `.claude/state/verify-receipt.json` 이 `all_ok: true` 이고 그 시각이 이번 턴의 마지막
  산출물 쓰기보다 뒤다. `VERDICT: FAIL` 이거나 판정 줄이 없으면(검증자가 설계만 냈다)
  충족되지 않는다. `max_close_blocks` 회 이후엔 무조건 통과 — 검증이 막혀도 세션이 안 잠긴다.
  정본과 갈라진 설치처를 위해 `require_verdict: false` 로 두면 검증자가 끝나기만 해도
  충족된다(종전 동작).
- 예산 안에서 메인이 직접 끝낸 턴은 검증 의무가 없다. 거기까지 강제하면 싼 경로가 비싼 경로와
  같아진다. 재량이 아니라 문턱이며, `main_thread_file_limit` 을 그대로 재사용한다.

### I4. 오케스트레이터는 아는 것을 넘긴다

- `기계` `handoff_roles`(기본 `architect` · `maker`)를 띄울 때 브리프가 **실재하는 파일을
  하나도 가리키지 않으면** 스폰이 차단된다. 서브에이전트는 빈 컨텍스트로 시작하므로,
  오케스트레이터가 이미 확인한 사실(파일:라인 · 재현 명령 · 실측값)은 적어두지 않으면
  전달되지 않는다. 훅은 브리프의 **품질**은 못 본다 — 그러나 **아무것도 안 넘긴 것**은 본다.
- `조언` scout 는 대상이 아니다. 조사하러 가는 역할이라 넘겨줄 사실이 아직 없다.
- `관측` 툴 호출 계측에 `agent_id` 를 남긴다. 이것이 없으면 한 세션의 Maker 여럿이 한 줄로
  합산돼 "첫 쓰기까지 몇 번 호출했나"를 도출할 수 없다. **무산출 문턱은 만들지 않았다** —
  데이터가 없는 상태에서 숫자를 지어내는 것이 아래 4절이 금지하는 바로 그것이다.

**왜 이 불변식이 하네스에 늦게 생겼나.** 이 문서는 오랫동안 메인 스레드를 쓰기 개수와
Bash 차단 두 줄로만 규정했다. 브리프를 어떻게 쓸지, 사실을 넘길지, 한 에이전트에 얼마나
몰지에 대한 규칙이 없었고, 그래서 같은 조사를 반복시키는 것이 **규칙 위반이 아니었다.**
서브에이전트의 일탈은 촘촘히 막으면서 그들을 굶기는 쪽은 아무도 안 보고 있었다.

## 1.5 계측

`기계` 훅이 **모든 툴 호출**을 역할별로 기록한다 — 어느 역할이 몇 번 호출하는지가
비용의 실체이기 때문이다. 대가는 **툴 호출당 28ms** (실측).

## 2. 역할

| 역할 | 도구 (`기계`) | 하는 일 |
| --- | --- | --- |
| `scout` | Read, Glob, Grep, Bash, WebFetch, WebSearch | 코드베이스와 문서를 조사해 사실만 보고한다. |
| `architect` | Read, Glob, Grep, Bash, WebFetch, WebSearch | 사실 지도를 받아 실행 계획을 작성한다. |
| `maker` | Read, Write, Edit, Glob, Grep, Bash | 승인된 계획을 코드 변경으로 옮긴다. |
| `critic` | Read, Glob, Grep, Bash | 변경을 e2e 로 검증하고 PASS/CONDITIONAL/FAIL 판정을 낸다. |
| `referee` | Read, Glob, Grep | 여러 병렬 에이전트의 결과를 하나로 종합한다. |

`architect` 와 `scout` 는 도구가 같다 — 둘의 차이는 프롬프트지 권한이 아니다. `조언` 으로 취급한다.

## 3. 언제 위임하는가

- `기계` 산출물 파일 `main_thread_file_limit` 개를 넘으면 위임한다. 그 아래면 직접 한다.
- `조언` 설계 판단(형식 선택, 트레이드오프, 스펙 개정)이 실재하면 maker 앞에 architect 를 둔다.
  단일 변환을 N 개 파일에 적용하는 것뿐이면 architect 를 생략한다.
- `조언` 대상 목록이 불확실하면 scout 를 먼저 부른다. 모르는 채로 치환하면 누락이 난다.

## 4. 계측 기록

`기계` 모든 훅이 이벤트 한 줄을 `.claude/state/harness-metrics.jsonl` 에 append 한다.
**이벤트만 남긴다 — 프롬프트도 파일 내용도 기록하지 않는다.**

현재 문턱은 기존 스펙("1~2 개는 직접, 3 개째부터는 계획")에서 유도한 값이다.
이 데이터가 다른 값을 가리키면 그때 바꾼다 — 근거 없는 숫자를 먼저 박고 나중에 정당화하지 않는다.

`관측` 표시는 지금 하나도 없다. 남아 있으면 그 규칙이 실제로 막히는지 확인하고 표기를 고쳐라.

## 5. 커밋

`조언` 제목 `<type>: <한국어> / <English>`. 본문은 한국어 블록 → `[EN]` → 영문 블록.
구분자로 `---` 를 쓰지 않는다(`git am` 이 뒤를 잘라낸다). `Co-Authored-By` 금지.

## 6. 이 하네스를 고칠 때

전역 설정은 손으로 고치지 않는다. `harness/global/CLAUDE.harness.md` 를 고치고
`harness/install.sh --global` 로 반영한다. **`install.sh` 자신은 `HARNESS_FILES` 목록에
없어 설치된 프로젝트로 복사되지 않는다 — 이 명령도, 아래 `test_install_global.sh` 도
정본 저장소(`agent-harness`)에서만 성립한다. 설치된 프로젝트에는 이 파일이 없다.**

게이트를 바꾸면(**모든 설치처**에서 돈다) [`tests/test_gate.py`](tests/test_gate.py) 를 돌려라:

```bash
python3 harness/tests/test_gate.py
```

`install.sh` 의 `--global` 경로를 바꾸면(**정본 저장소에서만** 돈다) `test_install_global.sh`
도 돌려라 — 실제 `$HOME` 은 건드리지 않고 `mktemp -d` 오버라이드로만 검증한다:

```bash
bash harness/tests/test_install_global.sh   # 12 케이스
```

게이트는 **양쪽이 다 통과해야** 완성이다 — 메인 스레드를 막는 것과, 서브에이전트를 막지 **않는** 것.
한 방향만 보면 "무용한 게이트"와 "마비된 세션"이 둘 다 성공처럼 보인다.

CORE.md 의 역할 표나 `DEFAULTS` 의 키를 바꾸면 [`tests/test_docs_sync.py`](tests/test_docs_sync.py) 도
돌려라 — 역할 표가 `agents/*.md` frontmatter 와, 설정 키가 README·전역 블록·facts 와 어긋나는 것을
기계로 잡는다:

```bash
python3 harness/tests/test_docs_sync.py
```

## 7. 검증 축 — 차단만 시험하면 막다른 길을 못 본다

`기계` `test_gate.py` 는 세 종류를 다 갖춰야 한다. 앞의 둘만 있으면 **전부 통과하는데
쓸 수 없는 하네스**가 나온다. 실제로 그런 적이 있다 — 승인이 한 턴만 유효해서 승인과 위임
사이에 사용자가 한 마디만 하면 쓰기도 위임도 불가능했는데, 152개가 전부 통과했다.

1. **차단 시험** — "여기서 막히는가". 지금 대부분이 이것이다.
2. **관통 시험** — "규정된 경로가 끝까지 가는가". `test_sanctioned_path_runs_end_to_end` 가
   예산 소진 → 승인 → 턴 경계 → 위임 → 서브에이전트 쓰기 → 검증 → 종료를 한 번에 통과시킨다.
   자기가 지정한 탈출 경로의 한 단계를 스스로 막는 게이트는 쓸 수 없다.
3. **메타 시험** — 규칙이 근거를 갖췄는지 시험한다.
   - 금지를 단언하는 테스트(`_does_not_` · `_never_` · `_blocks_` · `_requires_` ·
     `_is_bounded`)는 **docstring 이 있어야 한다.** 이유가 없으면 그것이 요구사항인지
     결함 고정인지 구분할 수 없다. `test_approval_does_not_survive_the_turn` 이 막다른 길을
     지키며 오래 통과했다.
   - `DEFAULTS` 의 **수치 키는 전부 이 문서에 언급돼야 한다.** 근거 없는 숫자가 조용히
     살아남는 경로를 닫는다(4절과 짝).
