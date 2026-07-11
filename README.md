# agent-harness — 멀티 에이전트 하네스 (독립 배포판)

**하네스**란 에이전트(모델) 한 세션을 감싸, 작업을 **수행·검증·재현 가능**하게 만드는 실행 골격이다.
단일 세션은 자기 검증 불가·역할 혼재·컨텍스트 한계라는 세 문제에 부딪히는데, 이 저장소가 정의하는
하네스는 이를 더 똑똑한 모델이 아니라 **구조**로 푼다: 만드는 역할과 검증하는 역할을 분리하고,
역할마다 책임·권한·경계를 고정하고, 필요하면 작업을 여러 인스턴스로 쪼갠다. 경계는 요구 이해부터
릴리스 노트 작성까지이며, 실제 배포·운영 실행은 명시적으로 하네스 밖이다. 자세한 정의는
[`base/docs/harness/00-definition.md`](base/docs/harness/00-definition.md) 참조.

## 5 역할

| 역할 | 요약 |
| --- | --- |
| **Scout** | 코드베이스·문서를 조사해 사실 지도를 만든다. 판단·권고·파일 수정 금지 (read-only). |
| **Architect** | Scout의 사실 지도를 바탕으로 실행 계획을 세운다. 코드 작성·파일 수정 금지 (read-only). |
| **Maker** | 승인된 계획을 코드 변경으로 옮긴다. 하네스에서 write 권한을 가진 유일한 역할. |
| **Critic** | Maker의 변경을 검증하고 판정한다. 코드 수정 금지, 발견·판정·보고만. 자기가 만든 변경은 검증하지 않는다. |
| **Referee** | 팬아웃(Critic ×N)·분할-정복(Maker ×M) 패턴에서 여러 산출물을 종합한다. 새 작업·새 코드 생성 금지. |

불변식: **write는 오직 Maker만** 한다. 자기 산출물을 자기가 최종 검증하지 않는다(Maker ≠ Critic).
게이트 없는 상태 전이는 없다. 각 역할의 상세 정의·산출물 계약은 [`base/agents/`](base/agents/) 참조.

## 설치

1. 개발자용 간략 안내: [`base/INSTALL.md`](base/INSTALL.md)
2. 비개발자용 상세 안내(단계별 스크린샷 수준): [`base/GUIDE.md`](base/GUIDE.md)

요약하면, 번들을 받은 뒤:

```bash
bash install-harness.sh --global                    # 모든 프로젝트가 상속하는 기본값
bash install-harness.sh --project /path/to/repo      # 특정 저장소에 스펙·훅·상태 디렉토리 추가
```

`--dry-run`으로 실제 쓰기 전에 무엇을 할지 미리 볼 수 있고, `--uninstall`로 되돌릴 수 있다.
폐쇄망 환경을 전제로 하며, 실행에 필요한 도구는 bash / python3 / git 뿐이다(네트워크 접근 없음).

## 빌드

배포용 번들(zip + sha256 매니페스트)은 `package-harness.sh`가 만든다.

```bash
bash package-harness.sh              # build-out/<타임스탬프>/ 에 zip + HARNESS-BUNDLE.md 생성
bash package-harness.sh --dry-run    # 무엇을 만들지만 미리 확인, 산출물 없음
```

이 저장소 자체가 하네스의 단일 정본이므로, 패키저는 모든 소스를 `base/` 아래에서 직접 읽는다.

## 레이아웃

```text
agent-harness/
├── README.md                  이 문서
├── install-harness.sh         받는 쪽 인스톨러 (번들 최상위)
├── package-harness.sh         빌드측 패키저 (이 저장소 전용, 번들에 포함 안 됨)
├── .gitignore                 build-out/ 제외
├── base/                      번들에 포함되는 모든 것 (정본)
│   ├── agents/                scout / architect / maker / critic / referee 5원형
│   ├── docs/harness/          스펙 4문서 (00-definition ~ 03-adoption)
│   ├── hooks/                 inject-repo-facts / lint-gate 훅 2종
│   ├── templates/             _repo-facts / agent 특화 / DECISIONS / VERIFY / CLAUDE 템플릿
│   ├── settings.harness.json  훅 배선 + 권한(permissions) 기본값
│   ├── GUIDE.md                받는 쪽 설치 안내 (비개발자용, 번들 최상위로 승격)
│   └── INSTALL.md              받는 쪽 설치 안내 (개발자용, 번들 최상위로 승격)
└── docs/
    └── DECISIONS.md            이 저장소 자체의 의사결정 로그
```

## 출처

이 저장소는 어느 사설 프로젝트(비공개 저장소) 안에서 구축·검증된 하네스를 독립 정본으로 추출한
것이다. 배경은 [`docs/DECISIONS.md`](docs/DECISIONS.md)의 D-001 참조.
