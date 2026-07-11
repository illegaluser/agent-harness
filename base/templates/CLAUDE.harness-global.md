<!-- HARNESS:BEGIN -->
## 커밋 메시지 규약 — 한글·영문 병기

모든 커밋 메시지는 **한글과 영문을 병기**한다. 한국어가 먼저이고(비개발자 독자 기준), 영문은 같은 내용을 옮긴 것이다.

- **제목** — `<type>: <한국어 요약> / <English summary>`. 슬래시 하나(` / `)로 병기한다. `<type>` 은 저장소의 기존 관례(`feat` / `fix` / `docs` / `refactor` / `chore` 등)를 따른다.
- **본문** — 한국어 항목 블록을 먼저 쓰고, `[EN]` 한 줄을 구분자로 둔 뒤, 같은 항목을 같은 순서로 영문 블록에 쓴다. 두 블록의 항목 수와 순서는 1:1 로 대응한다.
- **문체** — 한국어는 비개발자도 이해할 쉬운 말. 영문은 같은 내용을 영어권 커밋 관례(명령형 현재시제)로 옮긴다.
- **본문이 한 줄이면** 블록을 나누지 않고 `한국어 문장 / English sentence` 한 줄 병기로 갈음할 수 있다.
- **구분자로 `---` 를 쓰지 않는다** — `git format-patch` / `git am` 이 `---` 로 시작하는 줄을 패치 경계로 보고 그 뒤(영문 블록 전체)를 잘라낸다. 그래서 `[EN]` 을 쓴다.
- **`Co-Authored-By` trailer 금지.** 다른 trailer 도 사용자가 명시 요청할 때만 붙인다.

예시:

```text
docs: 하네스 커밋 규약 추가 / Add harness commit convention

- 5개 에이전트 정의의 커밋 규칙을 병기로 통일
- 전역 CLAUDE.md에 동일 규칙 추가

[EN]

- Unify commit rules across 5 agent definitions
- Add the same rule to the global CLAUDE.md
```

## Subagent 위임 규칙 — Scout → Architect → Maker → Critic

> 스펙 출처: 이식 대상 프로젝트의 `docs/harness/00-definition.md` · `01-roles.md` · `02-orchestration.md`
> · `03-adoption.md` (harness-dist로 설치됨)

`~/.claude/agents/` 에 **scout / architect / maker / critic / referee** 다섯 글로벌 subagent 정의가
있다. 프로젝트가 자기 `.claude/agents/` 에 같은 이름으로 정의를 두면 그 프로젝트에서는 project-level
이 우선 적용된다.

**불변식 (프로젝트가 풀 수 없음):** write 는 오직 Maker 만 한다. 자기 산출물을 자기가 최종 검증하지
않는다(Maker ≠ Critic). 게이트 없는 상태 전이는 없다.

### 자동 파이프라인이 발동하는 카테고리

다음 중 **하나라도 해당하면** Scout → Architect → (사용자 승인) → Maker → Critic 순서로 진행한다.

- 신규 모듈/패키지 추가 또는 기존 모듈의 아키텍처 변경
- 신규 테스트 슈트 추가 (특히 e2e / integration)
- `build.sh` / launcher / CI / 배포 / git hook 스크립트 수정
- 실행 토폴로지 변경 (host ↔ container ↔ VM ↔ remote)
- 외부 시스템 (DB, MQ, LLM provider, vector store 등) 연동 흐름 수정
- 의존성 버전 핀 변경 (보안 / 호환성 영향이 있는 것)
- 보안/약관 영향이 있는 변경 (인증·인가, 외부 LLM 호출 경로 등)
- 프로젝트 `CLAUDE.md` 가 추가로 지정한 카테고리

### 파이프라인을 건너뛰는 케이스 (직접 처리)

- 1~2 개 파일의 명확한 버그 수정 / 오타 / 문서 단순 갱신
- 사용자가 이미 구체적 코드 변경 위치/내용을 지시한 경우
- lint 만 정리하는 작업
- 단, 위 경우에도 변경 후 critic 단독 호출은 **권장** (사용자가 빠르게 끝내라고 명시한 경우 면제)

### 기계적 변경 — Architect 생략

**단일 정의된 변환을 N개 파일에 적용하고 설계 판단이 없으면**, 파일 개수와 무관하게 Architect 를
생략한다: `@agent-scout` → `@agent-maker` → `@agent-critic`.

