# MT-INVITE 템플릿 필드 해설

Samsung Galaxy A31(SM-A315N)이 착신 통화(MT call)로 인식하기 위해 필요한 SIP INVITE 메시지의 각 필드를 설명한다. 이 필드들은 3GPP TS 24.229(IMS call control)에 기반하며, A31의 IMS 앱 레이어가 실제로 검증하는 항목들이다.

---

## Request-Line

```
INVITE sip:{{impi}}@{{ue_ip}}:{{request_uri_port_pc}};alias={{ue_ip}}~{{request_uri_port_ps}}~1 SIP/2.0
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{impi}}` | `001010000123512` | UE의 IMS Private Identity. USIM에 저장된 고유 식별자 |
| `{{ue_ip}}` | `10.20.20.14` (동적) | UE가 EPC로부터 할당받은 IP. 재등록마다 변경 |
| `{{request_uri_port_pc}}` | `9000` (동적) | UE의 IPsec protected client port. REGISTER 시 협상 |
| `{{request_uri_port_ps}}` | `9001` (동적) | UE의 IPsec protected server port |

**역할**: P-CSCF가 UE에게 착신 INVITE를 전달할 때 사용하는 주소. `alias` 파라미터는 UE의 NAT traversal용 다중 포트 식별자(port-c~port-s~transport)이다.

---

## Via

```
Via: SIP/2.0/UDP {{pcscf_ip}}:{{local_port}};branch={{branch}}
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{pcscf_ip}}` | `172.22.0.21` | P-CSCF의 IP 주소 |
| `{{local_port}}` | `15100` (기본값) | 송신 측 UDP 포트. 응답(180 Ringing 등)을 이 포트로 수신 |
| `{{branch}}` | `z9hG4bKvmf` + 랜덤 | SIP 트랜잭션 식별자. `z9hG4bK` 접두사는 RFC 3261 magic cookie |

**역할**: SIP 응답이 돌아올 경로를 지정한다. UE는 180 Ringing을 이 Via의 주소:포트로 보낸다. `local_port`가 xfrm selector의 port-c와 다르면(예: 15100 vs 5100) IPsec ESP를 우회하여 평문 전송된다.

---

## Record-Route (3개)

```
Record-Route: <sip:mo@{{pcscf_ip}}:6101;lr=on;ftag={{from_tag}};rm=8;did=643.7a11>
Record-Route: <sip:mo@172.22.0.20:6060;transport=tcp;r2=on;lr=on;ftag={{from_tag}};did=643.3382>
Record-Route: <sip:mo@172.22.0.20:6060;r2=on;lr=on;ftag={{from_tag}};did=643.3382>
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{pcscf_ip}}` | `172.22.0.21` | P-CSCF IP |
| `{{from_tag}}` | seed 기반 랜덤 | From 헤더의 tag와 동일한 값 |

**역할**: IMS 코어 네트워크의 SIP 프록시 경유 경로를 기록한다. 3개인 이유:
1. **P-CSCF** (172.22.0.21:6101) — UE와 직접 연결되는 프록시
2. **S-CSCF TCP** (172.22.0.20:6060, transport=tcp) — 서빙 CSCF의 TCP 측
3. **S-CSCF UDP** (172.22.0.20:6060) — 서빙 CSCF의 UDP 측

`lr=on`은 loose routing, `r2=on`은 double Record-Route(TCP↔UDP 전환 시 필요), `did`는 Kamailio의 dialog ID이다. A31은 Record-Route가 없거나 불완전하면 INVITE를 무시한다.

---

## From / To

```
From: <sip:{{from_msisdn}}@ims.mnc001.mcc001.3gppnetwork.org>;tag={{from_tag}}
To: "{{to_msisdn}}"<tel:{{to_msisdn}};phone-context=ims.mnc001.mcc001.3gppnetwork.org>
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{from_msisdn}}` | `222222` (기본값) | 발신자 전화번호 (MO측 MSISDN) |
| `{{to_msisdn}}` | `222222` | 착신자 전화번호 (MT측 MSISDN) |
| `{{from_tag}}` | seed 기반 랜덤 | 다이얼로그 식별용 태그 |

