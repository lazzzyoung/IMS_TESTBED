import subprocess
import threading
import time
from collections import deque
from queue import Empty, Queue

from volte_mutation_fuzzer.adb.contracts import (
    AdbAnomalyEvent,
    AdbCollectorConfig,
    AdbDeviceInfo,
)
from volte_mutation_fuzzer.adb.patterns import ANOMALY_PATTERNS, AnomalyPattern


class AdbConnector:
    def __init__(self, serial: str | None = None) -> None:
        self._serial = serial

    def _adb_cmd(self, *args: str) -> list[str]:
        base = ["adb"]
        if self._serial:
            base.extend(["-s", self._serial])
        base.extend(args)
        return base

    def check_device(self) -> AdbDeviceInfo:
        target_serial = self._serial or "unknown"
        try:
            result = subprocess.run(
                self._adb_cmd("devices", "-l"),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            return AdbDeviceInfo(
                serial="unknown",
                state="not_found",
                error="adb not found",
            )

        selected_line: str | None = None
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("List of devices attached"):
                continue

            serial, _, remainder = line.partition("\t")
            if not remainder:
                continue

            if self._serial is not None and serial != self._serial:
                continue

            selected_line = line
            target_serial = serial
            break

        if selected_line is None:
            return AdbDeviceInfo(serial=target_serial, state="not_found")

        serial, _, remainder = selected_line.partition("\t")
        state, _, details = remainder.partition(" ")
        model: str | None = None
        for token in details.split():
            if token.startswith("model:"):
                model = token.removeprefix("model:")
                break

        return AdbDeviceInfo(serial=serial, state=state, model=model)

    def run_shell(
        self, *args: str, timeout: int = 30
    ) -> subprocess.CompletedProcess[str]:
        cmd = self._adb_cmd("shell", *args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class AdbLogCollector:
    def __init__(self, config: AdbCollectorConfig | None = None) -> None:
        self._config = config or AdbCollectorConfig()
        self._connector = AdbConnector(serial=self._config.serial)
        self._procs: dict[str, subprocess.Popen[str]] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._queue: Queue[tuple[str, str]] = Queue()
        self._running = threading.Event()

    def start(self, clear: bool = True) -> None:
        if clear:
            subprocess.run(
                self._connector._adb_cmd("logcat", "-c"),
                capture_output=True,
                timeout=10,
            )

        self.stop()
        self._running.set()
        for buffer_name in self._config.buffers:
            cmd = self._connector._adb_cmd(
                "logcat",
                "-b",
                buffer_name,
                "-v",
                self._config.log_format,
            )
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._procs[buffer_name] = proc
            thread = threading.Thread(
                target=self._reader_loop,
                args=(buffer_name, proc),
                daemon=True,
            )
            self._threads[buffer_name] = thread
            thread.start()

    def stop(self) -> None:
        self._running.clear()
        for proc in self._procs.values():
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        for thread in self._threads.values():
            thread.join(timeout=5)
        self._procs.clear()
        self._threads.clear()

    def get_lines(
        self, max_lines: int = 1000, timeout: float = 0.0
    ) -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = []
        try:
            if timeout > 0:
                lines.append(self._queue.get(timeout=timeout))
            else:
                lines.append(self._queue.get_nowait())
        except Empty:
            return lines

        try:
            while len(lines) < max_lines:
                lines.append(self._queue.get_nowait())
        except Empty:
            pass
        return lines

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    def _reader_loop(self, buffer_name: str, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return

        try:
            for line in proc.stdout:
                if not self._running.is_set():
                    break
                self._queue.put((buffer_name, line.rstrip("\n")))
        except Exception:
            pass


class AdbAnomalyDetector:
    def __init__(
        self,
        patterns: tuple[AnomalyPattern, ...] | None = None,
        max_events: int = 10000,
    ) -> None:
        self._patterns = patterns or ANOMALY_PATTERNS
        self._events: deque[AdbAnomalyEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._total_lines_scanned = 0

    def feed_line(self, buffer_name: str, line: str) -> AdbAnomalyEvent | None:
        self._total_lines_scanned += 1
        for pattern in self._patterns:
            if pattern.compiled.search(line):
                event = AdbAnomalyEvent(
                    timestamp=time.time(),
                    severity=pattern.severity,
                    category=pattern.category,
                    pattern_name=pattern.name,
                    matched_pattern=pattern.regex,
                    matched_line=line[:500],
                    buffer=buffer_name,
                )
                with self._lock:
                    self._events.append(event)
                return event
        return None

    def feed_lines(self, lines: list[tuple[str, str]]) -> list[AdbAnomalyEvent]:
        results: list[AdbAnomalyEvent] = []
        for buffer_name, line in lines:
            event = self.feed_line(buffer_name, line)
            if event is not None:
                results.append(event)
        return results

    def drain_events(self) -> list[AdbAnomalyEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def peek_events(self) -> list[AdbAnomalyEvent]:
        with self._lock:
            return list(self._events)

    @property
    def total_lines_scanned(self) -> int:
        return self._total_lines_scanned
