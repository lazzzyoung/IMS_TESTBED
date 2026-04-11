"""
Real-time crash analysis for VolteMutationFuzzer campaigns
"""

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from volte_mutation_fuzzer.campaign.contracts import CaseResult


@dataclass
class CrashCase:
    """Detailed crash case information"""
    case_id: int
    verdict: str  # crash, stack_failure, suspicious
    reason: str
    method: str
    layer: str
    strategy: str
    mutation_ops: List[str]
    elapsed_ms: float
    response_code: Optional[int]
    pcap_path: Optional[str]
    timestamp: float
    packet_summary: Optional[str] = None
    crash_category: Optional[str] = None


class PacketAnalyzer:
    """Analyze pcap files for packet content"""

    @staticmethod
    def analyze_pcap(pcap_path: str) -> Optional[str]:
        """Extract SIP message summary from pcap file"""
        if not pcap_path or not Path(pcap_path).exists():
            return None

        try:
            # Extract SIP message using tcpdump (first packet only)
            result = subprocess.run([
                'tcpdump', '-r', pcap_path, '-A', '-c', '1',
                'src', '172.22.0.21'  # From P-CSCF
            ], capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return "pcap analysis failed"

            output = result.stdout

            # Extract SIP method
            method_match = re.search(r'(INVITE|OPTIONS|REGISTER|MESSAGE|BYE|ACK|CANCEL)\s+sip:', output)
            method = method_match.group(1) if method_match else "Unknown"

            # Extract Request-URI
            uri_match = re.search(r'sip:([^@]+@[^;\s]+)', output)
            uri = uri_match.group(1) if uri_match else "unknown"

            # Extract Content-Length
            content_len_match = re.search(r'Content-Length:\s*(\d+)', output)
            content_len = content_len_match.group(1) if content_len_match else "0"

            # Detect anomalies
            anomalies = []
            if len(output) > 5000:  # Oversized packet
                anomalies.append("oversized")
            if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\xFF]', output):  # Binary data
                anomalies.append("binary_data")
            if re.search(r'(.{100,})\1', output):  # Repetitive pattern
                anomalies.append("repetitive")

            summary_parts = [f"{method} {uri}", f"len={content_len}"]
            if anomalies:
                summary_parts.append(f"anomalies={','.join(anomalies)}")

            return " | ".join(summary_parts)

        except Exception as e:
            return f"pcap analysis error: {e}"


class CrashCategorizer:
    """Automatic crash type classification"""

    CATEGORIES = {
        'memory_corruption': [
            r'SIGSEGV', r'SIGABRT', r'segmentation fault',
            r'double free', r'heap.*corruption', r'buffer.*overflow',
            r'use.*after.*free', r'null.*pointer'
        ],
        'parser_crash': [
            r'parsing.*failed', r'malformed.*message', r'invalid.*format',
            r'unexpected.*token', r'parse.*error', r'400.*bad.*request'
        ],
        'protocol_violation': [
            r'415.*unsupported.*media', r'481.*call.*not.*found',
            r'482.*loop.*detected', r'protocol.*violation'
        ],
        'resource_exhaustion': [
            r'out.*of.*memory', r'too.*many.*connections',
            r'resource.*limit', r'timeout.*exceeded'
        ],
        'authentication_error': [
            r'401.*unauthorized', r'403.*forbidden',
            r'authentication.*failed', r'invalid.*credentials'
        ],
        'state_machine_error': [
            r'invalid.*state', r'unexpected.*response',
            r'state.*transition.*error', r'dialog.*mismatch'
        ]
    }

    @classmethod
    def categorize(cls, reason: str, verdict: str) -> str:
        """Categorize crash based on reason and verdict"""
        reason_lower = reason.lower()

        # Pattern matching
        for category, patterns in cls.CATEGORIES.items():
            for pattern in patterns:
                if re.search(pattern, reason_lower):
                    return category

        # Verdict-based fallback
        if verdict == "crash":
            return "process_crash"
        elif verdict == "stack_failure":
            return "stack_trace"
        elif verdict == "suspicious":
            return "protocol_error"

        return "unknown"


