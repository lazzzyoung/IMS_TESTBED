from __future__ import annotations

import json
import unittest

from typer.testing import CliRunner

from tests.sender._server import UDPResponder
from volte_mutation_fuzzer.generator.cli import app


class SIPSenderCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_send_request_command_generates_and_sends_packet(self) -> None:
        responder = UDPResponder(
            responses=(b"SIP/2.0 200 OK\r\nContent-Length: 0\r\n\r\n",)
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.runner.invoke(
            app,
            [
                "send",
                "request",
                "OPTIONS",
                "--target-host",
                responder.host,
                "--target-port",
                str(responder.port),
                "--timeout",
                "0.5",
            ],
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifact_kind"], "packet")
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["responses"][-1]["status_code"], 200)

    def test_send_packet_command_accepts_generator_packet_json_from_stdin(self) -> None:
        baseline_result = self.runner.invoke(app, ["request", "OPTIONS"])
        self.assertEqual(baseline_result.exit_code, 0, msg=baseline_result.output)

        responder = UDPResponder(
            responses=(b"SIP/2.0 486 Busy Here\r\nContent-Length: 0\r\n\r\n",)
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.runner.invoke(
            app,
            [
                "send",
                "packet",
                "--target-host",
                responder.host,
                "--target-port",
                str(responder.port),
                "--timeout",
                "0.5",
            ],
            input=baseline_result.stdout,
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"], "error")
        self.assertEqual(payload["responses"][-1]["status_code"], 486)

    def test_send_packet_command_accepts_raw_wire_text(self) -> None:
        responder = UDPResponder(
            responses=(b"SIP/2.0 180 Ringing\r\nContent-Length: 0\r\n\r\n",)
        )
        responder.start()
        self.addCleanup(responder.close)

        result = self.runner.invoke(
            app,
            [
                "send",
                "packet",
                "--target-host",
                responder.host,
                "--target-port",
                str(responder.port),
                "--timeout",
                "0.5",
            ],
            input="OPTIONS sip:ue@example.com SIP/2.0\r\nContent-Length: 0\r\n\r\n",
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifact_kind"], "wire")
        self.assertEqual(payload["outcome"], "provisional")


if __name__ == "__main__":
    unittest.main()
