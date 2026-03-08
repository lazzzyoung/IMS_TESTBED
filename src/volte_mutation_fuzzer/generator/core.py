from __future__ import annotations

from uuid import uuid4
from typing import Any

from volte_mutation_fuzzer.generator.contracts import (
    DialogContext,
    GeneratorSettings,
    RequestSpec,
    ResponseSpec,
)
from volte_mutation_fuzzer.sip.catalog import SIPCatalog, SIP_CATALOG
from volte_mutation_fuzzer.sip.common import (
    CSeqHeader,
    EventHeader,
    NameAddress,
    RAckHeader,
    SIPMethod,
    SIPURI,
    SubscriptionStateHeader,
    URIReference,
    ViaHeader,
)
from volte_mutation_fuzzer.sip.requests import REQUEST_MODELS_BY_METHOD, SIPRequest
from volte_mutation_fuzzer.sip.responses import SIPResponse


class SIPGenerator:
    """Orchestrates request/response model generation from generator contracts."""

    def __init__(
        self,
        settings: GeneratorSettings,
        *,
        catalog: SIPCatalog | None = None,
    ) -> None:
        self.settings = settings
        self.catalog = SIP_CATALOG if catalog is None else catalog

    def generate_request(
        self,
        spec: RequestSpec,
        context: DialogContext | None = None,
    ) -> SIPRequest:
        raise NotImplementedError("request generation is not implemented yet")

    def generate_response(
        self,
        spec: ResponseSpec,
        context: DialogContext,
    ) -> SIPResponse:
        raise NotImplementedError("response generation is not implemented yet")

    def _resolve_request_model(self, spec: RequestSpec) -> type[SIPRequest]:
        try:
            definition = self.catalog.get_request(spec.method)
        except StopIteration as exc:
            raise ValueError(
                f"request method {spec.method} is not present in the SIP catalog"
            ) from exc

        try:
            model = REQUEST_MODELS_BY_METHOD[spec.method]
        except KeyError as exc:
            raise ValueError(
                f"request method {spec.method} does not have a registered SIP model"
            ) from exc

        if model.__name__ != definition.model_name:
            raise ValueError(
                f"request model mismatch for {spec.method}: "
                f"catalog expects {definition.model_name}, "
                f"mapping provides {model.__name__}"
            )

        return model

    def _resolve_response_model(self, spec: ResponseSpec) -> type[SIPResponse]:
        raise NotImplementedError

    def _build_request_defaults(
        self,
        spec: RequestSpec,
        context: DialogContext | None = None,
    ) -> dict[str, Any]:
        model = self._resolve_request_model(spec)
        request_uri = self._build_request_uri(context)

        defaults: dict[str, Any] = {
            "method": spec.method,
            "request_uri": request_uri,
            "sip_version": "SIP/2.0",
            "via": [self._build_via()],
            "max_forwards": 70,
            "from_": self._build_from(context),
            "to": self._build_to(context),
            "call_id": self._build_call_id(context),
            "cseq": self._build_cseq(spec.method, context),
            "user_agent": self.settings.user_agent,
            "content_length": 0,
        }

        if context is not None and context.route_set:
            defaults["route"] = list(context.route_set)

        if spec.method in {
            SIPMethod.INVITE,
            SIPMethod.NOTIFY,
            SIPMethod.REFER,
            SIPMethod.SUBSCRIBE,
            SIPMethod.UPDATE,
        }:
            defaults["contact"] = [self._build_contact()]

        if spec.method == SIPMethod.NOTIFY:
            defaults["event"] = self._build_event_header()
            defaults["subscription_state"] = SubscriptionStateHeader(
                state="active",
                expires=3600,
            )

        if spec.method == SIPMethod.PRACK:
            defaults["rack"] = RAckHeader(
                response_num=1,
                cseq_num=max(context.local_cseq, 1) if context is not None else 1,
                method=SIPMethod.INVITE,
            )

        if spec.method == SIPMethod.PUBLISH:
            defaults["event"] = self._build_event_header()

        if spec.method == SIPMethod.REFER:
            defaults["refer_to"] = NameAddress(
                display_name=self.settings.target_ue_name,
                uri=request_uri,
            )

        if spec.method == SIPMethod.SUBSCRIBE:
            defaults["event"] = self._build_event_header()

        if "contact" in model.model_fields and model.model_fields["contact"].is_required():
            defaults.setdefault("contact", [self._build_contact()])

        return defaults

    def _build_response_defaults(
        self,
        spec: ResponseSpec,
        context: DialogContext,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _apply_overrides(
        self,
        defaults: dict[str, Any],
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _validate_preconditions(
        self,
        *,
        context: DialogContext | None,
        preconditions: tuple[str, ...],
    ) -> None:
        raise NotImplementedError

    def _build_via(self) -> ViaHeader:
        return ViaHeader(
            transport=self.settings.transport,
            host=self.settings.via_host,
            port=self.settings.via_port,
            branch=f"z9hG4bK-{uuid4().hex}",
        )

    def _build_from(self, context: DialogContext | None) -> NameAddress:
        remote_tag = context.remote_tag if context is not None else None
        if remote_tag is None:
            remote_tag = self._new_tag()
            if context is not None:
                context.remote_tag = remote_tag

        return NameAddress(
            display_name=self.settings.from_display_name,
            uri=SIPURI(
                scheme="sip",
                user=self.settings.from_user,
                host=self.settings.from_host,
                port=self.settings.from_port,
            ),
            parameters={"tag": remote_tag},
        )

    def _build_to(self, context: DialogContext | None) -> NameAddress:
        parameters: dict[str, str | None] = {}
        if context is not None and context.local_tag is not None:
            parameters["tag"] = context.local_tag

        return NameAddress(
            display_name=self.settings.to_display_name,
            uri=SIPURI(
                scheme="sip",
                user=self.settings.to_user,
                host=self.settings.to_host,
                port=self.settings.to_port,
            ),
            parameters=parameters,
        )

    def _build_contact(self) -> NameAddress:
        has_contact_override = any(
            value is not None
            for value in (
                self.settings.contact_display_name,
                self.settings.contact_user,
                self.settings.contact_host,
                self.settings.contact_port,
            )
        )

        return NameAddress(
            display_name=(
                self.settings.contact_display_name
                if has_contact_override
                else self.settings.from_display_name
            ),
            uri=SIPURI(
                scheme="sip",
                user=self.settings.contact_user or self.settings.from_user,
                host=self.settings.contact_host or self.settings.from_host,
                port=(
                    self.settings.contact_port
                    if has_contact_override
                    else self.settings.from_port
                ),
            ),
        )

    def _build_call_id(self, context: DialogContext | None) -> str:
        if context is not None and context.call_id is not None:
            return context.call_id

        call_id = f"{uuid4().hex}@{self.settings.from_host}"
        if context is not None:
            context.call_id = call_id
        return call_id

    def _build_cseq(
        self,
        method: SIPMethod,
        context: DialogContext | None,
    ) -> CSeqHeader:
        sequence = 1 if context is None else context.next_remote_cseq()
        return CSeqHeader(sequence=sequence, method=method)

    def _build_request_uri(
        self,
        context: DialogContext | None,
    ) -> URIReference:
        if context is not None and context.request_uri is not None:
            return context.request_uri

        request_uri = SIPURI(
            scheme="sip",
            user=self.settings.request_uri_user,
            host=self.settings.request_uri_host,
            port=self.settings.request_uri_port,
        )
        if context is not None:
            context.request_uri = request_uri
        return request_uri

    def _build_event_header(self) -> EventHeader:
        return EventHeader(package="presence")

    def _new_tag(self) -> str:
        return uuid4().hex[:16]