class CampaignCrashAnalyzer:
    """Integrated crash analyzer for campaign execution"""

    def __init__(self, output_dir: str = "crash_analysis", enabled: bool = True):
        self.output_dir = Path(output_dir)
        self.enabled = enabled

        if not self.enabled:
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Analysis state
        self.crash_cases: List[CrashCase] = []
        self.analysis_start_time = time.time()

        # Analysis tools
        self.packet_analyzer = PacketAnalyzer()
        self.categorizer = CrashCategorizer()

        # Statistics
        self.stats = {
            'total_cases': 0,
            'crashes': 0,
            'stack_failures': 0,
            'suspicious': 0,
            'categories': {}
        }

        print("🔍 Real-time crash analysis enabled")
        print(f"📊 Analysis output: {self.output_dir}")

    def analyze_case_immediately(self, case_result: CaseResult) -> None:
        """Analyze a case result immediately after execution"""
        if not self.enabled:
            return

        # Update statistics
        self.stats['total_cases'] += 1
        verdict = case_result.verdict

        # Only analyze critical cases
        if verdict in ['crash', 'stack_failure', 'suspicious']:
            self.stats[verdict.replace('_', '_').lower()] = self.stats.get(verdict.replace('_', '_').lower(), 0) + 1

            # Detailed analysis
            crash_case = self._convert_case_result(case_result)
            self.crash_cases.append(crash_case)

            # Update category stats
            category = crash_case.crash_category
            self.stats['categories'][category] = self.stats['categories'].get(category, 0) + 1

            # Immediate notification
            self._notify_crash(crash_case)

            # Update live report
            self._update_live_report()

    def _convert_case_result(self, case_result: CaseResult) -> CrashCase:
        """Convert CaseResult to CrashCase with detailed analysis"""
        # Packet analysis
        packet_summary = None
        if case_result.pcap_path:
            packet_summary = self.packet_analyzer.analyze_pcap(case_result.pcap_path)

        # Crash categorization
        crash_category = self.categorizer.categorize(case_result.reason, case_result.verdict)

        # Handle mutation_ops (might be string or list)
        mutation_ops = case_result.mutation_ops
        if isinstance(mutation_ops, str):
            mutation_ops = [mutation_ops]
        elif not isinstance(mutation_ops, (list, tuple)):
            mutation_ops = []

        return CrashCase(
            case_id=case_result.case_id,
            verdict=case_result.verdict,
            reason=case_result.reason,
            method=case_result.method,
            layer=case_result.layer,
            strategy=case_result.strategy,
            mutation_ops=list(mutation_ops),
            elapsed_ms=case_result.elapsed_ms,
            response_code=case_result.response_code,
            pcap_path=case_result.pcap_path,
            timestamp=case_result.timestamp,
            packet_summary=packet_summary,
            crash_category=crash_category
        )

    def _notify_crash(self, crash_case: CrashCase) -> None:
        """Immediate console notification for crashes"""
        severity_emoji = {
            'crash': '💥',
            'stack_failure': '🔥',
            'suspicious': '⚠️'
        }

        emoji = severity_emoji.get(crash_case.verdict, '❓')

        print(f"\n{emoji} CRASH DETECTED:")
        print(f"  Case ID: {crash_case.case_id}")
        print(f"  Verdict: {crash_case.verdict}")
        print(f"  Category: {crash_case.crash_category}")
        print(f"  Config: {crash_case.method} | {crash_case.layer} | {crash_case.strategy}")
        print(f"  Reason: {crash_case.reason[:100]}{'...' if len(crash_case.reason) > 100 else ''}")

        if crash_case.mutation_ops:
            ops_summary = ', '.join(crash_case.mutation_ops[:3])
            if len(crash_case.mutation_ops) > 3:
                ops_summary += f'... (+{len(crash_case.mutation_ops)-3} more)'
            print(f"  Mutations: {ops_summary}")

        if crash_case.packet_summary:
            print(f"  Packet: {crash_case.packet_summary}")

        if crash_case.pcap_path:
            print(f"  Evidence: {crash_case.pcap_path}")

        print("-" * 60)

    def _update_live_report(self) -> None:
        """Update live summary report"""
        live_report = self.output_dir / "live_summary.txt"

        with open(live_report, 'w', encoding='utf-8') as f:
            f.write(f"🔍 LIVE CRASH ANALYSIS SUMMARY\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {time.time() - self.analysis_start_time:.1f}s\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"📊 STATISTICS:\n")
            f.write(f"  Total cases: {self.stats['total_cases']}\n")
            f.write(f"  Crashes: {self.stats.get('crashes', 0)}\n")
            f.write(f"  Stack failures: {self.stats.get('stack_failures', 0)}\n")
            f.write(f"  Suspicious: {self.stats.get('suspicious', 0)}\n")

            if self.stats['categories']:
                f.write(f"\n🏷️  CRASH CATEGORIES:\n")
                for category, count in sorted(self.stats['categories'].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"  {category}: {count}\n")

            if self.crash_cases:
                f.write(f"\n🚨 RECENT CRASHES (last 5):\n")
                for crash in self.crash_cases[-5:]:
                    f.write(f"  Case {crash.case_id}: {crash.verdict} - {crash.crash_category}\n")
                    f.write(f"    {crash.reason[:80]}{'...' if len(crash.reason) > 80 else ''}\n")

    def generate_final_report(self) -> None:
        """Generate comprehensive final report"""
        if not self.enabled or len(self.crash_cases) == 0:
            if self.enabled:
                print(f"✅ Campaign completed - no crashes detected")
            return

        report_file = self.output_dir / f"crash_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        json_file = self.output_dir / f"crash_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        print(f"\n📋 Generating crash analysis report...")

        # Text report
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("🔍 VOLTE FUZZER CRASH ANALYSIS REPORT\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Analysis duration: {time.time() - self.analysis_start_time:.1f}s\n\n")

            # Overall statistics
            f.write("📊 OVERALL STATISTICS:\n")
            f.write(f"  Total cases processed: {self.stats['total_cases']}\n")
            f.write(f"  Total crashes: {self.stats.get('crashes', 0)}\n")
            f.write(f"  Stack failures: {self.stats.get('stack_failures', 0)}\n")
            f.write(f"  Suspicious cases: {self.stats.get('suspicious', 0)}\n")

            total_critical = self.stats.get('crashes', 0) + self.stats.get('stack_failures', 0)
            if self.stats['total_cases'] > 0:
                critical_rate = (total_critical / self.stats['total_cases']) * 100
                f.write(f"  Critical issue rate: {critical_rate:.2f}%\n")
            f.write("\n")

            # Category analysis
            if self.stats['categories']:
                f.write("🏷️  CRASH CATEGORIES:\n")
                sorted_categories = sorted(self.stats['categories'].items(), key=lambda x: x[1], reverse=True)
                for category, count in sorted_categories:
                    percentage = (count / len(self.crash_cases)) * 100 if self.crash_cases else 0
                    f.write(f"  {category}: {count} cases ({percentage:.1f}%)\n")
                f.write("\n")

            # Layer/strategy effectiveness
            if self.crash_cases:
                f.write("🎯 FUZZING EFFECTIVENESS:\n")

                # Layer analysis
                layer_stats = {}
                strategy_stats = {}
                for crash in self.crash_cases:
                    layer_stats[crash.layer] = layer_stats.get(crash.layer, 0) + 1
                    strategy_stats[crash.strategy] = strategy_stats.get(crash.strategy, 0) + 1

                f.write("  Most effective layers:\n")
                for layer, count in sorted(layer_stats.items(), key=lambda x: x[1], reverse=True):
                    f.write(f"    {layer}: {count} crashes\n")

                f.write("  Most effective strategies:\n")
                for strategy, count in sorted(strategy_stats.items(), key=lambda x: x[1], reverse=True):
                    f.write(f"    {strategy}: {count} crashes\n")
                f.write("\n")

            # Top crash cases
            if self.crash_cases:
                f.write("🚨 TOP CRASH CASES:\n")

                # Sort by severity (crash > stack_failure > suspicious)
                severity_order = {'crash': 3, 'stack_failure': 2, 'suspicious': 1}
                sorted_crashes = sorted(self.crash_cases,
                                      key=lambda x: (severity_order.get(x.verdict, 0), x.case_id),
                                      reverse=True)

                for i, crash in enumerate(sorted_crashes[:10], 1):
                    f.write(f"\n  #{i} Case {crash.case_id} ({crash.verdict}):\n")
                    f.write(f"    Category: {crash.crash_category}\n")
                    f.write(f"    Config: {crash.method} | {crash.layer} | {crash.strategy}\n")
                    f.write(f"    Reason: {crash.reason}\n")

                    if crash.mutation_ops:
                        f.write(f"    Mutations: {', '.join(crash.mutation_ops[:3])}\n")

                    if crash.packet_summary:
                        f.write(f"    Packet: {crash.packet_summary}\n")

                    if crash.pcap_path:
                        f.write(f"    Evidence: {crash.pcap_path}\n")

                    f.write(f"    Timestamp: {datetime.fromtimestamp(crash.timestamp).strftime('%H:%M:%S')}\n")

            # Recommendations
            f.write(f"\n💡 RECOMMENDATIONS:\n")
            if total_critical > 0:
                f.write("  - Focus on reproducing top crash cases for deeper analysis\n")
                f.write("  - Analyze pcap files to understand exact malformed packets\n")
                f.write("  - Use successful layer/strategy combinations for targeted fuzzing\n")
            else:
                f.write("  - No critical crashes found in this session\n")
                f.write("  - Consider different fuzzing parameters or target methods\n")

            if self.stats.get('suspicious', 0) > 0:
                f.write("  - Investigate suspicious cases for potential security issues\n")

        # JSON data export
        json_data = {
            'analysis_info': {
                'generated_at': datetime.now().isoformat(),
                'analysis_duration_seconds': time.time() - self.analysis_start_time
            },
            'statistics': self.stats,
            'crash_cases': [asdict(crash) for crash in self.crash_cases]
        }

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Crash analysis reports generated:")
        print(f"  📋 Text report: {report_file}")
        print(f"  📊 JSON data: {json_file}")
        print(f"  🎯 Found: {len(self.crash_cases)} crash cases")

    def print_live_stats(self, force: bool = False) -> None:
        """Print live statistics (occasionally)"""
        if not self.enabled:
            return

        # Print stats every 10 crash cases or when forced
        if force or (len(self.crash_cases) > 0 and len(self.crash_cases) % 10 == 0):
            total_critical = self.stats.get('crashes', 0) + self.stats.get('stack_failures', 0)
            print(f"📊 Live stats: {self.stats['total_cases']} cases | {total_critical} critical issues found")