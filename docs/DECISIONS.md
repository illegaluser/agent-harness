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

## D-004 · Close three existential warnings from the D-003 verification verdict / D-003 검증 판정의 존립 위협 3건 해소 — 2026-07-12

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: After the D-003 token-saving settings landed, Critic returned a CONDITIONAL verdict with
  five WARNINGs, three of which threatened the change's survival: (a) the airgap project's stale
  vendored harness copy (`harness-dist/`) still shipped a working installer whose `--global
  --force` run would silently overwrite today's global config with yesterday's frontmatter,
  undoing the settings; (b) the role spec's meta tables in `01-roles.md` still prescribed the old
  models/effort for Maker, Critic, and Referee, and under the harness's own Docs-First norm the
  spec outranks the implementation, so the stale table would eventually win back; (c) the
  mechanical-change rule and the auto-pipeline categories in the global CLAUDE.md template could
  both apply to the same change (e.g. a rename that touches `build.sh`) with no stated precedence.
  KO: D-003 토큰 절감 설정이 반영된 뒤, Critic 이 CONDITIONAL 판정과 WARNING 5건을 냈고 그중
  3건이 이 변경의 존립을 위협했다 — (a) airgap 프로젝트의 옛 하네스 배포 사본
  (`harness-dist/`)이 여전히 동작하는 인스톨러를 담고 있어 `--global --force` 를 실행하면
  오늘 설정이 어제의 옛 frontmatter 로 조용히 덮여 되돌아갈 위험이 있었음; (b) `01-roles.md`
  의 메타 표가 여전히 Maker·Critic·Referee 의 옛 모델/effort 를 규정했고, 하네스 자신의
  Docs-First 규범상 스펙이 구현을 이기므로 방치하면 결국 옛 표가 다시 이김; (c) 글로벌
  CLAUDE.md 템플릿의 기계적 변경 규칙과 자동 파이프라인 카테고리가 같은 변경(예: `build.sh`
  를 포함한 이름 치환)에 동시에 적용될 수 있는데 우선순위 문장이 없었음.
- 결정 (Decision):
  EN: (a) Delete `harness-dist/` from the airgap repo entirely (it is a consumer, not a
  distributor, of the harness) and fix the two stray references to that directory name left in
  H's own templates. (b) Update the R3/R4/R5 default-model/effort rows in `01-roles.md` (both H's
  canonical copy and A's project copy) to match the new frontmatter: Maker and Referee to standard
  tier / medium, Critic to standard tier / high with an explicit escalate-on-high-risk note; also
  fix `03-adoption.md`'s Referee effort line and repoint its R0.3 commit-convention pointer at the
  global CLAUDE.md instead of an ambiguous "this file". (c) Add a precedence paragraph to the
  mechanical-change section of the global CLAUDE.md template stating that pipeline categories win
  over the mechanical-change shortcut.
  KO: (a) airgap 저장소에서 `harness-dist/` 를 통째로 삭제한다(이 저장소는 하네스의 소비자이지
  배포자가 아니다) 및 H 자신의 템플릿에 남은 그 디렉토리 이름에 대한 참조 2곳을 고친다.
  (b) `01-roles.md`(H 정본·A 프로젝트 사본 양쪽)의 R3/R4/R5 기본 모델/effort 행을 새
  frontmatter 에 맞춘다 — Maker·Referee 는 표준 tier/medium, Critic 은 표준 tier/high +
  고위험 시 승격 명시 문구. `03-adoption.md` 의 Referee effort 줄도 고치고, R0.3 커밋 규약
  정본 위치 표기를 모호한 "이 파일" 대신 글로벌 CLAUDE.md 로 바꾼다. (c) 글로벌 CLAUDE.md
  템플릿의 기계적 변경 절에 "카테고리 규칙이 이긴다"는 우선순위 문단을 추가한다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) Keep `harness-dist/` and just sync it to the canonical repo — rejected: it leaves two
  copies of the packager and source in existence, so drift recurs by construction. (2) Leave the
  spec tables as-is and rely on the frontmatter alone — rejected: the harness's own Docs-First
  norm means the spec wins over the implementation, so an unmatched table would get silently
  restored on the next spec-first read.
  KO: (1) `harness-dist/` 를 남기고 정본과 동기화만 하기 — 기각: 패키저와 소스 사본이 두 벌
  존재하는 구조 자체가 남아 drift 가 구조적으로 재발한다. (2) 스펙 표는 그대로 두고
  frontmatter 만 믿기 — 기각: 하네스 자신의 Docs-First 규범상 스펙이 구현을 이기므로,
  일치하지 않는 표는 다음 스펙 우선 판독에서 조용히 되살아난다.
- 사유 (Rationale):
  EN: A settings change is not done while a path remains that can revert it — a working stale
  installer, an outranking stale spec table, and an unresolved rule conflict are each such a
  path. Closing all three, rather than the frontmatter alone, is what makes D-003 durable.
  KO: 설정 변경은 그것을 되돌릴 수 있는 경로가 남아 있으면 완료된 것이 아니다 — 동작하는 옛
  인스톨러, 구현을 이기는 옛 스펙 표, 미해결 규칙 충돌이 각각 그런 경로였다. frontmatter
  만이 아니라 이 세 경로를 모두 닫아야 D-003 이 오래간다.
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): `base/docs/harness/01-roles.md` R3·R4·R5 메타 표 · `base/docs/harness/03-adoption.md` · `base/templates/CLAUDE.harness-global.md` · [[D-003]]

## D-005 · Classify Maker's plan deviations into method vs scope, and require a pre-substitution count check / Maker 의 계획 이탈을 방법·범위로 구분하고 치환 전 대상 개수 확인을 의무화 — 2026-07-12

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: While performing a substitution, Maker discovered that the target string was identical not
  only in the intended row but also in a different role's row. The plan's assert condition caught
  this, but the plan required Maker to stop and report — instead Maker changed its method on its
  own and continued. There was no rule distinguishing the kinds of deviation.
  KO: Maker 가 치환 작업 중 대상 문자열이 의도한 행 말고 다른 역할의 행에도 동일하게 존재함을
  발견했다. 계획서의 assert 조건이 이를 잡았지만, 계획서는 "멈추고 보고"를 요구했는데 Maker 는
  스스로 방법을 바꿔 진행했다. 이탈의 종류를 구분하는 규정이 없었다.
- 결정 (Decision):
  EN: Split deviations in the Maker definition into two kinds — a method deviation may proceed but
  must always be disclosed, while a scope/goal deviation requires an immediate stop. When the kind
  is unclear, default to stopping. Also require counting the targets before any multi-site
  substitution.
  KO: Maker 정의에 이탈을 두 종류로 구분한다 — 방법 이탈은 진행하되 반드시 보고, 범위·목표
  이탈은 즉시 정지. 판단이 서지 않으면 정지. 아울러 다중 치환 전 대상 개수 확인을 의무화한다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) Stop on every deviation — rejected. Stopping every time the method changes creates a
  user round-trip each time, exploding token and latency cost, which conflicts with D-003's
  savings goal. (2) Leave all deviations to Maker's discretion — rejected. It would erode the
  plan's authority and hollow out the approval gate.
  KO: (1) 모든 이탈에서 정지 — 기각. 방법이 바뀔 때마다 사용자 왕복이 생겨 토큰·지연 비용이
  폭발하고, 이는 D-003 의 절감 목표와 충돌한다. (2) 모든 이탈을 Maker 재량에 맡김 — 기각.
  계획서의 권위가 무너지고 승인 게이트가 형해화된다.
- 사유 (Rationale):
  EN: A plan constrains the goal and the scope, not the means. However, the fact that the means
  changed is something the verifier needs to know, so disclosure is never waived.
  KO: 계획은 목표와 범위를 구속하는 것이지 수단까지 구속하는 것이 아니다. 다만 수단을 바꿨다는
  사실은 검증자가 알아야 하므로 보고는 면제되지 않는다.
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): `base/agents/maker.md` · [[D-003]]

## D-006 · Record sub-agent cost, but do not enforce thresholds on it / 서브에이전트 비용을 기록하되 문턱은 만들지 않는다 — 2026-08-02

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: `harness/tools/subagent_cost.py` now aggregates 545 recorded sub-agent runs
  (`~/.claude/projects/*/*/subagents/agent-*.jsonl`) into per-agentType `ctx_peak`/`new_tok`/
  `out_tok`/`tool_calls`/`wall_s` statistics. The question was whether any of these five metrics
  should become an enforced cap, given the harness's own principle that a rule without an
  enforcement point should not be written.
  KO: `harness/tools/subagent_cost.py` 가 기록된 서브에이전트 런 545개
  (`~/.claude/projects/*/*/subagents/agent-*.jsonl`)를 agentType 별 `ctx_peak`/`new_tok`/
  `out_tok`/`tool_calls`/`wall_s` 통계로 집계하게 됐다. 이 다섯 지표 중 무엇이라도 집행되는
  상한으로 만들어야 하는지가 쟁점이었다 — "집행 지점이 없는 규칙은 쓰지 않는다"는 하네스
  자신의 원칙이 있기 때문이다.