**역할**: From은 발신자, To는 착신자를 식별한다. `phone-context`는 3GPP IMS 도메인을 나타내며, `mnc001.mcc001`은 PLMN ID(MCC=001, MNC=01)이다. To에 `tel:` URI를 사용하는 것은 E.164 전화번호 형식이다.

---

## Call-ID / CSeq

```
Call-ID: {{call_id}}
CSeq: 1 INVITE
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{call_id}}` | seed 기반 랜덤 hex | 전역적으로 유일한 통화 식별자 |

**역할**: Call-ID는 SIP 다이얼로그를 식별한다. 같은 Call-ID로 INVITE를 보내면 UE가 재전송으로 인식하므로 매 케이스마다 새로 생성해야 한다. CSeq는 트랜잭션 내 순서 번호이다.

---

## Contact

```
Contact: <sip:{{from_msisdn}}@{{mo_contact_host}}:{{mo_contact_port_pc}};alias={{mo_contact_host}}~{{mo_contact_port_ps}}~1>;+sip.instance="<urn:gsma:imei:86838903-875492-0>";+g.3gpp.icsi-ref="urn%3Aurn-7%3A3gpp-service.ims.icsi.mmtel";audio;video;+g.3gpp.mid-call;+g.3gpp.srvcc-alerting;+g.3gpp.ps2cs-srvcc-orig-pre-alerting
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{from_msisdn}}` | `222222` | 발신자 MSISDN |
| `{{mo_contact_host}}` | `10.20.20.9` (기본값) | 발신측(MO) UE의 IP |
| `{{mo_contact_port_pc}}` | `31800` (기본값) | 발신측 UE의 protected client port |
| `{{mo_contact_port_ps}}` | `31100` (기본값) | 발신측 UE의 protected server port |

**역할**: 발신측 UE의 직접 연락 주소. Feature tag들의 의미:

| Feature Tag | 의미 |
|-------------|------|
| `+sip.instance` | 단말 고유 식별자 (IMEI 기반 URN) |
| `+g.3gpp.icsi-ref="...mmtel"` | IMS Multimedia Telephony 서비스 식별 |
| `audio` | 음성 통화 지원 |
| `video` | 영상 통화 지원 |
| `+g.3gpp.mid-call` | 통화 중 서비스 변경 지원 |
| `+g.3gpp.srvcc-alerting` | SRVCC(PS→CS 핸드오버) alerting 지원 |
| `+g.3gpp.ps2cs-srvcc-orig-pre-alerting` | SRVCC 사전 alerting 지원 |

A31은 `+g.3gpp.icsi-ref`가 mmtel이 아니면 INVITE를 무시한다.

---

## Accept-Contact

```
Accept-Contact: *;+g.3gpp.icsi-ref="urn%3Aurn-7%3A3gpp-service.ims.icsi.mmtel"
```

**역할**: 착신 UE에게 "이 통화는 mmtel(음성/영상) 서비스"임을 알린다. Contact의 feature tag와 매칭되어야 한다.

---

## P-Access-Network-Info

```
P-Access-Network-Info: 3GPP-E-UTRAN-FDD;utran-cell-id-3gpp=0010100010019B01
```

**역할**: 발신자의 접속 네트워크 정보. `3GPP-E-UTRAN-FDD`는 LTE FDD 접속을 의미하고, `utran-cell-id-3gpp`는 셀 ID(MCC=001, MNC=01, LAC=0001, CellID=9B01)이다. IMS 코어가 과금 및 위치 기반 서비스에 사용한다.

---

## P-Preferred-Service

```
P-Preferred-Service: urn:urn-7:3gpp-service.ims.icsi.mmtel
```

**역할**: 요청하는 IMS 서비스 유형. mmtel = Multimedia Telephony(VoLTE 음성/영상 통화).

