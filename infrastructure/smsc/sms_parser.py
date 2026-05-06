from __future__ import annotations

from math import ceil

_SMS_DEFAULT_SMSC = "821000000000"
_SMS_DEFAULT_SCTS_HEX = "62403151423300"
_RP_MESSAGE_TYPE_NAMES = {
    0x00: "rp-data-ms-to-network",
    0x01: "rp-data-network-to-ms",
    0x02: "rp-ack-ms-to-network",
    0x03: "rp-ack-network-to-ms",
    0x04: "rp-error-ms-to-network",
    0x05: "rp-error-network-to-ms",
    0x06: "rp-smma",
}
_TPDU_TYPE_NAMES = {
    0x00: "sms-deliver",
    0x01: "sms-submit",
    0x02: "sms-status-report",
}


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


def _decode_tbcd_all(raw: bytes) -> str:
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
    return "".join(digits)


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


def _decode_rp_address(raw: bytes) -> dict[str, object] | None:
    if not raw:
        return None
    ton_npi = raw[0]
    digits = _decode_tbcd_all(raw[1:])
    return {
        "ton_npi": f"0x{ton_npi:02X}",
        "digits": digits,
    }


def _best_effort_ud_text(user_data: bytes) -> str | None:
    if not user_data:
        return None
    try:
        text = user_data.decode("ascii", errors="replace")
    except Exception:
        return None
    return text


def _parse_tpdu(tpdu: bytes) -> dict[str, object]:
    result: dict[str, object] = {
        "tpdu_len": len(tpdu),
        "tpdu_hex": tpdu.hex().upper(),
    }
    if not tpdu:
        result["empty"] = True
        return result

    first_octet = tpdu[0]
    mti = first_octet & 0x03
    result["tpdu_first_octet"] = f"0x{first_octet:02X}"
    result["tpdu_mti"] = mti
    result["tpdu_type"] = _TPDU_TYPE_NAMES.get(mti, "unknown")

    if mti == 0x01 and len(tpdu) >= 5:
        # SMS-SUBMIT
        result["tp_message_reference"] = tpdu[1]
        digits_len = tpdu[2]
        ton_npi = tpdu[3]
        size = ceil(digits_len / 2)
        end = 4 + size
        if end <= len(tpdu):
            destination = _decode_tbcd(tpdu[4:end], digits_len)
            result["tp_destination"] = {
                "digits_len": digits_len,
                "ton_npi": f"0x{ton_npi:02X}",
                "digits": destination,
            }
        idx = end
        if idx + 2 <= len(tpdu):
            result["tp_pid"] = f"0x{tpdu[idx]:02X}"
            result["tp_dcs"] = f"0x{tpdu[idx + 1]:02X}"
            idx += 2
        if idx < len(tpdu):
            udl = tpdu[idx]
            result["tp_user_data_length"] = udl
            user_data = tpdu[idx + 1 : idx + 1 + udl]
            result["tp_user_data_hex"] = user_data.hex().upper()
            text = _best_effort_ud_text(user_data)
            if text is not None:
                result["tp_user_data_text"] = text

    elif mti == 0x00 and len(tpdu) >= 4:
        # SMS-DELIVER
        digits_len = tpdu[1]
        ton_npi = tpdu[2]
        size = ceil(digits_len / 2)
        end = 3 + size
        if end <= len(tpdu):
            originating = _decode_tbcd(tpdu[3:end], digits_len)
            result["tp_originating"] = {
                "digits_len": digits_len,
                "ton_npi": f"0x{ton_npi:02X}",
                "digits": originating,
            }
        idx = end
        if idx + 2 <= len(tpdu):
            result["tp_pid"] = f"0x{tpdu[idx]:02X}"
            result["tp_dcs"] = f"0x{tpdu[idx + 1]:02X}"
            idx += 2
        if idx + 7 <= len(tpdu):
            result["tp_scts_hex"] = tpdu[idx : idx + 7].hex().upper()
            idx += 7
        if idx < len(tpdu):
            udl = tpdu[idx]
            result["tp_user_data_length"] = udl
            user_data = tpdu[idx + 1 : idx + 1 + udl]
            result["tp_user_data_hex"] = user_data.hex().upper()
            text = _best_effort_ud_text(user_data)
            if text is not None:
                result["tp_user_data_text"] = text

    return result


def build_mt_3gpp_sms_payload(
    *,
    originating_msisdn: str,
    text: str,
    rp_message_reference: int,
    service_center_msisdn: str = _SMS_DEFAULT_SMSC,
    service_center_ton_npi: int = 0x91,
    originating_ton_npi: int = 0x91,
    rp_message_type: int = 0x01,
    scts_hex: str = _SMS_DEFAULT_SCTS_HEX,
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
        + scts_hex
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

    rp_message_type = payload[0]
    result["rp_message_type"] = f"0x{rp_message_type:02X}"
    result["rp_message_type_name"] = _RP_MESSAGE_TYPE_NAMES.get(rp_message_type, "unknown")
    if len(payload) > 1:
        result["rp_message_reference"] = payload[1]

    if rp_message_type in (0x00, 0x01) and len(payload) >= 4:
        idx = 2
        rp_originator_len = payload[idx]
        idx += 1
        rp_originator_raw = payload[idx : idx + rp_originator_len]
        idx += rp_originator_len
        result["rp_originator_address_length"] = rp_originator_len
        if rp_originator_raw:
            result["rp_originator_address"] = _decode_rp_address(rp_originator_raw)

        if idx < len(payload):
            rp_destination_len = payload[idx]
            idx += 1
            rp_destination_raw = payload[idx : idx + rp_destination_len]
            idx += rp_destination_len
            result["rp_destination_address_length"] = rp_destination_len
            if rp_destination_raw:
                result["rp_destination_address"] = _decode_rp_address(rp_destination_raw)

        if idx < len(payload):
            rp_user_data_len = payload[idx]
            idx += 1
            rp_user_data = payload[idx : idx + rp_user_data_len]
            result["rp_user_data_length"] = rp_user_data_len
            result["rp_user_data_hex"] = rp_user_data.hex().upper()
            result["tpdu"] = _parse_tpdu(rp_user_data)

            tpdu = result["tpdu"]
            if isinstance(tpdu, dict):
                tp_destination = tpdu.get("tp_destination")
                if isinstance(tp_destination, dict) and isinstance(tp_destination.get("digits"), str):
                    result["tp_destination_digits"] = tp_destination["digits"]
                    result["best_effort_destination"] = tp_destination["digits"]
                tp_originating = tpdu.get("tp_originating")
                if isinstance(tp_originating, dict) and isinstance(tp_originating.get("digits"), str):
                    result["tp_originating_digits"] = tp_originating["digits"]
                    result["best_effort_originating"] = tp_originating["digits"]

    candidates = _scan_address_candidates(payload)
    if candidates:
        result["address_candidates"] = candidates
        tel_candidates = [c["digits"] for c in candidates if isinstance(c.get("digits"), str)]
        if tel_candidates:
            result.setdefault("best_effort_destination", tel_candidates[-1])
            result.setdefault("best_effort_originating", tel_candidates[0])

    return result
