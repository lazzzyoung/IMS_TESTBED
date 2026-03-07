from __future__ import annotations

from volte_mutation_fuzzer.sip import SIP_CATALOG


def main() -> None:
    response_counts = SIP_CATALOG.grouped_response_counts()
    print(
        "SIP catalog ready: "
        f"{SIP_CATALOG.request_count} requests, "
        f"{SIP_CATALOG.response_count} responses "
        f"(1xx={response_counts[1]}, 2xx={response_counts[2]}, 3xx={response_counts[3]}, "
        f"4xx={response_counts[4]}, 5xx={response_counts[5]}, 6xx={response_counts[6]})"
    )
