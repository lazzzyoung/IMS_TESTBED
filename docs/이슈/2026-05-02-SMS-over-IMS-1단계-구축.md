# 2026-05-02 — SMS over IMS 1단계 구축 메모

## 이번 단계에서 추가한 것

- `smsc` SIP Application Server stub 컨테이너 추가
- IMS DNS zone 에 `smsc.ims.mnc001.mcc001.3gppnetwork.org` A/SRV 레코드 복구
- PyHSS 기본 iFC 에서 `MESSAGE -> SMSC` 라우팅 블록 재활성화
- `.env`, `.env.example` 에 `SMSC_IP` 추가

관련 파일:

- `docker-compose.yml`
- `infrastructure/smsc/Dockerfile`
- `infrastructure/smsc/smsc_server.py`
- `infrastructure/dns/ims_zone`
- `infrastructure/pyhss/default_ifc.xml`
- `.env`
- `.env.example`

## 이번 단계에서 가능한 것

- UE 메시지 앱 또는 IMS 경유 `MESSAGE` 가 S-CSCF 의 iFC 에 의해 SMSC AS 로 라우팅되는지 확인
- SMSC AS 가 SIP `MESSAGE` 를 수신하고 `202 Accepted` 를 응답하는지 확인
- 원본 SIP body / content-type / Call-ID / From / To 를 로그/JSON 파일로 수집

## 아직 안 되는 것

- 실제 peer UE 로 store-and-forward 전달
- RP-DATA 해석 후 정상 SMS 전달 완료
- SMSC DB 적재 / 재전송 / 배달 상태 관리
- MMS / RCS

즉, 이번 단계는 **"SMSC 도달 확인"** 이지 **"완전한 SMS 서비스"** 는 아니다.

## 실험용 컴퓨터에서 실행 순서

1. 최신 코드 반영

```bash
git pull origin main
uv sync
```

2. 새 서비스 빌드

```bash
poe epc-build
```

또는 최소:

```bash
docker compose build smsc dns pyhss
```

3. 코어/IMS 재기동

```bash
poe epc-run
```

4. iFC 및 가입자 재반영

```bash
poe provision
```

5. DNS/SMSC 확인

```bash
docker exec dns getent hosts smsc.ims.mnc001.mcc001.3gppnetwork.org
docker logs smsc --since 2m
```

정상 기대값:

- DNS 에서 `smsc... -> 172.22.0.22`
- `smsc` 컨테이너 로그에 listening 메시지 출력

## 1차 테스트 방법

### A. UE 앱에서 실제 메시지 전송

- UE1 에서 UE2 번호로 문자 앱 전송 시도
- 또는 UE2 에서 UE1 로 전송 시도

현재 기대값:

- 반드시 상대 UE 문자 수신까지는 아니어도 됨
- 대신 `smsc` 컨테이너에 `MESSAGE` 수신 흔적이 남아야 함

확인 명령:

```bash
docker logs smsc --since 5m
ls -1 infrastructure/smsc/logs
```

### B. 수신 파일 확인

`infrastructure/smsc/logs/*.json` 에 아래 정보가 저장된다.

- method
- uri
- from
- to
- call_id
- cseq
- content_type
- body
- body_hex
- sms_parse (best-effort 주소 후보 파싱)

## 성공 판단 기준

1차 성공:

- UE 가 IMS REGISTER 유지
- 문자 앱 전송 시 `smsc` 컨테이너에 `MESSAGE` 수신 로그가 생김
- `logs/*.json` 파일이 생성됨
- `202 Accepted` 응답이 반환됨

2차 성공(다음 단계):

- 수신한 메시지를 상대 UE 방향으로 재송신
- 상대 UE 앱/UI 에 실제 표시

## 다음 단계 예정

1. `smsc` 컨테이너 수신 확인
2. RP-DATA / content-type 실제 형태 분석
3. 최소 store-and-forward 구현
4. UE2 방향 재송신 로직 추가
