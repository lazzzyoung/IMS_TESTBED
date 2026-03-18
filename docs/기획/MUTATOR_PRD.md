# Mutator PRD

## 1. 문서 목적
본 문서는 SIP 퍼저의 Mutator를 어떤 책임과 구조로 구현할지 정의한다. Mutator는 Generator가 만든 정상 SIP 메시지를 입력으로 받아 재현 가능한 방식으로 변조하는 계층이며, 이후 Sender, Oracle, Controller가 사용할 의미 있는 비정상 입력을 제공하는 역할을 맡는다.

이 문서의 목표는 "필드를 랜덤하게 바꾼다"는 수준의 추상적인 설명을 넘어서, Mutator가 어떤 입력을 받고 어떤 출력을 반환해야 하는지, 어떤 클래스가 공개 API를 담당하고 어떤 로직이 내부 메서드로 숨겨져야 하는지, 그리고 왜 model 기반 변조, wire 기반 변조, byte 기반 변조를 분리해야 하는지를 분명하게 정리하는 데 있다.

## 2. Mutator의 역할
Mutator는 현재 저장소에 이미 정의되어 있는 SIP catalog, Pydantic 스키마, 그리고 Generator가 반환하는 `SIPRequest` 또는 `SIPResponse` 인스턴스를 재사용하는 서비스 계층으로 구현한다. Mutator의 핵심 역할은 정상 baseline 패킷을 받아 변조 대상과 변조 전략을 해석하고, seed 기반으로 연산을 선택하여, 최종적으로 모델 수준, wire 수준, 또는 byte 수준의 변조 결과를 반환하는 것이다.

Mutator는 세 종류의 변조를 모두 지원해야 한다.

첫째, **model-based mutation**은 Pydantic 모델과 그 내부 필드를 기준으로 값을 바꾸는 방식이다. 이 계층은 Call-ID, CSeq, tag, URI, status code, Reason-Phrase, body 관련 값처럼 프로토콜 의미와 상태에 직접 연결된 필드를 변조하는 데 적합하다.

둘째, **wire-based mutation**은 실제 SIP 텍스트 패킷과 유사한 편집 가능한 표현을 기준으로 헤더 삭제, 중복, 순서 변경, start-line 손상, Content-Length 불일치 같은 구조 변조를 수행하는 방식이다. 이 계층은 모델이 표현하기 어려운 parser robustness 계열 입력을 만드는 데 필요하다.

셋째, **byte-based mutation**은 wire 표현을 bytes로 본 뒤 bit flip, byte insertion, byte deletion, truncation, delimiter 손상, 비정상 인코딩 바이트 주입 같은 연산을 수행하는 방식이다. 이 계층은 더 이상 "의미 있는 SIP 텍스트"를 유지할 필요가 없으며, parser와 lower-level 입력 처리 경로를 더 공격적으로 자극하는 데 필요하다.

중요한 점은 Mutator의 **핵심 로직**이 Generator CLI 실행 결과에만 의존하는 프로그램이어서는 안 된다는 것이다. 현재 Generator는 CLI와 별개로 `SIPGenerator` 서비스 API를 제공하므로, Mutator 서비스 계층은 shell 명령 실행이 아니라 Generator가 반환한 Pydantic 인스턴스를 직접 입력으로 받을 수 있어야 한다.

다만 사용자 인터페이스 차원에서는 **Typer 기반 Mutator CLI**를 별도로 제공해야 한다. 이 CLI는 두 가지 입력 경로를 모두 지원해야 한다.

첫째, Generator CLI가 출력한 JSON 형태의 baseline 패킷을 stdin 또는 파일 입력으로 받아 변조 결과를 보여주는 방식이다. 이 모드는 `generator cli -> mutator cli` 파이프라인 사용성을 위한 것이다.

둘째, Mutator CLI가 내부적으로 `SIPGenerator`의 request/response 생성 메서드를 직접 호출해 baseline 패킷을 만들고, 그 결과를 즉시 변조해 보여주는 방식이다. 이 모드는 사용자가 별도 generator 명령 없이 한 번에 baseline 생성과 변조를 수행할 수 있도록 하기 위한 것이다.

또한 byte-based mutation은 "완전히 말이 안 되는 패킷"을 만드는 용도를 포함한다. 다만 이 역시 baseline 없이 임의의 랜덤 바이트를 처음부터 생성하는 것이 아니라, baseline SIP 메시지에서 출발해 점진적으로 손상시키는 방식으로 정의하는 것이 본 프로젝트의 목적과 더 잘 맞는다.

