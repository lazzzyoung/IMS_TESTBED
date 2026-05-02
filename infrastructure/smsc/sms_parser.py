from __future__ import annotations

from datetime import datetime, timezone
from math import ceil


def _decode_tbcd(raw: bytes, digits_len: int) -> str:
    digits: list[str] = []
    for byte in raw:
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        for nibble in (low, high):
            if nibble == 0x0F:
                continue
            if 0 <= nibble <= 9:
                digits.append(str(nibble))
            else:
                digits.append(f"[{nibble:X}]")
            if len(digits) >= digits_len:
                return "".join(digits[:digits_len])
    return "".join(digits[:digits_len])


def _scan_address_candidates(payload: bytes) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for idx in range(1, len(payload) - 2):
        digits_len = payload[idx - 1]
        ton_npi = payload[idx]
        if digits_len == 0 or digits_len > 20:
            continue
        if ton_npi not in (0x81, 0x91):
            continue
        size = ceil(digits_len / 2)
        end = idx + 1 + size
        if end > len(payload):
            continue
        digits = _decode_tbcd(payload[idx + 1 : end], digits_len)
        if not digits:
            continue
        candidates.append(
            {
                "offset": idx - 1,
                "digits_len": digits_len,
                "ton_npi": f"0x{ton_npi:02X}",
                "digits": digits,
            }
        )
    dedup: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()
    for item in candidates:
        key = (int(item["offset"]), str(item["digits"]))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def _encode_tbcd(digits: str) -> str:
    padded = digits + ("F" if len(digits) % 2 else "")
    return "".join(padded[i + 1] + padded[i] for i in range(0, len(padded), 2))


def _encode_scts(dt: datetime | None = None) -> str:
    stamp = dt or datetime.now(timezone.utc)
    digits = stamp.strftime("%y%m%d%H%M%S") + "00"
    return "".join(digits[i + 1] + digits[i] for i in range(0, len(digits), 2))


def build_mt_3gpp_sms_payload(
    *,
    originating_msisdn: str,
    service_center_msisdn: str,
    text: str,
    rp_message_reference: int,
    service_center_ton_npi: int = 0x81,
    originating_ton_npi: int = 0x81,
    rp_message_type: int = 0x01,
) -> bytes:
    ud_bytes = text.encode("ascii", errors="replace")
    tp_oa = (
        f"{len(originating_msisdn):02X}"
        f"{originating_ton_npi:02X}"
        f"{_encode_tbcd(originating_msisdn)}"
    )
    tpdu_hex = (
        "04"  # SMS-DELIVER
        + tp_oa
        + "00"  # TP-PID
        + "04"  # TP-DCS: 8-bit data
        + _encode_scts()
        + f"{len(ud_bytes):02X}"
        + ud_bytes.hex().upper()
    )
    tpdu_len = len(bytes.fromhex(tpdu_hex))

    rp_oa_body = f"{service_center_ton_npi:02X}{_encode_tbcd(service_center_msisdn)}"
    rp_oa_len = len(bytes.fromhex(rp_oa_body))
    rp_hex = (
        f"{rp_message_type:02X}"
        f"{rp_message_reference & 0xFF:02X}"
        f"{rp_oa_len:02X}{rp_oa_body}"
        "00"
        f"{tpdu_len:02X}{tpdu_hex}"
    )
    return bytes.fromhex(rp_hex)


def parse_3gpp_sms_payload(payload: bytes) -> dict[str, object]:
    result: dict[str, object] = {
        "payload_len": len(payload),
        "payload_hex": payload.hex().upper(),
    }
    if not payload:
        result["empty"] = True
        return result

    result["rp_message_type"] = f"0x{payload[0]:02X}"
    if len(payload) > 1:
        result["rp_message_reference"] = payload[1]

    candidates = _scan_address_candidates(payload)
    if candidates:
        result["address_candidates"] = candidates
        tel_candidates = [c["digits"] for c in candidates if isinstance(c.get("digits"), str)]
        if tel_candidates:
            result["best_effort_destination"] = tel_candidates[-1]
            result["best_effort_originating"] = tel_candidates[0]

    return result