---

## P-Early-Media

```
P-Early-Media: supported
```

**역할**: 통화 연결 전 미디어(링백톤, 안내 방송 등) 지원 여부. `supported`는 early media를 수신할 수 있음을 의미한다.

---

## Supported / Allow / Accept

```
Supported: 100rel,histinfo,join,norefersub,precondition,replaces,timer,sec-agree
Allow: INVITE,ACK,OPTIONS,BYE,CANCEL,UPDATE,INFO,PRACK,NOTIFY,MESSAGE,REFER
Accept: application/sdp,application/3gpp-ims+xml
```

| 헤더 | 역할 |
|------|------|
| **Supported** | 지원하는 SIP 확장 기능 목록 |
| **Allow** | 지원하는 SIP 메서드 목록 |
| **Accept** | 수신 가능한 Content-Type |

주요 Supported 값:
- `100rel`: 임시 응답(1xx)의 신뢰성 보장 (PRACK)
- `precondition`: QoS 사전 조건 (VoLTE 필수)
- `sec-agree`: Security Agreement (IPsec 협상)
- `timer`: Session Timer (세션 유지 관리)

---

## Session-Expires / Min-SE

```
Session-Expires: 1800
Min-SE: 90
```

**역할**: SIP 세션 타이머. 1800초(30분) 후 세션 갱신 필요, 최소 갱신 간격 90초. 장시간 통화 시 세션이 살아있는지 확인하는 메커니즘.

---

## User-Agent

```
User-Agent: IM-client/OMA1.0 HW-Rto/V1.0
```

**역할**: 발신 단말의 소프트웨어 식별자. 실제 단말 정보를 숨기고 일반적인 IMS 클라이언트로 표시.

---

## P-Charging-Vector

```
P-Charging-Vector: icid-value={{icid}};icid-generated-at={{pcscf_ip}}
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{icid}}` | seed 기반 랜덤 hex | IMS Charging ID. 과금 레코드 식별 |
| `{{pcscf_ip}}` | `172.22.0.21` | ICID를 생성한 노드 (P-CSCF) |

**역할**: IMS 과금 시스템에서 통화를 추적하기 위한 식별자. 각 통화마다 고유한 ICID가 필요하다.

---

## P-Visited-Network-ID

```
P-Visited-Network-ID: ims.mnc001.mcc001.3gppnetwork.org
```

**역할**: 발신자가 현재 접속한 방문 네트워크 식별자. 로밍 시 홈 네트워크와 구분하기 위해 사용. 테스트망에서는 홈/방문이 동일.

---

## P-Asserted-Identity

```
P-Asserted-Identity: <sip:{{from_msisdn}}@ims.mnc001.mcc001.3gppnetwork.org>
```

**역할**: 네트워크가 인증한 발신자 신원. P-CSCF/S-CSCF가 삽입하는 헤더로, 발신자가 실제로 인증된 사용자임을 착신 UE에게 보증한다. A31은 이 헤더가 없으면 INVITE를 신뢰하지 않는다.

---

## Content-Type / Content-Length

```
Content-Type: application/sdp
Content-Length: {{content_length}}
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{content_length}}` | 자동 계산 | SDP 바디의 바이트 수 |

**역할**: SIP 바디(SDP)의 타입과 크기. `render_mt_invite()`가 SDP 바디 크기를 계산하여 자동으로 채운다.

---

## SDP (Session Description Protocol) 바디

