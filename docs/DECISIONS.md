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

## D-002 · Bilingual (KO/EN) commit message convention / 커밋 메시지 한글·영문 병기 규약 — 2026-07-12

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: The harness R0.3 global rules mandated Korean-only commit messages, duplicated verbatim
  across five agent definitions and the R0 spec. Contributors and tooling that read English
  histories could not follow the log, and there was no single canonical place holding the
  message format.
  KO: 하네스 R0.3 글로벌 룰은 한국어 전용 커밋 메시지를 요구했고, 그 문장이 5개 에이전트
  정의와 R0 스펙에 그대로 중복돼 있었다. 영문 이력을 읽는 사람·도구는 로그를 따라갈 수
  없었고, 메시지 형식의 정본이 한 곳에 없었다.
- 결정 (Decision):
  EN: Require bilingual commit messages — title `<type>: <KO summary> / <EN summary>`, body as a
  Korean bullet block followed by an `[EN]` separator line and a matching English bullet block.
  The full format and example live in one canonical place, the harness-managed block of the
  global CLAUDE.md; the R0.3 bullet in the five agent files and 01-roles keeps a self-contained
  one-line rule that points there.
  KO: 커밋 메시지를 한글·영문 병기로 요구한다 — 제목은 `<type>: <한국어 요약> / <English
  summary>`, 본문은 한국어 불릿 블록 뒤에 `[EN]` 구분자 줄과 대응하는 영문 불릿 블록.
  전체 형식과 예시는 단일 정본(글로벌 CLAUDE.md 의 하네스 관리 블록)에 두고, 5개 에이전트
  파일과 01-roles 의 R0.3 불릿에는 자립 가능한 한 줄 규칙 + 정본 참조만 남긴다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) A bare `---` separator between the two blocks — rejected: verified that `git am` on
  `git format-patch` output treats any line starting with `---` as the patch boundary and drops
  the entire English block. (2) Keeping the full format duplicated in all six R0.3 copies —
  rejected: it re-creates the drift this repo exists to prevent. (3) Replacing the R0.3 bullet
  with a bare pointer to the global CLAUDE.md — rejected: a project may override an agent file
  wholesale (03-adoption A2.1), and that copy must still carry an operative rule.
  KO: (1) 두 블록 사이에 맨 `---` 구분자 — 기각: `git format-patch` 산출물을 `git am` 으로
  적용하면 `---` 로 시작하는 줄을 패치 경계로 보고 영문 블록 전체를 버리는 것을 실측 확인.
  (2) 여섯 개 R0.3 사본 전부에 전체 형식을 중복 기술 — 기각: 이 저장소가 막으려는 드리프트를
  다시 만든다. (3) R0.3 불릿을 글로벌 CLAUDE.md 참조만으로 축약 — 기각: 프로젝트가 에이전트
  파일을 통째로 오버라이드할 수 있고(03-adoption A2.1) 그 사본도 규칙을 자립적으로 실어야 한다.
- 사유 (Rationale):
  EN: Korean stays first because the primary reader is a non-developer; English is added so the
  history is legible to English-reading contributors and tooling. Placing the canonical text
  inside the HARNESS-managed marker block makes `install-harness.sh --global` the single sync
  path (idempotent, backed up, reversible by `--uninstall`).
  KO: 1차 독자가 비개발자이므로 한국어를 앞에 둔다. 영문은 영어권 기여자·도구가 이력을 읽을 수
  있게 덧붙인다. 정본을 HARNESS 관리 마커 블록 안에 두면 `install-harness.sh --global` 이 유일한
  동기화 경로가 된다(멱등·백업·`--uninstall` 로 되돌림 가능).
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): `base/templates/CLAUDE.harness-global.md` · `base/docs/harness/01-roles.md` R0.3 · `base/agents/*.md` R0.3

## D-003 · Cut harness token usage via risk-based routing, model tiers, and tool-call discipline / 위험도 기반 라우팅·모델 등급·툴 호출 규율로 하네스 토큰 소비 절감 — 2026-07-12

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: A single-line documentation-string substitution applied across a fixed set of files
  consumed 241k sub-agent tokens in one run. The root cause was not risk level but the routing
  rule itself — the pipeline (Scout→Architect→Maker→Critic) fired based on how many files were
  touched rather than whether any design judgment was actually needed, and no agent definition
  placed a discipline on tool-call count, so Maker replayed the same transform file-by-file via
  67 individual `Edit` calls instead of one script.
  KO: 고정된 파일 집합에 문서 문자열 한 줄을 치환하는 작업 하나가 한 실행에서 서브에이전트
  토큰 241k를 소비했다. 근본 원인은 위험도가 아니라 라우팅 규칙 자체였다 — 파이프라인
  (Scout→Architect→Maker→Critic)이 실제로 설계 판단이 필요한지가 아니라 몇 개 파일을
  건드리는지로 발동했고, 어떤 에이전트 정의에도 툴 호출 횟수에 대한 규율이 없어서
  Maker가 같은 변환을 스크립트 한 번이 아니라 파일별 `Edit` 67회로 재생했다.