## 3. 설계 원칙
Mutator는 가능한 한 작은 공개 API를 갖고, 세부 operator 선택과 변조 절차는 내부 메서드로 숨긴다. 외부에서는 "어떤 baseline 패킷을 어떤 전략으로 변조할 것인가"만 전달하고, Mutator 내부에서는 definition 해석, target 수집, operator 선택, 변조 적용, 기록 생성 순서로 동작하게 한다.

또한 Mutator는 **model 계층, wire 계층, byte 계층을 명시적으로 분리**해야 한다. model 계층은 의미 있는 상태 변조에 강하고, wire 계층은 파서 견고성 테스트에 강하며, byte 계층은 텍스트 규칙 자체가 무너진 입력까지 다룰 수 있다. 이 셋을 한 표현 안에 억지로 합치면 API가 불명확해지고, 반대로 너무 일찍 별도 프레임워크나 레지스트리 클래스로 과도하게 분리하면 초기 구현이 불필요하게 복잡해진다. 따라서 초기 버전에서는 `SIPMutator`와 편집 가능한 wire/byte 표현을 중심으로 시작하고, operator dispatch는 private 메서드 수준에서 관리하는 것을 기본안으로 삼는다. CLI 역시 이 서비스 계층 위에 얇게 얹혀야 하며, CLI 편의 로직이 core mutation 흐름을 대신해서는 안 된다.

재현성도 중요한 원칙이다. 동일한 baseline 패킷과 동일한 seed, 동일한 설정을 주었을 때는 가능한 한 동일한 변조 결과가 나와야 한다. 다만 현재 Generator 자체는 UUID 기반 기본값을 생성하므로, Mutator의 재현성은 **고정된 baseline 입력에 대한 재현성**으로 정의하는 것이 안전하다. 전체 퍼징 재현성은 seed뿐 아니라 원본 baseline 패킷 자체도 함께 저장하는 방향을 전제로 한다.

마지막으로 Mutator는 catalog metadata를 적극 활용해야 한다. 단순 JSON Schema만으로는 conditional required field, forbidden field, related method, wire header 이름 같은 정보를 충분히 알 수 없기 때문이다. 따라서 Mutator는 field descriptor와 definition metadata를 함께 사용해 어떤 target을 우선적으로 선택하고 어떤 layer에서 다루어야 하는지 판단해야 한다. 반면 byte 계층으로 내려간 이후에는 catalog보다도 "어떤 직렬화 경계가 깨졌는가"와 "어떤 bytes 연산이 적용되었는가"가 더 중요한 정보가 된다.

## 4. 주요 구성 요소

### 4.1 `SIPMutator`
`SIPMutator`는 Mutator의 메인 서비스 클래스다. 외부 호출자는 이 클래스를 통해 baseline request 또는 response를 전체 변조하거나 특정 필드를 지정해 변조한다. 이 클래스는 다음 흐름을 오케스트레이션한다.

1. 호출자가 전달한 baseline 패킷과 변조 설정을 해석한다.
2. catalog와 모델 타입을 이용해 해당 패킷의 definition을 찾는다.
3. 전략에 따라 model target, wire target, byte target 후보를 수집한다.
4. seed 기반으로 operator를 선택한다.
5. model layer 변조를 먼저 적용하고, 필요하면 wire layer, byte layer 변조를 이어서 적용한다.
6. 적용된 변조를 기록하고 최종 결과 객체를 반환한다.

초기 구현에서는 공개 메서드를 최소화한다. 외부에서 직접 호출하는 메서드는 `mutate(...)`와 `mutate_field(...)` 두 개로 시작하는 것을 기본안으로 삼는다.

### 4.2 `MutationConfig`
`MutationConfig`는 하나의 변조 실행에서 사용할 설정을 표현하는 클래스다. 최소한 seed, strategy 이름, layer 선택(`model`, `wire`, `byte`, `auto`), 최대 연산 수, 그리고 model 유효성을 유지할지 여부 같은 옵션을 담아야 한다.