- 결정 (Decision):
  EN: (1) No wall-clock cap. A local max of 24,173s was observed, but the field mixes idle time
  with actual work and the data has no field to separate the two. (2) No token cap. The only hook
  point during a sub-agent's own run is its internal `PreToolUse`, and that payload carries no
  token fields (confirmed against the hooks reference) — so any token figure is post-hoc-record
  only, never an enforcement point. (3) No `tool_calls` cap for now — user decision: look at the
  distribution first via `subagent_cost.py`, then revisit. Observed data (agentType: n,
  ctx_peak median/max): scout 53, 90,062/231,919; maker 123 (plan-time snapshot: 121), 115,433/
  518,152 (plan-time median snapshot: 119,457); critic 123 (plan-time snapshot: 122), 83,146/
  198,133 (plan-time median snapshot: 83,334); architect 46, 90,696/272,230; referee 12, 36,993/
  67,355. Medians for maker/critic drifted slightly from the plan's snapshot because the corpus
  grew between planning and this write (n +1~+2); the max values match exactly. (4) Correction:
  the state note in `.claude/harness-facts.md` claiming "one scout run spent 116K tokens" as an
  outlier is refuted by this data — scout's `ctx_peak` median is 90,062, so 116K sits inside the
  normal range, not above it. All figures above are a snapshot taken at record time — the corpus
  keeps growing, so a later run of `subagent_cost.py` will show different numbers.
  KO: (1) wall-clock 상한을 만들지 않는다. 로컬 실측 최대 24,173초가 관측되나, 이 필드는
  유휴 시간과 실제 작업 시간이 섞여 있고 데이터에 둘을 분리할 필드가 없다. (2) 토큰 상한을
  만들지 않는다. 서브에이전트 자기 실행 중 걸리는 유일한 훅 지점은 그 내부의
  `PreToolUse` 인데, 그 페이로드에는 토큰 필드가 없다(hooks 레퍼런스로 확인) — 따라서
  어떤 토큰 수치도 사후 기록 전용이지 집행 지점이 될 수 없다. (3) `tool_calls` 캡은
  지금 만들지 않는다 — 사용자 결정: `subagent_cost.py` 로 분포를 먼저 보고 나중에 재론한다.
  실측(agentType: n, ctx_peak 중앙/최대): scout 53, 90,062/231,919 · maker 123(계획 당시
  스냅샷 121), 115,433/518,152(계획 당시 중앙값 스냅샷 119,457) · critic 123(계획 당시
  스냅샷 122), 83,146/198,133(계획 당시 중앙값 스냅샷 83,334) · architect 46, 90,696/
  272,230 · referee 12, 36,993/67,355. maker·critic 의 중앙값이 계획 스냅샷과 소폭
  어긋나는 것은 계획 수립 시점 이후 코퍼스가 늘었기 때문이며(n +1~+2), 최대값은 정확히
  일치한다. (4) 정정 기록: `.claude/harness-facts.md` 의 "scout 하나가 116K 토큰을 썼다"는
  이상치 진술은 이 데이터로 반증됐다 — scout `ctx_peak` 중앙값이 90,062이므로 116K 는 정상
  범위 안이지 이상치가 아니다. 위 수치는 전부 기록 시점 스냅샷이다 — 코퍼스가 계속 늘어나므로
  나중에 `subagent_cost.py` 를 다시 돌리면 다른 값이 나온다.
