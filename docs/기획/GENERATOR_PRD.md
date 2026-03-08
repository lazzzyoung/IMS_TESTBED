# Generator PRD

## 1. 문서 목적
본 문서는 SIP 퍼저의 Generator를 어떤 책임과 구조로 구현할지 정의한다. Generator는 RFC와 catalog에 맞는 정상 SIP 메시지를 만들어 내는 계층이며, 이후 Mutator, Sender, Controller가 신뢰할 수 있는 기준 입력을 제공하는 역할을 맡는다.

이 문서의 목표는 "패킷을 만든다"는 수준의 추상적인 설명을 넘어서, Generator가 어떤 입력을 받고 어떤 출력을 반환해야 하는지, 어떤 클래스가 공개 API를 담당하고 어떤 로직을 내부 메서드로 감출지를 분명하게 정리하는 데 있다.

## 2. Generator의 역할
Generator는 현재 저장소에 이미 정의되어 있는 SIP catalog와 Pydantic 스키마를 재사용하는 서비스 계층으로 구현한다. Generator의 핵심 역할은 요청된 SIP 메시지 종류에 맞는 모델을 선택하고, `.env`에서 읽은 기본 설정과 선택적인 대화 문맥을 바탕으로 필수 필드를 채운 뒤, 최종적으로 검증 가능한 Pydantic 인스턴스를 반환하는 것이다.

Generator는 정상 메시지 생성만 책임진다. 실제 SIP 문자열 직렬화, 네트워크 전송, 변조, 오라클 관측은 Generator의 범위에 포함하지 않는다. 이 문서 기준에서 Generator의 출력은 wire text가 아니라 `SIPRequest` 또는 `SIPResponse` 계열의 Pydantic 인스턴스다.

## 3. 설계 원칙
Generator는 가능한 한 작은 공개 API를 갖고, 세부 생성 로직은 내부 메서드로 숨긴다. 외부에서는 "어떤 패킷을 만들고 싶은가"만 전달하고, Generator 내부에서는 모델 선택, 기본값 채움, 문맥 반영, override 병합, 검증을 순서대로 수행한다.

또한 설정, 상태, 생성 요청은 서로 다른 성격을 가지므로 별도의 타입으로 유지한다. 반면 값 생성 로직 자체는 초기에 별도 팩토리 클래스로 과도하게 분리하지 않고 `SIPGenerator` 내부 private 메서드로 관리한다.

## 4. 주요 구성 요소

### 4.1 `SIPGenerator`
`SIPGenerator`는 Generator의 메인 서비스 클래스다. 외부 호출자는 이 클래스를 통해 요청 메시지 또는 응답 메시지를 생성한다. 이 클래스는 다음과 같은 흐름을 오케스트레이션한다.

1. 호출자가 전달한 생성 요청을 해석한다.
2. catalog와 스키마를 이용해 적절한 Pydantic 모델을 선택한다.
3. 설정과 문맥을 바탕으로 기본 필드를 채운다.
4. 호출자가 넘긴 override를 반영한다.
5. 전제조건과 모델 검증을 수행한다.
6. 최종 Pydantic 인스턴스를 반환한다.

초기 구현에서는 공개 메서드를 최소화한다. 외부에서 직접 호출하는 메서드는 `generate_request(...)`와 `generate_response(...)` 두 개로 시작하는 것을 기본안으로 삼는다.

### 4.2 `GeneratorSettings`
`GeneratorSettings`는 `.env`에서 읽는 기본 설정을 표현하는 클래스다. 대상 단말 정보, 기본 SIP 호스트/포트, 기본 발신자/수신자 URI 구성 요소, transport, User-Agent처럼 반복적으로 사용되는 값은 이 객체에 담는다.

중요한 점은 `.env` 로딩 책임이 `SIPGenerator` 본체에 직접 들어가지 않는다는 것이다. 설정은 `GeneratorSettings.from_env()` 같은 명시적인 초기화 메서드로 읽고, `SIPGenerator`는 이미 준비된 설정 객체를 주입받아 사용한다. 이렇게 해야 Generator 자체를 테스트할 때 환경 변수 의존성을 쉽게 분리할 수 있다.

### 4.3 `DialogContext`
`DialogContext`는 상태가 있는 SIP 시나리오를 위해 유지되는 문맥 객체다. 예를 들어 Call-ID, 로컬/리모트 tag, CSeq, route set, request URI, registration 상태, 재협상 여부 같은 정보는 단순 파라미터 집합이 아니라 하나의 대화 상태로 보는 편이 맞다.

Generator는 문맥이 없는 단발성 메시지도 생성할 수 있어야 하지만, INVITE 이후 ACK, 기존 dialog 위의 BYE, 구독 이후 NOTIFY처럼 상태가 필요한 경우에는 `DialogContext`를 입력으로 받아 그 내용을 재사용한다.