이 객체는 단순 옵션 모음 이상의 역할을 가진다. 예를 들어 `strategy="state_breaker"`이면 dialog/state 의존 필드 위주로 operator를 선택하고, `strategy="header_chaos"`이면 헤더 삭제/중복/순서 변경 같은 wire 연산을 우선적으로 선택하도록 할 수 있다. `strategy="byte_noise"`나 이에 준하는 전략은 bit flip, byte insertion, truncation 같은 byte 연산을 우선적으로 선택하도록 설계할 수 있다. `MutationConfig`를 별도 타입으로 두면 추후 CLI, campaign controller, 테스트 코드가 같은 설정 구조를 공유하기 쉬워진다.

중요한 점은 `MutationConfig`가 곧바로 \"모든 내부 operator를 사용자에게 노출한다\"는 뜻은 아니라는 것이다. 기본적으로는 사용자에게 전략, layer, seed, target, 최대 연산 수 같은 상위 옵션을 공개하고, 특정 operator 강제 지정이나 byte offset/range 지정 같은 세밀한 조작은 고급 옵션으로 분리하는 것이 안전하다.

### 4.3 `MutationTarget`
`MutationTarget`은 "어느 위치를 변조할 것인가"를 표현하는 입력 타입이다. model layer에서는 `call_id`, `cseq.sequence`, `from_.parameters.tag`, `request_uri.host` 같은 field path가 target이 될 수 있다. wire layer에서는 `start_line`, `header:Call-ID`, `header[3]`, `body` 같은 위치 표현이 target이 될 수 있다. byte layer에서는 `byte[17]`, `range[40:55]`, `delimiter:CRLF`, `segment:start_line` 같은 위치 표현이 target이 될 수 있다.

이 객체를 최종 SIP 패킷 모델과 분리해야 하는 이유는, target 지정은 변조 요청의 일부이지 결과 패킷의 일부가 아니기 때문이다. 또한 이 객체를 분리해 두어야 alias 정규화와 layer별 path 규칙을 명확하게 관리할 수 있다.

### 4.4 `MutationRecord`
`MutationRecord`는 실제로 어떤 연산이 적용되었는지를 기록하는 결과 타입이다. 최소한 어떤 layer에서, 어떤 operator가, 어떤 target에, 어떤 before/after 값을 만들었는지와 seed 또는 파생 random 결정 정보를 담아야 한다.

Mutator는 단순히 최종 결과만 반환하면 안 된다. 이후 Oracle 분석, 재현, 보고서 작성까지 고려하면 "무엇을 어떻게 바꿨는가"를 구조적으로 기록해야 한다. `MutationRecord`는 그 역할을 담당한다.

### 4.5 `MutatedCase`
`MutatedCase`는 Mutator의 최종 반환 타입이다. 최소한 원본 packet, 변조 결과 packet 또는 wire 표현 또는 byte 표현, 적용된 mutation 목록, seed, 전략 이름, 필요 시 context 스냅샷을 담는다.

중요한 점은 model-based mutation 결과, wire-based mutation 결과, byte-based mutation 결과를 같은 타입으로 감싸야 한다는 것이다. model-based mutation의 경우에는 최종 `mutated_packet`이 존재할 수 있지만, wire-based mutation에서는 `editable_message`가 핵심 결과가 되고, byte-based mutation에서는 최종 bytes artifact가 핵심 결과가 될 수 있다. 이 차이를 `MutatedCase`가 흡수해야 상위 계층 API가 불필요하게 갈라지지 않는다.

### 4.6 `EditableSIPMessage`
`EditableSIPMessage`는 wire-based mutation을 위한 편집 가능한 SIP 표현이다. 이 객체는 start-line, 순서가 유지되는 header 목록, body를 별도로 보존해야 한다. 또한 동일 헤더의 중복, 알 수 없는 헤더명, 잘못된 Content-Length, 비정상적인 순서 같은 상태를 허용해야 한다.

이 객체는 "정상 SIP 모델"이 아니라 "변조 가능한 wire 중간 표현"이다. 따라서 Pydantic request/response 모델이 엄격하게 금지하는 조합도 이 표현 안에서는 유지될 수 있어야 한다. 그래야 Mutator가 parser robustness 테스트에 필요한 입력을 만들 수 있다.

### 4.7 `EditablePacketBytes`
`EditablePacketBytes`는 byte-based mutation을 위한 편집 가능한 바이트 표현이다. 이 객체는 최종 전송 직전의 bytes 시퀀스를 보존하고, bit flip, byte overwrite, insertion, deletion, truncation, delimiter 변조 같은 연산을 적용할 수 있어야 한다.

