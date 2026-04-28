# AGENTS.md

이 문서는 이 저장소에서 Codex가 계속 참고할 운영 메모다.

## 1. 현재까지 확정된 작업 맥락

- 현재 저장소는 `Open5GS EPC + Kamailio IMS + PyHSS + srsENB + SIP fuzzing tool` 구조다.
- 단기 목표는 최종 실습 전체를 한 번에 끝내는 것이 아니라, 먼저 아래 범위를 안정화하는 것이다.
  - 실제 SIM 프로그래밍
  - HSS / PyHSS 가입자 반영
  - SDR 기반 eNB attach
  - IMS REGISTER 확인
  - baseline INVITE 수신 검증
- 최종 실습 목표는 아래와 같지만, 현재는 아직 전부 구현된 상태가 아니다.
  - SMS, MMS, RCS 메시지 패킷 분석
  - IMS 로그 추출 및 분석
  - iPhone iMessage, Galaxy 메시지플러스 사용/미사용 비교

## 2. 현재 저장소 기준 결론

- 지금 바로 가능한 범위:
  - SDR eNB attach
  - Open5GS HSS / PyHSS 가입자 반영
  - IMS REGISTER 확인
  - real-ue-direct baseline INVITE 검증
  - pcap / ADB / IMS 로그 수집
  - SIP MESSAGE 패킷을 UE 파서까지 보내는 실험
- 아직 별도 보강이 필요한 범위:
  - 실제 SMSC 기반 SMS over IMS
  - MMS 인프라
  - RCS 인프라
  - iMessage / 메시지플러스 비교 실험 자동화

## 3. 중요한 기술 메모

- `docker-compose.yml`에는 현재 `SMS(SMSC)` 컨테이너가 없다.
- `infrastructure/pyhss/default_ifc.xml`에서도 MESSAGE -> SMSC 라우팅이 비활성화돼 있다.
- 따라서 현재는 "정상 SMS 서비스"보다 "SIP MESSAGE가 단말 파서까지 도달하는지" 확인하는 단계로 보는 것이 맞다.
- 실제 SIM 값이 오면 `.env`의 `UE1_IMSI`, `UE1_KI`, `UE1_OPC`, `UE1_AMF`, `UE1_MSISDN`를 우선 반영한다.
- 실제 PLMN이 `001/01`이 아니면 `.env`의 `MCC`, `MNC`, `VMF_IMS_DOMAIN`과 eNB 설정값도 같이 수정해야 한다.
- 실험은 로컬 macOS IDE가 아니라 Ubuntu + Docker + SDR가 연결된 실험용 컴퓨터에서 수행해야 한다.

## 4. 우선 참고 문서

- `docs/REAL_SIM_ATTACH_CHECKLIST.md`
- `docs/A31_REAL_UE_GUIDE.md`
- `docs/SERVER_SETUP.md`
- `docs/이슈/A31-real-ue-direct-시스템-요구사항.md`

## 5. 실험용 컴퓨터에서의 기본 진행 순서

1. `uv sync`
2. 필요 시 `poe epc-build`
3. `poe epc-run`
4. `poe enb-run`
5. `poe net-setup`
6. 실제 SIM 값으로 `.env` 수정
7. 외부 USIM 프로그래밍 도구로 SIM 기록
8. `poe provision`
9. 단말에 SIM 삽입 후 VoLTE 활성화
10. 단말 IMS 재등록 유도
11. `docker exec pcscf ip xfrm state` 확인
12. baseline INVITE 1회 검증

## 6. 커밋 컨벤션

기본 원칙:

- Git flow 스타일을 참고하되, 커밋 메시지 prefix는 "현재 작업 브랜치 이름"을 앞에 둔다.
- 형식은 아래 중 하나를 사용한다.

```text
<branch>: <작업내용>
<branch>/<topic>: <작업내용>
```

예시:

```text
dev: 작업내용1
feat/a: 작업내용2
release/1.0.0: 배포 준비
hotfix/login: 로그인 예외 수정
main: 문서 및 운영 메모 정리
```

세부 규칙:

- `branch`는 실제 체크아웃된 브랜치명을 그대로 사용한다.
- `작업내용`은 한 줄 요약으로 작성한다.
- 가능하면 "무엇을 바꿨는지"가 드러나게 쓴다.
- 여러 성격이 섞이면 가장 대표 작업 1개 기준으로 쓴다.

## 7. Codex 커밋/푸시 작업 규칙

- 사용자가 명시적으로 요청하면 Codex가 커밋과 푸시까지 수행한다.
- 사용자 변경으로 보이는 파일 삭제/수정은 명시 요청 없으면 커밋에 포함하지 않는다.
- 커밋 전에는 `git status`로 변경 범위를 확인한다.
- 커밋 메시지는 반드시 위 커밋 컨벤션을 따른다.
- 푸시는 현재 브랜치 기준으로 수행한다.
- 예시:
  - 현재 브랜치가 `dev`면 `dev: ...`
  - 현재 브랜치가 `feat/a`면 `feat/a: ...`
  - 현재 브랜치가 `main`이면 `main: ...`

## 8. 이번 세션에서 추가된 산출물

- `docs/REAL_SIM_ATTACH_CHECKLIST.md`
- `AGENTS.md`

