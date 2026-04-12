import subprocess
import unittest
from unittest.mock import patch

from volte_mutation_fuzzer.sender.contracts import SendArtifact, TargetEndpoint
from volte_mutation_fuzzer.sender.real_ue import (
    IPsecSAStatus,
    RealUEDirectResolver,
    RouteCheckResult,
    check_ipsec_sa_alive,
    check_route_to_target,
    prepare_real_ue_direct_payload,
)


class RealUEDirectHelperTests(unittest.TestCase):
    def test_resolver_prefers_kamctl_contact_for_msisdn(self) -> None:
        resolver = RealUEDirectResolver(
            {
                "VMF_REAL_UE_SCSCF_CONTAINER": "scscf",
                "VMF_REAL_UE_PCSCF_CONTAINER": "pcscf",
            }
        )
        target = TargetEndpoint(mode="real-ue-direct", msisdn="222222")

        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["docker"],
                returncode=0,
                stdout=(
                    "AOR: sip:222222@ims.mnc001.mcc001.3gppnetwork.org\n"
                    "    Contact: <sip:001010000123512@10.20.20.2:5072>;expires=300\n"
                ),
                stderr="",
            ),
        ):
            resolved = resolver.resolve(target)

        self.assertEqual(resolved.host, "10.20.20.2")
        self.assertEqual(resolved.port, 5072)
        self.assertEqual(
            resolved.observer_events,
            ("resolver:scscf-kamctl:222222->10.20.20.2:5072",),
        )

    def test_check_route_to_target_uses_darwin_route_get(self) -> None:
        with (
            patch(
                "volte_mutation_fuzzer.sender.real_ue.platform.system",
                return_value="Darwin",
            ),
            patch(
                "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=["route"],
                    returncode=0,
                    stdout="route to: 10.20.20.2\ngateway: 127.0.0.1\n",
                    stderr="",
                ),
            ) as mock_run,
        ):
            result = check_route_to_target("10.20.20.2")

        self.assertEqual(result, RouteCheckResult(True, "route to: 10.20.20.2"))
        mock_run.assert_called_once()
        self.assertEqual(
            mock_run.call_args.args[0],
            ["route", "-n", "get", "10.20.20.2"],
        )

    def test_prepare_real_ue_direct_payload_rewrites_wire_routing_headers(self) -> None:
        wire_text = (
            "OPTIONS sip:ue@example.com SIP/2.0\r\n"
            "Via: SIP/2.0/UDP proxy.example.com:5060;branch=z9hG4bK-1\r\n"
            "Contact: <sip:attacker@203.0.113.10:5090>\r\n"
            "Content-Length: 0\r\n\r\n"
        )

        payload, events = prepare_real_ue_direct_payload(
            SendArtifact.from_wire_text(wire_text),
            local_host="127.0.0.1",
            local_port=43210,
        )
        rendered = payload.decode("utf-8")

        self.assertIn(
            "Via: SIP/2.0/UDP 127.0.0.1:43210;branch=z9hG4bK-1;rport",
            rendered,
        )
        self.assertIn("Contact: <sip:attacker@127.0.0.1:43210>", rendered)
        self.assertEqual(
            events,
            (
                "direct-normalization:wire:via",
                "direct-normalization:wire:contact",
            ),
        )

    def test_prepare_real_ue_direct_payload_keeps_bytes_unmodified(self) -> None:
        original = b"INVITE sip:ue@example.com SIP/2.0\r\nContent-Length: 0\r\n\r\n"
        payload, events = prepare_real_ue_direct_payload(
            SendArtifact.from_packet_bytes(original),
            local_host="127.0.0.1",
            local_port=43210,
        )

        self.assertEqual(payload, original)
        self.assertEqual(events, ("direct-normalization:bytes-unmodified",))


class IPsecSACheckTests(unittest.TestCase):
    """Tests for check_ipsec_sa_alive()."""

    _XFRM_OUTPUT_WITH_UE_SA = (
        "src 10.20.20.8 dst 172.22.0.21\n"
        "\tproto esp spi 0xc3a2b100 reqid 1 mode transport\n"
        "\tsel src 10.20.20.8/32 dst 172.22.0.21/32 sport 5100 dport 5060\n"
        "src 172.22.0.21 dst 10.20.20.8\n"
        "\tproto esp spi 0xd4b3c200 reqid 2 mode transport\n"
        "\tsel src 172.22.0.21/32 dst 10.20.20.8/32 sport 5060 dport 5100\n"
    )

    _XFRM_OUTPUT_NO_UE_SA = (
        "src 172.22.0.21 dst 172.22.0.1\n"
        "\tproto esp spi 0xaabb reqid 1 mode transport\n"
        "\tsel src 172.22.0.21/32 dst 172.22.0.1/32\n"
    )

    def test_alive_when_ue_sa_exists(self) -> None:
        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["docker"], returncode=0,
                stdout=self._XFRM_OUTPUT_WITH_UE_SA, stderr="",
            ),
        ):
            status = check_ipsec_sa_alive()
        self.assertTrue(status.alive)
        self.assertGreaterEqual(status.sa_count, 1)

    def test_not_alive_when_no_ue_sa(self) -> None:
        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["docker"], returncode=0,
                stdout=self._XFRM_OUTPUT_NO_UE_SA, stderr="",
            ),
        ):
            status = check_ipsec_sa_alive()
        self.assertFalse(status.alive)
        self.assertEqual(status.sa_count, 0)

    def test_not_alive_when_empty_output(self) -> None:
        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["docker"], returncode=0, stdout="", stderr="",
            ),
        ):
            status = check_ipsec_sa_alive()
        self.assertFalse(status.alive)

    def test_not_alive_on_command_failure(self) -> None:
        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["docker"], returncode=1, stdout="", stderr="not found",
            ),
        ):
            status = check_ipsec_sa_alive()
        self.assertFalse(status.alive)
        self.assertIn("not found", status.detail)

    def test_not_alive_on_exception(self) -> None:
        with patch(
            "volte_mutation_fuzzer.sender.real_ue.subprocess.run",
            side_effect=FileNotFoundError("docker not found"),
        ):
            status = check_ipsec_sa_alive()
        self.assertFalse(status.alive)
        self.assertIn("docker not found", status.detail)


if __name__ == "__main__":
    unittest.main()