이 객체는 더 이상 "SIP 문법을 이해하는 구조"가 아니다. 일부 전략에서는 여전히 start-line이나 CRLF 경계를 참고할 수 있지만, byte 계층의 핵심은 문법 유효성보다 바이트열 자체를 손상시킬 수 있다는 점이다. 따라서 이 표현은 결과가 더 이상 사람이 읽을 수 있는 SIP가 아니어도 허용해야 한다.

### 4.8 `MutatorCLI`
`MutatorCLI`는 Typer 기반 사용자 인터페이스 계층이다. 이 계층은 `SIPMutator` 본체를 감싸는 얇은 어댑터로 구현하며, baseline packet을 얻는 두 가지 경로를 모두 지원해야 한다.

첫째, `packet input mode`는 Generator CLI가 출력한 JSON을 stdin 또는 파일에서 읽어 packet을 복원한 뒤 변조하는 방식이다. 이 경로는 유닉스 파이프라인과 저장된 baseline 재사용에 적합하다.

둘째, `generate-and-mutate mode`는 CLI 내부에서 `SIPGenerator.generate_request(...)` 또는 `SIPGenerator.generate_response(...)`를 직접 호출해 baseline을 만든 뒤 바로 변조하는 방식이다. 이 경로는 사용자가 request/response 종류와 generator 옵션만 넘기면 한 번에 결과를 볼 수 있게 해 준다.

## 5. `SIPMutator`의 공개 메서드

### 5.1 `mutate(packet, config, context=None)`
이 메서드는 baseline `SIPRequest` 또는 `SIPResponse`, `MutationConfig`, 선택적인 `DialogContext`를 받아 전체 변조를 수행한다. 내부적으로는 먼저 해당 packet의 catalog definition을 찾고, strategy와 layer에 맞는 target 후보를 수집한 뒤, seed 기반으로 변조 연산을 선택하여 적용한다.

이 메서드는 크게 네 가지 동작 모드를 지원해야 한다. `model` 모드에서는 model 기반 변조만 수행하고, `wire` 모드에서는 wire 기반 변조만 수행하며, `byte` 모드에서는 byte 기반 변조만 수행한다. `auto` 모드에서는 일반적으로 model 기반 변조를 먼저 적용한 뒤 필요할 경우 wire 기반 변조를 거치고, 더 공격적인 전략이 요구되면 byte 기반 변조까지 이어서 수행한다. 초기 버전의 기본값은 `auto`로 두는 것이 자연스럽다.

### 5.2 `mutate_field(packet, target, config, context=None)`
이 메서드는 baseline packet과 명시적인 `MutationTarget`을 받아 특정 위치를 직접 변조한다. 사용자는 전체 전략 기반 선택 대신 "Call-ID만 바꿔라", "From tag만 바꿔라", "Call-ID 헤더를 지워라", "34번째 byte를 뒤집어라" 같은 식으로 target을 직접 지정할 수 있어야 한다.

이 메서드는 targeted mutation API이므로, 전체 변조보다 더 예측 가능한 동작을 제공해야 한다. 대신 target이 주어진 layer와 맞지 않거나, 해당 packet에 존재하지 않는 위치를 가리키거나, 현재 strategy에서 허용하지 않는 operator를 요구하는 경우에는 명시적으로 실패해야 한다.

## 6. `SIPMutator`의 내부 메서드
초기 구현에서는 별도 `MutationOperatorRegistry` 클래스를 먼저 도입하기보다, target 수집과 operator dispatch를 `SIPMutator` 내부 private 메서드로 두는 방식을 기본안으로 삼는다. 이 방식이면 클래스 수를 과도하게 늘리지 않으면서도 책임 경계를 유지할 수 있다.

내부 메서드는 다음 역할을 나눠 갖는다.

### 6.1 definition 해석과 target 수집
- `_resolve_packet_definition(packet)`
- `_collect_model_targets(packet, definition)`
- `_collect_wire_targets(editable_message, definition)`
- `_collect_byte_targets(editable_bytes)`
- `_normalize_target_name(target)`

이 메서드들은 packet이 request인지 response인지 판별하고, catalog metadata와 field descriptor를 바탕으로 어떤 위치가 변조 가능한지 목록을 만든다. 또한 `From`, `from`, `from_`, `Call-ID`, `byte[10]` 같은 다양한 입력 표기를 내부 target 표현으로 정규화한다.

