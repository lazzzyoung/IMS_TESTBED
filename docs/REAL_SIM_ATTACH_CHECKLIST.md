# Real SIM Attach Checklist

이 문서는 현재 저장소 기준으로 "실제 SIM 값을 받아서 USIM 프로그래밍 + HSS/PyHSS 반영 + SDR eNB/EPC/IMS attach + IMS baseline 검증"까지 진행하기 위한 체크리스트다.

## 1. 현재 저장소 상태

- `docker-compose.yml`은 Open5GS EPC + Kamailio IMS + PyHSS + P-CSCF 환경을 포함한다.
- `scripts/provision_subscribers.py`는 `.env`의 `UE1_*`, `UE2_*` 값을 읽어 Open5GS HSS와 PyHSS를 동시에 갱신한다.
- `poe enb-run`은 `infrastructure/srsenb/enb.conf`를 사용해 별도 `srsenb` 컨테이너를 실행한다.
- 현재 저장소는 `SMS(SMSC)` 컨테이너가 빠져 있다. 따라서 attach/IMS REGISTER/INVITE baseline은 가능하지만, "실제 SMS over IMS 서비스"는 아직 완성 상태가 아니다.

## 2. 지금 바로 확인할 것

1. 실험은 macOS IDE가 아니라 Ubuntu + Docker + SDR 장비가 연결된 호스트에서 수행해야 한다.
2. SDR 종류가 USRP B210이 아니면 `infrastructure/srsenb/enb.conf`의 `device_name`, `device_args`를 수정해야 한다.
3. 실제 SIM의 PLMN이 `001/01`이 아니면 `.env`의 `MCC`, `MNC`, `VMF_IMS_DOMAIN`과 eNB 설정의 `mcc`, `mnc`, `tac`, `dl_earfcn`을 함께 맞춰야 한다.

## 3. 실제 SIM 값이 오면 채워 넣을 항목

`.env`에서 최소 아래 값들을 실제 SIM 기준으로 바꾼다.

```env
UE1_IMSI=<real_sim_imsi>
UE1_KI=<real_sim_ki>
UE1_OPC=<real_sim_opc>
UE1_AMF=<real_sim_amf_or_8000>
UE1_MSISDN=<real_sim_msisdn>
```

추가로 아래 값들도 실제 실험 서버 기준으로 맞춘다.

```env
VMF_GENERATOR_TARGET_UE_NAME=RealUE
VMF_GENERATOR_VIA_HOST=<ubuntu_host_ip>
VMF_GENERATOR_FROM_HOST=<ubuntu_host_ip>
VMF_GENERATOR_CONTACT_HOST=<ubuntu_host_ip>
VMF_GENERATOR_TO_HOST=172.22.0.21
VMF_GENERATOR_REQUEST_URI_HOST=172.22.0.21
DOCKER_HOST_IP=<ubuntu_host_ip>
```

필요 시 함께 확인할 값:

- `MCC`
- `MNC`
- `TAC`
- `VMF_IMS_DOMAIN`
- `VMF_REAL_UE_PCSCF_IP`
- `VMF_CELL_ID`

## 4. SIM 프로그래밍 전에 받아야 하는 정보

- IMSI
- Ki
- OPC 또는 OP
- AMF
- MSISDN
- SIM 프로그래밍용 ADM/PIN 정보
- 실제 사용할 MCC/MNC
- 단말이 붙을 LTE band / EARFCN 정보

## 5. 실제 진행 순서

1. `uv sync`
2. 필요 시 `poe epc-build`
3. `poe epc-run`
4. `poe enb-run`
5. `poe net-setup`
6. 실제 SIM 값으로 `.env` 수정
7. 외부 USIM 프로그래밍 도구로 SIM 카드에 같은 IMSI/Ki/OPC를 기록
8. `poe provision`
9. 단말에 SIM 삽입 후 VoLTE 활성화
10. 비행기모드 on/off 또는 VoLTE 토글로 IMS 재등록 유도
11. `docker exec pcscf ip xfrm state`로 IMS 등록 여부 확인
12. `docker logs pcscf --since 5m`로 REGISTER 및 Term UE 로그 확인
13. baseline INVITE 1회 실행

## 6. baseline 검증 커맨드

```bash
uv run fuzzer campaign run \
  --mode real-ue-direct \
  --target-msisdn <UE1_MSISDN> \
  --impi <UE1_IMSI> \
  --methods INVITE --layer wire --strategy identity \
  --mt-invite-template a31 \
  --ipsec-mode null \
  --preserve-contact --preserve-via \
  --mt-local-port 15100 \
  --max-cases 1 --timeout 10 --no-process-check
```

기대 결과:

- 단말이 LTE attach + IMS REGISTER 완료
- `pcscf`에 UE 포트 정보가 보임
- 단말에서 수신 UI 또는 벨 확인
- fuzzer 결과가 `normal (180 ...)`

## 7. 현재 바로 가능한 범위

- SDR 기반 eNB attach
- Open5GS HSS / PyHSS 가입자 반영
- IMS REGISTER 확인
- INVITE baseline 검증
- pcap / ADB / IMS 로그 수집
- SIP MESSAGE 패킷을 UE 파서까지 보내는 실험

## 8. 아직 별도 보강이 필요한 범위

- 실제 SMSC 기반 SMS over IMS 서비스
- MMS 인프라
- RCS 인프라
- iPhone iMessage / Galaxy Message+ 비교 실험용 서비스/수집 자동화

현재 `infrastructure/pyhss/default_ifc.xml`에서는 MESSAGE용 SMSC 라우팅이 비활성화되어 있다. 즉, 지금은 "SIP MESSAGE가 UE까지 가는지"는 볼 수 있지만 "정상 SMS 서비스 시맨틱"은 아직 아니다.