- 대안·기각 (Alternatives · Rejected):
  EN: Enforce a hard wall-clock or token cap on sub-agents anyway, on the theory that an
  approximate signal beats none — rejected. The harness's own founding principle (`harness/
  CORE.md`) is that a rule without an enforcement point degrades into an ignored norm, which was
  the exact failure mode the old `base/` harness had (10% of 183 norms mechanically enforced).
  Writing an unenforceable cap here would reintroduce that failure inside the very tool built to
  measure it.
  KO: 그래도 서브에이전트에 하드 wall-clock/토큰 캡을 걸자는 안 — "근사 신호가 없는 것보단
  낫다"는 논리. 기각. 하네스 자신의 창립 원칙(`harness/CORE.md`)이 "집행 지점 없는 규칙은
  무시되는 규범으로 퇴화한다"는 것이고, 이는 옛 `base/` 하네스가 겪은 바로 그 실패 양상이다
  (규범 183개 중 기계 집행 10%). 여기서 집행 불가능한 캡을 쓰면 그것을 측정하려 만든 도구
  안에서 같은 실패를 재도입하는 것이다.
- 사유 (Rationale):
  EN: A threshold that cannot block anything is documentation dressed as enforcement, and the
  harness's whole design point is to keep those two categories visibly distinct (machine vs.
  advisory). Recording the five metrics without a cap keeps the option open once either the data
  gains an idle-time field or a hook payload gains token fields.
  KO: 아무것도 막을 수 없는 문턱은 집행처럼 보이는 문서일 뿐이고, 이 하네스 설계 전체의
  요점은 그 둘(기계/조언)을 눈에 보이게 구분하는 것이다. 캡 없이 다섯 지표를 기록해 두면
  나중에 데이터에 유휴 시간 필드가 생기거나 훅 페이로드에 토큰 필드가 생겼을 때 다시 논의할
  여지를 남긴다.
- 결정자 (Decider): 사용자 (User)
- 연결 (Links): `harness/tools/subagent_cost.py` · `harness/CORE.md` · `.claude/harness-facts.md`

## D-007 · Follow symlinks in `install.sh --global`, gate on `python3` first, and skip no-op backups / `install.sh --global` 이 심링크를 따라가고 `python3` 를 제일 먼저 확인하며 무변화 백업을 만들지 않게 한다 — 2026-08-03

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: A prior critic pass on `install.sh --global` left four unresolved findings (W3, W4, W5, N4;
  see "미완 4번" in `.claude/harness-facts.md`). If `~/.claude/agents` or `~/.claude/CLAUDE.md` is a
  symlink (a dotfiles setup), `cp -R`/`mv` silently replaced the symlink with a real file/dir (W4)
  or backed up only the symlink itself, not its target's content (W3). With no upfront `python3`
  check, a machine missing it hit a bare `command not found` mid-install, after files were already
  copied (W5). And every re-run created a fresh `.bak-<epoch>` even when nothing had changed (N4).
  A subsequent Critic (opus) re-review of that first fix returned CONDITIONAL, and one of
  the 4 WARNINGs is W-2: `copy_with_backup()` applied `resolve_if_symlink()` at the
  directory level (whole `agents` dir as a symlink) but not at the file level. So a setup
  where the 5 agent files are each individually symlinked to dotfiles real files (the
  directory itself being real) still had `rm -f "$dst"` unconditionally destroy the symlink
  and replace it with a plain file — even when content was identical, with no backup at all.
  KO: 이전 critic 검증이 `install.sh --global` 에 미해결 4건을 남겼다(W3, W4, W5, N4;
  `.claude/harness-facts.md` 의 "미완 4번"). `~/.claude/agents` 나 `~/.claude/CLAUDE.md` 가
  심링크(dotfiles 구성)면 `cp -R`/`mv` 가 심링크를 조용히 실파일/실디렉터리로 대체하거나(W4)
  심링크 자신만 백업하고 그 대상 내용은 못 담았다(W3). `python3` 사전 확인이 없어 없는 머신은
  파일이 이미 복사된 뒤에 맨 `command not found` 로 죽었다(W5). 그리고 아무것도 안 바뀌었어도
  재실행마다 새 `.bak-<epoch>` 를 만들었다(N4).
  이 1차 수정에 대한 Critic(opus) 재검증이 CONDITIONAL 을 냈고, WARNING 4건 중 하나가
  W-2 다: `copy_with_backup()` 은 `resolve_if_symlink()` 를 디렉터리 단위(`agents` 전체가
  심링크인 경우)에는 적용했지만 파일 단위에는 적용하지 않았다. 그래서 에이전트 5개를
  각각 dotfiles 실파일로 개별 심링크한 구성(디렉터리 자체는 실디렉터리)에서는 내용이
  같아도 `rm -f "$dst"` 가 심링크를 무조건 지우고 실파일로 대체했다 — 백업조차 없이.
- 결정 (Decision):
  EN: (1) Follow symlinks (D1). `resolve_if_symlink()` leaves a non-symlink path unchanged, resolves
  a live symlink to its physical target via `python3 -c 'import os,sys;print(os.path.realpath(...))'`,
  and exits 1 on a dangling one before touching anything. Applied to both `global_claude` and
  `global_agents_dir` right after assignment, before any `mkdir -p`/backup, in both
  `do_install_global` and `do_uninstall_global`. `~/.claude` itself being a symlink is out of scope.
  (2) `require_python3()` (D2), shaped exactly like `require_jq` (same file, `command -v` check +
  two `log` lines + `exit 1`), called as the literal first statement of `do_install_global` and
  `do_uninstall_global` — before any `mkdir -p` or backup. (3) Skip no-op backups (part of the same
  change, extending N4's existing per-file `cmp -s` pattern from `copy_with_backup`): the
  directory-level `agents` backup is now gated by a new `agents_dir_unchanged()` predicate (5×
  `cmp -s` against source, not `diff -r` — `diff -r` always reports a difference here because the
  target directory can hold the user's own extra agent files that the source never has), and the
  `CLAUDE.md` backup is moved to immediately before the `mv` that mutates it, gated by
  `! cmp -s "$merged" "$global_claude"`. (4) The 3 backups already on this machine
  (`CLAUDE.md.bak-1785688294`, `agents.bak-1785688294`, `agents.bak-2026-08-02`) are left in place —
  no automated cleanup was added (D4). All of this is covered by a new 10-case
  `harness/tests/test_install_global.sh`, isolated entirely via `HOME` overrides from `mktemp -d`;
  it never touches the real `$HOME`.
  (5) The W-2 fix: `copy_with_backup()` itself resolves `dst` via `resolve_if_symlink()` first
  (reusing D1's existing function, not a new idiom). So even when the target is an individual
  file symlink (directory itself real, but each of the 5 files individually routed to a
  dotfiles real file), the write lands on the physical path and the symlink itself is never
  removed. This path is also crossed by project-install's (`install.sh <target>`)
  `copy_with_backup` calls, but that `dst` is a file the installer itself created, so unless
  the user manually symlinked it `resolve_if_symlink()` passes through unchanged (byte-identical
  to before for the non-symlink case) — not a regression. **Where the backup lands**: in a
  symlinked setup, `<dst>.bak-<epoch>` is created next to the *resolved physical path*, i.e.
  inside the user's dotfiles directory, not next to the symlink — not silent (the full path is
  printed via `log`). Since dotfiles setups are typically their own git repo, a subsequent
  `git add -A` can sweep the whole `agents.bak-<epoch>/` (or `<file>.bak-<epoch>`) into a commit
  — an implication worth noting when the user commits their dotfiles repo. 2 new cases (10, 11)
  verify this, bringing the total to 12.
  KO: (1) 심링크를 따라간다(D1). `resolve_if_symlink()` 는 심링크가 아닌 경로는 그대로 두고,
  살아있는 심링크는 `python3 -c 'import os,sys;print(os.path.realpath(...))'` 로 물리 경로를 구해
  풀며, 끊긴 심링크면 아무것도 건드리기 전에 exit 1 한다. `global_claude` · `global_agents_dir`
  양쪽 모두 대입 직후, `mkdir -p`/백업보다 앞에서 `do_install_global` 과 `do_uninstall_global`
  둘 다에 적용했다. `~/.claude` 디렉터리 자신이 심링크인 경우는 범위 밖이다.
  (2) `require_python3()`(D2) 를 같은 파일의 `require_jq` 와 정확히 같은 형태(`command -v` 확인 +
  `log` 두 줄 + `exit 1`)로 만들어, `do_install_global` 과 `do_uninstall_global` 각각의 첫
  실행문 — `mkdir -p` 나 백업보다 앞 — 으로 호출한다. (3) 무변화 백업을 만들지 않는다(같은
  변경의 일부, N4 를 `copy_with_backup` 의 기존 파일별 `cmp -s` 패턴으로 확장): 디렉터리 단위
  `agents` 백업은 새 `agents_dir_unchanged()` 술어(소스 대비 `cmp -s` 5회, `diff -r` 아님 —
  `diff -r` 은 여기서 항상 다르다고 답한다: 대상 디렉터리엔 사용자 자신의 다른 에이전트 파일이
  있을 수 있고 소스에는 정확히 5개뿐이기 때문)로 감쌌고, `CLAUDE.md` 백업은 그것을 변형하는
  `mv` 직전으로 옮겨 `! cmp -s "$merged" "$global_claude"` 로 감쌌다. (4) 이 머신에 이미 쌓인
  백업 3개(`CLAUDE.md.bak-1785688294`, `agents.bak-1785688294`, `agents.bak-2026-08-02`)는 그대로
  둔다 — 자동 정리는 추가하지 않았다(D4). 이 전부를 신규 10케이스
  `harness/tests/test_install_global.sh` 가 덮는다 — `mktemp -d` 의 `HOME` 오버라이드로만
  격리하며 실제 `$HOME` 은 절대 건드리지 않는다.
  (5) W-2 수정: `copy_with_backup()` 자체가 `dst` 를 `resolve_if_symlink()` 로 먼저 해석한다
  (새 관용구가 아니라 D1 의 기존 함수 재사용). 그래서 대상이 개별 파일 심링크여도(디렉터리
  자체는 실디렉터리인 채로 파일 5개가 각각 dotfiles 로 흘러가는 구성 포함) 쓰기는 물리
  경로에 떨어지고 심링크 자신은 지워지지 않는다. 이 경로가 프로젝트 설치(`install.sh
  <target>`)의 `copy_with_backup` 호출도 함께 지나가지만, 그 경로의 `dst` 는 설치기가 직접
  만든 실파일이라 심링크가 아닌 한 `resolve_if_symlink()` 는 그대로 통과하므로(non-symlink
  경로는 오늘과 바이트 동일) 회귀가 아니다. **백업이 생기는 위치**: 심링크 구성에서는
  `<dst>.bak-<epoch>` 가 심링크 경로가 아니라 **해석된 물리 경로 옆**, 즉 사용자 dotfiles
  디렉터리 안에 생긴다 — 조용하지 않다(전체 경로가 `log` 에 찍힌다). dotfiles 는 보통 그
  자체가 git 저장소이므로, 다음 `git add -A` 한 번에 `agents.bak-<epoch>/`(또는
  `<file>.bak-<epoch>`)가 통째로 커밋될 수 있다 — 사용자가 dotfiles 저장소를 커밋할 때
  유의해야 하는 함의다. 신규 2케이스(10·11)로 이것을 검증한다 — 총 12개가 된다.
- 대안·기각 (Alternatives · Rejected):
  EN: Abort the install instead of following a live symlink — rejected (D1). A user who put
  `~/.claude/agents` or `~/.claude/CLAUDE.md` under a dotfiles repo did so deliberately to route
  content through it; aborting would make the installer unusable for that (arguably more careful)
  setup, while a dangling symlink still aborts since the user's config is already broken there.
  Using `readlink -f` instead of the `python3` one-liner — rejected: not present on older macOS,
  and `python3` is already a guaranteed dependency after the W5 fix. Using `diff -r` for the
  directory no-op check — rejected (D3): it answers the wrong question, since the target directory
  routinely holds files the source doesn't.
  KO: 살아있는 심링크를 따라가는 대신 설치를 중단하는 안 — 기각(D1). `~/.claude/agents` 나
  `~/.claude/CLAUDE.md` 를 dotfiles 저장소 아래 둔 사용자는 의도적으로 그렇게 한 것이다 —
  중단하면 그 (오히려 더 신중한) 구성에서 설치기를 못 쓰게 된다. 끊긴 심링크는 사용자 설정이
  이미 깨진 상태이므로 여전히 중단한다. `python3` 한 줄 대신 `readlink -f` 를 쓰는 안 — 기각:
  구형 macOS 에 없고, W5 수정 이후 `python3` 은 이미 보증된 의존성이다. 디렉터리 무변화 확인에
  `diff -r` 을 쓰는 안 — 기각(D3): 틀린 질문에 답한다. 대상 디렉터리에는 소스에 없는 사용자
  자신의 파일이 늘 있을 수 있기 때문이다.
- 사유 (Rationale):
  EN: All three fixes share one principle: the installer must never silently destroy or
  misrepresent something the user already had, and must not create side effects (files, backups)
  it cannot justify. Symlink resolution keeps a dotfiles-managed config intact instead of quietly
  replacing it. The upfront `python3` check turns a mid-install crash into a clean no-op abort.
  Skipping no-op backups keeps `.bak-*` a meaningful signal ("something changed here") instead of
  accumulating on every run regardless of content.
  KO: 세 수정 모두 하나의 원칙을 공유한다 — 설치기는 사용자가 이미 가진 것을 조용히 파괴하거나
  왜곡해서는 안 되고, 정당화할 수 없는 부작용(파일, 백업)을 만들어서도 안 된다. 심링크 해석은
  dotfiles 로 관리되는 설정을 조용히 대체하지 않고 그대로 지킨다. `python3` 사전 확인은 설치
  중간 크래시를 깔끔한 무변화 중단으로 바꾼다. 무변화 백업을 건너뛰는 것은 `.bak-*` 를 "여기서
  뭔가 바뀌었다"는 의미 있는 신호로 유지한다 — 내용과 무관하게 매 실행 쌓이는 대신.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect) 을 Maker 가 구현
- 연결 (Links): `harness/install.sh` · `harness/tests/test_install_global.sh` · `harness/CORE.md` ·
  `.claude/harness-facts.md`

## D-008 · Make the orchestrator hand over what it knows, and add the verification axis that catches dead ends / 오케스트레이터가 아는 것을 넘기게 강제하고, 막다른 길을 잡는 검증 축을 만든다 — 2026-08-05

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: In one session the harness failed in both directions at once. It blocked its own sanctioned
  route — approval was scoped to a single turn, so the moment the user said anything between
  approving a plan and spawning the maker, writing (budget spent) and delegating (approval gone)
  were both impossible and the only escape was switching the gate off. And it failed to block the
  waste it existed for: three makers burned twelve minutes re-deriving facts a scout had already
  measured, because those facts lived only in the orchestrator's context and the 40-line report cap
  had cut them. Neither was a rule violation. `CORE.md` described the main thread in exactly two
  lines (write budget, bash bypass) and said nothing about briefs, handover, or task size.
  KO: 한 세션에서 하네스가 두 방향으로 동시에 실패했다. 자기가 지정한 경로를 스스로 막았다 —
  승인이 한 턴만 유효해서, 계획 승인과 maker 스폰 사이에 사용자가 한 마디만 하면 쓰기도(예산
  소진) 위임도(승인 소실) 불가능해지고 빠져나갈 길은 게이트를 끄는 것뿐이었다. 동시에 존재
  이유인 낭비는 못 막았다 — Maker 셋이 Scout 가 이미 측정한 사실을 다시 캐느라 12분을 태웠다.
  그 사실이 오케스트레이터 컨텍스트에만 있었고 40줄 보고 제한이 그것을 잘라냈기 때문이다.
  둘 다 규칙 위반이 아니었다. `CORE.md` 는 메인 스레드를 딱 두 줄(쓰기 예산·Bash 우회)로만
  규정했고 브리프·인수인계·작업 크기에 대해서는 아무 말이 없었다.
- 결정 (Decision):
  EN: (1) Handoff gate — `기계`: spawning `architect` or `maker` is denied when the brief names no
  file that exists. A hook cannot judge a brief's quality, but it can see that nothing was handed
  over, which is the cheap failure. (2) Per-agent tool-call metric — `관측` only: record `agent_id`
  so calls attribute to one subagent instead of summing per (session, role). No threshold is set;
  the data to derive one does not exist yet. (3) An end-to-end test of the sanctioned route.
  (4) Two meta-tests: a test asserting a prohibition must state why, and every numeric threshold in
  `DEFAULTS` must be explained in `CORE.md`. (5) Reports keep the 40-line cap but must write the
  overflow to a file and cite its path.
  KO: (1) 인수인계 게이트 — `기계`: 브리프가 실재하는 파일을 하나도 안 가리키면 `architect` ·
  `maker` 스폰을 차단한다. 훅은 브리프의 품질은 못 보지만 아무것도 안 넘긴 것은 볼 수 있고,
  그것이 가장 싼 실패다. (2) 에이전트별 툴 호출 계측 — `관측` 만: `agent_id` 를 남겨 호출이
  (세션, 역할) 합산이 아니라 한 서브에이전트에 귀속되게 한다. 문턱은 만들지 않는다 — 도출할
  데이터가 아직 없다. (3) 규정된 경로의 관통 테스트. (4) 메타 테스트 둘 — 금지를 단언하는
  테스트는 이유를 적어야 하고, `DEFAULTS` 의 수치 문턱은 전부 `CORE.md` 에 설명돼야 한다.
  (5) 보고는 40줄 제한을 유지하되 넘치는 상세를 파일로 남기고 경로를 적는다.
- 기각안 (Rejected):
  EN: Enforcing the subagent's first tool call to be a Read of the cited file — rejected: the hook
  would have to remember the cited path per `agent_id`, and that state file becomes another loss
  point of exactly the kind this entry is fixing. A no-output threshold ("block after N reads with
  no write") — rejected for now: the only measurement available says a working maker's first write
  lands on call 3–4, and the failed makers' calls could not be separated from it. Inventing N is
  the same mistake as the unjustified two-file limit. Deleting the 60 bash regression checks —
  rejected after inspection: they are not duplicates, each guards a distinct regex path, and they
  caught the redirect-regex rewrite in this very change.
  KO: 서브에이전트의 첫 툴 호출을 인용 파일 Read 로 강제하는 안 — 기각: 훅이 `agent_id` 별로
  인용 경로를 기억해야 하고, 그 상태 파일이 바로 이 항목이 고치는 종류의 유실 지점이 하나 더
  생긴다. 무산출 문턱("쓰기 없이 N회면 차단") — 지금은 기각: 가진 측정은 "일하는 Maker 의 첫
  쓰기는 3~4번째 호출"뿐이고 헛돈 Maker 의 호출은 분리되지 않았다. N 을 지어내는 것은 근거
  없던 2개 제한과 같은 잘못이다. Bash 회귀 60건 삭제 — 확인 후 기각: 중복이 아니라 각각 다른
  정규식 경로를 지키며, 바로 이 변경의 리다이렉트 정규식 재작성을 잡아냈다.
- 사유 (Rationale):
  EN: A rule the hooks cannot see is advice, and advice was not followed — that is the whole reason
  this harness exists. So the orchestrator's obligations had to be expressed at the only boundary a
  hook observes: the spawn call. Symmetrically, the reason the dead end survived 152 passing tests
  is that every one of them asked "is this blocked here?" and none asked "does the sanctioned route
  reach the end?" A suite with only the first axis cannot distinguish a working gate from a
  paralysed one. `test_approval_does_not_survive_the_turn` passed for weeks while guarding the
  defect, which is why a prohibition now has to state its reason.
  KO: 훅이 볼 수 없는 규칙은 `조언` 이고, `조언` 은 지켜지지 않았다 — 이 하네스가 존재하는
  이유가 바로 그것이다. 그래서 오케스트레이터의 의무는 훅이 관측하는 유일한 경계, 즉 스폰
  호출에 걸어야 했다. 대칭으로, 그 막다른 길이 152개 통과 테스트를 뚫고 살아남은 이유는 전부가
  "여기서 막히는가"만 묻고 "규정된 경로가 끝까지 가는가"는 아무도 안 물었기 때문이다. 첫 번째
  축만 가진 슈트는 작동하는 게이트와 마비된 게이트를 구분하지 못한다.
  `test_approval_does_not_survive_the_turn` 이 결함을 지키며 몇 주를 통과했고, 그래서 이제
  금지에는 이유를 적어야 한다.
- 정정 (Correction):
  EN: D-007's commit message claimed the three-key `harness.json` left `approval_gate` and
  `close_gate` "silently off". That is false, measured: `load_config` seeds `DEFAULTS` first, so a
  missing key resolves to `True` / `["critic"]` / `["maker"]`. The gates were on. The real defect
  was transparency — the file could not tell you which gates were live. The code change stands; the
  stated reason was wrong.
  KO: D-007 의 커밋 메시지는 키 3개짜리 `harness.json` 이 `approval_gate` 와 `close_gate` 를
  "조용히 꺼진 채" 두었다고 적었다. 실측 결과 거짓이다 — `load_config` 가 `DEFAULTS` 를 먼저
  깔아 누락 키는 `True` / `["critic"]` / `["maker"]` 로 채워진다. 게이트는 켜져 있었다. 실제
  결함은 투명성이었다 — 파일만 봐서는 무엇이 켜져 있는지 알 수 없었다. 코드 변경은 유효하고
  적어둔 이유가 틀렸다.
- 결정자 (Decider): 사용자 (User) — 팝업으로 항목별 결정
- 연결 (Links): `harness/hooks/gate.py` · `harness/tests/test_gate.py` · `harness/CORE.md` ·
  `harness/agents/*.md` · `harness/install.sh`

## D-009 · Read the verifier's verdict string at the close gate, instead of trusting that a verifier merely finished / close 게이트가 검증자의 판정 문자열을 읽게 한다 — 끝나기만 하면 된다는 가정을 버린다 — 2026-10-19

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: The close gate only checked whether a verifier subagent had finished, not what it reported.
  A critic that presented a design and never ran, or one that returned FAIL, still satisfied the
  gate — the exact unresolved gap (#3) a critic.md revision (commit `3ea3720`) left behind when it
  split critic into a design-then-approval-then-execution procedure without teaching the hook to
  tell the stages apart.
  KO: close 게이트는 검증자 서브에이전트가 "끝났는지"만 봤고 "뭐라고 했는지"는 보지 않았다.
  설계만 제시하고 실행은 안 한 critic, 또는 FAIL 을 낸 critic 도 게이트를 풀었다 — critic.md 를
  설계→승인→수행 3단으로 바꾼 커밋(`3ea3720`)이 훅에 단계를 구분하는 법을 안 가르친 채 남긴
  미해결 불일치(#3) 그대로였다.
- 결정 (Decision):
  EN: `handle_subagent_stop` now calls the existing `resolve_subagent_jsonl()` to find the
  verifier's run file, and a new `read_verdict()` regex-matches the LAST assistant text block for
  `VERDICT: PASS|CONDITIONAL|FAIL`. Only PASS/CONDITIONAL set `state["verified"]`; FAIL and "no
  verdict line" (design-stage) do not, and `handle_stop`'s block message now names which case it
  is. An unresolvable run file still fails open (`verified-unparsed`) — the critic resolution rate
  is 3/3 in the 26-run sample, but a hook must not assume every future run resolves. A new
  `require_verdict: false` keeps the old "finished = verified" behaviour for an install whose
  `critic.md` has not adopted the VERDICT line.
  KO: `handle_subagent_stop` 이 기존 `resolve_subagent_jsonl()` 로 검증자 런 파일을 찾고, 신규
  `read_verdict()` 가 **마지막** assistant 텍스트 블록에서 `VERDICT: PASS|CONDITIONAL|FAIL` 을
  정규식으로 찾는다. PASS·CONDITIONAL 만 `state["verified"]` 를 켠다 — FAIL 과 "판정 줄 없음"
  (설계 단계)은 안 켠다. `handle_stop` 의 차단 메시지가 이제 어느 경우인지를 밝힌다. 런 파일을
  못 찾으면 그래도 fail-open(`verified-unparsed`) 한다 — 26런 샘플에서 critic 해결률은 3/3 이지만,
  훅이 앞으로 모든 런이 해결된다고 가정할 수는 없다. 신규 `require_verdict: false` 는 `critic.md`
  가 VERDICT 줄을 아직 안 쓰는 설치처에서 "끝나면 검증됨"이던 종전 동작을 유지한다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) Count critic spawns instead of reading text — rejected: cannot distinguish a
  design-stage spawn from an execution spawn. (2) Have the orchestrator record the verdict in
  state itself — rejected: self-certification, the exact failure mode `spawn_gate`'s own comment
  already rejects for approval.
  KO: (1) 텍스트를 읽는 대신 critic 스폰 횟수를 세는 안 — 기각: 설계 스폰과 수행 스폰을 구분하지
  못한다. (2) 오케스트레이터가 직접 판정을 state 에 기록하는 안 — 기각: 자기 인증이다 — `spawn_gate`
  의 주석이 승인에 대해 이미 같은 이유로 기각한 설계다.
- 사유 (Rationale):
  EN: A gate that releases on "a verifier ran" rather than "what it found" is advisory dressed as
  enforcement. Reading the verdict string closes exactly the gap the harness's own commit history
  (`3ea3720`) flagged as open.
  KO: "검증자가 돌았다"로 풀리고 "무엇을 찾았는지"로는 안 풀리는 게이트는 조언을 집행처럼
  포장한 것이다. 판정 문자열을 읽는 것이 하네스 자신의 커밋 이력(`3ea3720`)이 미해결로 적어둔
  바로 그 틈을 닫는다.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect) 을 Maker 가 구현
- 연결 (Links): `harness/hooks/gate.py` · `harness/tests/test_gate.py` · `harness/agents/critic.md` ·
  `harness/CORE.md` I3

## D-010 · Let changes with no UI or API close the gate with a verify.sh receipt / 화면·API 없는 변경은 verify.sh 영수증으로 close 게이트를 닫는다 — 2026-10-19

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: `critic.md` only runs two kinds of test — API e2e and browser UI e2e — and refuses code
  review or doc-consistency checks (confirmed 2026-08-10). That left no verifier for the harness's
  own code, docs, and scripts, which have neither a UI nor an API (unresolved gap #4).
  KO: `critic.md` 는 API e2e 와 브라우저 UI e2e 둘만 하고 코드리뷰·문서 대조는 반려한다
  (2026-08-10 확정). 그래서 화면도 API 도 없는 하네스 자신의 코드·문서·스크립트를 검증할
  주체가 없었다(미해결 불일치 #4).
- 결정 (Decision):
  EN: A new setting `verify_commands` (default `[]`) names shell commands a project runs instead
  of an e2e test. A new `harness/tools/verify.sh` runs them in order and writes
  `.claude/state/verify-receipt.json` (`{ts, commands:[{cmd,exit}], all_ok}`). The close gate's new
  `receipt_ok()` accepts the receipt in lieu of a verifier when `all_ok is True` (strict, not
  truthy) and `receipt.ts >= state.last_write_ts` — a stale receipt from an earlier turn cannot
  satisfy a later one. `.claude/state/` is hard-exempted from the product-write gate (both the
  write gate and the bash gate) so the receipt write itself is never blocked.
  KO: 신규 설정 `verify_commands`(기본 `[]`)가 e2e 대신 돌릴 셸 명령을 선언한다. 신규
  `harness/tools/verify.sh` 가 순서대로 돌리고 `.claude/state/verify-receipt.json`
  (`{ts, commands:[{cmd,exit}], all_ok}`)을 쓴다. close 게이트의 신규 `receipt_ok()` 는
  `all_ok` 가 (truthy 전부가 아니라) 글자 그대로 True 이고 `receipt.ts >= state.last_write_ts`
  일 때만 영수증을 검증자 대신으로 받는다 — 이전 턴의 낡은 영수증은 이후 턴을 충족시키지
  못한다. `.claude/state/` 는 산출물 쓰기 게이트(쓰기·bash 양쪽)에서 하드 면제돼, 영수증을 쓰는
  행위 자체가 막히지 않는다.
- 대안·기각 (Alternatives · Rejected):
  EN: (1) A new `auditor` role — rejected: a 6th role adds a standing routing rule and a per-run
  cost (observed critic median 274K new-tokens/700s) for work a shell test already answers. (2)
  Have critic do doc/code review after all — rejected: reverses the user's 2026-08-10 decision.
  (3) Exempt these turns from verification entirely — rejected: the harness's own code would ship
  unverified.
  KO: (1) 신규 `auditor` 역할 — 기각: 6번째 역할은 상시 라우팅 규칙과 런당 비용(critic 중앙값
  274K new-tok/700s 실측)을 셸 테스트가 이미 답하는 일에 더한다. (2) critic 이 결국 문서·코드
  대조를 하게 하는 안 — 기각: 사용자의 2026-08-10 결정을 뒤집는다. (3) 이런 턴을 검증에서 통째로
  면제하는 안 — 기각: 하네스 자신의 코드가 무검증으로 나간다.
- 사유 (Rationale):
  EN: The real verification of a documentation or hook change is "do the tests pass", and that is
  a command, not a person. A receipt makes that command's result observable to the same gate that
  already reads a critic's verdict, without inventing a verifier that cannot run.
  KO: 문서나 훅 변경의 진짜 검증은 "시험이 통과하는가"이고 그것은 사람이 아니라 명령이다.
  영수증은 그 명령의 결과를 critic 판정을 이미 읽는 같은 게이트에서 보이게 하면서, 돌 수 없는
  검증자를 지어내지 않는다.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect) 을 Maker 가 구현
- 연결 (Links): `harness/tools/verify.sh` · `harness/hooks/gate.py` · `.claude/harness.json` ·
  [[D-009]]

## D-011 · Make harness/CORE.md the single normative source and shrink the always-injected block below 5KB / harness/CORE.md 를 유일한 정본으로 삼고 상시 주입 블록을 5KB 아래로 줄인다 — 2026-10-19

- 게이트 (Gate): 검증 (Verification)
- 맥락 (Context):
  EN: The same rules (gate table, role boundaries, machine/advisory split, verification tiers)
  were written three times — in `harness/CORE.md`, the always-injected global block, and
  `README.md` — and two of the four reported inconsistencies (#1 a stale role table, #2 a stale
  pipeline description) came from exactly this triple copy going out of sync. The global block
  alone was 14,160 B (7,691 chars), reloaded on every subagent spawn.
  KO: 같은 규칙(게이트 표·역할 경계·기계/조언 구분·검증 등급)이 `harness/CORE.md`·상시 주입
  전역 블록·`README.md` 세 곳에 중복 서술돼 있었고, 보고된 불일치 4건 중 2건(#1 낡은 역할 표,
  #2 낡은 파이프라인 서술)이 바로 이 3중 복사가 어긋난 데서 왔다. 전역 블록 하나만 14,160B
  (7,691 chars)였고 서브에이전트 스폰마다 다시 실렸다.
- 결정 (Decision):
  EN: `harness/CORE.md` becomes the one normative source (`install.sh`'s `install_files()` already
  copies only it to every installed project, confirmed by inspection). The global block keeps the
  byte-identical 24-line commit convention and replaces everything else with a 1,600-char-class
  behavioural core that defers detail to CORE.md; `README.md`'s gate/role tables are replaced with
  links. `.claude/harness-facts.md` drops its history sections (moved to this log) and keeps only
  project-specific facts the generated session-start summary cannot cover. `gate.py` gains
  `config_summary()`, which generates a <=700B session-start block FROM the live config instead of
  a hand-written one, so the table-drift failure mode cannot recur by construction. A new
  `harness/tests/test_docs_sync.py` checks the role table against `agents/*.md` frontmatter and
  checks that no DEFAULTS key is copied into README/the global block/facts (two inline references
  to `enforce` and `verify_commands` in the global block are the one documented exception —
  cross-references, not a copied key:value table).
  KO: `harness/CORE.md` 가 유일한 정본이 된다(`install.sh` 의 `install_files()` 가 이미 그것만
  모든 설치 프로젝트로 복사한다는 것을 확인했다). 전역 블록은 바이트 동일한 24행 커밋 규약을
  유지하고 나머지는 전부 1,600자대의 행동 핵심으로 바꿔 상세는 CORE.md 에 넘긴다.
  `README.md` 의 게이트·역할 표는 링크로 바뀐다. `.claude/harness-facts.md` 는 이력 절을
  빼고(이 로그로 이관) 생성된 세션 시작 요약이 못 덮는 프로젝트 고유 사실만 남긴다. `gate.py`
  에 `config_summary()` 가 추가돼 손으로 쓰지 않고 **지금 설정에서 생성한** 700B 이하 블록을
  세션 시작에 내보낸다 — 표가 어긋나는 실패 양상이 구조적으로 재발할 수 없다. 신규
  `harness/tests/test_docs_sync.py` 가 역할 표를 `agents/*.md` frontmatter 와 대조하고,
  README·전역 블록·facts 로 DEFAULTS 키가 복사되지 않았는지 본다(전역 블록의 `enforce` ·
  `verify_commands` 인라인 참조 2건만 문서화된 예외다 — key:value 표 복사가 아니라 문장 속
  단일 참조).
- 대안·기각 (Alternatives · Rejected):
  EN: Delete the always-injected block entirely and rely only on the installed hook's generated
  summary — rejected: a project with no harness installed has no hook, and the behavioural core
  (plan before the 3rd file, read fully before a verdict, diff cross-references) must still hold
  there.
  KO: 상시 주입 블록을 통째로 삭제하고 설치된 훅의 생성 요약에만 의존하는 안 — 기각: 하네스가
  없는 프로젝트는 훅이 없고, 행동 핵심(3개째 전 계획·판정 전 통독·전수 대조)은 거기서도
  지켜져야 한다.
- 사유 (Rationale):
  EN: A rule written three times can go stale in two of the three without anyone noticing which
  copy is current. A single normative source plus a generated (not hand-written) session block
  closes that path rather than re-documenting it more carefully.
  KO: 세 번 쓴 규칙은 세 곳 중 두 곳이 낡아도 어느 사본이 최신인지 아무도 모른 채 지나간다.
  단일 정본 + (손으로 안 쓴) 생성 세션 블록은 그 경로를 더 정성껏 다시 적는 게 아니라
  구조적으로 닫는다.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect) 을 Maker 가 구현
- 연결 (Links): `harness/CORE.md` · `harness/global/CLAUDE.harness.md` · `README.md` ·
  `.claude/harness-facts.md` · `harness/tests/test_docs_sync.py` · `harness/hooks/gate.py`

## D-012 · Pin the 2-spawn critic procedure's approval to the orchestrator, keeping the user's approval round-trip at one / critic 2스폰 절차의 승인을 오케스트레이터로 못박아 사용자 승인 왕복을 1회로 유지한다 — 2026-10-19

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: `critic.md`'s 3-stage procedure (present an API e2e design, present a UI scenario, run only
  after approval) names who approves as "부른 쪽" (the caller) but the always-injected block's
  pipeline list still described a 1-spawn critic, an unresolved gap (#2) left by the critic.md
  revision in `3ea3720`.
  KO: `critic.md` 의 3단 절차(API e2e 설계 제시 → UI 시나리오 제시 → 승인 뒤에만 수행)는 승인자를
  "부른 쪽"이라고 적어두는데, 상시 주입 블록의 파이프라인 목록은 여전히 critic 1스폰짜리를
  서술했다 — `3ea3720` 의 critic.md 개정이 남긴 미해결 불일치(#2)다.
- 결정 (Decision):
  EN: "부른 쪽" is read literally as the orchestrator (main session), not the end user — reading
  it as the user would grow the approval round-trip from 1 to 2. The pipeline is now: scout →
  architect → **one user approval** (ExitPlanMode) → maker → verification, where verification is
  either critic's 2 spawns (design, then the orchestrator approves/adjusts scope, then execution
  with a VERDICT line) or, for UI/API-less changes, a `verify.sh` receipt (D-010). A 1-spawn
  shortcut is allowed only when the user-approved plan already contains critic.md's exact e2e
  table/scenario format, the brief cites that plan's path and section, and the brief says "run
  as-is if nothing differs, otherwise present and stop."
  KO: "부른 쪽"은 글자 그대로 오케스트레이터(메인 세션)로 읽는다 — 사용자로 읽으면 승인 왕복이
  1에서 2로 늘어난다. 파이프라인은 scout → architect → **사용자 승인 1회**(ExitPlanMode) →
  maker → 검증이 되고, 검증은 critic 2스폰(설계 → 오케스트레이터가 승인/범위조정 →
  VERDICT 줄을 낸 수행) 또는, 화면·API 가 없는 변경이면 `verify.sh` 영수증(D-010) 중 하나다.
  1스폰 축약은 사용자 승인 계획에 critic.md 의 e2e 표/시나리오 형식이 **그대로** 있고, 브리프가
  그 경로·절 번호를 인용하며, "다르면 제시하고 멈춰라"를 적을 때만 허용한다.
- 대안·기각 (Alternatives · Rejected):
  EN: Read "부른 쪽" as the end user — rejected: doubles the user round-trip the harness exists to
  keep cheap, and the source text says "부른 쪽" (caller), not "사용자" (user).
  KO: "부른 쪽"을 사용자로 읽는 안 — 기각: 하네스가 싸게 지키려는 사용자 왕복을 두 배로
  늘리고, 원문이 "부른 쪽"이라고 썼지 "사용자"라고 쓰지 않았다.
- 사유 (Rationale):
  EN: The pipeline description must match what `critic.md` actually requires, or the next
  orchestrator follows a stale shortcut and either skips the approval critic.md demands or burns
  an extra user round-trip it does not.
  KO: 파이프라인 서술은 `critic.md` 가 실제로 요구하는 것과 맞아야 한다. 안 그러면 다음
  오케스트레이터가 낡은 축약을 따라 critic.md 가 요구하는 승인을 건너뛰거나, 필요 없는
  사용자 왕복을 추가로 태운다.
- 결정자 (Decider): 사용자 (User) — "critic 3단 절차의 '승인'을 누가 하나요?" 에 "오케스트레이터" 로 답함
- 연결 (Links): `harness/agents/critic.md` · `harness/global/CLAUDE.harness.md` · `harness/CORE.md`

## D-013 · Leave the two other installed projects unsynced, and keep require_verdict as the knob that absorbs the gap / 설치된 다른 두 프로젝트는 이번에 동기화하지 않고, require_verdict 를 그 격차를 흡수하는 노브로 둔다 — 2026-10-19

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: `airgap-test-toolchain` carries a `critic.md` and `test_gate.py` already diverged from this
  repo's canonical copies (per Scout's survey), so its critic does not write a VERDICT line. `MyK`
  runs with `enforce: false`, so no hook blocks anything there. Shipping D-009's verdict-reading
  close gate without addressing either would make `airgap-test-toolchain` block up to
  `max_close_blocks` times on every delegated turn until someone notices.
  KO: `airgap-test-toolchain` 은 이미 이 저장소의 정본과 갈라진 `critic.md`·`test_gate.py` 를
  가지고 있어(Scout 조사 기준) 그곳의 critic 은 VERDICT 줄을 쓰지 않는다. `MyK` 는
  `enforce: false` 로 돌아 어떤 훅도 아무것도 막지 않는다. 둘 중 하나도 손대지 않은 채 D-009 의
  판정-읽기 close 게이트를 내보내면, `airgap-test-toolchain` 은 위임된 턴마다 누군가 알아챌 때까지
  `max_close_blocks` 회씩 헛차단된다.
- 결정 (Decision):
  EN: Do not touch either installed project in this change — syncing a drifted `critic.md` is that
  project's own approval decision, not this repo's to make unilaterally. Instead, `require_verdict`
  (default `True`) exists specifically so a project whose verifier has not adopted the VERDICT
  line can set it `false` and keep the pre-D-009 "finished = verified" behaviour until it chooses
  to sync.
  KO: 이번 변경에서 두 프로젝트 중 어느 것도 건드리지 않는다 — 갈라진 `critic.md` 를
  동기화하는 것은 그 프로젝트 자신의 승인 사안이지 이 저장소가 일방적으로 정할 일이 아니다.
  대신 `require_verdict`(기본 `True`)를 정확히 이 목적으로 둔다 — 검증자가 VERDICT 줄을 아직
  안 쓰는 프로젝트가 `false` 로 두고 동기화 전까지 D-009 이전의 "끝나면 검증됨" 동작을 유지할
  수 있게.
- 대안·기각 (Alternatives · Rejected):
  EN: Force-sync both projects as part of this change — rejected: out of this repo's authority
  over those projects' own `.claude/` state, and `MyK`'s unsynced `.bak-*` files are untouched for
  the same reason.
  KO: 이번 변경에 두 프로젝트 강제 동기화를 포함하는 안 — 기각: 그 프로젝트들 자신의
  `.claude/` 상태에 대한 권한 밖이다. `MyK` 의 미동기화 `.bak-*` 파일도 같은 이유로 그대로 둔다.
- 사유 (Rationale):
  EN: A knob that absorbs a known, named gap (two specific projects, two specific reasons) is a
  justified knob — the opposite of inventing a threshold with no data behind it.
  KO: 알려지고 이름 붙은 격차(구체적 프로젝트 둘, 구체적 이유 둘)를 흡수하는 노브는 근거 있는
  노브다 — 데이터 없이 문턱을 지어내는 것의 반대다.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect) 을 Maker 가 구현
- 연결 (Links): `.claude/harness.json` · `harness/hooks/gate.py` · [[D-009]]

## D-014 · Block direct writes to verify-receipt.json, and re-sync both installed projects to canonical / 영수증 파일 직접 쓰기를 차단하고, 설치된 두 프로젝트를 정본으로 다시 맞춘다 — 2026-10-19

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: `.claude/state/` is exempt from `is_product()` so `verify.sh`'s own receipt write does not
  trip the bash gate (D-009's I3 close-gate path). That exemption cuts both ways: nothing stopped
  the main thread from Writing `{"all_ok": true}` straight into `verify-receipt.json` and closing
  the turn without ever running a test — self-certification through the very gap meant to let the
  real verifier through. Separately, `airgap-test-toolchain` (installed with `enforce: true`) and
  `MyK` (installed with `enforce: false`) both still carry a pre-D-009 `gate.py`/`critic.md`, which
  D-013 deliberately left unsynced pending a user decision.
  KO: `.claude/state/` 는 `is_product()` 에서 면제다 — `verify.sh` 자신의 영수증 쓰기가 bash
  게이트에 안 걸리게 하려는 것이다(D-009 의 I3 close-게이트 경로). 그 면제는 양날이다 — 메인
  스레드가 `{"all_ok": true}` 를 `verify-receipt.json` 에 바로 Write 해서 테스트 한 번 없이
  턴을 닫는 것을 아무것도 막지 않았다 — 진짜 검증자를 통과시키려던 그 틈으로 자기 인증을 한
  것이다. 별개로, `airgap-test-toolchain`(`enforce: true` 로 설치)과 `MyK`(`enforce: false` 로
  설치) 둘 다 여전히 D-009 이전의 `gate.py`/`critic.md` 를 갖고 있었고, D-013 은 사용자 결정이
  나기 전까지 이를 일부러 동기화하지 않고 두었다.
- 결정 (Decision):
  EN: (1) `gate.py` now denies any Write/Edit/MultiEdit/NotebookEdit or Bash command that names
  `.claude/state/verify-receipt.json` as a target, regardless of actor (main or sub) — only
  running `harness/tools/verify.sh` may produce that file, as a side effect of actually executing
  the verify commands. The deny reason is `receipt-forgery`; `enforce: false` degrades to
  observe-only like every other gate. (2) Both `airgap-test-toolchain` and `MyK` are reinstalled
  from this repo's canonical `gate.py` · `critic.md` · `verify.sh` · `test_gate.py` via
  `harness/install.sh`, which backs up any pre-existing copy to `.bak`. `airgap-test-toolchain`'s
  own `verify_commands` are left empty for that project to set. Neither installed project's
  `.claude/harness.json` is touched, and no commit is made in either — the working tree is left
  for that project's own review.
  KO: (1) `gate.py` 는 이제 `.claude/state/verify-receipt.json` 을 대상으로 지목하는 Write/
  Edit/MultiEdit/NotebookEdit 이나 Bash 명령을, actor(main/sub) 와 무관하게 차단한다 — 그 파일을
  만들 수 있는 것은 `harness/tools/verify.sh` 실행이 실제로 검증 명령을 돌린 부작용뿐이다. 차단
  사유는 `receipt-forgery` 이고, `enforce: false` 면 다른 게이트와 같이 관측만 한다. (2)
  `airgap-test-toolchain` 과 `MyK` 둘 다 `harness/install.sh` 로 이 저장소의 정본
  `gate.py`·`critic.md`·`verify.sh`·`test_gate.py` 를 재설치한다 — 기존 사본은 `.bak` 로
  백업한다. `airgap-test-toolchain` 자신의 `verify_commands` 는 그 프로젝트가 정하도록 비워
  둔다. 두 프로젝트의 `.claude/harness.json` 은 손대지 않고, 어느 쪽에도 커밋하지 않는다 —
  작업 트리를 그 프로젝트 자신의 검토를 위해 그대로 남긴다.
- 대안·기각 (Alternatives · Rejected):
  EN: Leave the receipt write path as-is — rejected: an exemption meant only to let `verify.sh`
  write its own output doubled as a way to forge `all_ok: true` without running anything, which
  defeats I3's entire purpose. Re-syncing only one of the two installed projects, or deferring
  both again as D-013 did — rejected: the user's decision this time is "both, to canonical," not
  a partial or further-deferred sync.
  KO: 영수증 쓰기 경로를 그대로 둔다 — 기각: `verify.sh` 자신의 출력을 쓰게 하려던 면제가
  아무것도 안 돌리고 `all_ok: true` 를 위조하는 수단으로도 쓰여 I3 의 존재 목적을 무력화한다.
  설치된 두 프로젝트 중 하나만 재동기화하거나, D-013 처럼 둘 다 다시 미룬다 — 기각: 이번
  사용자 결정은 "둘 다, 정본으로" 이고 부분·재연기가 아니다.
- 사유 (Rationale):
  EN: A gate whose own exemption can be used to fabricate the evidence it exists to check is not a
  gate. Re-syncing both installed projects now that the user has explicitly decided to is the
  direct application of that decision, not a new judgment call by this repo.
  KO: 자신의 면제가 그 게이트가 확인하려는 증거를 위조하는 데 쓰일 수 있는 게이트는 게이트가
  아니다. 사용자가 명시적으로 결정한 지금, 설치된 두 프로젝트를 재동기화하는 것은 그 결정의
  직접 적용이지 이 저장소가 새로 내리는 판단이 아니다.
- 결정자 (Decider): 사용자 (User) — 승인된 계획(Architect 생략, 기계적 변경 + 카테고리 해당)을
  Maker 가 구현
- 연결 (Links): `harness/hooks/gate.py` · `harness/tests/test_gate.py` · `harness/CORE.md` ·
  `harness/install.sh` · [[D-009]] · [[D-013]]

## D-015 · Re-pick per-role models as aliases and unify critic's verification grade / 역할별 모델을 별칭으로 재선정하고 critic 등급을 하나로 합친다 — 2026-10-19

- 게이트 (Gate): 승인 (Approval)
- 맥락 (Context):
  EN: Per-metrics-run median new_tok was scout 133,681 · architect 99,643 · maker 216,821 ·
  critic 274,438. Prior frontmatter pinned exact model IDs (`claude-sonnet-5`, `claude-opus-5`) and
  the global block/CORE.md §3.5 told callers to re-raise critic to `claude-opus-5` / `effort:
  xhigh` for high-stakes categories (auth, deploy, migration, the harness itself) — but that same
  category list is mostly screen/API-less, so it closes through `verify.sh`, not critic's e2e,
  giving the override no real target to act on. A session execution record from 2026-10-19 also
  showed the pin surviving a generation swap: calls kept hitting `claude-sonnet-5`/`claude-opus-5`
  instead of the newest generation, because the exact ID does not follow a model-family upgrade.
  `~/.claude/settings.json`'s main model `"opus[1m]"` resolves to Opus 5.5 — confirming an alias
  slot already exists and resolves to the current generation without a pinned ID.
  KO: 메트릭 런당 new_tok 중앙값은 scout 133,681 · architect 99,643 · maker 216,821 · critic
  274,438 이었다. 기존 frontmatter 는 정확한 모델 ID(`claude-sonnet-5`, `claude-opus-5`) 를
  고정했고, 전역 블록·CORE.md §3.5 는 고위험 범주(인증·배포·마이그레이션·하네스 자체)에서
  critic 을 `claude-opus-5` / `effort: xhigh` 로 다시 올려 부르라고 했다 — 그런데 그 범주는
  대부분 화면·API 가 없어 critic 의 e2e 가 아니라 `verify.sh` 로 닫히므로, 오버라이드가 작동할
  실제 대상이 없었다. 2026-10-19 세션 실행 기록에서도 세대 교체 후에도 ID 고정이 그대로 남아
  호출이 최신 세대가 아니라 `claude-sonnet-5`/`claude-opus-5` 로 계속 실행되는 것이 확인됐다 —
  정확한 ID 는 모델군 승급을 따라가지 않기 때문이다. `~/.claude/settings.json` 의 메인 모델
  `"opus[1m]"` 은 Opus 5.5 로 풀린다 — 별칭 슬롯이 이미 존재하고, ID 고정 없이도 현재 세대로
  풀린다는 근거다.
- 결정 (Decision):
  EN: (1) Per-role models become generation-agnostic aliases: scout `haiku`/`low`, architect
  `opus`/`high`, maker `sonnet`/`medium`, referee `sonnet`/`medium`. (2) Critic collapses to a
  single grade — `sonnet`/`high`, frontmatter value only, never raised at call time; CORE.md §3.5
  and the global block's override bullet are deleted. (3) `test_docs_sync.py` gains two checks:
  all five agents/*.md `model:` values are in `{haiku, sonnet, opus, inherit}`, and
  `claude-(opus|sonnet|haiku|fable)-[0-9]` has zero matches across CORE.md, the global block,
  agents/*.md, and README.md (docs/DECISIONS.md excluded as history).
  KO: (1) 역할별 모델을 세대 교체에 안 걸리는 별칭으로 바꾼다 — scout `haiku`/`low`, architect
  `opus`/`high`, maker `sonnet`/`medium`, referee `sonnet`/`medium`. (2) critic 등급을 하나로
  합친다 — `sonnet`/`high`, frontmatter 값만 쓰고 호출 시점에 올리지 않는다. CORE.md §3.5 와
  전역 블록의 오버라이드 불릿을 삭제한다. (3) `test_docs_sync.py` 에 검사 둘을 추가한다 — 다섯
  agents/*.md 의 `model:` 값이 전부 `{haiku, sonnet, opus, inherit}` 안에 있는지, 그리고
  `claude-(opus|sonnet|haiku|fable)-[0-9]` 가 CORE.md·전역 블록·agents/*.md·README.md 전체에서
  0건인지(docs/DECISIONS.md 는 이력이라 제외).
- 대안·기각 (Alternatives · Rejected):
  EN: Keep exact model IDs and just update them by hand on each generation swap — rejected: that
  is exactly the failure mode the 2026-10-19 session record showed, a manual step that was
  skipped. Keep the critic override but narrow its trigger list to only categories that actually
  have a screen/API — rejected: the categories named (harness, build.sh, CI, git hook) are
  screen/API-less by definition, so a narrower list would be empty and the override would still
  have no target. Measure maker's `effort: medium` before adopting it — rejected for this round:
  the user's approved decision ("제안안") adopted it directly; effort impact stays unmeasured and
  is noted here rather than blocking the change.
  KO: 정확한 모델 ID 를 유지하고 세대 교체마다 손으로 바꾸기로 한다 — 기각: 그게 바로
  2026-10-19 세션 기록이 보여준 실패 양상이다 — 손으로 할 단계가 생략됐다. critic 오버라이드를
  유지하되 트리거 목록을 실제로 화면·API 가 있는 범주로만 좁힌다 — 기각: 지목된 범주(하네스·
  build.sh·CI·git hook) 는 정의상 화면·API 가 없어 좁힌 목록이 비게 되고 오버라이드는 여전히
  대상이 없다. maker 의 `effort: medium` 을 채택 전에 실측한다 — 이번 회차는 기각: 사용자가
  승인한 결정("제안안")을 그대로 채택했고, effort 영향은 미측정 상태로 여기 기록해 두되 변경을
  막는 근거로 쓰지 않는다.
- 사유 (Rationale):
  EN: Sonnet-5.5 pricing is the $2/$10 per-1M-tokens baseline (relative cost 1); haiku-5.5 is
  $0.10/$0.50 (over $0.50/$2.50 past a 100K-token prompt) and opus-5.5 is $4/$20, versus the prior
  opus-5 pin at $5/$25. Because each model's input:output price ratio holds regardless of a given
  run's input/output token split, the aliasing plus critic unification holds for one full
  pipeline run (875→698 relative cost, −20%) and for a screen/API-less change that skips critic's
  e2e entirely (875→424, −52%). Collapsing critic to one grade removes the override's dead branch
  (no real target) without losing verification strength, since verify.sh already carries the
  screen/API-less categories.
  KO: Sonnet 5.5 단가는 1M 토큰당 $2/$10 이고 이를 상대비용 1 로 둔다. haiku 5.5 는
  $0.10/$0.50(프롬프트가 100K 를 넘으면 $0.50/$2.50), opus 5.5 는 $4/$20 이다 — 이전에 고정했던
  opus 5 의 $5/$25 보다 낮다. 어느 모델이든 입력:출력 단가 비율이 그 런의 입출력 토큰 비중과
  무관하게 성립하므로, 별칭 전환과 critic 등급 통합을 합치면 파이프라인 1회 전체 상대비용은
  875→698(−20%), critic 의 e2e 를 완전히 건너뛰는 화면·API 없는 변경은 875→424(−52%) 가 된다.
  critic 을 등급 하나로 합치는 것은 검증 강도를 잃는 게 아니라, 작동할 대상이 없던 오버라이드
  죽은 가지를 걷어내는 것이다 — 화면·API 없는 범주는 이미 verify.sh 가 닫고 있었기 때문이다.
- 결정자 (Decider): 사용자 (User) — 팝업으로 승인한 결정("제안안"/"하나로 합친다"/"별칭")을
  Maker 가 구현
- 연결 (Links): `harness/agents/scout.md` · `harness/agents/architect.md` ·
  `harness/agents/maker.md` · `harness/agents/critic.md` · `harness/agents/referee.md` ·
  `harness/CORE.md` · `harness/global/CLAUDE.harness.md` · `harness/tests/test_docs_sync.py` ·
  [[D-013]] · [[D-014]]
