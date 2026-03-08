from __future__ import annotations

import unittest

from volte_mutation_fuzzer.generator import (
    DialogContext,
    GeneratorSettings,
    RequestSpec,
    ResponseSpec,
    SIPGenerator,
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


if __name__ == "__main__":
    unittest.main()
