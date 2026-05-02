from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure" / "smsc"))

from sms_parser import build_mt_3gpp_sms_payload, parse_3gpp_sms_payload


def test_build_mt_sms_payload_uses_network_to_ms_rp_data() -> None:
    payload = build_mt_3gpp_sms_payload(
        originating_msisdn="222222",
        service_center_msisdn="00155",
        text="VMF relay from 222222",
        rp_message_reference=6,
    )

    parsed = parse_3gpp_sms_payload(payload)

    assert payload[0] == 0x01
    assert parsed["rp_message_type"] == "0x01"
    assert parsed["rp_message_reference"] == 6
    assert parsed["payload_len"] > 20
    assert b"VMF relay from 222222" in payload


def test_parse_existing_mo_payload_extracts_destination_candidate() -> None:
    payload = bytes.fromhex("0006000581005155F51001060681111111000006D47B794EAF01")

    parsed = parse_3gpp_sms_payload(payload)

    assert parsed["rp_message_type"] == "0x00"
    assert parsed["best_effort_destination"] == "111111"
    assert parsed["best_effort_originating"] == "00155"
