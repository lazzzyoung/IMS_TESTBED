from __future__ import annotations

import json
import os
import re
import secrets
import socket
import socketserver
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sms_parser import build_mt_3gpp_sms_payload, parse_3gpp_sms_payload

CRLF = "\r\n"
HOST = "0.0.0.0"
PORT = 5060
LOG_DIR = Path(os.environ.get("SMSC_LOG_DIR", "/var/log/smsc"))
MCC = os.environ.get("MCC", "001")
MNC = os.environ.get("MNC", "01").zfill(3)
IMS_DOMAIN = f"ims.mnc{MNC}.mcc{MCC}.3gppnetwork.org"
SCSCF_HOST = os.environ.get("SCSCF_IP", "172.22.0.20")
SCSCF_PORT = int(os.environ.get("SMSC_FORWARD_PORT", "6060"))
SMSC_FQDN = f"smsc.{IMS_DOMAIN}"
USER_RE = re.compile(r"(?:sip:|tel:)?([0-9]+)")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
PENDING_FORWARDS: dict[str, dict[str, Any]] = {}
PENDING_FORWARDS_BY_RP_REF: dict[int, list[dict[str, Any]]] = {}
PENDING_FORWARDS_LOCK = threading.Lock()


@dataclass
class SIPMessage:
    start_line: str
    is_response: bool
    method: str
    uri: str | None
    version: str
    status_code: int | None
    reason: str | None
    headers: list[tuple[str, str]]
    body: str
    body_bytes: bytes

    def header_values(self, name: str) -> list[str]:
        needle = name.casefold()
        return [value for key, value in self.headers if key.casefold() == needle]

    def first_header(self, name: str) -> str | None:
        values = self.header_values(name)
        return values[0] if values else None

    def file_label(self) -> str:
        if self.is_response:
            code = self.status_code if self.status_code is not None else "unknown"
            reason = self.reason or "response"
            return f"response_{code}_{_safe_component(reason)}"
        return _safe_component(self.method)


def _extract_digits(value: str | None) -> str | None:
    if not value:
        return None
    match = USER_RE.search(value)
    if match:
        return match.group(1)
    return None


def _safe_component(value: str) -> str:
    sanitized = SAFE_NAME_RE.sub("_", value.strip())
    return sanitized.strip("._") or "unknown"


def _read_tcp_message(rfile) -> bytes:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = rfile.read(1)
        if not chunk:
            break
        header += chunk
        if len(header) > 65535:
            break
    if not header:
        return b""
    body_len = 0
    header_text = header.decode("utf-8", errors="replace")
    for line in header_text.split(CRLF):
        if line.lower().startswith("content-length:"):
            try:
                body_len = int(line.split(":", 1)[1].strip())
            except ValueError:
                body_len = 0
            break
    body = rfile.read(body_len) if body_len > 0 else b""
    return header + body


def parse_sip_message(data: bytes) -> SIPMessage | None:
    try:
        separator = b"\r\n\r\n"
        header_bytes, _, body_bytes = data.partition(separator)
        header_text = header_bytes.decode("utf-8", errors="replace")
        body = body_bytes.decode("utf-8", errors="replace")
        lines = [line for line in header_text.split(CRLF) if line]
        if not lines:
            return None
        parts = lines[0].split(" ", 2)
        if len(parts) != 3:
            return None
        is_response = parts[0].upper().startswith("SIP/")
        if is_response:
            version, status_text, reason = parts
            try:
                status_code = int(status_text)
            except ValueError:
                return None
            method = version.strip().upper()
            uri = None
        else:
            method, uri, version = parts
            status_code = None
            reason = None
        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers.append((k.strip(), v.strip()))
        return SIPMessage(
            start_line=lines[0],
            is_response=is_response,
            method=method.strip().upper(),
            uri=uri.strip() if uri is not None else None,
            version=version.strip(),
            status_code=status_code,
            reason=reason.strip() if reason is not None else None,
            headers=headers,
            body=body,
            body_bytes=body_bytes,
        )
    except Exception:
        return None


def build_response(req: SIPMessage, code: int, reason: str) -> bytes:
    lines = [f"SIP/2.0 {code} {reason}"]
    for value in req.header_values("Via"):
        lines.append(f"Via: {value}")
    for name in ("From", "To", "Call-ID", "CSeq"):
        value = req.first_header(name)
        if value is not None:
            lines.append(f"{name}: {value}")
    lines.append("Server: vmf-smsc/0.1")
    lines.append("Content-Length: 0")
    return (CRLF.join(lines) + CRLF + CRLF).encode("utf-8")


