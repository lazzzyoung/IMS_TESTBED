from __future__ import annotations

import socket
import unittest

from volte_mutation_fuzzer.generator.contracts import GeneratorSettings, RequestSpec
from volte_mutation_fuzzer.generator.core import SIPGenerator
from volte_mutation_fuzzer.sender.contracts import SendArtifact, TargetEndpoint
from volte_mutation_fuzzer.sender.core import SIPSenderReactor
from volte_mutation_fuzzer.sip.common import SIPMethod
from tests.sender._server import TCPResponder, UDPResponder


class SIPSenderReactorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = SIPGenerator(GeneratorSettings())
        self.reactor = SIPSenderReactor()
        self.packet = self.generator.generate_request(
            RequestSpec(method=SIPMethod.OPTIONS), None
        )

    def test_send_packet_udp_returns_success_with_correlation_key(self) -> None:
        responder = UDPResponder(
            responses=(
                b"SIP/2.0 200 OK\r\n"
                b"Via: SIP/2.0/UDP proxy.example.com;branch=z9hG4bK-1\r\n"
                b"Call-ID: call-1\r\n"
                b"CSeq: 1 OPTIONS\r\n"
                b"Content-Length: 0\r\n"
                b"\r\n",
            )
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.reactor.send_packet(
            self.packet,
            TargetEndpoint(
                host=responder.host, port=responder.port, timeout_seconds=0.5
            ),
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.correlation_key.call_id, self.packet.call_id)
        self.assertEqual(result.correlation_key.cseq_method, self.packet.cseq.method)
        self.assertEqual(result.responses[-1].status_code, 200)
        self.assertGreater(result.bytes_sent, 0)
        self.assertEqual(len(responder.received_payloads), 1)

    def test_send_udp_collect_all_responses_keeps_provisional_and_final(self) -> None:
        responder = UDPResponder(
            responses=(
                b"SIP/2.0 180 Ringing\r\n"
                b"Via: SIP/2.0/UDP proxy.example.com;branch=z9hG4bK-1\r\n"
                b"Content-Length: 0\r\n"
                b"\r\n",
                b"SIP/2.0 486 Busy Here\r\n"
                b"Via: SIP/2.0/UDP proxy.example.com;branch=z9hG4bK-1\r\n"
                b"Content-Length: 0\r\n"
                b"\r\n",
            ),
            delay_seconds=0.01,
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.reactor.send_packet(
            self.packet,
            TargetEndpoint(
                host=responder.host, port=responder.port, timeout_seconds=0.2
            ),
            collect_all_responses=True,
        )

        self.assertEqual(result.outcome, "error")
        self.assertEqual(
            [item.classification for item in result.responses],
            ["provisional", "client_error"],
        )
        self.assertEqual(
            result.final_response.status_code if result.final_response else None, 486
        )

    def test_send_packet_to_silent_udp_target_times_out(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            host, port = sock.getsockname()

        result = self.reactor.send_packet(
            self.packet,
            TargetEndpoint(host=host, port=port, timeout_seconds=0.05),
        )

        self.assertEqual(result.outcome, "timeout")
        self.assertEqual(result.responses, ())
        self.assertIsNone(result.final_response)

    def test_send_wire_text_tcp_reads_success_response(self) -> None:
        responder = TCPResponder(
            response=b"SIP/2.0 200 OK\r\nContent-Length: 0\r\n\r\n"
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.reactor.send_artifact(
            SendArtifact.from_wire_text(
                "OPTIONS sip:ue@example.com SIP/2.0\r\nContent-Length: 0\r\n\r\n"
            ),
            TargetEndpoint(
                host=responder.host,
                port=responder.port,
                transport="TCP",
                timeout_seconds=0.5,
            ),
        )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.responses[-1].status_code, 200)
        self.assertEqual(len(responder.received_payloads), 1)


if __name__ == "__main__":
    unittest.main()
