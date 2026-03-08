from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeneratorSettings(BaseModel):
    """Environment-backed defaults consumed by the SIP generator service."""

    model_config = ConfigDict(extra="forbid")

    ENV_PREFIX: ClassVar[str] = "VMF_GENERATOR_"
    _INT_ENV_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "via_port",
            "from_port",
            "to_port",
            "request_uri_port",
            "contact_port",
        }
    )

    target_ue_name: str = Field(default="UE", min_length=1)
    via_host: str = Field(default="proxy.example.com", min_length=1)
    via_port: int | None = Field(default=5060, ge=1, le=65535)
    transport: str = Field(default="UDP", min_length=1)
    user_agent: str = Field(default="volte-mutation-fuzzer/0.1.0", min_length=1)

    from_display_name: str | None = "Remote"
    from_user: str = Field(default="remote", min_length=1)
    from_host: str = Field(default="example.com", min_length=1)
    from_port: int | None = Field(default=None, ge=1, le=65535)

    to_display_name: str | None = "UE"
    to_user: str = Field(default="ue", min_length=1)
    to_host: str = Field(default="example.com", min_length=1)
    to_port: int | None = Field(default=None, ge=1, le=65535)

    request_uri_user: str | None = "ue"
    request_uri_host: str = Field(default="example.com", min_length=1)
    request_uri_port: int | None = Field(default=None, ge=1, le=65535)

    contact_display_name: str | None = None
    contact_user: str | None = None
    contact_host: str | None = None
    contact_port: int | None = Field(default=None, ge=1, le=65535)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        prefix: str | None = None,
    ) -> "GeneratorSettings":
        """Load generator defaults from an env mapping or the process env."""

        source = os.environ if env is None else env
        env_prefix = cls.ENV_PREFIX if prefix is None else prefix
        payload: dict[str, Any] = {}

        for field_name in cls.model_fields:
            env_key = f"{env_prefix}{field_name}".upper()
            raw_value = source.get(env_key)
            if raw_value is None:
                continue
            payload[field_name] = cls._parse_env_value(field_name, raw_value)

        return cls.model_validate(payload)

    @classmethod
    def _parse_env_value(cls, field_name: str, raw_value: str) -> Any:
        value = raw_value.strip()
        if value == "":
            return None
        if field_name in cls._INT_ENV_FIELDS:
            return int(value)
        return value

    @field_validator(
        "target_ue_name",
        "via_host",
        "transport",
        "user_agent",
        "from_display_name",
        "from_user",
        "from_host",
        "to_display_name",
        "to_user",
        "to_host",
        "request_uri_user",
        "request_uri_host",
        "contact_display_name",
        "contact_user",
        "contact_host",
        mode="before",
    )
    @classmethod
    def _normalize_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("transport")
    @classmethod
    def _normalize_transport(cls, value: str) -> str:
        return value.upper()
