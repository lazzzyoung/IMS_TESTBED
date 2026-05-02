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

from sms_parser import parse_3gpp_sms_payload

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


@dataclass
class SIPRequest:
    start_line: str
    method: str
    uri: str
    version: str
    headers: list[tuple[str, str]]
    body: str
    body_bytes: bytes

    def header_values(self, name: str) -> list[str]:
        needle = name.casefold()
        return [value for key, value in self.headers if key.casefold() == needle]

    def first_header(self, name: str) -> str | None:
        values = self.header_values(name)
        return values[0] if values else None


def _extract_digits(value: str | None) -> str | None:
    if not value:
        return None
    match = USER_RE.search(value)
    if match:
        return match.group(1)
    return None


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


def parse_sip_request(data: bytes) -> SIPRequest | None:
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
        method, uri, version = parts
        headers: list[tuple[str, str]] = []
        for line in lines[1:]:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers.append((k.strip(), v.strip()))
        return SIPRequest(
            start_line=lines[0],
            method=method.strip().upper(),
            uri=uri.strip(),
            version=version.strip(),
            headers=headers,
            body=body,
            body_bytes=body_bytes,
        )
    except Exception:
        return None


def build_response(req: SIPRequest, code: int, reason: str) -> bytes:
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


def persist_request(req: SIPRequest, transport: str, peer: tuple[str, int]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    sms_parse = None
    content_type = req.first_header("Content-Type")
    if content_type == "application/vnd.3gpp.sms":
        sms_parse = parse_3gpp_sms_payload(req.body_bytes)
    payload = {
        "timestamp": ts,
        "transport": transport,
        "peer_host": peer[0],
        "peer_port": peer[1],
        "method": req.method,
        "uri": req.uri,
        "from": req.first_header("From"),
        "to": req.first_header("To"),
        "call_id": req.first_header("Call-ID"),
        "cseq": req.first_header("CSeq"),
        "content_type": content_type,
        "content_length": req.first_header("Content-Length"),
        "body": req.body,
        "body_hex": req.body_bytes.hex().upper(),
        "sms_parse": sms_parse,
    }
    (LOG_DIR / f"{ts}_{transport.lower()}_{req.method}.json").write_text(
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
) -> bytes:
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
    return CRLF.join(lines).encode("utf-8") + body_bytes


def forward_to_ims(req: SIPRequest, sms_parse: dict[str, object] | None) -> None:
    if req.method != "MESSAGE" or sms_parse is None:
        return
    destination = sms_parse.get("best_effort_destination")
    if not isinstance(destination, str) or not destination:
        persist_forward_result(
            {
                "status": "skipped",
                "reason": "destination-not-found",
                "sms_parse": sms_parse,
                "call_id": req.first_header("Call-ID"),
            }
        )
        return

    originating = _extract_digits(req.first_header("From")) or "unknown"
    content_type = req.first_header("Content-Type") or "application/octet-stream"
    payload = build_forward_message(
        destination_msisdn=destination,
        originating_msisdn=originating,
        body_bytes=req.body_bytes,
        content_type=content_type,
    )
    event: dict[str, object] = {
        "status": "attempt",
        "destination_msisdn": destination,
        "originating_msisdn": originating,
        "scscf_host": SCSCF_HOST,
        "scscf_port": SCSCF_PORT,
        "call_id": req.first_header("Call-ID"),
        "content_type": content_type,
        "payload_hex_prefix": payload[:160].hex().upper(),
    }
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5.0)
            sock.sendto(payload, (SCSCF_HOST, SCSCF_PORT))
            data, addr = sock.recvfrom(65535)
            event["status"] = "response"
            event["response_from"] = f"{addr[0]}:{addr[1]}"
            event["response_text"] = data.decode("utf-8", errors="replace")
    except TimeoutError:
        event["status"] = "timeout"
    except OSError as exc:
        event["status"] = "error"
        event["error"] = str(exc)
    persist_forward_result(event)


def handle_request_bytes(data: bytes, transport: str, peer: tuple[str, int]) -> bytes | None:
    req = parse_sip_request(data)
    if req is None:
        return None
    print(
        f"[smsc] {transport} {peer[0]}:{peer[1]} {req.method} {req.uri} "
        f"call-id={req.first_header('Call-ID')}",
        flush=True,
    )
    sms_parse = None
    if req.first_header("Content-Type") == "application/vnd.3gpp.sms":
        sms_parse = parse_3gpp_sms_payload(req.body_bytes)
    persist_request(req, transport, peer)
    if req.method == "MESSAGE":
        threading.Thread(
            target=forward_to_ims,
            args=(req, sms_parse),
            daemon=True,
        ).start()
    if req.method == "MESSAGE":
        return build_response(req, 202, "Accepted")
    if req.method == "OPTIONS":
        return build_response(req, 200, "OK")
    return build_response(req, 405, "Method Not Allowed")


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