### 6.2 model layer 변조
- `_mutate_model(packet, config, context)`
- `_apply_model_operator(packet, target, operator, rng)`
- `_validate_model_result(packet)`

이 메서드들은 Pydantic 모델과 그 내부 필드를 기준으로 값을 변조한다. 이 단계에서는 가능한 한 packet이 여전히 구조화된 모델로 유지되도록 하는 것이 초기 구현에 유리하다. 예를 들어 URI 일부 교체, tag 변경, `Max-Forwards` 축소, `Reason-Phrase` 변경, `CSeq` 값 조정 같은 연산이 여기에 속한다.

### 6.3 wire layer 변조
- `_to_editable_message(packet)`
- `_mutate_wire(editable_message, config)`
- `_apply_wire_operator(editable_message, target, operator, rng)`
- `_finalize_wire_message(editable_message)`

이 메서드들은 packet을 wire 편집 표현으로 변환한 뒤, 헤더 삭제, 중복, 순서 변경, 잘못된 헤더명 삽입, start-line 손상, Content-Length 불일치 같은 구조 변조를 수행한다. 이 단계에서는 최종 결과가 더 이상 Pydantic 모델로 표현되지 않아도 된다.

### 6.4 byte layer 변조
- `_to_packet_bytes(editable_message)`
- `_mutate_bytes(editable_bytes, config)`
- `_apply_byte_operator(editable_bytes, target, operator, rng)`
- `_finalize_packet_bytes(editable_bytes)`

이 메서드들은 wire 표현을 bytes로 변환한 뒤, bit flip, byte overwrite, byte insertion, byte deletion, truncation, delimiter 손상, 비정상 인코딩 바이트 주입 같은 연산을 수행한다. 이 단계의 결과는 더 이상 SIP 메시지로 해석되지 않을 수도 있으며, 바로 그 점이 byte mutation의 핵심 목적이다.

### 6.5 기록과 재현성
- `_rng_from_seed(seed)`
- `_record_mutation(...)`
- `_snapshot_context(context)`

이 메서드들은 하나의 mutation run이 어떤 random 흐름을 탔는지, 어떤 before/after가 있었는지, context가 어떻게 달라졌는지를 정리해 `MutationRecord`와 `MutatedCase`에 반영한다. 재현성을 위해서는 seed뿐 아니라 mutation chain 자체도 구조적으로 남겨야 한다.

## 7. 입력과 출력
Mutator는 네 종류의 입력을 사용한다.

첫째, baseline `SIPRequest` 또는 `SIPResponse`다. 이 입력은 일반적으로 Generator가 생성한 정상 패킷이며, Mutator가 직접 shell로 CLI를 호출해 얻는 결과가 아니라 애플리케이션 서비스 호출 결과를 전제로 한다.

둘째, 선택적인 `DialogContext`다. 이는 Call-ID, local/remote tag, CSeq, request URI, route set 같은 상태 의존 필드 변조에 사용된다. Mutator는 context를 참조할 수 있어야 하지만, 원본 context를 직접 파괴하지 않도록 스냅샷이나 복사 전략을 고려해야 한다.

셋째, `MutationConfig`다. 이 입력은 seed, strategy, layer, 최대 연산 수, target 제한 같은 변조 제어 정보를 제공한다.

넷째, 선택적인 `MutationTarget` 또는 operator 힌트다. 이는 targeted mutation에서 사용된다.

CLI 관점에서는 여기에 추가로 두 종류의 baseline 입력 경로가 존재한다. 하나는 Generator CLI 출력 JSON을 읽는 입력이고, 다른 하나는 CLI 내부에서 `SIPGenerator`를 호출해 만든 baseline이다. 하지만 이 차이는 CLI 어댑터 계층의 차이일 뿐, `SIPMutator`가 받는 핵심 입력 계약 자체를 바꾸지는 않는다.

출력은 항상 `MutatedCase`다. model-based mutation 결과는 보통 `mutated_packet`이 채워진다. wire-based mutation 결과는 `editable_message` 또는 최종 wire text가 핵심 결과가 되며, byte-based mutation 결과는 최종 bytes artifact가 핵심 결과가 된다. 이 경우 `mutated_packet`은 비어 있을 수 있고, byte 결과는 더 이상 사람이 읽는 SIP 텍스트가 아닐 수 있다. 중요한 것은 Mutator의 산출물이 "단순 문자열"이 아니라, 원본/결과/적용 연산/seed를 함께 담은 재현 가능한 케이스 객체라는 점이다.

