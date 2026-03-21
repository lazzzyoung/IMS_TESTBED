from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from volte_mutation_fuzzer.sip.common import SIPMethod
from volte_mutation_fuzzer.sip.render import PacketModel

TargetMode = Literal["softphone", "real-ue-pcscf", "real-ue-direct"]
TransportProtocol = Literal["UDP", "TCP"]
ArtifactKind = Literal["packet", "wire", "bytes"]
ObservationClass = Literal[
    "provisional",
    "success",
    "redirection",
    "client_error",
    "server_error",
    "global_error",
    "invalid",
]
DeliveryOutcome = Literal[
    "provisional",
    "success",
    "error",
    "timeout",
    "send_error",
    "invalid_response",
]


class CorrelationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    call_id: str | None = None
    cseq_method: SIPMethod | None = None
    cseq_sequence: int | None = Field(default=None, ge=0)


class TargetEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: TargetMode = "softphone"
    host: str = Field(min_length=1)
    port: int = Field(default=5060, ge=1, le=65535)
    transport: TransportProtocol = "UDP"
    timeout_seconds: float = Field(default=2.0, gt=0.0, le=60.0)
    label: str | None = None

    @field_validator("host", "label", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("transport", mode="before")
    @classmethod
    def _normalize_transport(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class SendArtifact(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, arbitrary_types_allowed=True
    )

    packet: PacketModel | None = None
    wire_text: str | None = None
    packet_bytes: bytes | None = None

    @classmethod
    def from_packet(cls, packet: PacketModel) -> "SendArtifact":
        return cls(packet=packet)

    @classmethod
    def from_wire_text(cls, wire_text: str) -> "SendArtifact":
        return cls(wire_text=wire_text)

    @classmethod
    def from_packet_bytes(cls, packet_bytes: bytes) -> "SendArtifact":
        return cls(packet_bytes=packet_bytes)

    @computed_field
    @property
    def artifact_kind(self) -> ArtifactKind:
        if self.packet is not None:
            return "packet"
        if self.wire_text is not None:
            return "wire"
        return "bytes"

    @model_validator(mode="after")
    def _ensure_exactly_one_artifact(self) -> "SendArtifact":
        artifact_count = sum(
            1
            for item in (self.packet, self.wire_text, self.packet_bytes)
            if item is not None
        )
        if artifact_count != 1:
            raise ValueError(
                "exactly one of packet, wire_text, packet_bytes must be set"
            )
        return self


class SocketObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    source: Literal["socket"] = "socket"
    remote_host: str | None = None
    remote_port: int | None = Field(default=None, ge=0, le=65535)
    status_code: int | None = Field(default=None, ge=100, le=699)
    reason_phrase: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    raw_text: str = ""
    raw_size: int = Field(default=0, ge=0)
    classification: ObservationClass

    @field_validator("reason_phrase", "remote_host", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None


class SendReceiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    target: TargetEndpoint
    artifact_kind: ArtifactKind
    correlation_key: CorrelationKey = Field(default_factory=CorrelationKey)
    bytes_sent: int = Field(ge=0)
    outcome: DeliveryOutcome
    responses: tuple[SocketObservation, ...] = Field(default_factory=tuple)
    send_started_at: float
    send_completed_at: float = Field(ge=0.0)
    error: str | None = None
    observer_events: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("error", mode="before")
    @classmethod
    def _normalize_error(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @computed_field
    @property
    def duration_ms(self) -> float:
        return max((self.send_completed_at - self.send_started_at) * 1000.0, 0.0)

    @computed_field
    @property
    def final_response(self) -> SocketObservation | None:
        return self.responses[-1] if self.responses else None


__all__ = [
    "ArtifactKind",
    "CorrelationKey",
    "DeliveryOutcome",
    "ObservationClass",
    "SendArtifact",
    "SendReceiveResult",
    "SocketObservation",
    "TargetEndpoint",
    "TargetMode",
    "TransportProtocol",
]
