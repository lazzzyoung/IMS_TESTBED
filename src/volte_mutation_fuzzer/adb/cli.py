import json
import subprocess
import time
from pathlib import Path
from typing import Annotated

import typer

from volte_mutation_fuzzer.adb.contracts import AdbCollectorConfig, AdbSnapshotResult
from volte_mutation_fuzzer.adb.core import (
    AdbAnomalyDetector,
    AdbConnector,
    AdbLogCollector,
)

app = typer.Typer(
    add_completion=False,
    help="Inspect Android devices and monitor ADB logcat anomalies.",
)


def _parse_buffers(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None:
        return AdbCollectorConfig().buffers
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("check")
def check_command(
    serial: Annotated[
        str | None, typer.Option("--serial", help="ADB device serial.")
    ] = None,
) -> None:
    """Check ADB device connectivity and emit JSON."""
    connector = AdbConnector(serial=serial)
    device = connector.check_device()
    _echo_json(device.model_dump(mode="json"))


@app.command("monitor")
def monitor_command(
    serial: Annotated[
        str | None, typer.Option("--serial", help="ADB device serial.")
    ] = None,
    buffers: Annotated[
        str | None,
        typer.Option("--buffers", help="Comma-separated logcat buffers to follow."),
    ] = None,
    clear: Annotated[
        bool, typer.Option("--clear/--no-clear", help="Clear logcat before streaming.")
    ] = True,
    poll_interval: Annotated[
        float, typer.Option("--poll-interval", help="Polling interval in seconds.")
    ] = 0.2,
    show_lines: Annotated[
        bool, typer.Option("--show-lines", help="Emit raw log lines as JSON.")
    ] = False,
) -> None:
    """Monitor logcat and emit anomaly events in real time."""
    collector = AdbLogCollector(
        AdbCollectorConfig(serial=serial, buffers=_parse_buffers(buffers))
    )
    detector = AdbAnomalyDetector()
    collector.start(clear=clear)

    try:
        while True:
            lines = collector.get_lines(timeout=poll_interval)
            if show_lines:
                for buffer_name, line in lines:
                    _echo_json({"type": "line", "buffer": buffer_name, "line": line})
            for event in detector.feed_lines(lines):
                _echo_json({"type": "anomaly", **event.model_dump(mode="json")})
            time.sleep(0.01)
    except KeyboardInterrupt:
        raise typer.Exit(code=0)
    finally:
        collector.stop()


@app.command("snapshot")
def snapshot_command(
    output_dir: Annotated[
        str,
        typer.Option(
            "--output-dir", help="Directory where snapshot files are written."
        ),
    ] = "artifacts/adb",
    serial: Annotated[
        str | None, typer.Option("--serial", help="ADB device serial.")
    ] = None,
    bugreport: Annotated[
        bool,
        typer.Option(
            "--bugreport/--no-bugreport",
            help="Capture a full adb bugreport in addition to meminfo and dmesg.",
        ),
    ] = False,
) -> None:
    """Capture diagnostic snapshots from a connected Android device."""
    connector = AdbConnector(serial=serial)
    device = connector.check_device()
    if device.state != "device":
        result = AdbSnapshotResult(errors=(f"device unavailable: {device.state}",))
        _echo_json(result.model_dump(mode="json"))
        raise typer.Exit(code=1)

    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    meminfo_path: str | None = None
    dmesg_path: str | None = None
    bugreport_path: str | None = None

    def _write_shell_output(filename: str, *args: str, timeout: int) -> str | None:
        path = base_dir / filename
        try:
            result = connector.run_shell(*args, timeout=timeout)
        except Exception as exc:
            errors.append(f"{' '.join(args)} failed: {exc}")
            return None

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown error"
            errors.append(f"{' '.join(args)} failed: {message}")
            return None

        path.write_text(result.stdout, encoding="utf-8")
        return str(path)

    meminfo_path = _write_shell_output("meminfo.txt", "dumpsys", "meminfo", timeout=60)
    dmesg_path = _write_shell_output("dmesg.txt", "dmesg", timeout=60)

    if bugreport:
        path = base_dir / "bugreport.txt"
        try:
            result = subprocess.run(
                connector._adb_cmd("bugreport"),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                message = (
                    result.stderr.strip() or result.stdout.strip() or "unknown error"
                )
                errors.append(f"bugreport failed: {message}")
            else:
                path.write_text(result.stdout, encoding="utf-8")
                bugreport_path = str(path)
        except Exception as exc:
            errors.append(f"bugreport failed: {exc}")

    snapshot = AdbSnapshotResult(
        meminfo_path=meminfo_path,
        dmesg_path=dmesg_path,
        bugreport_path=bugreport_path,
        errors=tuple(errors),
    )
    _echo_json(snapshot.model_dump(mode="json"))
