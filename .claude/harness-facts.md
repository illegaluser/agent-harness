# 하네스 상태 — SessionStart 자동 주입

이 파일은 `harness/hooks/gate.py` 가 매 세션·매 서브에이전트 시작 시, 훅이 생성하는 현재
설정 요약 뒤에 이어붙여 컨텍스트에 넣는다. 그 요약은 손으로 쓰지 않는다 — 설정이 바뀌면
자동으로 갱신된다. **이 파일에는 그 요약이 못 담는, 이 프로젝트에만 있는 사실만 남긴다.**

## 이 프로젝트에만 있는 사실

- 산출물은 코드가 아니라 문서다 — 이 저장소의 산출물은 `docs/**` · `harness/**` 다.
- 전역 설정(`~/.claude/CLAUDE.md` 의 하네스 블록, `~/.claude/agents/` 5개)도 이 저장소가
  정본이다. 손으로 고치지 말고 `harness/global/CLAUDE.harness.md` 와 `harness/agents/` 를
  고친 뒤 아래로 반영한다.

```bash
bash harness/install.sh --global              # 전역 설치·갱신
bash harness/install.sh --global --uninstall  # 전역 제거
bash harness/install.sh <프로젝트경로>          # 대상 프로젝트에 설치
```

## 규칙 본문

[`harness/CORE.md`](../harness/CORE.md) 가 전부다. 규칙마다 등급이 붙어 있다 — 훅이 막는 것과
아무것도 확인하지 않는 것을 섞어 읽으면 안 된다.

## 고칠 때

게이트를 건드리면:

```bash
python3 harness/tests/test_gate.py
```

문서·역할 표를 건드리면:

```bash
python3 harness/tests/test_docs_sync.py
```

양쪽 다 **양방향**을 본다 — 메인을 막는 것과 서브에이전트를 막지 **않는** 것.
한 방향만 보면 "무용한 게이트"와 "마비된 세션"이 둘 다 성공처럼 보인다.

## 이력

지난 결정과 그 근거(버전 확인·심링크 수정·오케스트레이터 불변식 등)는 여기서 뺐다 —
[`docs/DECISIONS.md`](../docs/DECISIONS.md) 를 봐라. 배경은
[`docs/PLAN_HARNESS_REDESIGN.md`](../docs/PLAN_HARNESS_REDESIGN.md) 에 있다.