```
v=0
o=rue 3251 3251 IN IP4 {{sdp_owner_ip}}
s=-
b=AS:41
b=RR:1537
b=RS:512
t=0 0
m=audio {{sdp_audio_port}} RTP/AVP 107 106 105 104 101 102
c=IN IP4 {{sdp_owner_ip}}
b=AS:41
b=RR:1537
b=RS:512
a=rtpmap:107 AMR-WB/16000
a=fmtp:107 mode-change-capability=2;max-red=0
a=rtpmap:106 AMR-WB/16000
a=fmtp:106 octet-align=1;mode-change-capability=2;max-red=0
a=rtpmap:105 AMR/8000
a=fmtp:105 mode-change-capability=2;max-red=0
a=rtpmap:104 AMR/8000
a=fmtp:104 octet-align=1;mode-change-capability=2;max-red=0
a=rtpmap:101 telephone-event/16000
a=fmtp:101 0-15
a=rtpmap:102 telephone-event/8000
a=fmtp:102 0-15
a=curr:qos local none
a=curr:qos remote none
a=des:qos mandatory local sendrecv
a=des:qos optional remote sendrecv
a=sendrecv
a=rtcp:{{sdp_rtcp_port}}
a=ptime:20
a=maxptime:240
```

| 슬롯 | 채워야 하는 값 | 의미 |
|------|--------------|------|
| `{{sdp_owner_ip}}` | `172.22.0.16` (기본값) | RTP 미디어 소스 IP |
| `{{sdp_audio_port}}` | `49196` (기본값) | RTP 오디오 포트 |
| `{{sdp_rtcp_port}}` | `49197` (기본값) | RTCP 제어 포트 |

### SDP 필드 상세

| 필드 | 값 | 의미 |
|------|-----|------|
| `v=0` | 프로토콜 버전 | SDP 버전 0 |
| `o=rue 3251 3251` | 세션 소유자 | 세션 ID와 버전 |
| `b=AS:41` | 대역폭 | Application-Specific: 41kbps (AMR-WB) |
| `b=RR:1537` | RTCP 수신 보고 대역폭 | |
| `b=RS:512` | RTCP 송신 보고 대역폭 | |

### 코덱 (payload type 순서)

| PT | 코덱 | 샘플레이트 | 설명 |
|----|------|-----------|------|
| 107 | AMR-WB | 16kHz | 광대역 음성 (HD Voice), bandwidth-efficient |
| 106 | AMR-WB | 16kHz | 광대역 음성, octet-aligned |
| 105 | AMR | 8kHz | 협대역 음성, bandwidth-efficient |
| 104 | AMR | 8kHz | 협대역 음성, octet-aligned |
| 101 | telephone-event | 16kHz | DTMF 톤 (광대역) |
| 102 | telephone-event | 8kHz | DTMF 톤 (협대역) |

AMR-WB가 먼저 제안되어 HD Voice가 우선 협상된다. A31은 AMR 또는 AMR-WB가 SDP에 없으면 통화를 거부한다.

### QoS Precondition

```
a=curr:qos local none       ← 현재 로컬 QoS: 없음
a=curr:qos remote none      ← 현재 원격 QoS: 없음
a=des:qos mandatory local sendrecv   ← 필수: 로컬 양방향 QoS 확보 요구
a=des:qos optional remote sendrecv   ← 선택: 원격 양방향 QoS
```

**역할**: VoLTE에서 음성 품질 보장을 위한 QoS 사전 조건. `mandatory local sendrecv`는 "통화 연결 전에 로컬 QoS bearer가 반드시 설정되어야 함"을 의미한다. 이 필드가 없으면 일부 단말은 precondition 미충족으로 통화를 거부한다.

---

## 동적으로 조회해야 하는 값 (매 전송마다)

| 값 | 조회 방법 | 변경 시점 |
|----|----------|----------|
| UE IP | pcscf OPTIONS ping 로그 파싱 | UE 재등록 시 |
| IMPI | 같은 로그에서 추출 | 변경 없음 (USIM 고정) |
| port_pc / port_ps | xfrm state 또는 pcscf 로그 | UE 재등록 시 |

## seed 기반 결정론적 생성 값 (재현 가능)

| 값 | 생성 방법 |
|----|----------|
| Call-ID | `random.Random(seed)` 기반 hex |
| From-Tag | 동일 |
| Via Branch | 동일 |
| ICID | 동일 |
