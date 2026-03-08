from __future__ import annotations

import unittest

from volte_mutation_fuzzer.generator import GeneratorSettings


class GeneratorSettingsTests(unittest.TestCase):
    def test_from_env_uses_defaults_when_env_is_empty(self) -> None:
        settings = GeneratorSettings.from_env({})

        self.assertEqual(settings.target_ue_name, "UE")
        self.assertEqual(settings.via_host, "proxy.example.com")
        self.assertEqual(settings.via_port, 5060)
        self.assertEqual(settings.transport, "UDP")
        self.assertEqual(settings.user_agent, "volte-mutation-fuzzer/0.1.0")
        self.assertEqual(settings.from_user, "remote")
        self.assertEqual(settings.to_user, "ue")
        self.assertEqual(settings.request_uri_user, "ue")

    def test_from_env_reads_prefixed_values_and_normalizes_text(self) -> None:
        settings = GeneratorSettings.from_env(
            {
                "VMF_GENERATOR_TARGET_UE_NAME": " Pixel-9-Pro ",
                "VMF_GENERATOR_VIA_HOST": " ims.example.net ",
                "VMF_GENERATOR_VIA_PORT": " 5080 ",
                "VMF_GENERATOR_TRANSPORT": " tls-sctp ",
                "VMF_GENERATOR_USER_AGENT": " fuzz/0.2 ",
                "VMF_GENERATOR_FROM_DISPLAY_NAME": " P-CSCF ",
                "VMF_GENERATOR_FROM_USER": " scscf ",
                "VMF_GENERATOR_FROM_HOST": " ims.example.net ",
                "VMF_GENERATOR_TO_DISPLAY_NAME": " Victim UE ",
                "VMF_GENERATOR_TO_USER": " ue001 ",
                "VMF_GENERATOR_TO_HOST": " device.example.net ",
                "VMF_GENERATOR_REQUEST_URI_USER": " ue001 ",
                "VMF_GENERATOR_REQUEST_URI_HOST": " device.example.net ",
                "VMF_GENERATOR_CONTACT_DISPLAY_NAME": " ",
                "VMF_GENERATOR_CONTACT_USER": " proxy-contact ",
                "VMF_GENERATOR_CONTACT_HOST": " edge.example.net ",
                "VMF_GENERATOR_CONTACT_PORT": " 5090 ",
            }
        )

        self.assertEqual(settings.target_ue_name, "Pixel-9-Pro")
        self.assertEqual(settings.via_host, "ims.example.net")
        self.assertEqual(settings.via_port, 5080)
        self.assertEqual(settings.transport, "TLS-SCTP")
        self.assertEqual(settings.user_agent, "fuzz/0.2")
        self.assertEqual(settings.from_display_name, "P-CSCF")
        self.assertEqual(settings.to_display_name, "Victim UE")
        self.assertEqual(settings.request_uri_host, "device.example.net")
        self.assertIsNone(settings.contact_display_name)
        self.assertEqual(settings.contact_user, "proxy-contact")
        self.assertEqual(settings.contact_host, "edge.example.net")
        self.assertEqual(settings.contact_port, 5090)

    def test_from_env_rejects_blank_required_string(self) -> None:
        with self.assertRaises(ValueError):
            GeneratorSettings.from_env({"VMF_GENERATOR_VIA_HOST": "   "})


if __name__ == "__main__":
    unittest.main()
