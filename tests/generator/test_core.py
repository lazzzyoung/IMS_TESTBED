from __future__ import annotations

import unittest

from volte_mutation_fuzzer.generator import (
    DialogContext,
    GeneratorSettings,
    RequestSpec,
    ResponseSpec,
    SIPGenerator,
)
from volte_mutation_fuzzer.sip.catalog import SIPCatalog, SIP_CATALOG
from volte_mutation_fuzzer.sip.common import SIPMethod, SIPURI
from volte_mutation_fuzzer.sip.requests import (
    REQUEST_MODELS_BY_METHOD,
    InviteRequest,
    OptionsRequest,
)


class SIPGeneratorSignatureTests(unittest.TestCase):
    def test_init_sets_settings_and_uses_default_catalog(self) -> None:
        settings = GeneratorSettings()

        generator = SIPGenerator(settings)

        self.assertIs(generator.settings, settings)
        self.assertEqual(generator.catalog.request_count, 14)
        self.assertEqual(generator.catalog.response_count, 75)

    def test_public_methods_are_stubbed_until_implementation_is_added(self) -> None:
        generator = SIPGenerator(GeneratorSettings())

        with self.assertRaises(NotImplementedError):
            generator.generate_request(RequestSpec(method="OPTIONS"))

        with self.assertRaises(NotImplementedError):
            generator.generate_response(
                ResponseSpec(status_code=100, related_method="OPTIONS"),
                DialogContext(),
            )

    def test_resolve_request_model_returns_registered_request_type(self) -> None:
        generator = SIPGenerator(GeneratorSettings())

        self.assertIs(
            generator._resolve_request_model(RequestSpec(method=SIPMethod.OPTIONS)),
            OptionsRequest,
        )
        self.assertIs(
            generator._resolve_request_model(RequestSpec(method=SIPMethod.INVITE)),
            InviteRequest,
        )

    def test_resolve_request_model_rejects_catalog_model_mismatch(self) -> None:
        invite_definition = SIP_CATALOG.get_request(SIPMethod.INVITE)
        mismatched_catalog = SIPCatalog(
            request_definitions=tuple(
                invite_definition.model_copy(update={"model_name": "WrongInviteModel"})
                if definition.method == SIPMethod.INVITE
                else definition
                for definition in SIP_CATALOG.request_definitions
            ),
            response_definitions=SIP_CATALOG.response_definitions,
        )
        generator = SIPGenerator(GeneratorSettings(), catalog=mismatched_catalog)

        with self.assertRaisesRegex(ValueError, "request model mismatch"):
            generator._resolve_request_model(RequestSpec(method=SIPMethod.INVITE))

    def test_build_request_defaults_produces_valid_initial_options_payload(self) -> None:
        generator = SIPGenerator(GeneratorSettings())

        defaults = generator._build_request_defaults(RequestSpec(method=SIPMethod.OPTIONS))
        packet = OptionsRequest.model_validate(defaults)

        self.assertEqual(packet.method, SIPMethod.OPTIONS)
        self.assertEqual(packet.request_uri.host, "example.com")
        self.assertEqual(packet.cseq.sequence, 1)
        self.assertEqual(packet.cseq.method, SIPMethod.OPTIONS)
        self.assertEqual(packet.user_agent, "volte-mutation-fuzzer/0.1.0")
        self.assertEqual(packet.via[0].host, "proxy.example.com")

    def test_build_request_defaults_updates_context_for_stateful_requests(self) -> None:
        generator = SIPGenerator(GeneratorSettings())
        context = DialogContext(local_tag="ue-tag")

        defaults = generator._build_request_defaults(
            RequestSpec(method=SIPMethod.INVITE),
            context,
        )
        packet = InviteRequest.model_validate(defaults)

        self.assertIsNotNone(context.call_id)
        self.assertIsNotNone(context.remote_tag)
        self.assertEqual(context.remote_cseq, 1)
        self.assertIsInstance(context.request_uri, SIPURI)
        self.assertEqual(packet.call_id, context.call_id)
        self.assertEqual(packet.from_.parameters["tag"], context.remote_tag)
        self.assertEqual(packet.to.parameters["tag"], "ue-tag")
        self.assertEqual(packet.cseq.sequence, 1)
        self.assertEqual(len(packet.contact), 1)

    def test_build_request_defaults_cover_all_request_models(self) -> None:
        generator = SIPGenerator(GeneratorSettings())

        for method, model in REQUEST_MODELS_BY_METHOD.items():
            with self.subTest(method=method):
                context = DialogContext(
                    call_id="call-1",
                    local_tag="ue-tag",
                    remote_tag="remote-tag",
                    local_cseq=3,
                    request_uri=SIPURI(
                        scheme="sip",
                        user="ue001",
                        host="device.example.net",
                    ),
                )

                defaults = generator._build_request_defaults(
                    RequestSpec(method=method),
                    context,
                )
                packet = model.model_validate(defaults)

                self.assertEqual(packet.method, method)
                self.assertEqual(packet.cseq.method, method)


if __name__ == "__main__":
    unittest.main()