## 8. 변조 절차
Mutator의 내부 동작은 아래 순서를 따른다.

1. baseline packet, `MutationConfig`, 선택적인 `DialogContext`와 `MutationTarget`을 받는다.
2. packet 타입과 catalog definition을 해석한다.
3. target 이름을 내부 표현으로 정규화한다.
4. 원본 packet과 context를 복사하거나 스냅샷한다.
5. strategy와 seed를 바탕으로 model layer target과 operator를 선택한다.
6. model 기반 변조를 적용하고 필요 시 모델 유효성을 점검한다.
7. 설정이 `wire`, `byte`, `auto`를 요구하면 현재 결과를 `EditableSIPMessage`로 변환한다.
8. wire target과 operator를 선택해 구조 변조를 적용한다.
9. 설정이 `byte` 또는 `auto`를 요구하면 현재 결과를 bytes로 변환한다.
10. byte target과 operator를 선택해 bit/byte 수준 변조를 적용한다.
11. 적용된 연산을 `MutationRecord`로 축적한다.
12. 최종 `MutatedCase`를 반환한다.

이 순서를 지키면 "어떤 baseline에서 출발했는지", "어떤 연산이 먼저 적용되었는지", "어느 시점에서 모델 공간을 벗어났는지", "어느 시점에서 텍스트 수준조차 벗어났는지"가 명확해진다. 이는 이후 Sender, Oracle, 결과 저장 계층이 동일한 테스트 케이스를 재현하는 데 중요하다.

## 9. CLI와의 경계
Mutator는 **Typer 기반 CLI 인터페이스를 반드시 제공해야 한다.** 다만 CLI는 `SIPMutator` 클래스 내부 책임이 아니라 별도 모듈에서 구현되는 어댑터 계층이어야 한다. CLI는 seed, strategy, target, baseline 입력 옵션 등을 파싱하고 `SIPGenerator`, `MutationConfig`, `MutationTarget`, `DialogContext`를 구성한 뒤 `SIPMutator`를 호출한다.

즉, CLI는 입출력 인터페이스이고, `SIPMutator`는 순수한 애플리케이션 서비스다. 이 분리를 유지해야 테스트에서 CLI 없이도 Mutator를 직접 검증할 수 있고, 추후 Controller나 campaign 실행 계층이 같은 서비스를 재사용하기 쉬워진다.

Mutator CLI는 최소한 아래 두 가지 사용자 흐름을 모두 지원해야 한다.

### 9.1 packet input mode
이 모드는 Generator CLI가 출력한 JSON baseline을 그대로 받아 변조 결과를 보여주는 방식이다. 입력 경로는 stdin, 파일, 또는 JSON 문자열 옵션 중 하나가 될 수 있다. 핵심은 사용자가 아래와 같은 흐름을 사용할 수 있어야 한다는 점이다.

- `fuzzer request ... | fuzzer mutate packet ...`
- `fuzzer response ... > baseline.json` 후 `fuzzer mutate packet --input baseline.json ...`

이 모드에서 CLI는 packet 복원, layer/strategy 설정 해석, 변조 결과 출력 역할만 담당한다. baseline 생성 자체는 이미 끝난 상태라고 본다.

### 9.2 generate-and-mutate mode
이 모드는 Mutator CLI가 내부적으로 `SIPGenerator`를 호출해 baseline을 만든 뒤 즉시 변조하는 방식이다. request baseline 생성 흐름과 response baseline 생성 흐름을 모두 지원해야 한다. 예를 들어 request method 또는 response status code/related method를 받아 baseline을 만든 뒤, 곧바로 변조 결과를 출력하는 식이다.

이 모드는 shell pipeline 없이 한 번에 baseline 생성과 변조를 수행하려는 사용자에게 적합하다. 또한 이 경로는 Generator CLI JSON 포맷에 의존하지 않고, 애플리케이션 서비스 호출 기준으로 직접 동작한다는 장점이 있다.

### 9.3 CLI 출력 원칙
Mutator CLI는 최소한 다음 정보를 보여줄 수 있어야 한다.

- 원본 baseline packet 또는 그 요약
- 변조 결과 packet / wire text / bytes artifact
- 적용된 strategy와 seed
- 적용된 mutation record 목록 또는 요약