def persist_message(msg: SIPMessage, transport: str, peer: tuple[str, int]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    sms_parse = None
    content_type = msg.first_header("Content-Type")
    if content_type == "application/vnd.3gpp.sms":
        sms_parse = parse_3gpp_sms_payload(msg.body_bytes)
    payload = {
        "timestamp": ts,
        "transport": transport,
        "peer_host": peer[0],
        "peer_port": peer[1],
        "start_line": msg.start_line,
        "is_response": msg.is_response,
        "method": msg.method,
        "uri": msg.uri,
        "version": msg.version,
        "status_code": msg.status_code,
        "reason": msg.reason,
        "from": msg.first_header("From"),
        "to": msg.first_header("To"),
        "call_id": msg.first_header("Call-ID"),
        "cseq": msg.first_header("CSeq"),
        "content_type": content_type,
        "content_length": msg.first_header("Content-Length"),
        "body": msg.body,
        "body_hex": msg.body_bytes.hex().upper(),
        "sms_parse": sms_parse,
    }
    (LOG_DIR / f"{ts}_{transport.lower()}_{msg.file_label()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def persist_forward_result(event: dict[str, object]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    (LOG_DIR / f"{ts}_forward.json").write_text(
        json.dumps(event, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_forward_message(
    *,
    destination_msisdn: str,
    originating_msisdn: str,
    body_bytes: bytes,
    content_type: str,
) -> tuple[str, bytes]:
    call_id = f"{secrets.token_hex(8)}@{SMSC_FQDN}"
    lines = [
        f"MESSAGE sip:{destination_msisdn}@{IMS_DOMAIN} SIP/2.0",
        f"Via: SIP/2.0/UDP {SMSC_FQDN}:5060;branch=z9hG4bK-{secrets.token_hex(8)}",
        "Max-Forwards: 70",
        f"From: <sip:{originating_msisdn}@{IMS_DOMAIN}>;tag={secrets.token_hex(4)}",
        f"To: <sip:{destination_msisdn}@{IMS_DOMAIN}>",
        f"Call-ID: {call_id}",
        "CSeq: 1 MESSAGE",
        f"Contact: <sip:smsc@{SMSC_FQDN}:5060>",
        "Server: vmf-smsc/0.1",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body_bytes)}",
        "",
        "",
    ]
    return call_id, CRLF.join(lines).encode("utf-8") + body_bytes


def _register_pending_forward(
    call_id: str,
    event: dict[str, object],
    *,
    rp_message_reference: int | None,
) -> threading.Event:
    waiter = threading.Event()
    with PENDING_FORWARDS_LOCK:
        pending = {"waiter": waiter, "event": event, "rp_message_reference": rp_message_reference}
        PENDING_FORWARDS[call_id] = pending
        if rp_message_reference is not None:
            bucket = PENDING_FORWARDS_BY_RP_REF.setdefault(rp_message_reference, [])
            bucket.append(pending)
    return waiter


def _resolve_pending_forward(msg: SIPMessage, transport: str, peer: tuple[str, int]) -> None:
    if not msg.is_response:
        return
    call_id = msg.first_header("Call-ID")
    if not call_id:
        return
    with PENDING_FORWARDS_LOCK:
        pending = PENDING_FORWARDS.pop(call_id, None)
    if pending is None:
        return
    event = pending["event"]
    event["status"] = "response"
    event["response_transport"] = transport
    event["response_from"] = f"{peer[0]}:{peer[1]}"
    event["response_start_line"] = msg.start_line
    event["response_status_code"] = msg.status_code
    event["response_reason"] = msg.reason
    event["response_text"] = (
        msg.start_line + CRLF + CRLF + msg.body
        if msg.body
        else msg.start_line
    )
    pending["waiter"].set()


def _annotate_control_signal(
    msg: SIPMessage,
    sms_parse: dict[str, object] | None,
    transport: str,
    peer: tuple[str, int],
) -> None:
    if sms_parse is None:
        return
    rp_message_type = sms_parse.get("rp_message_type")
    rp_message_reference = sms_parse.get("rp_message_reference")
    if rp_message_type != "0x05" or not isinstance(rp_message_reference, int):
        return
    with PENDING_FORWARDS_LOCK:
        pendings = list(PENDING_FORWARDS_BY_RP_REF.get(rp_message_reference, []))
    for pending in pendings:
        event = pending["event"]
        event["control_signal_seen"] = True
        event["control_signal_call_id"] = msg.first_header("Call-ID")
        event["control_signal_transport"] = transport
        event["control_signal_from"] = f"{peer[0]}:{peer[1]}"
        event["control_signal_rp_message_type"] = rp_message_type
        event["control_signal_rp_message_reference"] = rp_message_reference
        event["control_signal_from_header"] = msg.first_header("From")
        event["control_signal_to_header"] = msg.first_header("To")
        event["control_signal_body_hex"] = msg.body_bytes.hex().upper()
        event["control_signal_start_line"] = msg.start_line


def forward_to_ims(msg: SIPMessage, sms_parse: dict[str, object] | None) -> None:
    if msg.method != "MESSAGE" or sms_parse is None:
        return
    rp_message_type = sms_parse.get("rp_message_type")
    if rp_message_type != "0x00":
        persist_forward_result(
            {
                "status": "skipped",
                "reason": "non-mo-rp-message",
                "rp_message_type": rp_message_type,
                "sms_parse": sms_parse,
                "call_id": msg.first_header("Call-ID"),
            }
        )
        return
    destination = sms_parse.get("best_effort_destination")
    if not isinstance(destination, str) or not destination:
        persist_forward_result(
            {
                "status": "skipped",
                "reason": "destination-not-found",
                "sms_parse": sms_parse,
                "call_id": msg.first_header("Call-ID"),
            }
        )
        return

    originating = _extract_digits(msg.first_header("From")) or "unknown"
    content_type = msg.first_header("Content-Type") or "application/octet-stream"
    rp_message_reference = sms_parse.get("rp_message_reference")
    if not isinstance(rp_message_reference, int):
        rp_message_reference = 0
    relay_text = f"VMF relay from {originating}"
    mt_body_bytes = build_mt_3gpp_sms_payload(
        originating_msisdn=originating,
        text=relay_text,
        rp_message_reference=rp_message_reference,
    )
    forward_call_id, payload = build_forward_message(
        destination_msisdn=destination,
        originating_msisdn=originating,
        body_bytes=mt_body_bytes,
        content_type=content_type,
    )
    event: dict[str, object] = {
        "status": "attempt",
        "destination_msisdn": destination,
        "originating_msisdn": originating,
        "scscf_host": SCSCF_HOST,
        "scscf_port": SCSCF_PORT,
        "call_id": msg.first_header("Call-ID"),
        "forward_call_id": forward_call_id,
        "content_type": content_type,
        "source_rp_message_type": rp_message_type,
        "relay_text": relay_text,
        "relay_body_hex": mt_body_bytes.hex().upper(),
        "payload_hex_prefix": payload[:160].hex().upper(),
    }
    waiter = _register_pending_forward(
        forward_call_id,
        event,
        rp_message_reference=rp_message_reference,
    )
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, (SCSCF_HOST, SCSCF_PORT))
        if not waiter.wait(timeout=8.0):
            event["status"] = "timeout"
    except OSError as exc:
        event["status"] = "error"
        event["error"] = str(exc)
    finally:
        with PENDING_FORWARDS_LOCK:
            pending = PENDING_FORWARDS.pop(forward_call_id, None)
            if pending is not None:
                ref = pending.get("rp_message_reference")
                if isinstance(ref, int):
                    bucket = PENDING_FORWARDS_BY_RP_REF.get(ref, [])
                    bucket = [item for item in bucket if item is not pending]
                    if bucket:
                        PENDING_FORWARDS_BY_RP_REF[ref] = bucket
                    else:
                        PENDING_FORWARDS_BY_RP_REF.pop(ref, None)
    persist_forward_result(event)


