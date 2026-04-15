# Capstone Fuzzer Dumpipe IPsec 우회 분석

> Capstone fuzzer가 IPsec을 어떻게 다루는지에 대한 코드 기반 분석.
> 출처: `/Users/chaejisung/Desktop/Project/fuzzer(capstone)/`

---

## 1. IPsec 설정 상태: 켜져 있다

Capstone의 P-CSCF는 IPsec이 **활성화**되어 있다.

**출처**: `infrastructure/pcscf/pcscf.cfg:151`
```
#!define WITH_IPSEC
```

`#!define`은 Kamailio 전처리기 매크로 정의이므로, `#!ifdef WITH_IPSEC` 블록이 모두 활성화된다.

### IPsec 모듈 로드 및 파라미터

**출처**: `infrastructure/pcscf/kamailio_pcscf.cfg:174-175, 423-430`

```kamailio
#!ifdef WITH_IPSEC
loadmodule "ims_ipsec_pcscf.so"
```

```kamailio
#!ifdef WITH_IPSEC
modparam("ims_ipsec_pcscf", "ipsec_listen_addr", IPSEC_LISTEN_ADDR)
modparam("ims_ipsec_pcscf", "ipsec_client_port", IPSEC_CLIENT_PORT)    # 5100
modparam("ims_ipsec_pcscf", "ipsec_server_port", IPSEC_SERVER_PORT)    # 6100
modparam("ims_ipsec_pcscf", "ipsec_spi_id_start", 4096)
modparam("ims_ipsec_pcscf", "ipsec_max_connections", IPSEC_MAX_CONN)   # 10
modparam("ims_ipsec_pcscf", "ipsec_preferred_ealg", "null")            # 핵심
```

- `ims_ipsec_pcscf.so` 모듈이 로드됨
- UE 등록 시 `ipsec_create()` 호출로 IPsec SA 터널 실제 생성 (`register.cfg:302`)
- **`ipsec_preferred_ealg = "null"`**: ESP 헤더는 붙지만 암호화는 안 함 (무결성만)

### IPsec 포트 구성

**출처**: `infrastructure/pcscf/pcscf.cfg:15-16`

```
#!define IPSEC_CLIENT_PORT 5100
#!define IPSEC_SERVER_PORT 6100
```

P-CSCF ↔ UE 간 IPsec 트래픽은 이 포트들을 통해 ESP로 캡슐화된다.

---

## 2. Dumpipe: IPsec을 뚫는 게 아니라 안 거침

### 핵심 아키텍처

**출처**: `fuzzer/fuzzer/dumpipe.py:17-24`

```
정상 흐름:    발신자 → P-CSCF → IPsec 터널(5100/6100) → UE
Dumpipe:     Fuzzer → UPF(172.22.0.8) → UE(10.20.20.x:5060)
```

Dumpipe는 P-CSCF를 경유하지 않으므로 IPsec 터널 자체를 사용하지 않는다.

### 소켓 생성: 포트 조작 없음

**출처**: `fuzzer/fuzzer/dumpipe.py:255-259`

```python
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(self.timeout)
sock.bind(('', 0))  # OS가 가용 포트 할당
```

- source port: OS가 랜덤 할당 (IPsec 포트 매칭 없음)
- xfrm policy 회피: 고려하지 않음
- Source IP 스푸핑: 없음 (fuzzer 호스트 자체 IP 사용)

### 헤더 조작: Via/Contact만 교체

**출처**: `fuzzer/fuzzer/dumpipe.py:272-278`

```python
# Via 헤더의 IP:port만 교체 (fuzz 파라미터는 유지)
via_pattern = r'(Via:\s*SIP/2\.0/UDP\s+)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+'
message = re.sub(via_pattern, rf'\g<1>{local_ip}:{local_port}', message)

# Contact 헤더의 IP:port도 교체 (응답 수신 주소)
contact_pattern = r'(Contact:\s*<sip:[^@]+@)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+'
message = re.sub(contact_pattern, rf'\g<1>{local_ip}:{local_port}', message)
```

