import re

from volte_mutation_fuzzer.adb.contracts import AnomalyCategory, AnomalySeverity


class AnomalyPattern:
    def __init__(
        self,
        name: str,
        regex: str,
        severity: AnomalySeverity,
        category: AnomalyCategory,
    ) -> None:
        self.name = name
        self.regex = regex
        self.severity = severity
        self.category = category
        self.compiled = re.compile(regex, re.IGNORECASE)


ANOMALY_PATTERNS: tuple[AnomalyPattern, ...] = (
    AnomalyPattern("SIGSEGV", r"SIGSEGV|signal 11", "critical", "fatal_signal"),
    AnomalyPattern("SIGABRT", r"SIGABRT|signal 6", "critical", "fatal_signal"),
    AnomalyPattern(
        "tombstone",
        r"tombstone.*written|Tombstone written",
        "critical",
        "fatal_signal",
    ),
    AnomalyPattern(
        "native_crash",
        r"Fatal signal|DEBUG\s*:.*\*\*\*",
        "critical",
        "fatal_signal",
    ),
    AnomalyPattern(
        "ims_deregistration",
        r"IMS.*(?:deregist|DEREGIST)",
        "warning",
        "ims_anomaly",
    ),
    AnomalyPattern(
        "ims_reg_failure",
        r"IMS.*(?:registration.*fail|reg.*fail)",
        "warning",
        "ims_anomaly",
    ),
    AnomalyPattern(
        "pdn_disconnect",
        r"PDN.*disconnect|PDN.*lost",
        "warning",
        "ims_anomaly",
    ),
    AnomalyPattern(
        "ims_registered",
        r"IMS.*(?:registered|REGISTERED)",
        "info",
        "ims_anomaly",
    ),
    AnomalyPattern(
        "unexpected_disconnect",
        r"(?:call|CALL).*(?:disconnect|DROP).*unexpected",
        "warning",
        "call_anomaly",
    ),
    AnomalyPattern(
        "oem_ril_error",
        r"oem.*ril.*error|RILJ.*Error",
        "warning",
        "call_anomaly",
    ),
    AnomalyPattern(
        "oem_ril_crash",
        r"oem.*ril.*(?:crash|restart|died)",
        "critical",
        "call_anomaly",
    ),
    AnomalyPattern(
        "system_server_restart",
        r"system_server.*(?:restart|crash|died)",
        "critical",
        "system_anomaly",
    ),
    AnomalyPattern(
        "telephony_crash",
        r"(?:com\.android\.phone|telephony).*(?:crash|died|killed)",
        "critical",
        "system_anomaly",
    ),
    AnomalyPattern(
        "lmk_ims",
        r"(?:lowmemorykiller|lmk).*(?:ims|com\.android\.ims)",
        "warning",
        "system_anomaly",
    ),
)