### 4.4 `RequestSpec`
`RequestSpec`은 "어떤 요청 패킷을 만들 것인가"를 표현하는 입력 타입이다. 최소한 어떤 SIP method를 만들지, 어떤 시나리오를 전제로 하는지, 호출자가 직접 덮어쓰고 싶은 필드가 무엇인지를 담는다.

이 객체는 최종 SIP 패킷 모델과 분리되어야 한다. `RequestSpec`은 생성 요청이고, `SIPRequest` 계열 객체는 생성 결과다. 이 둘을 분리해야 자동 생성된 기본값과 사용자가 지정한 override를 명확하게 구분할 수 있다.

### 4.5 `ResponseSpec`
`ResponseSpec`은 "어떤 응답 패킷을 만들 것인가"를 표현하는 입력 타입이다. 최소한 status code와 관련 request method, 필요한 override, 시나리오 정보 등을 담는다. 응답은 보통 선행 요청과 연결되어야 하므로 `RequestSpec`보다 `DialogContext` 의존성이 더 강하다.

## 5. `SIPGenerator`의 공개 메서드

### 5.1 `generate_request(spec, context=None)`
이 메서드는 `RequestSpec`과 선택적인 `DialogContext`를 받아 정상적인 SIP 요청 패킷을 생성한다. 내부적으로는 method에 맞는 request 모델을 찾고, 필수 헤더와 start-line 필드를 기본값으로 채운 뒤, override를 반영하고, Pydantic 검증을 수행한다.

이 메서드는 문맥이 없는 초기 요청 생성과 문맥이 있는 in-dialog 요청 생성을 모두 지원해야 한다. 예를 들어 첫 INVITE는 문맥 없이도 만들 수 있지만, ACK나 BYE는 일반적으로 기존 문맥을 참조해야 한다.

### 5.2 `generate_response(spec, context)`
이 메서드는 `ResponseSpec`과 `DialogContext`를 받아 정상적인 SIP 응답 패킷을 생성한다. 응답은 기존 요청과의 연관성이 중요하므로, 초기 버전에서는 `context`를 필수로 두는 것이 안전하다.

이 메서드는 status code에 맞는 response 모델을 선택하고, Via, From, To, Call-ID, CSeq 같은 상관관계 필드를 문맥에서 재사용한 뒤, 필요한 조건부 필드를 채워서 최종 응답 모델을 반환한다.

## 6. `SIPGenerator`의 내부 메서드
초기 구현에서는 별도 `DefaultValueFactory` 클래스를 도입하지 않고, 값 생성 로직을 `SIPGenerator` 내부 private 메서드로 둔다. 이 방식이면 클래스 수를 과도하게 늘리지 않으면서도 책임 경계를 유지할 수 있다.

내부 메서드는 다음 역할을 나눠 갖는다.

### 6.1 모델 선택
- `_resolve_request_model(spec)`
- `_resolve_response_model(spec)`

이 메서드들은 catalog와 현재 정의된 모델 매핑을 사용해 어떤 Pydantic 모델을 쓸지 결정한다.

### 6.2 기본 필드 생성
- `_build_request_defaults(spec, context)`
- `_build_response_defaults(spec, context)`
- `_build_via(...)`
- `_build_from(...)`
- `_build_to(...)`
- `_build_call_id(...)`
- `_build_cseq(...)`
- `_build_request_uri(...)`

이 메서드들은 `.env` 설정과 `DialogContext`를 참고해 사람이 매번 직접 입력하지 않아도 되는 기본값을 채운다.

### 6.3 병합과 검증
- `_apply_overrides(defaults, overrides)`
- `_validate_preconditions(definition, context)`

Generator는 자동 생성된 기본값 위에 사용자의 override를 덮어쓰고, catalog에 정리된 전제조건이나 문맥 조건을 점검한 뒤 최종 모델 검증을 수행한다.

## 7. 입력과 출력
Generator는 세 종류의 입력을 사용한다.

첫째, 호출자가 명시적으로 넘기는 `RequestSpec` 또는 `ResponseSpec`이다. 이 입력은 어떤 패킷을 만들지에 대한 의도를 표현한다.

둘째, `.env`에서 로드한 `GeneratorSettings`다. 이 입력은 반복 사용되는 환경 기본값을 제공한다. 대상 단말 정보나 기본 URI/호스트/포트 같은 값은 호출자가 매번 직접 넘기지 않는다.

셋째, 선택적인 `DialogContext`다. 이는 상태 의존 패킷 생성에 사용된다.

출력은 항상 Pydantic 인스턴스다. 요청 생성 결과는 `SIPRequest` 계열 인스턴스이고, 응답 생성 결과는 `SIPResponse` 계열 인스턴스다. Generator 단계에서는 wire text가 아니라 구조화된 모델을 기준 산출물로 본다.

## 8. 생성 절차
Generator의 내부 동작은 아래 순서를 따른다.

1. 생성 요청(`RequestSpec` 또는 `ResponseSpec`)을 받는다.
2. method 또는 status code에 맞는 모델을 찾는다.
3. 설정과 문맥을 바탕으로 기본 필드를 구성한다.
4. 호출자가 제공한 override를 반영한다.
5. 전제조건을 점검한다.
6. Pydantic 모델로 검증한다.
7. 최종 인스턴스를 반환한다.

