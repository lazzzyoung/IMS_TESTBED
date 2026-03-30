import unittest

from volte_mutation_fuzzer.dialog.core import DialogOrchestrator
from volte_mutation_fuzzer.dialog.scenarios import scenario_for_method
from volte_mutation_fuzzer.generator.contracts import GeneratorSettings
from volte_mutation_fuzzer.generator.core import SIPGenerator
from volte_mutation_fuzzer.mutator.contracts import MutationConfig
from volte_mutation_fuzzer.mutator.core import SIPMutator
from volte_mutation_fuzzer.sender.contracts import TargetEndpoint

from tests.dialog._dialog_server import (
    DialogUDPResponder,
    make_180_ringing,
    make_200_ok,
    make_200_ok_generic,
    make_486_busy,
)


def _make_target(host: str, port: int) -> TargetEndpoint:
    return TargetEndpoint(host=host, port=port, transport="UDP", timeout_seconds=1.0)


def _make_components() -> tuple[SIPGenerator, SIPMutator]:
    generator = SIPGenerator(GeneratorSettings())
    mutator = SIPMutator()
    return generator, mutator


class TestInviteDialogBye(unittest.TestCase):
    """Full INVITE→200→ACK→BYE(mutated)→200 exchange."""

    def setUp(self) -> None:
        self.server = DialogUDPResponder(
            responses_by_method={
                "INVITE": make_200_ok(),
                "ACK": b"",  # no response to ACK
                "BYE": make_200_ok_generic("BYE"),
            }
        )
        self.server.start()
        self.addCleanup(self.server.close)

    def test_setup_succeeds_and_fuzz_result_present(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("BYE")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=42, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is True
        assert exchange.fuzz_result is not None
        assert exchange.fuzz_result.method == "BYE"
        # INVITE + ACK setup
        assert len(exchange.setup_results) == 2

    def test_invite_was_sent(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("BYE")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=1, strategy="default", layer="model")

        orchestrator.execute(scenario, mutation_config)

        methods_received = []
        for payload in self.server.received_payloads:
            first_line = payload.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
            methods_received.append(first_line.split(" ", 1)[0])
        assert "INVITE" in methods_received
        assert "BYE" in methods_received


class TestInviteDialogUpdate(unittest.TestCase):
    """INVITE→200→ACK→UPDATE(mutated)→200→BYE(teardown)→200."""

    def setUp(self) -> None:
        self.server = DialogUDPResponder(
            responses_by_method={
                "INVITE": make_200_ok(),
                "ACK": b"",
                "UPDATE": make_200_ok_generic("UPDATE"),
                "BYE": make_200_ok_generic("BYE"),
            }
        )
        self.server.start()
        self.addCleanup(self.server.close)

    def test_update_exchange_succeeds(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("UPDATE")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=10, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is True
        assert exchange.fuzz_result is not None
        assert exchange.fuzz_result.method == "UPDATE"
        # Teardown BYE should be present
        assert len(exchange.teardown_results) >= 1


class TestInviteCancel(unittest.TestCase):
    """INVITE→180(provisional)→CANCEL(mutated)→200."""

    def setUp(self) -> None:
        # For CANCEL: INVITE must get a provisional (1xx) first
        self.server = DialogUDPResponder(
            responses_by_method={
                "INVITE": make_180_ringing(),
                "CANCEL": make_200_ok_generic("CANCEL"),
            }
        )
        self.server.start()
        self.addCleanup(self.server.close)

    def test_cancel_exchange_succeeds(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("CANCEL")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=5, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is True
        assert exchange.fuzz_result is not None
        assert exchange.fuzz_result.method == "CANCEL"


class TestInviteAck(unittest.TestCase):
    """INVITE→200→ACK(mutated)→BYE(teardown)."""

    def setUp(self) -> None:
        self.server = DialogUDPResponder(
            responses_by_method={
                "INVITE": make_200_ok(),
                "ACK": b"",
                "BYE": make_200_ok_generic("BYE"),
            }
        )
        self.server.start()
        self.addCleanup(self.server.close)

    def test_ack_exchange_succeeds(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("ACK")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=99, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is True
        assert exchange.fuzz_result is not None
        assert exchange.fuzz_result.method == "ACK"


class TestSetupFailureInviteRejected(unittest.TestCase):
    """INVITE → 486 Busy Here → setup_succeeded=False."""

    def setUp(self) -> None:
        self.server = DialogUDPResponder(
            responses_by_method={"INVITE": make_486_busy()}
        )
        self.server.start()
        self.addCleanup(self.server.close)

    def test_setup_fails_on_4xx(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("BYE")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=0, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is False
        assert exchange.fuzz_result is None
        assert exchange.error is not None


class TestSetupFailureInviteTimeout(unittest.TestCase):
    """INVITE gets no response → setup_succeeded=False."""

    def setUp(self) -> None:
        # Server sends nothing for INVITE
        self.server = DialogUDPResponder(responses_by_method={})
        self.server.start()
        self.addCleanup(self.server.close)

    def test_setup_fails_on_timeout(self) -> None:
        generator, mutator = _make_components()
        scenario = scenario_for_method("BYE")
        assert scenario is not None
        target = _make_target(self.server.host, self.server.port)
        target = target.model_copy(update={"timeout_seconds": 0.3})
        orchestrator = DialogOrchestrator(generator, mutator, target)
        mutation_config = MutationConfig(seed=0, strategy="default", layer="model")

        exchange = orchestrator.execute(scenario, mutation_config)

        assert exchange.setup_succeeded is False
        assert exchange.fuzz_result is None
