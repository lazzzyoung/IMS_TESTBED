from __future__ import annotations

import unittest

from volte_mutation_fuzzer.generator import (
    DialogContext,
    GeneratorSettings,
    RequestSpec,
    ResponseSpec,
    SIPGenerator,
)
from volte_mutation_fuzzer.mutator.contracts import MutationConfig, MutationTarget
from volte_mutation_fuzzer.mutator.core import SIPMutator
from volte_mutation_fuzzer.sip.catalog import SIPCatalog, SIP_CATALOG
from volte_mutation_fuzzer.sip.common import SIPMethod
from volte_mutation_fuzzer.sip.requests import SIPRequestDefinition
from volte_mutation_fuzzer.sip.responses import SIPResponseDefinition


class SIPMutatorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = SIPGenerator(GeneratorSettings())

    def build_request(self):
        return self.generator.generate_request(RequestSpec(method=SIPMethod.OPTIONS))

    def build_response(self):
        context = DialogContext(
            call_id="call-1",
            local_tag="ue-tag",
            local_cseq=7,
        )
        return self.generator.generate_response(
            ResponseSpec(status_code=200, related_method=SIPMethod.INVITE),
            context,
        )


class SIPMutatorInitTests(SIPMutatorTestCase):
    def test_init_uses_default_catalog(self) -> None:
        mutator = SIPMutator()

        self.assertIs(mutator.catalog, SIP_CATALOG)

    def test_init_accepts_custom_catalog(self) -> None:
        custom_catalog = SIPCatalog(
            request_definitions=SIP_CATALOG.request_definitions,
            response_definitions=SIP_CATALOG.response_definitions,
        )

        mutator = SIPMutator(catalog=custom_catalog)

        self.assertIs(mutator.catalog, custom_catalog)


class SIPMutatorDefinitionResolutionTests(SIPMutatorTestCase):
    def test_resolve_packet_definition_returns_request_definition(self) -> None:
        mutator = SIPMutator()
        packet = self.build_request()

        definition = mutator._resolve_packet_definition(packet)
        assert isinstance(definition, SIPRequestDefinition)

        self.assertEqual(definition.method, SIPMethod.OPTIONS)
        self.assertEqual(definition.model_name, packet.__class__.__name__)

    def test_resolve_packet_definition_returns_response_definition(self) -> None:
        mutator = SIPMutator()
        packet = self.build_response()

        definition = mutator._resolve_packet_definition(packet)
        assert isinstance(definition, SIPResponseDefinition)

        self.assertEqual(definition.status_code, 200)
        self.assertEqual(definition.model_name, packet.__class__.__name__)


class SIPMutatorPublicAPITests(SIPMutatorTestCase):
    def test_mutate_raises_explicit_not_implemented_error(self) -> None:
        mutator = SIPMutator()
        packet = self.build_request()

        with self.assertRaisesRegex(NotImplementedError, "not implemented yet"):
            mutator.mutate(packet, MutationConfig())

    def test_mutate_field_raises_explicit_not_implemented_error(self) -> None:
        mutator = SIPMutator()
        packet = self.build_request()
        target = MutationTarget(layer="model", path="call_id")

        with self.assertRaisesRegex(NotImplementedError, "not implemented yet"):
            mutator.mutate_field(packet, target, MutationConfig())


if __name__ == "__main__":
    unittest.main()