출력 포맷은 JSON을 기본으로 두는 것이 안전하다. 다만 wire/byte layer 결과를 사람이 빠르게 확인할 수 있도록 pretty text 출력 모드를 추가할 수 있다.

### 9.4 CLI 옵션 노출 원칙
Mutator CLI는 사용자가 실제로 조작할 수 있는 옵션을 제공해야 한다. 다만 모든 내부 helper나 operator dispatch 세부사항을 그대로 노출하기보다는, **기본 옵션**, **고급 옵션**, **내부 전용 설정**을 구분하는 것이 바람직하다.

기본적으로 사용자에게 바로 노출해야 하는 옵션은 다음과 같다.

- `--strategy`
- `--layer`
- `--seed`
- `--target`
- `--max-operations`
- baseline 입력 방식 관련 옵션
- 출력 포맷 관련 옵션

필요 시 고급 사용자에게 추가로 노출할 수 있는 옵션은 다음과 같다.

- `--operator`
- `--byte-offset`
- `--byte-range`
- `--preserve-valid-model`
- operator allowlist / denylist

반면 내부 메서드 이름, catalog 탐색 구현 세부사항, operator dispatch의 private 규칙 같은 것은 CLI에 직접 노출하지 않는 것이 맞다. CLI는 연구자와 사용자가 제어할 수 있는 표면을 제공하되, core 내부 구현 상세를 그대로 반영하는 디버그 콘솔이 되어서는 안 된다.

추후 `pyproject.toml`에 `fuzzer mutate` 또는 이에 준하는 엔트리포인트를 추가할 수 있지만, 이는 항상 `SIPMutator` 본체보다 마지막 단계에 둔다.

## 10. 범위에 포함하지 않는 것
본 문서 기준 Mutator 범위에는 아래 항목을 넣지 않는다.

- baseline 정상 패킷을 처음부터 생성하는 로직
- 실제 네트워크 전송
- 응답 수집과 타임아웃 처리
- crash/ANR/oracle 판정
- 캠페인 스케줄링과 병렬 실행 제어
- 범용 SIP parser/serializer 제품을 만드는 일
- baseline 없이 순수 랜덤 바이트 스트림을 처음부터 생성하는 일

다만 wire-based mutation을 위해 **변조 가능한 wire 표현 또는 최종 mutation artifact를 만드는 최소한의 직렬화/편집 기능**은 Mutator 범위에 포함한다. 또한 byte-based mutation을 위해 bytes 직렬화 이후의 bit/byte 변조 기능도 Mutator 범위에 포함한다. 즉, Mutator는 sender가 바로 전송 가능한 입력을 만들어 줄 수 있어야 하지만, 전송 그 자체의 책임까지 가져가지는 않는다.

## 11. 초기 구현 우선순위
초기 구현은 다음 순서로 진행한다.

1. `src/volte_mutation_fuzzer/mutator/contracts.py`를 먼저 만든다.
   이 파일 안에서는 `MutationConfig` -> `MutationTarget` -> `MutationRecord` -> `MutatedCase` 순서로 정의한다.
   가장 먼저 고정해야 하는 것은 Mutator의 입력 계약과 결과 계약이며, 이 경계가 먼저 잡혀야 `SIPMutator`의 공개 API도 흔들리지 않는다.
2. `src/volte_mutation_fuzzer/mutator/core.py`를 만든다.
   이 파일 안에서는 `SIPMutator.__init__` -> `mutate` -> `mutate_field` 순서로 작업한다.
   먼저 외부 공개 메서드 시그니처를 고정한 뒤, 내부 구현을 채우는 방식으로 진행한다.
3. 같은 `src/volte_mutation_fuzzer/mutator/core.py` 안에서 model mutation 경로를 먼저 완성한다.
   구현 순서는 `_resolve_packet_definition` -> `_collect_model_targets` -> `_apply_model_operator` -> `_mutate_model` 순서로 둔다.
   model 경로가 먼저 안정돼야 wire/byte 쪽에서도 baseline 선택과 기록 흐름을 재사용할 수 있다.
4. 이어서 같은 `src/volte_mutation_fuzzer/mutator/core.py` 안에서 재현성/기록 로직을 붙인다.
   구현 순서는 `_rng_from_seed` -> `_record_mutation` -> `_snapshot_context` 정도로 둔다.
   Mutator는 값 변경 자체보다 재현 가능한 기록이 더 중요하므로, operator를 늘리기 전에 기록 구조를 먼저 고정하는 편이 안전하다.
