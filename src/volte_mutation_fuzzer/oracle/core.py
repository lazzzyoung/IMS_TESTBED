import re
import subprocess
import time
from pathlib import Path

from volte_mutation_fuzzer.oracle.contracts import (
    LogCheckResult,
    OracleContext,
    OracleVerdict,
    ProcessCheckResult,
)
from volte_mutation_fuzzer.sender.contracts import SendReceiveResult


class SocketOracle:
    """Judges a SendReceiveResult against expected behavior for a SIP method."""

    def judge(
        self,
        send_result: SendReceiveResult,
        context: OracleContext,
    ) -> OracleVerdict:
        elapsed = send_result.duration_ms
        outcome = send_result.outcome
        final = send_result.final_response

        if outcome == "send_error":
            return OracleVerdict(
                verdict="unknown",
                reason=f"send error: {send_result.error or 'unknown infrastructure failure'}",
                elapsed_ms=elapsed,
            )

        if outcome == "timeout":
            return OracleVerdict(
                verdict="timeout",
                reason="no response received within timeout",
                elapsed_ms=elapsed,
            )

        if outcome == "invalid_response":
            return OracleVerdict(
                verdict="suspicious",
                reason="response could not be parsed as valid SIP",
                elapsed_ms=elapsed,
                details={"raw": final.raw_text if final else ""},
            )

        response_code = final.status_code if final else None
        classification = final.classification if final else None

        if response_code is not None and response_code >= 500:
            return OracleVerdict(
                verdict="suspicious",
                reason=f"server-side error response: {response_code}",
                response_code=response_code,
                elapsed_ms=elapsed,
            )

        if elapsed > context.slow_threshold_ms and final is not None:
            return OracleVerdict(
                verdict="suspicious",
                reason=f"abnormally slow response: {elapsed:.0f}ms > {context.slow_threshold_ms:.0f}ms threshold",
                response_code=response_code,
                elapsed_ms=elapsed,
            )

        return OracleVerdict(
            verdict="normal",
            reason=f"outcome={outcome}, code={response_code}, classification={classification}",
            response_code=response_code,
            elapsed_ms=elapsed,
        )


class ProcessOracle:
    """Checks if a named process is alive via pgrep."""

    def __init__(self, docker_mode: bool = False) -> None:
        self._docker_mode = docker_mode

    def check(self, process_name: str) -> ProcessCheckResult:
        if self._docker_mode:
            return self._check_docker(process_name)
        return self._check_local(process_name)

    def _check_local(self, process_name: str) -> ProcessCheckResult:
        check_time = time.time()
        try:
            result = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                raw = result.stdout.decode().strip()
                pid = int(raw.splitlines()[0]) if raw else None
                return ProcessCheckResult(
                    process_name=process_name,
                    alive=True,
                    pid=pid,
                    check_time=check_time,
                )
            return ProcessCheckResult(
                process_name=process_name,
                alive=False,
                check_time=check_time,
            )
        except Exception as exc:
            return ProcessCheckResult(
                process_name=process_name,
                alive=False,
                check_time=check_time,
                error=str(exc),
            )

    def _check_docker(self, container_name: str) -> ProcessCheckResult:
        check_time = time.time()
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format={{.State.Status}}\n{{.State.Pid}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"docker inspect exited with status {result.returncode}"
                )
                return ProcessCheckResult(
                    process_name=container_name,
                    alive=False,
                    check_time=check_time,
                    error=error,
                )

            lines = result.stdout.splitlines()
            status = lines[0].strip() if lines else ""
            pid = int(lines[1].strip()) if len(lines) > 1 else 0
            return ProcessCheckResult(
                process_name=container_name,
                alive=status == "running",
                pid=pid,
                check_time=check_time,
            )
        except Exception as exc:
            return ProcessCheckResult(
                process_name=container_name,
                alive=False,
                check_time=check_time,
                error=str(exc),
            )


