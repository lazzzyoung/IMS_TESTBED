from __future__ import annotations

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
