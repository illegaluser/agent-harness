# 의사결정 로그 (Decision Log)

이 파일은 멀티 에이전트 하네스(`base/docs/harness/00-definition.md` C6, `base/docs/harness/02-orchestration.md` O0)의
**승인 게이트**와 **검증 게이트**에서 확정된 결정을 append-only 로 누적한다. 메모리(최신 사실)와 달리
지워지지 않는 "왜의 이력" 이다. 작성 주체는 파이프라인을 모는 오케스트레이터(수동이면 메인 세션,
자동이면 Workflow)이며, 승인/검증 게이트 통과 시 항목을 덧붙인다. 핸드오프 게이트는 정상 통과 시
기록하지 않고 필드 누락으로 **차단됐을 때만** 기록한다.

새 항목은 이 파일 **끝**에 덧붙인다. 한 번 쓴 항목은 고치지 않는다(ADR과 같은 계열). 게이트 통과 시
오케스트레이터가 `DECISION_LOG: D-NNN appended` 또는 `DECISION_LOG: skip — <사유>`(사유는
no-new-decision / duplicate / pipeline-skipped 중 하나) 마커를 출력해야 게이트가 닫힌다
(`base/docs/harness/02-orchestration.md` O0 참조).

## 항목 스키마

```text
## D-NNN · <Title EN / 제목 KO> — <YYYY-MM-DD>
- 게이트 (Gate): 승인 | 검증 | 핸드오프(차단 시) (Approval | Verification | Handoff-on-block)
- 맥락 (Context):
  EN: <what needed to be decided>
  KO: <무엇을 결정해야 했나>
- 결정 (Decision):
  EN: <what was decided>
  KO: <무엇으로 정했나>
- 대안·기각 (Alternatives · Rejected):
  EN: <what was excluded and why>
  KO: <무엇을 왜 뺐나>
- 사유 (Rationale):
  EN: <grounds>
  KO: <근거>
- 결정자 (Decider): 사용자 | Architect | Critic (User | Architect | Critic)
- 연결 (Links): 관련 계획서 / PR / 커밋 / [[memory]]
```

`D-NNN` 은 파일 내 순번(001부터).

---

## D-001 · Extract the multi-agent harness into a standalone repo / 멀티 에이전트 하네스를 독립 저장소로 추출 — 2026-07-12

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: The multi-agent harness (5 roles, spec docs, hooks, templates) was built and validated
  inside a private project repository. Its canonical copy lived in that repo's own build-side
  packaging directory, with some pieces additionally drifting out of sync in the user's global
  Claude Code configuration. There was no independently tracked, standalone home for the harness
  itself, which made it hard to version, share, or install into other projects with confidence
  about which copy was current.
  KO: 멀티 에이전트 하네스(5원형·스펙 문서·훅·템플릿)는 한 사설 프로젝트 저장소 안에서
  구축·검증됐다. 정본 사본은 그 저장소 자체의 빌드측 패키징 디렉토리에 있었고, 일부는
  사용자의 전역 Claude Code 설정에서 추가로 어긋난(stale) 채로 흩어져 있었다. 하네스
  자체를 위한, 독립적으로 추적되는 정본 홈이 없어서 버전 관리·공유·다른 프로젝트로의
  설치 시 "어느 사본이 최신인가"를 확신하기 어려웠다.
- 결정 (Decision):
  EN: Promote the source repository's build-side packaging snapshot to this repository's single
  canonical `base/`, initialize this repository fresh (git init, no history import), and push it
  to its own remote as the standalone home for the harness going forward.
  KO: 소스 저장소의 빌드측 패키징 스냅샷을 이 저장소의 단일 정본 `base/`로 승격하고, 이
  저장소를 신규로 초기화(git init, 이력 이식 없음)해, 앞으로 하네스의 독립 정본 홈이 될
  자체 원격에 push 한다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) Keep the harness living inside the source project repo — rejected because the
  canonical copy stays scattered across a project-specific directory and is not tracked or
  versioned as a first-class, globally reusable artifact. (2) Two-layer dogfooding, where the
  source project keeps consuming and re-exporting its own harness copy back into itself —
  rejected because it reintroduces the exact drift problem this extraction is meant to solve
  (a canonical spec doc or hook silently diverging from what actually ships).
  KO: (1) 하네스를 소스 프로젝트 저장소 안에 계속 두는 안 — 정본 사본이 프로젝트 전용
  디렉토리에 계속 흩어진 채로 남고, 전역 재사용 가능한 1급 산출물로 추적·버전관리되지
  않아 기각. (2) 소스 프로젝트가 자기 하네스 사본을 계속 소비하고 다시 자기 자신으로
  재수출하는 2계층 도그푸드 안 — 이 추출 작업이 풀려는 바로 그 drift 문제(정본 스펙
  문서나 훅이 실제 배포본과 조용히 어긋나는 것)를 재도입하므로 기각.
- 사유 (Rationale):
  EN: A single canonical source, reproducibility, and a globally reproducible install path
  (bash / python3 / git only, no network access required) outweigh the convenience of keeping
  everything in one repository. A standalone repo makes the harness a first-class, independently
  versioned artifact that any project can install from without depending on the internals of the
  project it was originally built in.
  KO: 단일 정본, 재현성, 그리고 전역에서 재현 가능한 설치 경로(bash / python3 / git 뿐,
  네트워크 접근 불필요)가 모든 것을 한 저장소에 두는 편의보다 중요하다. 독립 저장소로
  두면 하네스가 원래 구축됐던 프로젝트의 내부 구조에 의존하지 않고, 어떤 프로젝트든
  설치할 수 있는 1급의 독립 버전관리 산출물이 된다.
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): [`README.md`](../README.md) · 출처 저장소: 비공개 사설 프로젝트