- 결정 (Decision):
  EN: Switch the routing rule from file-count to risk/design-judgment — skip Architect for
  mechanical changes (one transform, no new behavior/interface/dependency, one-`git revert`
  reversible) and go straight Scout→Maker→Critic, but require Scout first whenever the target
  list is uncertain. Lower the Critic default model to `claude-sonnet-5` and escalate to
  `claude-opus-4-8` only for a named high-risk list (auth/secrets/external-LLM paths, build/CI/
  deploy/hook/launcher scripts, execution-topology or external-system integration changes,
  costly-to-revert changes). Lower Maker's default effort to medium and Referee to
  sonnet-5/medium. Add an explicit tool-call discipline block to the Maker and Critic agent
  definitions: one script per multi-file transform, verification from `git diff`/`git show`
  rather than re-reading whole files, no duplicate confirmations.
  KO: 라우팅 규칙을 파일 개수 기준에서 위험도·설계 판단 기준으로 바꾼다 — 기계적 변경(단일
  변환, 새 동작·인터페이스·의존성 없음, `git revert` 한 번으로 원복)은 Architect 를 생략하고
  Scout→Maker→Critic 로 바로 가되, 대상 목록이 불확실하면 반드시 Scout 를 먼저 부른다.
  Critic 기본 모델을 `claude-sonnet-5` 로 낮추고, 지정된 고위험 목록(인증·비밀정보·외부
  LLM 호출 경로, build/CI/배포/훅/launcher 스크립트, 실행 토폴로지·외부 시스템 연동 변경,
  되돌리기 비용이 큰 변경)에만 `claude-opus-4-8` 로 올린다. Maker 기본 effort 를 medium 으로,
  Referee 를 sonnet-5/medium 으로 낮춘다. Maker·Critic 에이전트 정의에 명시적 툴 호출 규율
  블록을 추가한다 — 다중 파일 변환은 스크립트 한 번, 검증은 파일 전체 재독이 아니라
  `git diff`/`git show` 에서 시작, 같은 사실의 중복 재확인 금지.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) Add a separate `critic-deep` agent for high-risk verification — rejected: it breaks
  the fixed 5-role invariant (Scout/Architect/Maker/Critic/Referee) that the harness's write/
  verify separation depends on. (2) Lower model tiers only, without touching routing or tool-call
  discipline — rejected: the 241k spend was driven mainly by call count (67 `Edit` calls for one
  transform), not by which model answered each call, so a model-only fix would leave most of the
  cost in place.
  KO: (1) 고위험 검증용 별도 `critic-deep` 에이전트 추가 — 기각: 하네스의 write/verify
  분리가 의존하는 고정 5역할 불변식(Scout/Architect/Maker/Critic/Referee)을 훼손한다.
  (2) 라우팅·툴 호출 규율은 손대지 않고 모델 등급만 낮추기 — 기각: 241k 소비의 주 원인은
  어느 모델이 응답했는지가 아니라 호출 횟수(변환 하나에 `Edit` 67회)였으므로, 모델만
  낮추면 비용 대부분이 그대로 남는다.
- 사유 (Rationale):
  EN: File count is a poor proxy for risk — a 17-file rename and a 1-file auth-flow change are
  not equivalent, and routing on the wrong axis both over-invokes Architect for trivial work and
  under-scrutinizes genuinely risky single-file changes. Tool-call count is a direct, observable
  cost driver independent of model choice, so it needs its own explicit rule rather than being
  left to each agent's judgment call by call.
  KO: 파일 개수는 위험도의 부실한 대리 지표다 — 17개 파일 이름 변경과 1개 파일 인증 흐름
  변경은 동등하지 않고, 잘못된 축으로 라우팅하면 사소한 작업에 Architect 를 과호출하면서
  동시에 진짜 위험한 단일 파일 변경은 덜 검토하게 된다. 툴 호출 횟수는 모델 선택과
  무관하게 직접 관측 가능한 비용 요인이므로, 매 호출마다 각 에이전트의 임기응변에
  맡기지 않고 명시적 규칙으로 못박을 필요가 있다.
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): `base/templates/CLAUDE.harness-global.md` · `base/agents/maker.md` · `base/agents/critic.md` · `base/agents/referee.md`
