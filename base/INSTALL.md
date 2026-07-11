# 멀티 에이전트 하네스 설치 안내

이 번들은 Scout → Architect → Maker → Critic → Referee 5원형 멀티 에이전트 하네스(스펙:
`base/docs/harness/00-definition.md`~`03-adoption.md`)를 다른 프로젝트에 재현 가능하게 설치한다.
폐쇄망 환경을 전제로 하며, 실행에 필요한 도구는 **bash / python3 / git** 뿐이다(네트워크 접근 없음).

개발자가 아니거나 더 쉬운 설명이 필요하면 [`GUIDE.md`](GUIDE.md)(비개발자용, 상세)를 먼저 본다.

## 요구 사항

- Claude Code (훅을 지원하는 버전)
- bash
- python3
- git (프로젝트 설치 시 `--project`의 대상 경로 검증에 사용)

## 빠른 시작

### 1. 글로벌 층 설치 — 모든 프로젝트가 상속하는 기본값

```bash
bash install-harness.sh --global
```

`~/.claude/agents/{scout,architect,maker,critic,referee}.md`, `~/.claude/settings.json`(기존 설정과
JSON union 병합), `~/.claude/CLAUDE.md`(관리블록 병합)가 배치·병합된다. **훅(`hooks`)은 배선되지
않는다** — 훅은 `$CLAUDE_PROJECT_DIR` 상대경로로 프로젝트 스크립트를 참조하므로 프로젝트 층 전용이며,
글로벌 설치는 `settings.json`의 `hooks` 키를 건드리지 않는다(있던 그대로 둔다). `permissions`(deny
5종 + 범용 allow 11종)는 글로벌에도 병합된다.

### 2. 프로젝트 층 설치 — 특정 저장소에 스펙·훅·상태 디렉토리 추가

```bash
bash install-harness.sh --project /path/to/target-repo
```

대상 경로는 `git rev-parse --show-toplevel`로 실제 저장소 루트인지 검증한다(오탐 방지). 다음이
배치된다:

- `<repo>/docs/harness/{00-definition,01-roles,02-orchestration,03-adoption}.md` — 스펙 4종
- `<repo>/.claude/hooks/{inject-repo-facts,lint-gate}.sh` — 훅 2종 (exec bit 부여)
- `<repo>/.claude/settings.json` — 훅 배선 + deny 5종 + 범용 allow (기존 설정과 JSON union 병합)
- `<repo>/.claude/state/.gitkeep` — 훅 런타임 상태 디렉토리
- `<repo>/docs/DECISIONS.md` — 없으면 스키마 헤더로 시드, 있으면 건드리지 않음
- `<repo>/CLAUDE.md`(루트에 있으면) 또는 `<repo>/.claude/CLAUDE.md`(없으면) — 관리블록 병합

**다음은 자동 생성되지 않는다 — 프로젝트가 직접 채운다** (설치가 자동으로 하면 그 프로젝트를 모르는
채로 사실을 지어내는 것이 되기 때문):

- `<repo>/.claude/agents/_repo-facts.md` — `.claude/agents/` 폴더가 아직 없을 수 있으므로 `mkdir -p`로
  먼저 만든 뒤 `base/templates/_repo-facts.md.template` 를 복사해 §1~§8 플레이스홀더를 실제 값으로
  채운다.
- `<repo>/.claude/agents/{scout,architect,maker,critic}.md` 프로젝트 오버라이드 — 필요한 경우만.
  `base/templates/agent-specialization-stub.md` 의 S0/A0/M0/C0 골격을 각 역할 파일의 "경계" 절과
  "산출물 계약" 절 사이에 붙여넣는다. 오버라이드 없이도 전역 정의로 순차 게이트(Scout→Architect→
  Maker→Critic)는 완전히 동작한다(03-adoption A4 "점진 전환").
- `<repo>/CLAUDE.md`(또는 `.claude/CLAUDE.md`)의 관리블록 안 `{{PROJECT_SPECIFIC_TRIGGER_CATEGORIES}}`
  등 플레이스홀더 — 이 프로젝트 고유의 파이프라인 발동 카테고리를 채운다.
- `<repo>/docs/harness/VERIFY.md` — `base/templates/VERIFY.md.template` 를 복사해 드라이버 태스크를
  채우고 V1~V7 을 실제로 돌려 설치가 의도대로 동작하는지 검증한다(03-adoption A7).

### 3. 옵션

| 플래그 | 동작 |
| --- | --- |
| `--dry-run` | 실제 쓰기 없이 무엇을 할지만 출력. 파일시스템 무변화. |
| `--force` | 채워진 `_repo-facts.md`/오버라이드된 agent 파일도 skip 하지 않고 덮어쓴다(백업은 항상 먼저 뜬다). |
| `--uninstall` | 관리블록(`<!-- HARNESS:BEGIN/END -->` 사이)과 설치 시 새로 만든 스캐폴드 파일을 제거. `.bak-*` 백업은 보존. |

### 4. 설치 후 확인

- 새 Claude Code 세션에서 `/agents` 실행 → scout/architect/maker/critic/referee 가 뜨는지 확인
  (`base/docs/harness/03-adoption.md` A7 "경계 테스트" 참조).
- `_repo-facts.md` 를 채운 뒤 `@agent-architect`에 아무 조사 요청 → 응답 첫 줄에
  `REPO_FACTS_LOADED: yes` 가 뜨는지 확인.
- 멱등성 확인이 필요하면 같은 명령을 한 번 더 실행 — 두 번째 실행은 파일시스템 변화가 없어야 한다.

## 되돌리기

```bash
bash install-harness.sh --uninstall --global
bash install-harness.sh --uninstall --project /path/to/target-repo
```

관리블록 밖의 사용자 본문(CLAUDE.md의 기존 내용, settings.json의 기존 키)은 uninstall 후에도
그대로 남는다. 설치 중 만들어진 `.bak-<타임스탬프>` 백업 파일도 지워지지 않는다 — 필요하면 수동으로
정리한다.

**알려진 한계 — `settings.json` 의 best-effort 역병합**: `--uninstall` 은 `base/settings.harness.json`
에 나열된 항목과 **문자열이 정확히 일치**하는 `permissions.allow`/`deny`/`hooks` 항목을 뺀다(`hooks`
는 `--project` uninstall에만 해당 — `--global` uninstall은 애초에 `hooks`를 추가하지 않으므로
`hooks` 키를 아예 건드리지 않는 no-op이다). 만약
설치 전부터 대상 `settings.json`에 우연히 하네스와 **똑같은 문자열의** 항목(예: `Bash(git status:*)`)이
이미 있었다면, uninstall이 그 항목까지 함께 제거한다(설치가 "새로 추가한 것"과 "이미 있던 것"을
구분하는 별도 기록을 남기지 않기 때문 — union은 정보 손실적 연산이라 완벽한 역연산이 불가능하다).
이런 경우를 대비해 설치 시점에 만들어진 `settings.json.bak-<타임스탬프>` 를 항상 확인 — 필요하면
그 백업에서 정확한 사전 상태를 복원한다.
