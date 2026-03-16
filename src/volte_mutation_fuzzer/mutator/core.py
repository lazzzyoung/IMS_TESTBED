from __future__ import annotations

from typing import TypeAlias

from volte_mutation_fuzzer.generator import DialogContext
from volte_mutation_fuzzer.mutator.contracts import (
    MutatedCase,
    MutationConfig,
    MutationTarget,
    PacketModel,
)
from volte_mutation_fuzzer.sip.catalog import SIPCatalog, SIP_CATALOG
from volte_mutation_fuzzer.sip.requests import SIPRequest, SIPRequestDefinition
from volte_mutation_fuzzer.sip.responses import SIPResponse, SIPResponseDefinition

PacketDefinition: TypeAlias = SIPRequestDefinition | SIPResponseDefinition


class SIPMutator:
    """Public mutator service boundary for request/response mutation workflows."""

    def __init__(self, catalog: SIPCatalog | None = None) -> None:
        self.catalog = SIP_CATALOG if catalog is None else catalog

    def mutate(
        self,
        packet: PacketModel,
        config: MutationConfig,
        context: DialogContext | None = None,
    ) -> MutatedCase:
        definition = self._resolve_packet_definition(packet)
        return self._mutate_packet(
            packet=packet,
            definition=definition,
            config=config,
            context=context,
            target=None,
        )

    def mutate_field(
        self,
        packet: PacketModel,
        target: MutationTarget,
        config: MutationConfig,
        context: DialogContext | None = None,
    ) -> MutatedCase:
        definition = self._resolve_packet_definition(packet)
        return self._mutate_packet(
            packet=packet,
            definition=definition,
            config=config,
            context=context,
            target=target,
        )

    def _resolve_packet_definition(self, packet: PacketModel) -> PacketDefinition:
        if isinstance(packet, SIPRequest):
            return self.catalog.get_request(packet.method)
        if isinstance(packet, SIPResponse):
            return self.catalog.get_response(packet.status_code)
        raise TypeError("packet must be a SIPRequest or SIPResponse")

    def _mutate_packet(
        self,
        *,
        packet: PacketModel,
        definition: PacketDefinition,
        config: MutationConfig,
        context: DialogContext | None,
        target: MutationTarget | None,
    ) -> MutatedCase:
        _ = packet, definition, config, context, target
        raise NotImplementedError(
            "SIPMutator execution is not implemented yet; continue in the model "
            "mutation phase."
        )


__all__ = ["PacketDefinition", "SIPMutator"]
