"""MT-INVITE wire-text template loader and renderer for real-UE-direct campaigns.

The template file (generator/templates/mt_invite_a31.sip.tmpl) contains the full
3GPP-compliant MT INVITE that a real Samsung A31 UE accepts, with {{slot}} placeholders
for fields that vary per-call or per-session (port_pc, Call-ID, From-tag, etc.).

Usage::

    template_text = load_mt_invite_template("a31")
    slots = build_default_slots(
        msisdn="111111",
        impi="001010000123511",
        pcscf_ip="172.22.0.21",
        port_pc=8000,
        port_ps=8001,
        mo_contact_host="10.20.20.9",
        mo_contact_port_pc=31800,
        mo_contact_port_ps=31100,
        seed=0,
    )
    wire_text = render_mt_invite(template_text, slots)
"""

from __future__ import annotations

import importlib.resources
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_CRLF: Final[str] = "\r\n"
_SLOT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{\{(\w+)\}\}")
_ICID_HEX_LEN: Final[int] = 32


@dataclass(frozen=True)
class MTInviteSlots:
    """All substitution values for one MT INVITE render."""

    impi: str
    to_msisdn: str
    from_msisdn: str
    ue_ip: str
    pcscf_ip: str
    request_uri_port_pc: int
    request_uri_port_ps: int
    mo_contact_host: str
    mo_contact_port_pc: int
    mo_contact_port_ps: int
    sdp_owner_ip: str
    sdp_audio_port: int
    sdp_rtcp_port: int
    local_port: int
    call_id: str
    from_tag: str
    branch: str
    icid: str


def load_mt_invite_template(name: str = "a31") -> str:
    """Return the raw template text for the named MT INVITE shape.

    *name* is either a bundled template identifier (e.g. ``"a31"``) or an
    absolute/relative path to a custom ``.sip.tmpl`` file.  The returned text
    uses ``\\n`` line endings; ``render_mt_invite`` normalises to CRLF.
    """
    path = Path(name)
    if path.exists():
        return path.read_text(encoding="utf-8")

    resource_name = f"mt_invite_{name}.sip.tmpl"
    package_ref = importlib.resources.files("volte_mutation_fuzzer.generator.templates")
    resource = package_ref / resource_name
    return resource.read_text(encoding="utf-8")


def render_mt_invite(template_text: str, slots: MTInviteSlots) -> str:
    """Substitute *slots* into *template_text*, normalise CRLF, recompute Content-Length.

    Raises ``ValueError`` if any ``{{...}}`` placeholder remains after substitution.
    """
    mapping: dict[str, str] = {
        "impi": slots.impi,
        "to_msisdn": slots.to_msisdn,
        "from_msisdn": slots.from_msisdn,
        "ue_ip": slots.ue_ip,
        "pcscf_ip": slots.pcscf_ip,
        "request_uri_port_pc": str(slots.request_uri_port_pc),
        "request_uri_port_ps": str(slots.request_uri_port_ps),
        "mo_contact_host": slots.mo_contact_host,
        "mo_contact_port_pc": str(slots.mo_contact_port_pc),
        "mo_contact_port_ps": str(slots.mo_contact_port_ps),
        "sdp_owner_ip": slots.sdp_owner_ip,
        "sdp_audio_port": str(slots.sdp_audio_port),
        "sdp_rtcp_port": str(slots.sdp_rtcp_port),
        "local_port": str(slots.local_port),
        "call_id": slots.call_id,
        "from_tag": slots.from_tag,
        "branch": slots.branch,
        "icid": slots.icid,
        # content_length is filled last after CRLF normalisation
        "content_length": "",
    }

    text = template_text
    for key, value in mapping.items():
        text = text.replace(f"{{{{{key}}}}}", value)

    # Normalise line endings to CRLF (template file uses LF on disk)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", _CRLF)

    # Split headers / body at the blank line separator
    separator = _CRLF + _CRLF
    if separator not in text:
        raise ValueError("template has no blank-line header/body separator after substitution")

    header_part, body_part = text.split(separator, 1)

    # Recompute Content-Length from actual SDP body byte count
    body_bytes = body_part.encode("utf-8")
    content_length = len(body_bytes)

    # Replace the placeholder Content-Length value (rendered as empty string above)
    header_part = header_part.replace("Content-Length: ", f"Content-Length: {content_length}", 1)

    # Verify no leftover {{...}} slots
    remaining = _SLOT_PATTERN.findall(header_part) + _SLOT_PATTERN.findall(body_part)
    if remaining:
        raise ValueError(f"unresolved template slots after substitution: {remaining}")

    return header_part + separator + body_part


def build_default_slots(
    *,
    msisdn: str,
    impi: str,
    pcscf_ip: str,
    port_pc: int,
    port_ps: int,
    mo_contact_host: str,
    mo_contact_port_pc: int,
    mo_contact_port_ps: int,
    seed: int,
    ue_ip: str = "10.20.20.8",
    from_msisdn: str = "222222",
    local_port: int = 5100,
    env: dict[str, str] | None = None,
) -> MTInviteSlots:
    """Build ``MTInviteSlots`` with deterministic per-seed call identifiers.

    Call-ID, From-tag, branch, and ICID are derived from *seed* so that
    replaying the same seed reproduces the same packet shape.
    """
    source = env if env is not None else dict(os.environ)
    sdp_owner_ip = source.get("VMF_REAL_UE_SDP_OWNER_IP", "172.22.0.16")
    sdp_audio_port = int(source.get("VMF_REAL_UE_SDP_AUDIO_PORT", "49196"))

    rng = random.Random(seed)

    tag_bytes = rng.getrandbits(32)
    call_id_bytes = rng.getrandbits(64)
    branch_bytes = rng.getrandbits(32)
    icid_bytes = rng.getrandbits(128)

    from_tag = f"vmf{tag_bytes:08x}"
    call_id = f"{call_id_bytes:016x}@{mo_contact_host}"
    branch = f"z9hG4bKvmf{branch_bytes:08x}"
    icid = f"{icid_bytes:032X}"

    return MTInviteSlots(
        impi=impi,
        to_msisdn=msisdn,
        from_msisdn=from_msisdn,
        ue_ip=ue_ip,
        pcscf_ip=pcscf_ip,
        request_uri_port_pc=port_pc,
        request_uri_port_ps=port_ps,
        mo_contact_host=mo_contact_host,
        mo_contact_port_pc=mo_contact_port_pc,
        mo_contact_port_ps=mo_contact_port_ps,
        sdp_owner_ip=sdp_owner_ip,
        sdp_audio_port=sdp_audio_port,
        sdp_rtcp_port=sdp_audio_port + 1,
        local_port=local_port,
        call_id=call_id,
        from_tag=from_tag,
        branch=branch,
        icid=icid,
    )


__all__ = [
    "MTInviteSlots",
    "build_default_slots",
    "load_mt_invite_template",
    "render_mt_invite",
]