SIP 응답을 자기가 받기 위해 Via/Contact의 IP:port를 소켓 바인드 주소로 교체하는 것이 전부다.

### 라우팅: UPF 경유

**출처**: `fuzzer/fuzzer/dumpipe.py:211`

```python
def setup_route(self, ue_subnet: str = "10.20.20.0/24", gateway: str = "172.22.0.8") -> bool:
```

```bash
ip route add 10.20.20.0/24 via 172.22.0.8   # UPF를 게이트웨이로
```

UE 서브넷(10.20.20.0/24)으로 가는 트래픽을 UPF(172.22.0.8)를 통해 라우팅한다.
P-CSCF(172.22.0.21)는 경로에 포함되지 않는다.

---

## 3. UE IP 조회: S-CSCF DB 쿼리

**출처**: `fuzzer/tools/ue_lookup.py` (dumpipe.py:35에서 import)

```python
from tools.ue_lookup import UELookup, UEContact, check_ue_route, setup_ue_route
```

MSISDN → UE IP 변환을 S-CSCF의 MySQL DB(`scscf.location` 테이블)에서 조회한다.
환경변수 매핑이 아니라 실제 등록 DB를 쿼리하는 방식이다.

---

## 4. P-CSCF 경유 경로 (Sender)

Dumpipe 외에 P-CSCF를 거치는 일반 경로도 존재한다.

**출처**: `infrastructure/pcscf/pcscf.cfg:155-156`

```kamailio
#!define ENABLE_FUZZ_SANITY_BYPASS 1
```

이 플래그가 켜지면, P-CSCF가 malformed SIP 패킷도 sanity check에서 통과시킨다.
Dumpipe가 아닌 P-CSCF 경유 퍼징 시 사용하는 옵션이다.

---

## 5. Dumpipe가 동작하는 전제 조건

`docs/dumpipe.md:463-467`에 명시된 조건:

1. **UE IP 접근 가능**: fuzzer → UPF → UE 라우팅이 설정되어야 함
2. **SIP 포트 오픈**: UE가 5060에서 SIP을 리스닝해야 함
3. **인증 미검증**: UE가 P-CSCF 외부에서 온 메시지도 처리해야 함

핵심 가정: **UE가 IPsec 보호 포트(port_pc/port_ps) 외에 기본 5060 포트에서도 평문 SIP을 수신한다.**

---

## 6. VolteMutationFuzzer와의 비교

| 항목 | Capstone (Dumpipe) | VolteMutationFuzzer |
|------|-------------------|---------------------|
| **IPsec 설정** | 켜짐 (null ealg) | 켜짐 (aes-cbc) |
| **우회 전략** | P-CSCF 자체를 안 거침 | P-CSCF netns에서 Source IP 스푸핑 |
| **Source IP** | Fuzzer 호스트 자체 IP | P-CSCF IP (172.22.0.21) |
| **Source Port** | OS 랜덤 할당 | 15100 (xfrm policy 미매치용) |
| **목적 포트** | UE 5060 (기본 SIP) | UE port_pc/port_ps (IPsec 포트) |
| **라우팅** | UPF(172.22.0.8) 경유 | P-CSCF netns 내부 직접 송신 |
| **ESP 캡슐화** | 없음 | 없음 (xfrm selector 회피) |
| **UE IP 조회** | S-CSCF DB 쿼리 | 환경변수 매핑 |
| **포트 조작** | 없음 | Via sent-by ↔ bind_port 동기화 필요 |
| **xfrm 고려** | 안 함 | sport로 policy selector 회피 |

### 철학 차이

- **Capstone**: IPsec 경로를 우회하여 UE에 직접 접근 (환경 우회)
- **VolteMutationFuzzer**: IPsec 경로 위에서 policy gap을 이용 (환경 내 공략)

---

## 7. 한 줄 요약

Capstone의 Dumpipe는 IPsec이 켜져 있어도 P-CSCF를 통째로 건너뛰고 UPF 경유로 UE의 기본 5060 포트에 평문 UDP를 직접 보내며, source port 조작이나 xfrm policy 회피 같은 트릭은 일절 사용하지 않는다.