기계적 변경의 조건 (전부 충족):

- 변환 규칙이 한 문장으로 적히고 대상마다 동일하다 (문자열 치환, 이름 변경, 포맷 통일 등)
- 새 동작·새 인터페이스·새 의존성이 생기지 않는다
- 되돌리기가 `git revert` 한 번이다

**대상 목록이 불확실하면 Scout 를 반드시 먼저 부른다.** 사본이 몇 곳에 있는지 모르는 채로 Maker 를
부르면 누락이 난다. Scout 는 sonnet/low 라 싸다 — 여기서 아끼지 마라.

설계 판단이 하나라도 실재하면(형식 선택, 트레이드오프, 스펙 개정) 기계적 변경이 아니다. Architect 를 부른다.

### 검증 등급 — Critic 모델 오버라이드

Critic 기본은 `claude-sonnet-5` / high 다. 다음 중 하나라도 해당하면 `model: claude-opus-4-8` 로
**올려서** 호출한다:

- 인증·인가, 비밀정보 취급, 외부 LLM 호출 경로
- `build.sh` / CI / 배포 / git hook / launcher 스크립트
- 실행 토폴로지 변경, 외부 시스템(DB·MQ·vector store) 연동 흐름
- 되돌리기 비용이 큰 변경 (마이그레이션, 스키마)

### 토큰 규율 (모든 역할 공통)

- 같은 파일을 두 번 읽지 않는다. 필요한 범위만 읽는다.
- N개 파일에 같은 변환을 적용할 때는 파일별 Edit 이 아니라 **스크립트 한 번**으로 처리한다.
- diff 로 충분한 검증을 파일 전체 재독으로 하지 않는다.
- 탐색적 조회는 Scout 의 일이다. Architect / Maker / Critic 은 주어진 사실 지도 위에서 움직인다.
- 툴 호출 횟수가 곧 비용이다. 매 호출마다 대화 전체가 다시 실려 간다.

### 파이프라인 절차 (기본형: 순차 게이트)

1. `@agent-scout` 호출 → 사실 지도 작성 (코드베이스·문서 조사)
2. `@agent-architect` 호출 → 실행 계획 작성
3. 계획을 사용자에게 제시하고 **명시적 승인** 대기 (승인 게이트). 승인 없이 다음 단계 진행 금지.
4. `@agent-maker` 호출 → 승인된 계획으로 구현
5. `@agent-critic` 호출 → 판정 보고 (검증 게이트)
6. 판정에 따라:
   - PASS: 완료 보고
   - CONDITIONAL: WARNING 목록 사용자에게 전달, 처리 여부 결정 위임
   - FAIL: `@agent-maker` 재호출 (최대 2 회). 그래도 FAIL 이면 사용자에게 에스컬레이션.

### 오케스트레이션 패턴 참조 (02-orchestration.md)

| 패턴 | 구성 | 발동 조건 |
| --- | --- | --- |
| **순차 게이트** | Scout→Architect→Maker→Critic | 기본형. 재현성 최우선 |
| **팬아웃-검증** | Critic ×N → `@agent-referee` 종합 | 런타임 표면 코드 변경 기본 검증 (고위험은 적대적 검증 중첩) |
| **분할-정복** | Maker ×M → `@agent-referee` 병합 → Critic | 단일 컨텍스트를 초과하는 대규모 작업 |
| **적대적 검증** | Critic ×N 에게 "반증하라" | 판정 진위 확정이 치명적일 때 다른 패턴에 중첩 |

### 에이전트별 경계 (위반하면 즉시 멈춤)

- scout — 판단·권고·파일 수정 금지. read-only.
- architect — 코드 작성·파일 수정 금지. read-only.
- maker — 승인된 계획 없이 시작 금지. 3 개 파일 이상 변경하는데 계획이 없으면 architect 호출 안내 후 멈춤.
- critic — 코드 수정 금지. 발견·판정·보고만. 자기가 만든 변경 검증 금지.
- referee — 새 작업·새 코드 생성 금지. 팬아웃/분할 패턴에서만 사용.

수동 호출: `@agent-scout` / `@agent-architect` / `@agent-maker` / `@agent-critic` / `@agent-referee`
<!-- HARNESS:END -->
