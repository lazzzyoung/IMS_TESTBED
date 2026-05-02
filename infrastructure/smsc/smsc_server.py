from __future__ import annotations

import json
import os
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


def handle_request_bytes(data: bytes, transport: str, peer: tuple[str, int]) -> bytes | None:
    req = parse_sip_request(data)
    if req is None:
        return None
    print(
        f"[smsc] {transport} {peer[0]}:{peer[1]} {req.method} {req.uri} "
        f"call-id={req.first_header('Call-ID')}",
        flush=True,
    )
    persist_request(req, transport, peer)
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