5. `src/volte_mutation_fuzzer/mutator/editable.py`를 만든다.
   이 파일 안에서는 `EditableSIPMessage`와 `EditablePacketBytes` 및 필요한 보조 타입을 정의한다.
   구현 순서는 start-line 표현 -> ordered header 표현 -> body/Content-Length 표현 -> bytes buffer 표현 순으로 둔다.
6. 다시 `src/volte_mutation_fuzzer/mutator/core.py`로 돌아와 wire mutation 경로를 구현한다.
   구현 순서는 `_to_editable_message` -> `_collect_wire_targets` -> `_apply_wire_operator` -> `_mutate_wire` -> `_finalize_wire_message` 순서로 둔다.
   wire 경로는 model 경로보다 더 공격적인 입력을 다루므로, baseline/기록 구조가 먼저 정리된 뒤 붙이는 편이 안전하다.
7. 이어서 같은 `src/volte_mutation_fuzzer/mutator/core.py` 안에서 byte mutation 경로를 구현한다.
   구현 순서는 `_to_packet_bytes` -> `_collect_byte_targets` -> `_apply_byte_operator` -> `_mutate_bytes` -> `_finalize_packet_bytes` 순서로 둔다.
   byte 경로는 가장 공격적인 입력을 다루므로 항상 model/wire 흐름과 결과 기록이 먼저 정리된 뒤 붙이는 편이 안전하다.
8. `tests/mutator/test_contracts.py`를 추가한다.
   테스트 작성 순서는 `MutationConfig` 기본 동작 -> `MutationTarget` 정규화 -> `MutationRecord`/`MutatedCase` 직렬화 순서로 둔다.
9. `tests/mutator/test_core.py`를 추가한다.
   테스트 작성 순서는 request 정상 model mutation -> response 정상 model mutation -> targeted mutation -> 동일 seed 재현성 -> catalog 기반 실패 케이스 순서로 둔다.
10. `tests/mutator/test_editable.py`를 추가한다.
    테스트 작성 순서는 header 순서 유지 -> duplicate header 허용 -> required header 삭제 표현 -> Content-Length 불일치 표현 -> bytes buffer 변환 순서로 둔다.
11. `tests/mutator/test_bytes.py`를 추가한다.
    테스트 작성 순서는 bit flip 재현성 -> byte insertion/deletion -> truncation -> CRLF 손상 -> 사람이 읽을 수 없는 결과 허용 순서로 둔다.
12. `tests/mutator/test_cli.py`를 추가한다.
    테스트 작성 순서는 generator CLI JSON 입력 변조 -> 내부 generator 호출 기반 request 변조 -> 내부 generator 호출 기반 response 변조 -> 기본 옵션(`strategy`, `layer`, `seed`, `target`) 노출 검증 -> 잘못된 입력 JSON 실패 케이스 순서로 둔다.
13. 마지막으로 `src/volte_mutation_fuzzer/mutator/cli.py`를 만든다.
    이 파일 안에서는 Typer app 선언 -> packet input mode 커맨드 -> generate-and-mutate request 커맨드 -> generate-and-mutate response 커맨드 -> 필드 지정 변조 커맨드 순서로 붙인다.
    CLI는 Mutator의 핵심 책임이 아니라 가장 바깥 어댑터이므로 항상 마지막 단계에 둔다.

초기 버전에서 가장 중요한 완료 기준은 다음 다섯 가지다. 첫째, Generator가 만든 모든 request/response baseline을 Mutator가 입력으로 받을 수 있어야 한다. 둘째, 전체 변조, 필드 지정 변조, 전략 설정이라는 최소 기능을 지원해야 한다. 셋째, 동일한 baseline packet과 동일 seed에 대해 동일한 mutation chain을 재현할 수 있어야 한다. 넷째, 필요할 경우 최종 결과가 더 이상 정상 SIP 텍스트가 아니더라도 전송 가능한 bytes artifact로 내려갈 수 있어야 한다. 다섯째, Typer 기반 CLI가 generator CLI 출력 입력 모드와 내부 generator 호출 모드를 모두 지원해야 한다. 구조를 과도하게 일반화하는 것보다, 작은 공개 API와 명확한 model/wire/byte 분리 흐름을 먼저 고정하는 쪽을 우선한다.
