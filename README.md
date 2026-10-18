# agent-harness — 집행 우선 멀티 에이전트 하네스

## 무엇인가

**하네스**란 에이전트(모델) 한 세션을 감싸, 작업을 **수행·검증·재현 가능**하게 만드는 실행 골격이다.
이 저장소의 설계 원칙은 하나다 — **집행할 수 없는 규칙은 쓰지 않는다.** 규칙 본문은
[`harness/CORE.md`](harness/CORE.md) 하나뿐이고, 그 안의 모든 규칙에는 `기계`/`관측`/`조언`
표시가 붙는다. `기계`는 훅 또는 에이전트 정의의 `tools:` frontmatter가 어길 수 없게 강제하고,
`관측`은 훅이 기록만 하며(아직 막지 않음), `조언`은 아무것도 확인하지 않는다. 무엇을 실제로
막는지, 역할 5개가 각각 무엇을 하는지는 CORE.md 가 정본이고, 아래 README 는 중복해 적지 않는다.

## 설치

```bash
bash harness/install.sh <target-project-dir>       # 설치
bash harness/install.sh --uninstall <target-project-dir>  # 제거
```

설치되는 소스 파일 목록과 설치 검증 절차는 [`harness/CORE.md`](harness/CORE.md) 머리말·§6 에
있다. 5개 역할 정의는 대상 프로젝트의 `.claude/agents/`에 심링크로 걸린다(사본이 아니라
드리프트가 원리적으로 불가능하다). 훅 6개가 대상 설정에 병합되고, 설정 파일이 없으면 아무것도
막지 않는 기본값으로 새로 만든다 — 실사용 1세션을 거친 뒤 올리라는 뜻이다. `--uninstall`은 훅
항목만 선택적으로 제거하고(다른 훅은 보존), 설치기가 만든 파일만 지운다.

## 역할 5개

정본은 [`harness/agents/`](harness/agents/)이고 표는 [`harness/CORE.md`](harness/CORE.md) §2 에
있다. 불변식: **write는 오직 maker만** 한다(다른 넷은 `tools:`에 `Write`/`Edit`가 없어 파일을 못
쓴다). 자기 산출물을 자기가 최종 검증하지 않는다(maker ≠ critic). 게이트 없는 상태 전이는 없다.

## 저장소 구조

```text
agent-harness/
├── README.md                  이 문서
├── .gitignore
├── harness/                   하네스 정본 — 다른 프로젝트로 배포되는 단위
│   ├── CORE.md                 규칙 본문 전부
│   ├── install.sh               설치·언인스톨 스크립트
│   ├── hooks/gate.py            6개 이벤트를 처리하는 훅
│   ├── tests/test_gate.py       게이트 테스트
│   ├── tests/test_docs_sync.py  문서 정합 기계 대조
│   ├── tools/verify.sh          화면·API 없는 변경의 검증 영수증
│   ├── tools/subagent_cost.py   서브에이전트 비용 집계
│   └── agents/                  scout / architect / maker / critic / referee 5원형
├── .claude/
│   ├── settings.json            훅 배선
│   ├── harness.json             설정값 — 정본은 harness/CORE.md
│   ├── harness-facts.md         SessionStart·SubagentStart 자동 주입 상태 문서
│   └── agents/                  harness/agents/ 로 가는 심링크 5개
└── docs/
    ├── DECISIONS.md              이 저장소 자체의 의사결정 로그
    └── PLAN_HARNESS_REDESIGN.md  재설계 경위와 근거
```

## 테스트

```bash
python3 harness/tests/test_gate.py
python3 harness/tests/test_docs_sync.py
```

게이트는 **양방향이 다 통과해야** 완성이다 — 메인 스레드를 막는 것과, 서브에이전트를
막지 **않는** 것. 한 방향만 확인하면 "무용한 게이트"와 "마비된 세션"이 둘 다 성공처럼 보인다.

## 비용 집계

```bash
python3 harness/tools/subagent_cost.py
```

모든 훅이 역할별 툴 호출을 `.claude/state/` 아래 로그에 이벤트로만 남긴다(프롬프트·파일
내용은 기록하지 않는다). 이 스크립트가 그 로그를 읽어 서브에이전트 실행당 비용을 집계한다.

## 출처

배경과 재설계 경위는 [`docs/PLAN_HARNESS_REDESIGN.md`](docs/PLAN_HARNESS_REDESIGN.md)와
[`docs/DECISIONS.md`](docs/DECISIONS.md)에 있다.