def handle_request_bytes(data: bytes, transport: str, peer: tuple[str, int]) -> bytes | None:
    msg = parse_sip_message(data)
    if msg is None:
        return None
    print(
        f"[smsc] {transport} {peer[0]}:{peer[1]} {msg.start_line} "
        f"call-id={msg.first_header('Call-ID')}",
        flush=True,
    )
    sms_parse = None
    if msg.first_header("Content-Type") == "application/vnd.3gpp.sms":
        sms_parse = parse_3gpp_sms_payload(msg.body_bytes)
    persist_message(msg, transport, peer)
    _annotate_control_signal(msg, sms_parse, transport, peer)
    _resolve_pending_forward(msg, transport, peer)
    if msg.is_response:
        return None
    if msg.method == "MESSAGE":
        threading.Thread(
            target=forward_to_ims,
            args=(msg, sms_parse),
            daemon=True,
        ).start()
    if msg.method == "MESSAGE":
        return build_response(msg, 202, "Accepted")
    if msg.method == "OPTIONS":
        return build_response(msg, 200, "OK")
    return build_response(msg, 405, "Method Not Allowed")


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        response = handle_request_bytes(data, "UDP", self.client_address)
        if response:
            sock.sendto(response, self.client_address)


class TCPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        data = _read_tcp_message(self.rfile)
        if not data:
            return
        response = handle_request_bytes(data, "TCP", self.client_address)
        if response:
            self.wfile.write(response)
            self.wfile.flush()


class ThreadingUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_forever() -> None:
    udp_server = ThreadingUDPServer((HOST, PORT), UDPHandler)
    tcp_server = ThreadingTCPServer((HOST, PORT), TCPHandler)

    threads = [
        threading.Thread(target=udp_server.serve_forever, daemon=True),
        threading.Thread(target=tcp_server.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()

    print(f"[smsc] listening on {HOST}:{PORT} (udp/tcp)", flush=True)
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    serve_forever()