class LogOracle:
    """Scans a log file for stack trace / fatal error patterns."""

    DEFAULT_PATTERNS: tuple[str, ...] = (
        r"SIGSEGV",
        r"SIGABRT",
        r"Segmentation fault",
        r"Assertion failed",
        r"core dumped",
        r"backtrace",
        r"Traceback \(most recent call last\)",
        r"Exception in thread",
        r"\bFATAL\b",
        r"\bpanic:",
    )

    def __init__(
        self,
        patterns: tuple[str, ...] | None = None,
        docker_mode: bool = False,
    ) -> None:
        raw = patterns or self.DEFAULT_PATTERNS
        self._docker_mode = docker_mode
        self._compiled = re.compile("|".join(f"({p})" for p in raw), re.IGNORECASE)

    def check(
        self, log_path: str, after_position: int = 0
    ) -> tuple[LogCheckResult, int]:
        """Scan log_path starting from after_position bytes.

        Returns (result, new_position) so the caller can track incremental reads.
        """
        if self._docker_mode:
            return self._check_docker(log_path, after_position)
        return self._check_file(log_path, after_position)

    def _check_file(
        self, log_path: str, after_position: int = 0
    ) -> tuple[LogCheckResult, int]:
        path = Path(log_path)
        if not path.is_file():
            return LogCheckResult(
                log_path=log_path,
                matched=False,
                error=f"log file not found: {log_path}",
            ), after_position

        try:
            size = path.stat().st_size
            if size <= after_position:
                return LogCheckResult(
                    log_path=log_path,
                    matched=False,
                    lines_scanned=0,
                ), after_position

            with path.open("r", errors="replace") as f:
                f.seek(after_position)
                new_content = f.read()
                new_position = f.tell()

            lines = new_content.splitlines()
            for line in lines:
                m = self._compiled.search(line)
                if m:
                    return LogCheckResult(
                        log_path=log_path,
                        matched=True,
                        matched_pattern=m.group(0),
                        matched_line=line[:500],
                        lines_scanned=len(lines),
                    ), new_position

            return LogCheckResult(
                log_path=log_path,
                matched=False,
                lines_scanned=len(lines),
            ), new_position

        except Exception as exc:
            return LogCheckResult(
                log_path=log_path,
                matched=False,
                error=str(exc),
            ), after_position

    def _check_docker(
        self, container_name: str, after_position: int = 0
    ) -> tuple[LogCheckResult, int]:
        new_position = int(time.time())
        try:
            result = subprocess.run(
                ["docker", "logs", "--since", str(after_position), container_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                error = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"docker logs exited with status {result.returncode}"
                )
                return (
                    LogCheckResult(
                        log_path=container_name,
                        matched=False,
                        error=error,
                    ),
                    after_position,
                )

            output = result.stdout
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr

            lines = output.splitlines()
            for line in lines:
                m = self._compiled.search(line)
                if m:
                    return LogCheckResult(
                        log_path=container_name,
                        matched=True,
                        matched_pattern=m.group(0),
                        matched_line=line[:500],
                        lines_scanned=len(lines),
                    ), new_position

            return LogCheckResult(
                log_path=container_name,
                matched=False,
                lines_scanned=len(lines),
            ), new_position
        except Exception as exc:
            return (
                LogCheckResult(
                    log_path=container_name,
                    matched=False,
                    error=str(exc),
                ),
                after_position,
            )


class AdbOracle:
    """Oracle that checks ADB logcat anomaly events for crash/failure indicators."""

    def __init__(self, collector: object, detector: object) -> None:
        self._collector = collector
        self._detector = detector

    def check(self) -> LogCheckResult:
        lines = self._collector.get_lines()
        self._detector.feed_lines(lines)
        events = self._detector.drain_events()
        actionable = [e for e in events if e.severity in ("critical", "warning")]
        if actionable:
            critical = [e for e in actionable if e.severity == "critical"]
            top = (critical or actionable)[0]
            return LogCheckResult(
                log_path="adb:logcat",
                matched=True,
                matched_pattern=top.matched_pattern,
                matched_line=top.matched_line,
                lines_scanned=len(lines),
            )
        return LogCheckResult(
            log_path="adb:logcat",
            matched=False,
            lines_scanned=len(lines),
        )


class OracleEngine:
    """Combines SocketOracle + ProcessOracle into a single verdict."""

    def __init__(
        self,
        socket_oracle: SocketOracle | None = None,
        process_oracle: ProcessOracle | None = None,
        log_oracle: LogOracle | None = None,
        adb_oracle: AdbOracle | None = None,
        docker_mode: bool = False,
    ) -> None:
        self._socket_oracle = socket_oracle or SocketOracle()
        self._process_oracle = process_oracle or ProcessOracle(
            docker_mode=docker_mode
        )
        self._log_oracle = log_oracle
        self._adb_oracle = adb_oracle
        self._log_position: int = int(time.time()) if docker_mode else 0

    def evaluate(
        self,
        send_result: SendReceiveResult,
        context: OracleContext,
        *,
        process_name: str | None = None,
        log_path: str | None = None,
    ) -> OracleVerdict:
        verdict = self._socket_oracle.judge(send_result, context)

        if log_path is not None and self._log_oracle is not None:
            log_result, self._log_position = self._log_oracle.check(
                log_path, self._log_position
            )
            if log_result.matched:
                return OracleVerdict(
                    verdict="stack_failure",
                    confidence=0.85,
                    reason=f"stack trace pattern detected in log: {log_result.matched_pattern}",
                    response_code=verdict.response_code,
                    elapsed_ms=verdict.elapsed_ms,
                    details={
                        "socket_verdict": verdict.verdict,
                        "matched_pattern": log_result.matched_pattern,
                        "matched_line": log_result.matched_line,
                        "log_path": log_path,
                    },
                )

        if self._adb_oracle is not None:
            adb_result = self._adb_oracle.check()
            if adb_result.matched:
                return OracleVerdict(
                    verdict="stack_failure",
                    confidence=0.80,
                    reason=f"ADB anomaly detected: {adb_result.matched_pattern}",
                    response_code=verdict.response_code,
                    elapsed_ms=verdict.elapsed_ms,
                    details={
                        "socket_verdict": verdict.verdict,
                        "matched_pattern": adb_result.matched_pattern,
                        "matched_line": adb_result.matched_line,
                        "log_path": "adb:logcat",
                    },
                )

        if process_name is None:
            return verdict

        proc = self._process_oracle.check(process_name)

        if not proc.alive:
            return OracleVerdict(
                verdict="crash",
                confidence=0.9,
                reason=f"process '{process_name}' not found after send",
                response_code=verdict.response_code,
                elapsed_ms=verdict.elapsed_ms,
                process_alive=False,
                details={
                    "socket_verdict": verdict.verdict,
                    "process_error": proc.error,
                },
            )

        return verdict.model_copy(update={"process_alive": True})
