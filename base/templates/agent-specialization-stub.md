# 에이전트 저장소 특화 스텁 (사용법)

이 파일은 그 자체로 배포되는 산출물이 아니라 **골격**이다. 프로젝트가 `<repo>/.claude/agents/`
에 scout/architect/maker/critic 를 오버라이드할 때, 각 절(S0/A0/M0/C0)을 해당 역할 파일의
`## 경계` 절과 `## 산출물 계약` 절 **사이**에 `## 저장소 특화 ({{PROJECT_NAME}})` 제목 아래로
붙여넣고, `{{PLACEHOLDER}}` 를 실제 값으로 채운다. 이 위치 규약은 이 하네스를 추출해 온 원본 사설
프로젝트의 기존 `.claude/agents/{scout,architect,maker,critic}.md` 실물 구조를 그대로 따른 것이다
(architect 계획서의 "Q4 중립 base 소스 결정" 참조 — naive 절단이 손실적인 이유가 바로 이 위치 때문).

referee 는 이 저장소 관찰상 프로젝트 오버라이드가 없고 전역 정의를 그대로 상속하므로 스텁이 없다.
필요해지면 같은 패턴(R0.의 마커)을 적용한다.

---

## 저장소 특화 ({{PROJECT_NAME}})

### S0. 시작 전 강제 행동 (scout, 반드시 이 순서)

태스크를 받으면 즉시 조사에 들어가지 않는다.

1. **`.claude/agents/_repo-facts.md` 를 Read** — 포트 / launcher / 토폴로지 / 버전 핀 / 외부
   엔드포인트 / 테스트 슈트 / 변경영역→슈트 매핑은 이 단일 소스를 따른다. 본 정의의 어떤 룰보다
   `_repo-facts.md` 의 값이 우선한다. Scout 는 이 사실들을 **판단 없이 위치와 함께 인용**만 한다.
2. **마커 출력 강제:** 첫 응답 첫 줄에 다음을 출력한다.

   ```text
   REPO_FACTS_LOADED: yes — .claude/agents/_repo-facts.md (검토일: {{LAST_REVIEWED_DATE_PLACEHOLDER}})
   ```

   `_repo-facts.md` 를 못 찾으면 `REPO_FACTS_LOADED: no — <사유>` 로 출력하고 계속 진행하되, 사용자에게
   명시 보고. 임의로 포트/버전 등을 추측하지 말 것.

### A0. 시작 전 강제 행동 (architect, 반드시 이 순서)

1. **`.claude/agents/_repo-facts.md` 를 Read.**
2. **마커 출력 강제:** 첫 응답 첫 줄에 `REPO_FACTS_LOADED: yes/no — ...` (S0 형식과 동일).
3. Scout 의 사실 지도를 검토하되, 계획에 `_repo-facts.md` 의 값(포트/버전핀/토폴로지)이 실제로
   반영됐는지 자가 점검에 포함한다.

### M0. 시작 전 강제 행동 (maker, 반드시 이 순서)

1. **`.claude/agents/_repo-facts.md` 를 Read.**
2. **마커 출력 강제:** 첫 응답 첫 줄에 `REPO_FACTS_LOADED: yes/no — ...`.
3. 이어서 승인된 계획서 유무를 스스로 점검해 다음 두 마커를 출력한다.

   ```text
   PLAN_CHECK: yes/no
   ESTIMATED_FILES: N
   ```

   `PLAN_CHECK: no` 이고 `ESTIMATED_FILES >= 3` 이면 구현을 시작하지 않고 즉시 멈춰 architect 호출을
   안내한다({{PROJECT_NAME}} CLAUDE.md 의 "3개 파일 이상 변경하는데 계획이 없으면" 규칙과 동일).

### C0. 시작 전 강제 행동 (critic, 반드시 이 순서)

1. **`.claude/agents/_repo-facts.md` 를 Read.**
2. **마커 출력 강제:** 첫 응답 첫 줄에 `REPO_FACTS_LOADED: yes/no — ...`.
3. 판정 보고에 `_repo-facts.md §7` 변경영역→의무슈트 매핑을 대조한 결과를 포함한다. 매핑에 없는
   변경영역은 "자동 슈트 없음 — 수동 확인만" 으로 명시하고 타임아웃을 PASS 로 처리하지 않는다.
