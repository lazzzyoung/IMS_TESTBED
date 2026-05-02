# EPC/eNB Attach Runbook

이 문서는 실험용 컴퓨터에서 기존 Docker 컨테이너를 정리하고, `IMS_TESTBED`의 EPC/IMS/eNB를 다시 띄운 뒤 두 개의 UE가 망에 붙는지 확인하기 위한 실행 절차를 정리한 문서다.

## 1. 목적

오늘 목표는 아래까지만 확인하는 것이다.

- 기존 Docker 컨테이너 충돌 제거
- Open5GS EPC / IMS 컨테이너 재기동
- subscriber provisioning 반영
- SDR eNB 기동
- 두 개의 UE가 LTE/EPC에 attach 되는지 확인
- 가능하면 IMS REGISTER 로그까지 확인

## 2. 사전 조건

- 실험용 컴퓨터에서 작업 중이어야 함
- SDR 장비가 연결되어 있어야 함
- 프로그래밍 완료된 USIM 2장이 준비되어 있어야 함
- 현재 `.env` 기준 가입자 정보:

```env
UE1_IMSI=001010000123528
UE1_MSISDN=111111

UE2_IMSI=001010000123542
UE2_MSISDN=222222
```

## 3. 전체 실행 순서

1. 기존 Docker 컨테이너 전부 정지
2. 정지된 컨테이너 전부 제거
3. 남은 Docker 네트워크 정리
4. 프로젝트 폴더 이동
5. EPC/IMS 컨테이너 기동
6. subscriber provisioning 반영
7. 호스트 라우팅 / sysctl 설정
8. eNB 기동
9. 두 UE에 각각 USIM 삽입
10. MME/HSS/P-CSCF 로그 확인

## 4. 기존 컨테이너 정리

주의:

- 아래 명령은 **실험용 컴퓨터에서 실행 중인 다른 사람 컨테이너도 같이 멈출 수 있다**
- 같이 쓰는 환경이면 사전 공유가 필요하다

실행 중인 컨테이너 전부 정지:

```bash
docker stop $(docker ps -q)
```

정지된 컨테이너 전부 제거:

```bash
docker rm $(docker ps -aq)
```

남은 네트워크 확인:

```bash
docker network ls
```

`docker_open5gs_default`가 남아 있으면 제거:

```bash
docker network rm docker_open5gs_default 2>/dev/null || true
```

정리 결과 확인:

```bash
docker ps -a
```

## 5. 프로젝트 폴더 이동

```bash
cd ~/IMS_TESTBED/IMS_TESTBED
```

경로가 다르면 실제 저장소 경로로 이동하면 된다.

## 6. EPC/IMS 기동

처음 빌드가 안 되어 있거나 이미지 갱신이 필요하면:

```bash
poe epc-build
```

일반 기동:

```bash
poe epc-run
poe epc-status
```

기대 컨테이너:

- `mongo`
- `mysql`
- `hss`
- `mme`
- `sgwc`
- `sgwu`
- `smf`
- `upf`
- `dns`
- `pyhss`
- `icscf`
- `scscf`
- `pcscf`
- `webui`

문제 있으면 실시간 로그:

```bash
poe epc-logs
```

## 7. Subscriber Provisioning

`.env` 기준 subscriber 반영:

```bash
poe provision
```

이 단계에서 기대하는 것:

- Open5GS HSS(MongoDB)에 UE1/UE2 가입자 반영
- PyHSS(MySQL)에 IMS subscriber 반영
- 필요 시 `pyhss` 재시작

## 8. 호스트 네트워크 준비

```bash
poe net-setup
```

확인 포인트:

```bash
sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter net.ipv4.ip_nonlocal_bind
ip route | grep 10.20.20
```

정상 기대값:

- `ip_forward = 1`
- `rp_filter = 0`
- `ip_nonlocal_bind = 1`
- `10.20.20.0/24 via 172.22.0.8` 라우트 존재

## 9. eNB 기동

```bash
poe enb-run
poe enb-logs
```

eNB 로그에서 확인할 것:

- SDR 장비 인식 성공
- MME와 S1 연결 시도
- fatal error 없음

## 10. UE 준비

폰 A:

- USIM: `001010000123528`
- MSISDN: `111111`

폰 B:

- USIM: `001010000123542`
- MSISDN: `222222`

단말 설정:

- 비행기 모드 OFF
- LTE / 셀룰러 ON
- PIN 요청 시 `0000`
- 가능하면 한 번 재부팅 또는 비행기모드 on/off

## 11. LTE Attach 확인

가장 먼저 볼 로그:

```bash
docker logs mme --since 5m
```

같이 보면 좋은 로그:

```bash
docker logs hss --since 5m
docker logs sgwc --since 5m
docker logs sgwu --since 5m
```

기대하는 것:

- IMSI `001010000123528` attach/authentication 로그
- IMSI `001010000123542` attach/authentication 로그
- 인증 실패 없이 EPS attach 완료 흐름

## 12. IMS REGISTER 확인

LTE attach 후 IMS까지 붙는지 확인하려면:

```bash
docker logs pcscf --since 5m
docker logs scscf --since 5m
docker exec pcscf ip xfrm state
```

기대하는 것:

- `REGISTER` 관련 로그
- UE IMS IP/port 정보
- `xfrm state` 생성

## 13. 오늘 기준 성공 조건

오늘 목표 기준으로 아래면 성공이다.

- 두 폰이 셀을 잡음
- `mme` 로그에 두 IMSI attach 흔적이 보임
- 인증 실패 없이 attach가 완료됨
- 가능하면 `pcscf/scscf`에 IMS REGISTER 로그도 보임

## 14. 복붙용 최소 명령 세트

```bash
docker stop $(docker ps -q)
docker rm $(docker ps -aq)
docker network rm docker_open5gs_default 2>/dev/null || true

cd ~/IMS_TESTBED/IMS_TESTBED

poe epc-run
poe provision
poe net-setup
poe enb-run
```

다른 터미널에서 로그 확인:

```bash
docker logs mme --since 5m
docker logs hss --since 5m
docker logs pcscf --since 5m
```

## 15. 실패 시 우선 확인할 것

1. `poe enb-logs`
2. `docker logs mme --since 10m`
3. `docker logs hss --since 10m`
4. `docker logs pcscf --since 10m`
5. SDR 장비 연결 상태
6. 단말의 PIN 입력 / LTE 설정 / 비행기모드 상태