이 순서를 지키면 "어떤 값을 누가 넣었는지"가 명확해지고, 이후 Mutator나 Sender가 사용할 기준 패킷을 일관되게 생성할 수 있다.

## 9. CLI와의 경계
Generator는 Typer CLI를 통해 호출될 수 있지만, CLI는 `SIPGenerator` 클래스 내부 책임이 아니다. CLI는 별도 모듈에서 사용자 입력을 파싱하고 `GeneratorSettings`, `RequestSpec`, `ResponseSpec`, `DialogContext`를 구성한 뒤 `SIPGenerator`를 호출하는 얇은 어댑터 계층으로 구현한다.

즉, CLI는 입출력 인터페이스이고, `SIPGenerator`는 순수한 애플리케이션 서비스다. 이 분리를 유지해야 단위 테스트와 추후 API 확장이 쉬워진다.

`pyproject.toml`에는 Python 경로를 직접 실행하는 대신 `fuzzer` 형태의 스크립트 엔트리포인트를 정의하는 방향을 목표로 한다.

## 10. 범위에 포함하지 않는 것
본 문서 기준 Generator 범위에는 아래 항목을 넣지 않는다.

- 실제 SIP 문자열 또는 bytes 직렬화
- 패킷 전송
- mutation 로직
- crash/ANR/oracle 판정
- 캠페인 제어

이 항목들은 각각 Renderer, Sender/Reactor, Mutator, Oracle, Controller의 책임으로 분리한다.

## 11. 초기 구현 우선순위
초기 구현은 다음 순서로 진행한다.

1. `src/volte_mutation_fuzzer/generator/contracts.py`를 먼저 만든다.
   이 파일 안에서는 `GeneratorSettings` -> `DialogContext` -> `RequestSpec` -> `ResponseSpec` 순서로 정의한다.
   가장 먼저 고정해야 하는 것은 Generator의 입력 계약과 상태 계약이며, 이 경계가 먼저 잡혀야 `SIPGenerator`의 공개 API도 흔들리지 않는다.
2. `src/volte_mutation_fuzzer/generator/core.py`를 만든다.
   이 파일 안에서는 `SIPGenerator.__init__` -> `generate_request` -> `generate_response` 순서로 작업한다.
   먼저 외부 공개 메서드 시그니처를 고정한 뒤, 내부 구현을 채우는 방식으로 진행한다.
3. 같은 `src/volte_mutation_fuzzer/generator/core.py` 안에서 request 생성 경로를 먼저 완성한다.
   구현 순서는 `_resolve_request_model` -> `_build_request_defaults` -> `_apply_overrides` -> `_validate_preconditions` 순서로 둔다.
   request 경로가 먼저 안정돼야 response 쪽에서도 같은 생성 패턴을 재사용할 수 있다.
4. 이어서 같은 `src/volte_mutation_fuzzer/generator/core.py` 안에서 response 생성 경로를 구현한다.
   구현 순서는 `_resolve_response_model` -> `_build_response_defaults` -> `_apply_overrides` -> `_validate_preconditions` 순서로 둔다.
   response는 dialog context 의존성이 더 강하므로 request 생성 흐름이 먼저 정리된 뒤 붙이는 편이 안전하다.
5. request/response 공통 기본값 생성 로직을 같은 파일의 private 메서드로 정리한다.
   구현 순서는 `_build_via` -> `_build_from` -> `_build_to` -> `_build_call_id` -> `_build_cseq` -> `_build_request_uri` 정도로 둔다.
   초기 버전에서는 별도 `DefaultValueFactory` 클래스를 만들지 않고 `SIPGenerator` 내부 메서드로 유지한다.
6. `tests/generator/test_core.py`를 추가한다.
   테스트 작성 순서는 `GeneratorSettings`/`DialogContext` 기본 동작 -> `generate_request` 정상 케이스 -> `generate_response` 정상 케이스 -> catalog 기반 실패 케이스 순서로 둔다.
   구현보다 테스트가 뒤에 오더라도, 최소한 public API 기준의 동작 경계는 이 파일에서 바로 고정해야 한다.
7. 마지막으로 `src/volte_mutation_fuzzer/generator/cli.py`를 만든다.
   이 파일 안에서는 `Typer app` 선언 -> request 생성 커맨드 -> response 생성 커맨드 순서로 붙인다.
   CLI는 Generator의 핵심 책임이 아니라 가장 바깥 어댑터이므로 항상 마지막 단계에 둔다.

초기 버전에서 가장 중요한 완료 기준은 "모든 SIP request/response 스키마에 대해 Generator가 정상 Pydantic 인스턴스를 만들 수 있다"는 점이다. 구조를 과도하게 일반화하는 것보다, 작은 공개 API와 명확한 내부 생성 흐름을 먼저 고정하는 쪽을 우선한다.
