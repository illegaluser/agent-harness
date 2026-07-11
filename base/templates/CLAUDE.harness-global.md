<!-- HARNESS:BEGIN -->
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
