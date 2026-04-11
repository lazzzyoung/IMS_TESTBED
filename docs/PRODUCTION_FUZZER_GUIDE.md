# VolteMutationFuzzer 야무진 퍼저 운영 가이드

> **목표**: VolteMutationFuzzer를 실전급 고성능 퍼징 도구로 운영하는 완벽 가이드

## 🎯 야무진 퍼저란?

**성능 + 자동화 + 분석력**을 갖춘 실전 퍼징 시스템:
- 🚀 **고속 처리**: 최적화된 설정으로 처리량 극대화
- 🤖 **자동화**: 무인 야간 배치 + 자동 결과 분석
- 🧠 **지능형 분석**: 취약점 자동 분류 + 재현 명령어 생성  
- 📊 **실시간 모니터링**: 상태 추적 + 알림 시스템
- 🔍 **정밀 타겟팅**: 전략적 변이 + 집중 공격

---

## ⚡ 1. 성능 최적화

### 현재 성능 벤치마크
- **Real-UE-Direct (A31)**: ~30 cases/minute
- **Softphone**: ~100 cases/minute

### 고속 설정
```bash
# 🚀 터보 모드 설정
--timeout 3              # 5초 → 3초 단축
--cooldown 0.05          # 0.2초 → 0.05초 최소화
--no-process-check       # 프로세스 체크 생략
--max-cases 5000         # 큰 배치로 처리
```

### 리소스 최적화
```bash
# 💾 선택적 pcap (디스크 절약)
# crash/stack_failure 시에만 자동 저장됨

# 🔧 메모리 효율성
--max-cases 2000         # 메모리 사용량 제한
# 큰 배치 대신 여러 번 실행 권장
```

### 실제 고속 명령어
```bash
# A31 터보 퍼징
uv run fuzzer campaign run \
  --mode real-ue-direct --target-msisdn 111111 \
  --impi 001010000123511 --mt-invite-template a31 \
  --ipsec-mode null --methods INVITE \
  --layer wire,byte --strategy default \
  --timeout 3 --cooldown 0.05 --no-process-check \
  --max-cases 5000 \
  --output results/turbo_$(date +%Y%m%d_%H%M).jsonl
```

---

## 🤖 2. 배치 실행 시스템

### 야간 퍼징 스크립트

**파일**: `scripts/overnight_fuzzer.sh`
```bash
#!/bin/bash
# VolteMutationFuzzer 야간 배치 실행기

set -euo pipefail

# 설정
DATE=$(date +%Y%m%d)
TIME=$(date +%H%M)
BASE_DIR="results/overnight_$DATE"
A31_SERIAL="SM_A315F_12345"  # 실제 A31 시리얼로 수정

# 디렉토리 준비
mkdir -p "$BASE_DIR/pcap"
mkdir -p "$BASE_DIR/reports"

echo "🌙 Starting overnight fuzzing session: $DATE"

# Phase 1: A31 INVITE 집중 공격 (4시간)
echo "📱 Phase 1: A31 MT-INVITE Fuzzing"
uv run fuzzer campaign run \
  --mode real-ue-direct --target-msisdn 111111 \
  --impi 001010000123511 --mt-invite-template a31 \
  --ipsec-mode null --methods INVITE \
  --layer wire,byte --strategy identity,default \
  --max-cases 10000 --timeout 3 --cooldown 0.1 \
  --output "$BASE_DIR/a31_invite.jsonl" \
  --pcap --pcap-dir "$BASE_DIR/pcap" \
  --adb --adb-serial "$A31_SERIAL"

# Phase 2: 다양한 메서드 탐색 (2시간)
echo "🔍 Phase 2: Multi-method exploration"
for METHOD in OPTIONS MESSAGE REGISTER; do
  uv run fuzzer campaign run \
    --mode real-ue-direct --target-msisdn 111111 \
    --impi 001010000123511 \
    --ipsec-mode null --methods "$METHOD" \
    --layer wire,byte --strategy default \
    --max-cases 1000 --timeout 3 --cooldown 0.1 \
    --output "$BASE_DIR/${METHOD,,}.jsonl" \
    --pcap --pcap-dir "$BASE_DIR/pcap"
done

# 결과 통합 및 분석
echo "📊 Analyzing results..."
./scripts/analyze_overnight_results.sh "$BASE_DIR"

echo "✅ Overnight fuzzing completed: $(date)"
```

### 결과 분석 스크립트

**파일**: `scripts/analyze_overnight_results.sh`
```bash
#!/bin/bash
# 야간 퍼징 결과 자동 분석기

BASE_DIR="$1"
REPORT_DIR="$BASE_DIR/reports"
SUMMARY_FILE="$REPORT_DIR/overnight_summary.txt"

mkdir -p "$REPORT_DIR"

echo "📊 OVERNIGHT FUZZING ANALYSIS REPORT" > "$SUMMARY_FILE"
echo "Generated: $(date)" >> "$SUMMARY_FILE"
echo "=========================================" >> "$SUMMARY_FILE"

# 전체 통계 수집
echo -e "\n🔢 OVERALL STATISTICS:" >> "$SUMMARY_FILE"
TOTAL_CASES=0
TOTAL_CRASHES=0
TOTAL_SUSPICIOUS=0

for jsonl in "$BASE_DIR"/*.jsonl; do
  if [ -f "$jsonl" ]; then
    BASENAME=$(basename "$jsonl" .jsonl)
    echo "  $BASENAME:" >> "$SUMMARY_FILE"
    
    # 케이스 수 계산
    CASES=$(grep -c '"type":"case"' "$jsonl" || echo 0)
    CRASHES=$(grep -c '"verdict":"crash"' "$jsonl" || echo 0)
    STACK_FAILURES=$(grep -c '"verdict":"stack_failure"' "$jsonl" || echo 0)
    SUSPICIOUS=$(grep -c '"verdict":"suspicious"' "$jsonl" || echo 0)
    
    echo "    Cases: $CASES, Crashes: $CRASHES, Stack failures: $STACK_FAILURES, Suspicious: $SUSPICIOUS" >> "$SUMMARY_FILE"
    
    TOTAL_CASES=$((TOTAL_CASES + CASES))
    TOTAL_CRASHES=$((TOTAL_CRASHES + CRASHES + STACK_FAILURES))
    TOTAL_SUSPICIOUS=$((TOTAL_SUSPICIOUS + SUSPICIOUS))
  fi
done

echo -e "\n🎯 TOTAL SUMMARY:" >> "$SUMMARY_FILE"
echo "  Total cases: $TOTAL_CASES" >> "$SUMMARY_FILE"
echo "  Total crashes: $TOTAL_CRASHES" >> "$SUMMARY_FILE"
echo "  Total suspicious: $TOTAL_SUSPICIOUS" >> "$SUMMARY_FILE"
echo "  Crash rate: $(echo "scale=2; $TOTAL_CRASHES * 100 / $TOTAL_CASES" | bc -l)%" >> "$SUMMARY_FILE"

# 중요 케이스 추출
echo -e "\n🚨 CRITICAL CRASH CASES:" >> "$SUMMARY_FILE"
for jsonl in "$BASE_DIR"/*.jsonl; do
  if [ -f "$jsonl" ]; then
    jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | 
           "Case \(.case_id): \(.verdict) - \(.reason) [\(.pcap_path // "no pcap")]"' "$jsonl" 2>/dev/null >> "$SUMMARY_FILE" || true
  fi
done

# 재현 명령어 생성
echo -e "\n🔄 REPRODUCTION COMMANDS:" >> "$SUMMARY_FILE"
for jsonl in "$BASE_DIR"/*.jsonl; do
  if [ -f "$jsonl" ]; then
    jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | 
           .reproduction_cmd' "$jsonl" 2>/dev/null | head -5 >> "$SUMMARY_FILE" || true
  fi
done

# pcap 파일 목록
echo -e "\n📦 PCAP FILES FOR ANALYSIS:" >> "$SUMMARY_FILE"
find "$BASE_DIR/pcap" -name "*.pcap" -type f | sort >> "$SUMMARY_FILE" || true

# Slack/Discord 알림 (옵션)
if [ "$TOTAL_CRASHES" -gt 0 ] && [ -n "${SLACK_WEBHOOK:-}" ]; then
    curl -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"🚨 Overnight VoLTE Fuzzing: $TOTAL_CRASHES crashes found! Check $BASE_DIR\"}"
fi

echo "📋 Analysis complete. Report saved to: $SUMMARY_FILE"
cat "$SUMMARY_FILE"
```

---

## 🧠 3. 지능형 결과 분석

### 스마트 분석 도구

**파일**: `scripts/smart_analyzer.sh`
```bash
#!/bin/bash
# VolteMutationFuzzer 지능형 결과 분석기

JSONL_FILE="${1:-results/campaign.jsonl}"

if [ ! -f "$JSONL_FILE" ]; then
    echo "❌ JSONL file not found: $JSONL_FILE"
    exit 1
fi

echo "🧠 SMART ANALYSIS: $JSONL_FILE"
echo "Generated: $(date)"
echo "================================================="

# 1. 기본 통계
echo -e "\n📊 BASIC STATISTICS:"
uv run fuzzer campaign report "$JSONL_FILE"

# 2. 취약점 클러스터링
echo -e "\n🎯 VULNERABILITY CLUSTERING:"
echo "Critical cases (crash + stack_failure):"
jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | 
       "  Case \(.case_id): \(.method) \(.layer)/\(.strategy) - \(.reason)"' "$JSONL_FILE" 2>/dev/null || echo "None found"

# 3. 응답 코드 패턴 분석
echo -e "\n📈 RESPONSE CODE PATTERNS:"
echo "Suspicious response codes (frequency):"
jq -r 'select(.type=="case" and .verdict=="suspicious") | .response_code // "unknown"' "$JSONL_FILE" 2>/dev/null | 
       sort | uniq -c | sort -rn | head -10

# 4. 성능 분석
echo -e "\n⚡ PERFORMANCE ANALYSIS:"
TOTAL_TIME=$(jq -r 'select(.type=="case") | .elapsed_ms' "$JSONL_FILE" 2>/dev/null | awk '{sum+=$1} END {print sum/1000}')
CASE_COUNT=$(grep -c '"type":"case"' "$JSONL_FILE" || echo 0)
echo "Total execution time: ${TOTAL_TIME:-0}s"
echo "Average case time: $(echo "scale=2; ${TOTAL_TIME:-0} / ${CASE_COUNT:-1}" | bc -l)s"
echo "Throughput: $(echo "scale=2; ${CASE_COUNT:-0} * 60 / ${TOTAL_TIME:-1}" | bc -l) cases/min"

# 5. 레이어/전략 효과성
echo -e "\n🎭 LAYER/STRATEGY EFFECTIVENESS:"
for LAYER in wire byte model; do
    CRASHES=$(jq -r "select(.type==\"case\" and .layer==\"$LAYER\" and (.verdict==\"crash\" or .verdict==\"stack_failure\")) | .case_id" "$JSONL_FILE" 2>/dev/null | wc -l)
    TOTAL=$(jq -r "select(.type==\"case\" and .layer==\"$LAYER\") | .case_id" "$JSONL_FILE" 2>/dev/null | wc -l)
    if [ "$TOTAL" -gt 0 ]; then
        RATE=$(echo "scale=2; $CRASHES * 100 / $TOTAL" | bc -l)
        echo "  $LAYER layer: $CRASHES/$TOTAL crashes (${RATE}%)"
    fi
done

# 6. 시간대별 성능
echo -e "\n⏰ TIME-BASED PERFORMANCE:"
jq -r 'select(.type=="case") | "\(.timestamp) \(.verdict)"' "$JSONL_FILE" 2>/dev/null | 
       awk '{
           time = strftime("%H", $1); 
           verdict = $2; 
           hour[time]++; 
           if(verdict=="crash" || verdict=="stack_failure") crash[time]++;
       } 
       END {
           for(h=0; h<24; h++) {
               printf("  %02d:00 - %d cases, %d crashes\n", h, hour[sprintf("%02d", h)]+0, crash[sprintf("%02d", h)]+0)
           }
       }' | grep -v " 0 cases"

# 7. 핫스팟 식별 (자주 crash나는 패턴)
echo -e "\n🔥 CRASH HOTSPOTS:"
echo "Most crash-prone mutation operations:"
jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | .mutation_ops[]?' "$JSONL_FILE" 2>/dev/null | 
       sort | uniq -c | sort -rn | head -5

# 8. 재현 명령어 생성 (우선순위별)
echo -e "\n🔄 HIGH-PRIORITY REPRODUCTION COMMANDS:"
jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | 
       {case_id, verdict, reason, reproduction_cmd}' "$JSONL_FILE" 2>/dev/null | 
       jq -r '"## Case \(.case_id) (\(.verdict))\n# \(.reason)\n\(.reproduction_cmd)\n"' | head -20

echo -e "\n✅ Smart analysis complete!"
```

### 취약점 분류기

**파일**: `scripts/vulnerability_classifier.py`
```python
#!/usr/bin/env python3
"""VolteMutationFuzzer 취약점 자동 분류기"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


class VulnerabilityClassifier:
    """취약점을 유형별로 자동 분류하는 클래스"""
    
    # 취약점 패턴 정의
    PATTERNS = {
        'memory_corruption': [
            r'SIGSEGV', r'SIGABRT', r'segmentation fault',
            r'double free', r'heap corruption', r'buffer overflow'
        ],
        'parser_crash': [
            r'parsing.*(failed|error)', r'malformed.*message',
            r'invalid.*format', r'unexpected.*token'
        ],
        'protocol_violation': [
            r'400.*bad.*request', r'415.*unsupported.*media',
            r'481.*call.*not.*found', r'482.*loop.*detected'
        ],
        'resource_exhaustion': [
            r'out of memory', r'too many.*connections',
            r'resource.*limit', r'timeout.*exceeded'
        ],
        'authentication_bypass': [
            r'401.*unauthorized', r'403.*forbidden',
            r'authentication.*failed', r'invalid.*credentials'
        ]
    }
    
    def classify_case(self, case_data: dict) -> str:
        """케이스를 분류하여 취약점 유형 반환"""
        if case_data.get('verdict') not in ['crash', 'stack_failure', 'suspicious']:
            return 'normal'
            
        reason = case_data.get('reason', '').lower()
        
        # 패턴 매칭으로 분류
        for vuln_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, reason, re.IGNORECASE):
                    return vuln_type
        
        # 응답 코드 기반 분류
        response_code = case_data.get('response_code')
        if response_code:
            if 400 <= response_code < 500:
                return 'protocol_violation'
            elif 500 <= response_code < 600:
                return 'server_error'
        
        return 'unknown'
    
    def analyze_file(self, jsonl_path: Path) -> dict:
        """JSONL 파일 전체 분석"""
        classifications = defaultdict(list)
        total_cases = 0
        
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                    
                try:
                    data = json.loads(line)
                    if data.get('type') != 'case':
                        continue
                        
                    total_cases += 1
                    case_type = self.classify_case(data)
                    classifications[case_type].append(data)
                    
                except json.JSONDecodeError:
                    continue
        
        return {
            'total_cases': total_cases,
            'classifications': dict(classifications),
            'summary': {k: len(v) for k, v in classifications.items()}
        }
    
    def generate_report(self, analysis: dict) -> str:
        """분석 결과 리포트 생성"""
        report = []
        report.append("🔬 VULNERABILITY CLASSIFICATION REPORT")
        report.append("=" * 50)
        
        total = analysis['total_cases']
        summary = analysis['summary']
        
        report.append(f"\n📊 CLASSIFICATION SUMMARY (Total: {total} cases):")
        
        # 심각도 순으로 정렬
        severity_order = ['memory_corruption', 'parser_crash', 'authentication_bypass', 
                         'protocol_violation', 'server_error', 'resource_exhaustion', 
                         'unknown', 'normal']
        
        for vuln_type in severity_order:
            count = summary.get(vuln_type, 0)
            if count > 0:
                percentage = (count / total) * 100
                severity = self._get_severity_emoji(vuln_type)
                report.append(f"  {severity} {vuln_type}: {count} ({percentage:.1f}%)")
        
        # 상위 위험 케이스들 상세 정보
        report.append(f"\n🚨 HIGH-SEVERITY CASES:")
        high_severity = ['memory_corruption', 'parser_crash', 'authentication_bypass']
        
        for vuln_type in high_severity:
            cases = analysis['classifications'].get(vuln_type, [])
            if cases:
                report.append(f"\n### {vuln_type.upper()} ({len(cases)} cases):")
                for case in cases[:3]:  # 상위 3개만 표시
                    report.append(f"  - Case {case['case_id']}: {case['reason']}")
                    if case.get('pcap_path'):
                        report.append(f"    pcap: {case['pcap_path']}")
                if len(cases) > 3:
                    report.append(f"    ... and {len(cases) - 3} more cases")
        
        return '\n'.join(report)
    
    def _get_severity_emoji(self, vuln_type: str) -> str:
        """취약점 유형에 따른 심각도 이모지"""
        severity_map = {
            'memory_corruption': '💥',
            'parser_crash': '🔥',
            'authentication_bypass': '🚫',
            'protocol_violation': '⚠️',
            'server_error': '❌',
            'resource_exhaustion': '📉',
            'unknown': '❓',
            'normal': '✅'
        }
        return severity_map.get(vuln_type, '❓')


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 vulnerability_classifier.py <jsonl_file>")
        sys.exit(1)
    
    jsonl_path = Path(sys.argv[1])
    if not jsonl_path.exists():
        print(f"❌ File not found: {jsonl_path}")
        sys.exit(1)
    
    classifier = VulnerabilityClassifier()
    analysis = classifier.analyze_file(jsonl_path)
    report = classifier.generate_report(analysis)
    
    print(report)
    
    # JSON 형태로도 저장
    output_path = jsonl_path.parent / f"{jsonl_path.stem}_classification.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed analysis saved to: {output_path}")


if __name__ == '__main__':
    main()
```

---

## 📊 4. 실시간 모니터링 시스템

### 실시간 대시보드

**파일**: `scripts/fuzzer_monitor.sh`
```bash
#!/bin/bash
# VolteMutationFuzzer 실시간 모니터링 대시보드

# 설정
REFRESH_INTERVAL=10
LOG_FILE="monitor.log"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

get_fuzzer_status() {
    if pgrep -f "fuzzer campaign" > /dev/null; then
        echo -e "${GREEN}RUNNING${NC}"
        return 0
    else
        echo -e "${RED}STOPPED${NC}"
        return 1
    fi
}

get_a31_status() {
    if adb devices 2>/dev/null | grep -q "SM_A315F.*device"; then
        echo -e "${GREEN}CONNECTED${NC}"
        # VoLTE 상태 확인 (가능한 경우)
        return 0
    else
        echo -e "${RED}DISCONNECTED${NC}"
        return 1
    fi
}

get_docker_status() {
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "pcscf.*Up"; then
        echo -e "${GREEN}IMS READY${NC}"
        return 0
    else
        echo -e "${RED}IMS DOWN${NC}"
        return 1
    fi
}

display_recent_stats() {
    local jsonl_file="results/campaign.jsonl"
    if [ -f "$jsonl_file" ]; then
        echo -e "\n${BLUE}📊 LATEST STATISTICS:${NC}"
        
        # 최근 100개 케이스 통계
        tail -100 "$jsonl_file" | jq -s '
            map(select(.type=="case")) | 
            group_by(.verdict) | 
            map({verdict: .[0].verdict, count: length}) | 
            sort_by(.count) | reverse
        ' 2>/dev/null | jq -r '.[] | "  \(.verdict): \(.count)"' 2>/dev/null || echo "  No data yet"
        
        # 최근 crash/stack_failure
        local recent_crashes=$(tail -50 "$jsonl_file" | grep -c '"verdict":"crash"' || echo 0)
        local recent_stack_failures=$(tail -50 "$jsonl_file" | grep -c '"verdict":"stack_failure"' || echo 0)
        echo "  Recent issues: ${recent_crashes} crashes, ${recent_stack_failures} stack failures"
        
        # 처리 속도
        local start_time=$(head -5 "$jsonl_file" | jq -r 'select(.type=="case") | .timestamp' | head -1 2>/dev/null || echo 0)
        local end_time=$(tail -5 "$jsonl_file" | jq -r 'select(.type=="case") | .timestamp' | tail -1 2>/dev/null || echo 0)
        local total_cases=$(grep -c '"type":"case"' "$jsonl_file" || echo 0)
        
        if [ "$start_time" != "0" ] && [ "$end_time" != "0" ] && [ "$total_cases" -gt 0 ]; then
            local duration=$(echo "$end_time - $start_time" | bc -l)
            local rate=$(echo "scale=1; $total_cases * 60 / $duration" | bc -l)
            echo "  Processing rate: ${rate} cases/min"
        fi
    else
        echo -e "\n${YELLOW}📊 No campaign results yet${NC}"
    fi
}

display_system_resources() {
    echo -e "\n${BLUE}💻 SYSTEM RESOURCES:${NC}"
    
    # CPU 사용률
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 || echo "unknown")
    echo "  CPU Usage: ${cpu_usage}%"
    
    # 메모리 사용률
    local mem_info=$(free | grep Mem)
    local mem_total=$(echo $mem_info | awk '{print $2}')
    local mem_used=$(echo $mem_info | awk '{print $3}')
    local mem_percent=$(echo "scale=1; $mem_used * 100 / $mem_total" | bc -l)
    echo "  Memory Usage: ${mem_percent}%"
    
    # 디스크 사용량
    local disk_usage=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
    echo "  Disk Usage: ${disk_usage}%"
    
    # results 디렉토리 크기
    if [ -d "results" ]; then
        local results_size=$(du -sh results/ 2>/dev/null | cut -f1)
        echo "  Results Size: ${results_size:-unknown}"
    fi
}

check_alerts() {
    local alert_count=0
    
    # A31 연결 상태 확인
    if ! get_a31_status > /dev/null; then
        echo -e "${RED}🚨 ALERT: A31 device disconnected${NC}"
        log_message "ALERT: A31 device disconnected"
        alert_count=$((alert_count + 1))
    fi
    
    # Docker 상태 확인
    if ! get_docker_status > /dev/null; then
        echo -e "${RED}🚨 ALERT: IMS containers not running${NC}"
        log_message "ALERT: IMS containers not running"
        alert_count=$((alert_count + 1))
    fi
    
    # 디스크 공간 확인 (90% 이상)
    local disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        echo -e "${RED}🚨 ALERT: Disk usage critical (${disk_usage}%)${NC}"
        log_message "ALERT: Disk usage critical ($disk_usage%)"
        alert_count=$((alert_count + 1))
    fi
    
    # 최근 에러 증가 확인
    if [ -f "results/campaign.jsonl" ]; then
        local recent_errors=$(tail -20 "results/campaign.jsonl" | grep -c '"verdict":"unknown"' || echo 0)
        if [ "$recent_errors" -gt 5 ]; then
            echo -e "${YELLOW}⚠️  WARNING: High error rate detected${NC}"
            log_message "WARNING: High error rate detected ($recent_errors errors in last 20 cases)"
            alert_count=$((alert_count + 1))
        fi
    fi
    
    return $alert_count
}

# 메인 모니터링 루프
main_loop() {
    log_message "Starting fuzzer monitor"
    
    while true; do
        clear
        echo -e "${BLUE}🔥 VOLTEMU FUZZER MONITOR${NC} - $(date)"
        echo "================================================="
        
        # 시스템 상태
        echo -e "\n${BLUE}🔧 SYSTEM STATUS:${NC}"
        echo "  Fuzzer: $(get_fuzzer_status)"
        echo "  A31 Device: $(get_a31_status)"
        echo "  IMS Stack: $(get_docker_status)"
        
        # Fuzzer PID 정보
        local fuzzer_pid=$(pgrep -f "fuzzer campaign" | head -1)
        if [ -n "$fuzzer_pid" ]; then
            echo "  Fuzzer PID: $fuzzer_pid"
            echo "  Runtime: $(ps -o etime= -p "$fuzzer_pid" | xargs)"
        fi
        
        # 통계 정보
        display_recent_stats
        
        # 시스템 리소스
        display_system_resources
        
        # 알림 확인
        echo -e "\n${BLUE}🚨 ALERTS:${NC}"
        if ! check_alerts; then
            echo -e "${GREEN}  All systems operational${NC}"
        fi
        
        echo -e "\n${BLUE}⏱️  Last updated: $(date) (refresh every ${REFRESH_INTERVAL}s)${NC}"
        echo "Press Ctrl+C to exit"
        
        sleep $REFRESH_INTERVAL
    done
}

# 신호 핸들러
cleanup() {
    echo -e "\n\n${YELLOW}Shutting down monitor...${NC}"
    log_message "Monitor stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 실행
main_loop
```

### 웹 대시보드 (간단 버전)

**파일**: `scripts/web_dashboard.py`
```python
#!/usr/bin/env python3
"""VolteMutationFuzzer 웹 대시보드 (Flask 기반)"""

import json
import subprocess
import time
from pathlib import Path
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# HTML 템플릿
DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>VoLTE Fuzzer Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-good { color: #28a745; }
        .status-bad { color: #dc3545; }
        .status-warning { color: #ffc107; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
        .metric-value { font-size: 2em; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 VoLTE Mutation Fuzzer Dashboard</h1>
        
        <div class="grid">
            <div class="card">
                <h3>📊 System Status</h3>
                <p><strong>Fuzzer:</strong> <span class="{{ status.fuzzer_class }}">{{ status.fuzzer_status }}</span></p>
                <p><strong>A31 Device:</strong> <span class="{{ status.a31_class }}">{{ status.a31_status }}</span></p>
                <p><strong>IMS Stack:</strong> <span class="{{ status.ims_class }}">{{ status.ims_status }}</span></p>
                <p><strong>Runtime:</strong> {{ status.runtime }}</p>
            </div>
            
            <div class="card">
                <h3>📈 Live Statistics</h3>
                <div class="metric-value">{{ stats.total_cases }}</div>
                <p>Total Cases Processed</p>
                <p><strong>Rate:</strong> {{ stats.rate }} cases/min</p>
                <p><strong>Crashes:</strong> {{ stats.crashes }}</p>
                <p><strong>Success Rate:</strong> {{ stats.success_rate }}%</p>
            </div>
        </div>
        
        <div class="card">
            <h3>🎯 Verdict Distribution</h3>
            <table>
                <tr><th>Verdict</th><th>Count</th><th>Percentage</th></tr>
                {% for verdict in verdicts %}
                <tr>
                    <td>{{ verdict.name }}</td>
                    <td>{{ verdict.count }}</td>
                    <td>{{ verdict.percentage }}%</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        
        <div class="card">
            <h3>🚨 Recent Critical Cases</h3>
            {% if critical_cases %}
            <table>
                <tr><th>Case ID</th><th>Verdict</th><th>Reason</th><th>Time</th></tr>
                {% for case in critical_cases %}
                <tr>
                    <td>{{ case.case_id }}</td>
                    <td>{{ case.verdict }}</td>
                    <td>{{ case.reason }}</td>
                    <td>{{ case.time }}</td>
                </tr>
                {% endfor %}
            </table>
            {% else %}
            <p>No critical cases found in recent results.</p>
            {% endif %}
        </div>
        
        <div class="card">
            <h3>💻 System Resources</h3>
            <p><strong>CPU:</strong> {{ resources.cpu }}%</p>
            <p><strong>Memory:</strong> {{ resources.memory }}%</p>
            <p><strong>Disk:</strong> {{ resources.disk }}%</p>
            <p><strong>Results Size:</strong> {{ resources.results_size }}</p>
        </div>
        
        <p><em>Last updated: {{ timestamp }}</em></p>
    </div>
</body>
</html>
'''

class FuzzerMonitor:
    """퍼저 상태 모니터링 클래스"""
    
    def __init__(self, results_path="results/campaign.jsonl"):
        self.results_path = Path(results_path)
    
    def get_system_status(self):
        """시스템 상태 확인"""
        status = {}
        
        # Fuzzer 상태
        try:
            subprocess.run(["pgrep", "-f", "fuzzer campaign"], 
                         capture_output=True, check=True)
            status['fuzzer_status'] = 'RUNNING'
            status['fuzzer_class'] = 'status-good'
        except subprocess.CalledProcessError:
            status['fuzzer_status'] = 'STOPPED'
            status['fuzzer_class'] = 'status-bad'
        
        # A31 상태
        try:
            result = subprocess.run(["adb", "devices"], 
                                  capture_output=True, text=True)
            if "SM_A315F" in result.stdout and "device" in result.stdout:
                status['a31_status'] = 'CONNECTED'
                status['a31_class'] = 'status-good'
            else:
                status['a31_status'] = 'DISCONNECTED'
                status['a31_class'] = 'status-bad'
        except FileNotFoundError:
            status['a31_status'] = 'ADB NOT FOUND'
            status['a31_class'] = 'status-bad'
        
        # IMS 상태
        try:
            result = subprocess.run(["docker", "ps", "--filter", "name=pcscf"], 
                                  capture_output=True, text=True)
            if "Up" in result.stdout:
                status['ims_status'] = 'READY'
                status['ims_class'] = 'status-good'
            else:
                status['ims_status'] = 'DOWN'
                status['ims_class'] = 'status-bad'
        except FileNotFoundError:
            status['ims_status'] = 'DOCKER NOT FOUND'
            status['ims_class'] = 'status-bad'
        
        # Runtime
        try:
            result = subprocess.run(["pgrep", "-f", "fuzzer campaign"], 
                                  capture_output=True, text=True)
            if result.stdout.strip():
                pid = result.stdout.strip().split()[0]
                ps_result = subprocess.run(["ps", "-o", "etime=", "-p", pid], 
                                         capture_output=True, text=True)
                status['runtime'] = ps_result.stdout.strip() or 'Unknown'
            else:
                status['runtime'] = 'Not running'
        except:
            status['runtime'] = 'Unknown'
        
        return status
    
    def get_statistics(self):
        """통계 정보 수집"""
        if not self.results_path.exists():
            return {
                'total_cases': 0,
                'rate': 0,
                'crashes': 0,
                'success_rate': 0
            }
        
        stats = {'total_cases': 0, 'rate': 0, 'crashes': 0, 'success_rate': 0}
        
        with open(self.results_path, 'r') as f:
            lines = [line for line in f if line.strip()]
        
        if not lines:
            return stats
        
        cases = []
        for line in lines:
            try:
                data = json.loads(line)
                if data.get('type') == 'case':
                    cases.append(data)
            except json.JSONDecodeError:
                continue
        
        if not cases:
            return stats
        
        stats['total_cases'] = len(cases)
        
        # 처리 속도 계산
        if len(cases) > 1:
            start_time = cases[0]['timestamp']
            end_time = cases[-1]['timestamp']
            duration = (end_time - start_time) / 60  # minutes
            if duration > 0:
                stats['rate'] = round(len(cases) / duration, 1)
        
        # Crash 수
        stats['crashes'] = len([c for c in cases 
                              if c.get('verdict') in ['crash', 'stack_failure']])
        
        # 성공률
        normal_cases = len([c for c in cases if c.get('verdict') == 'normal'])
        stats['success_rate'] = round((normal_cases / len(cases)) * 100, 1)
        
        return stats
    
    def get_verdict_distribution(self):
        """verdict 분포 계산"""
        if not self.results_path.exists():
            return []
        
        verdict_counts = {}
        total = 0
        
        with open(self.results_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') == 'case':
                        verdict = data.get('verdict', 'unknown')
                        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                        total += 1
                except json.JSONDecodeError:
                    continue
        
        if total == 0:
            return []
        
        result = []
        for verdict, count in sorted(verdict_counts.items()):
            percentage = round((count / total) * 100, 1)
            result.append({
                'name': verdict,
                'count': count,
                'percentage': percentage
            })
        
        return result
    
    def get_critical_cases(self, limit=10):
        """최근 critical 케이스들"""
        if not self.results_path.exists():
            return []
        
        critical_cases = []
        
        with open(self.results_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if (data.get('type') == 'case' and 
                        data.get('verdict') in ['crash', 'stack_failure', 'suspicious']):
                        critical_cases.append({
                            'case_id': data.get('case_id'),
                            'verdict': data.get('verdict'),
                            'reason': data.get('reason', '')[:100] + '...',
                            'time': time.strftime('%H:%M:%S', 
                                                time.localtime(data.get('timestamp', 0)))
                        })
                except json.JSONDecodeError:
                    continue
        
        return critical_cases[-limit:]  # 최근 limit개
    
    def get_system_resources(self):
        """시스템 리소스 정보"""
        resources = {'cpu': 'unknown', 'memory': 'unknown', 
                    'disk': 'unknown', 'results_size': 'unknown'}
        
        try:
            # CPU (간단 버전)
            result = subprocess.run(["uptime"], capture_output=True, text=True)
            if "load average" in result.stdout:
                resources['cpu'] = 'monitored'
        except:
            pass
        
        try:
            # 메모리
            result = subprocess.run(["free"], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if line.startswith('Mem:'):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    resources['memory'] = round((used / total) * 100, 1)
                    break
        except:
            pass
        
        try:
            # 디스크
            result = subprocess.run(["df", "."], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 5:
                    resources['disk'] = parts[4].rstrip('%')
        except:
            pass
        
        try:
            # Results 크기
            if Path("results").exists():
                result = subprocess.run(["du", "-sh", "results/"], 
                                      capture_output=True, text=True)
                resources['results_size'] = result.stdout.split()[0]
        except:
            pass
        
        return resources

monitor = FuzzerMonitor()

@app.route('/')
def dashboard():
    """메인 대시보드"""
    data = {
        'status': monitor.get_system_status(),
        'stats': monitor.get_statistics(),
        'verdicts': monitor.get_verdict_distribution(),
        'critical_cases': monitor.get_critical_cases(),
        'resources': monitor.get_system_resources(),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return render_template_string(DASHBOARD_TEMPLATE, **data)

@app.route('/api/status')
def api_status():
    """API 엔드포인트"""
    return jsonify({
        'status': monitor.get_system_status(),
        'stats': monitor.get_statistics(),
        'timestamp': time.time()
    })

if __name__ == '__main__':
    print("🌐 Starting VoLTE Fuzzer Web Dashboard...")
    print("📊 Access dashboard at: http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
```

---

## 🎭 5. 고급 변이 전략

### 스마트 퍼징 시나리오

**파일**: `scripts/smart_fuzzing_campaigns.sh`
```bash
#!/bin/bash
# 지능형 다단계 퍼징 캠페인

BASE_DIR="results/smart_campaign_$(date +%Y%m%d_%H%M)"
mkdir -p "$BASE_DIR"

echo "🧠 Starting intelligent fuzzing campaign"

# Phase 1: Baseline establishment (identity cases)
echo "📋 Phase 1: Baseline validation"
uv run fuzzer campaign run \
  --mode real-ue-direct --target-msisdn 111111 \
  --impi 001010000123511 --mt-invite-template a31 \
  --ipsec-mode null --methods INVITE \
  --layer wire --strategy identity \
  --max-cases 5 --timeout 5 \
  --output "$BASE_DIR/phase1_baseline.jsonl"

# 모든 baseline이 성공하는지 확인
BASELINE_SUCCESS=$(grep -c '"verdict":"normal"' "$BASE_DIR/phase1_baseline.jsonl" || echo 0)
if [ "$BASELINE_SUCCESS" -lt 3 ]; then
    echo "❌ Baseline validation failed. Aborting campaign."
    exit 1
fi

# Phase 2: Wire-level systematic exploration
echo "🔍 Phase 2: Wire-level systematic fuzzing"
uv run fuzzer campaign run \
  --mode real-ue-direct --target-msisdn 111111 \
  --impi 001010000123511 --mt-invite-template a31 \
  --ipsec-mode null --methods INVITE \
  --layer wire --strategy default \
  --max-cases 2000 --timeout 3 --cooldown 0.1 \
  --output "$BASE_DIR/phase2_wire.jsonl" \
  --pcap --pcap-dir "$BASE_DIR/phase2_pcap" \
  --adb --adb-serial SM_A315F_12345

# Phase 3: Byte-level aggressive fuzzing
echo "💥 Phase 3: Byte-level aggressive fuzzing"
uv run fuzzer campaign run \
  --mode real-ue-direct --target-msisdn 111111 \
  --impi 001010000123511 --mt-invite-template a31 \
  --ipsec-mode null --methods INVITE \
  --layer byte --strategy default \
  --max-cases 3000 --timeout 3 --cooldown 0.05 \
  --output "$BASE_DIR/phase3_byte.jsonl" \
  --pcap --pcap-dir "$BASE_DIR/phase3_pcap" \
  --adb --adb-serial SM_A315F_12345

# Phase 4: Multi-method exploration
echo "🎯 Phase 4: Multi-method exploration"
for METHOD in OPTIONS MESSAGE REGISTER; do
    echo "  Testing method: $METHOD"
    uv run fuzzer campaign run \
      --mode real-ue-direct --target-msisdn 111111 \
      --impi 001010000123511 \
      --ipsec-mode null --methods "$METHOD" \
      --layer wire,byte --strategy default \
      --max-cases 500 --timeout 3 \
      --output "$BASE_DIR/phase4_${METHOD,,}.jsonl" \
      --pcap --pcap-dir "$BASE_DIR/phase4_pcap"
done

# Phase 5: Crash amplification (if crashes found)
echo "🔥 Phase 5: Crash amplification"
TOTAL_CRASHES=0
for jsonl in "$BASE_DIR"/*.jsonl; do
    if [ -f "$jsonl" ]; then
        CRASHES=$(grep -c '"verdict":"crash"' "$jsonl" || echo 0)
        STACK_FAILURES=$(grep -c '"verdict":"stack_failure"' "$jsonl" || echo 0)
        TOTAL_CRASHES=$((TOTAL_CRASHES + CRASHES + STACK_FAILURES))
    fi
done

if [ "$TOTAL_CRASHES" -gt 0 ]; then
    echo "💥 Found $TOTAL_CRASHES crashes! Running crash amplification..."
    
    # 가장 많은 crash가 발생한 설정으로 집중 공격
    BEST_CONFIG=$(ls "$BASE_DIR"/*.jsonl | xargs -I {} sh -c 'echo "$(grep -c "crash" {} || echo 0) {}"' | sort -rn | head -1 | cut -d' ' -f2)
    if [ -n "$BEST_CONFIG" ]; then
        # 동일한 설정으로 더 많은 케이스 실행
        uv run fuzzer campaign run \
          --mode real-ue-direct --target-msisdn 111111 \
          --impi 001010000123511 --mt-invite-template a31 \
          --ipsec-mode null --methods INVITE \
          --layer byte --strategy default \
          --max-cases 5000 --timeout 3 --cooldown 0.05 \
          --output "$BASE_DIR/phase5_amplification.jsonl" \
          --pcap --pcap-dir "$BASE_DIR/phase5_pcap" \
          --adb --adb-serial SM_A315F_12345
    fi
else
    echo "ℹ️  No crashes found in previous phases. Skipping amplification."
fi

# 통합 분석
echo "📊 Generating comprehensive analysis..."
./scripts/analyze_smart_campaign.sh "$BASE_DIR"

echo "✅ Smart fuzzing campaign completed!"
echo "📂 Results saved to: $BASE_DIR"
```

### 적응형 퍼징 전략

**파일**: `scripts/adaptive_fuzzing.py`
```python
#!/usr/bin/env python3
"""적응형 퍼징 전략 - 실시간 결과에 따른 전략 조정"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple


class AdaptiveFuzzingController:
    """실시간 결과 분석으로 퍼징 전략을 자동 조정하는 컨트롤러"""
    
    def __init__(self, output_dir: str = "results/adaptive"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 전략 효과성 추적
        self.strategy_stats = {
            'identity': {'crashes': 0, 'total': 0},
            'default': {'crashes': 0, 'total': 0},
            'state_breaker': {'crashes': 0, 'total': 0}
        }
        
        self.layer_stats = {
            'wire': {'crashes': 0, 'total': 0},
            'byte': {'crashes': 0, 'total': 0},
            'model': {'crashes': 0, 'total': 0}
        }
    
    def analyze_results(self, jsonl_path: Path) -> Dict:
        """결과 파일 분석하여 전략 효과성 측정"""
        stats = {
            'total_cases': 0,
            'crashes': 0,
            'success_rate': 0,
            'avg_response_time': 0,
            'strategy_effectiveness': {},
            'layer_effectiveness': {}
        }
        
        if not jsonl_path.exists():
            return stats
        
        cases = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') == 'case':
                        cases.append(data)
                except json.JSONDecodeError:
                    continue
        
        if not cases:
            return stats
        
        stats['total_cases'] = len(cases)
        
        # 기본 통계
        crash_cases = [c for c in cases if c.get('verdict') in ['crash', 'stack_failure']]
        normal_cases = [c for c in cases if c.get('verdict') == 'normal']
        
        stats['crashes'] = len(crash_cases)
        stats['success_rate'] = len(normal_cases) / len(cases) if cases else 0
        stats['avg_response_time'] = sum(c.get('elapsed_ms', 0) for c in cases) / len(cases)
        
        # 전략별 효과성
        for strategy in ['identity', 'default', 'state_breaker']:
            strategy_cases = [c for c in cases if c.get('strategy') == strategy]
            strategy_crashes = [c for c in strategy_cases if c.get('verdict') in ['crash', 'stack_failure']]
            
            if strategy_cases:
                effectiveness = len(strategy_crashes) / len(strategy_cases)
                stats['strategy_effectiveness'][strategy] = {
                    'crash_rate': effectiveness,
                    'total_cases': len(strategy_cases),
                    'crashes': len(strategy_crashes)
                }
        
        # 레이어별 효과성
        for layer in ['wire', 'byte', 'model']:
            layer_cases = [c for c in cases if c.get('layer') == layer]
            layer_crashes = [c for c in layer_cases if c.get('verdict') in ['crash', 'stack_failure']]
            
            if layer_cases:
                effectiveness = len(layer_crashes) / len(layer_cases)
                stats['layer_effectiveness'][layer] = {
                    'crash_rate': effectiveness,
                    'total_cases': len(layer_cases),
                    'crashes': len(layer_crashes)
                }
        
        return stats
    
    def determine_next_strategy(self, current_stats: Dict) -> Tuple[str, str, int]:
        """현재 결과를 바탕으로 다음 실행할 최적 전략 결정"""
        
        # 기본 전략
        next_layer = "wire"
        next_strategy = "default"
        next_batch_size = 1000
        
        # 전략별 효과성이 있다면 활용
        strategy_eff = current_stats.get('strategy_effectiveness', {})
        if strategy_eff:
            # 가장 효과적인 전략 선택
            best_strategy = max(strategy_eff.items(), 
                              key=lambda x: x[1]['crash_rate'])
            if best_strategy[1]['crash_rate'] > 0.01:  # 1% 이상 crash rate
                next_strategy = best_strategy[0]
        
        # 레이어별 효과성이 있다면 활용
        layer_eff = current_stats.get('layer_effectiveness', {})
        if layer_eff:
            best_layer = max(layer_eff.items(), 
                           key=lambda x: x[1]['crash_rate'])
            if best_layer[1]['crash_rate'] > 0.005:  # 0.5% 이상 crash rate
                next_layer = best_layer[0]
        
        # 배치 크기 조정
        total_crashes = current_stats.get('crashes', 0)
        if total_crashes > 10:
            # 많은 crash 발견 시 더 많은 케이스로 확장
            next_batch_size = 3000
        elif total_crashes > 5:
            next_batch_size = 2000
        elif current_stats.get('success_rate', 0) < 0.3:
            # 성공률이 낮으면 배치 크기 줄임
            next_batch_size = 500
        
        return next_strategy, next_layer, next_batch_size
    
    def run_adaptive_campaign(self, max_iterations: int = 10):
        """적응형 퍼징 캠페인 실행"""
        print(f"🧠 Starting adaptive fuzzing campaign (max {max_iterations} iterations)")
        
        iteration = 0
        total_crashes = 0
        best_config = None
        best_crash_rate = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n🔄 Iteration {iteration}/{max_iterations}")
            
            # 이전 결과 분석
            if iteration == 1:
                # 첫 번째는 기본 설정으로
                strategy = "default"
                layer = "wire"
                batch_size = 1000
            else:
                # 이전 결과를 바탕으로 최적 전략 결정
                prev_results = self.output_dir / f"iteration_{iteration-1}.jsonl"
                stats = self.analyze_results(prev_results)
                
                print(f"  Previous results: {stats['total_cases']} cases, {stats['crashes']} crashes")
                
                strategy, layer, batch_size = self.determine_next_strategy(stats)
                
                # 수렴 조건 검사
                if stats['crashes'] == 0 and iteration > 5:
                    print("  No crashes found in recent iterations. Campaign may have converged.")
                    break
            
            print(f"  Selected strategy: {strategy}, layer: {layer}, batch size: {batch_size}")
            
            # 퍼징 실행
            output_file = self.output_dir / f"iteration_{iteration}.jsonl"
            pcap_dir = self.output_dir / f"iteration_{iteration}_pcap"
            
            cmd = [
                "uv", "run", "fuzzer", "campaign", "run",
                "--mode", "real-ue-direct",
                "--target-msisdn", "111111",
                "--impi", "001010000123511",
                "--mt-invite-template", "a31",
                "--ipsec-mode", "null",
                "--methods", "INVITE",
                "--layer", layer,
                "--strategy", strategy,
                "--max-cases", str(batch_size),
                "--timeout", "3",
                "--cooldown", "0.1",
                "--output", str(output_file),
                "--pcap", "--pcap-dir", str(pcap_dir),
                "--adb", "--adb-serial", "SM_A315F_12345"
            ]
            
            print(f"  Executing: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                if result.returncode != 0:
                    print(f"  ❌ Fuzzing failed: {result.stderr}")
                    continue
                    
                # 결과 분석
                stats = self.analyze_results(output_file)
                iteration_crashes = stats['crashes']
                crash_rate = iteration_crashes / stats['total_cases'] if stats['total_cases'] > 0 else 0
                
                print(f"  ✅ Completed: {iteration_crashes} crashes found (rate: {crash_rate:.3f})")
                
                total_crashes += iteration_crashes
                
                # 최적 설정 추적
                if crash_rate > best_crash_rate:
                    best_crash_rate = crash_rate
                    best_config = (strategy, layer, batch_size)
                    print(f"  🎯 New best configuration: {best_config}")
                
            except subprocess.TimeoutExpired:
                print(f"  ⏰ Iteration {iteration} timed out")
                continue
            except Exception as e:
                print(f"  ❌ Iteration {iteration} failed: {e}")
                continue
        
        # 최종 보고서 생성
        self._generate_adaptive_report(total_crashes, best_config, iteration)
        
        print(f"\n✅ Adaptive campaign completed!")
        print(f"   Total iterations: {iteration}")
        print(f"   Total crashes found: {total_crashes}")
        print(f"   Best configuration: {best_config}")
    
    def _generate_adaptive_report(self, total_crashes: int, best_config: tuple, iterations: int):
        """적응형 퍼징 최종 보고서 생성"""
        report_path = self.output_dir / "adaptive_campaign_report.txt"
        
        with open(report_path, 'w') as f:
            f.write("🧠 ADAPTIVE FUZZING CAMPAIGN REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Campaign Duration: {iterations} iterations\n")
            f.write(f"Total Crashes Found: {total_crashes}\n")
            f.write(f"Best Configuration: {best_config}\n\n")
            
            f.write("📊 ITERATION SUMMARY:\n")
            for i in range(1, iterations + 1):
                result_file = self.output_dir / f"iteration_{i}.jsonl"
                if result_file.exists():
                    stats = self.analyze_results(result_file)
                    f.write(f"  Iteration {i}: {stats['total_cases']} cases, {stats['crashes']} crashes\n")
            
            f.write("\n🎯 RECOMMENDATIONS:\n")
            if best_config:
                strategy, layer, batch_size = best_config
                f.write(f"  - Use strategy '{strategy}' with layer '{layer}'\n")
                f.write(f"  - Optimal batch size: {batch_size}\n")
            
            if total_crashes > 0:
                f.write(f"  - Focus on crash amplification with best configuration\n")
                f.write(f"  - Analyze pcap files from high-crash iterations\n")
            else:
                f.write(f"  - Consider different UE targets or protocol methods\n")
        
        print(f"📋 Adaptive campaign report saved: {report_path}")


if __name__ == "__main__":
    controller = AdaptiveFuzzingController()
    controller.run_adaptive_campaign(max_iterations=8)
```

---

## 🚀 6. 즉시 실행 가능한 야무진 설정

### 원-클릭 프로덕션 퍼저

**파일**: `scripts/production_fuzzer.sh`
```bash
#!/bin/bash
# VolteMutationFuzzer 프로덕션 원-클릭 실행기

set -euo pipefail

# ============================================================================
# 설정 섹션
# ============================================================================

# 기본 설정
A31_SERIAL="${VMF_A31_SERIAL:-SM_A315F_12345}"
TARGET_MSISDN="${VMF_TARGET_MSISDN:-111111}"
MAX_CASES="${VMF_MAX_CASES:-10000}"
RUN_MODE="${VMF_RUN_MODE:-turbo}"  # turbo, balanced, thorough

# 출력 디렉토리
OUTPUT_BASE="results/production_$(date +%Y%m%d_%H%M)"
mkdir -p "$OUTPUT_BASE"

# 로그 설정
LOG_FILE="$OUTPUT_BASE/production.log"
MONITOR_PID=""

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# 헬퍼 함수
# ============================================================================

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # UV 체크
    if ! command -v uv &> /dev/null; then
        log_error "uv package manager not found"
        return 1
    fi
    
    # ADB 체크
    if ! command -v adb &> /dev/null; then
        log_error "adb not found"
        return 1
    fi
    
    # Docker 체크
    if ! command -v docker &> /dev/null; then
        log_error "docker not found"
        return 1
    fi
    
    # A31 연결 체크
    if ! adb devices | grep -q "$A31_SERIAL.*device"; then
        log_error "A31 device ($A31_SERIAL) not connected"
        return 1
    fi
    
    # IMS 컨테이너 체크
    if ! docker ps | grep -q "pcscf.*Up"; then
        log_error "IMS containers not running"
        return 1
    fi
    
    log_success "All prerequisites satisfied"
    return 0
}

get_run_config() {
    case "$RUN_MODE" in
        "turbo")
            echo "--timeout 2 --cooldown 0.05 --no-process-check"
            ;;
        "balanced")
            echo "--timeout 3 --cooldown 0.1"
            ;;
        "thorough")
            echo "--timeout 5 --cooldown 0.2"
            ;;
        *)
            echo "--timeout 3 --cooldown 0.1"
            ;;
    esac
}

start_monitoring() {
    log "Starting real-time monitoring..."
    
    # 백그라운드에서 모니터링 스크립트 실행
    nohup ./scripts/fuzzer_monitor.sh > "$OUTPUT_BASE/monitor.log" 2>&1 &
    MONITOR_PID=$!
    
    log "Monitor started with PID: $MONITOR_PID"
}

stop_monitoring() {
    if [ -n "$MONITOR_PID" ]; then
        log "Stopping monitor (PID: $MONITOR_PID)..."
        kill "$MONITOR_PID" 2>/dev/null || true
        wait "$MONITOR_PID" 2>/dev/null || true
    fi
}

run_fuzzing_phase() {
    local phase_name="$1"
    local methods="$2"
    local layers="$3"
    local strategies="$4"
    local max_cases="$5"
    local extra_args="$6"
    
    log "Starting $phase_name..."
    
    local output_file="$OUTPUT_BASE/${phase_name,,}.jsonl"
    local pcap_dir="$OUTPUT_BASE/${phase_name,,}_pcap"
    local run_config=$(get_run_config)
    
    local cmd=(
        uv run fuzzer campaign run
        --mode real-ue-direct
        --target-msisdn "$TARGET_MSISDN"
        --impi "001010000123511"
        --mt-invite-template "a31"
        --ipsec-mode "null"
        --methods "$methods"
        --layer "$layers"
        --strategy "$strategies"
        --max-cases "$max_cases"
        $run_config
        --output "$output_file"
        --pcap --pcap-dir "$pcap_dir"
        --adb --adb-serial "$A31_SERIAL"
        $extra_args
    )
    
    log "Command: ${cmd[*]}"
    
    if "${cmd[@]}"; then
        log_success "$phase_name completed successfully"
        
        # 간단한 결과 요약
        local cases=$(grep -c '"type":"case"' "$output_file" || echo 0)
        local crashes=$(grep -c '"verdict":"crash"' "$output_file" || echo 0)
        local stack_failures=$(grep -c '"verdict":"stack_failure"' "$output_file" || echo 0)
        local total_issues=$((crashes + stack_failures))
        
        log "  Results: $cases cases, $total_issues critical issues"
        
        return 0
    else
        log_error "$phase_name failed"
        return 1
    fi
}

generate_final_report() {
    log "Generating final production report..."
    
    local report_file="$OUTPUT_BASE/PRODUCTION_REPORT.txt"
    
    cat > "$report_file" << EOF
🔥 VOLTE MUTATION FUZZER - PRODUCTION REPORT
=============================================
Generated: $(date)
Mode: $RUN_MODE
Target: A31 (MSISDN: $TARGET_MSISDN)
Duration: $(date -d @$(($(date +%s) - START_TIME)) -u +%H:%M:%S)

📊 OVERALL STATISTICS:
EOF

    local total_cases=0
    local total_crashes=0
    local total_stack_failures=0
    
    for jsonl in "$OUTPUT_BASE"/*.jsonl; do
        if [ -f "$jsonl" ]; then
            local basename=$(basename "$jsonl" .jsonl)
            local cases=$(grep -c '"type":"case"' "$jsonl" || echo 0)
            local crashes=$(grep -c '"verdict":"crash"' "$jsonl" || echo 0)
            local stack_failures=$(grep -c '"verdict":"stack_failure"' "$jsonl" || echo 0)
            
            echo "  $basename: $cases cases, $crashes crashes, $stack_failures stack failures" >> "$report_file"
            
            total_cases=$((total_cases + cases))
            total_crashes=$((total_crashes + crashes))
            total_stack_failures=$((total_stack_failures + stack_failures))
        fi
    done
    
    cat >> "$report_file" << EOF

🎯 SUMMARY:
  Total Cases: $total_cases
  Total Crashes: $total_crashes
  Total Stack Failures: $total_stack_failures
  Critical Issues: $((total_crashes + total_stack_failures))
  Issue Rate: $(echo "scale=3; ($total_crashes + $total_stack_failures) * 100 / $total_cases" | bc -l)%

🚨 CRITICAL FINDINGS:
EOF

    # 중요 케이스 추출
    for jsonl in "$OUTPUT_BASE"/*.jsonl; do
        if [ -f "$jsonl" ]; then
            jq -r 'select(.type=="case" and (.verdict=="crash" or .verdict=="stack_failure")) | 
                   "  Case \(.case_id): \(.verdict) - \(.reason)"' "$jsonl" 2>/dev/null >> "$report_file" || true
        fi
    done
    
    cat >> "$report_file" << EOF

📦 ARTIFACTS:
  JSONL Results: $OUTPUT_BASE/*.jsonl
  PCAP Files: $OUTPUT_BASE/*_pcap/
  Monitor Logs: $OUTPUT_BASE/monitor.log
  Production Log: $LOG_FILE

🔄 REPRODUCTION:
  To reproduce critical cases, use the reproduction commands in the JSONL files.
  Example: jq -r 'select(.verdict=="crash") | .reproduction_cmd' $OUTPUT_BASE/*.jsonl

✅ Production fuzzing session completed successfully.
EOF

    log_success "Final report generated: $report_file"
    
    # 콘솔에도 요약 출력
    echo -e "\n${GREEN}🎯 PRODUCTION FUZZING SUMMARY${NC}"
    echo -e "${BLUE}Total Cases:${NC} $total_cases"
    echo -e "${RED}Critical Issues:${NC} $((total_crashes + total_stack_failures))"
    echo -e "${YELLOW}Output Directory:${NC} $OUTPUT_BASE"
}

send_completion_notification() {
    local total_issues="$1"
    
    # Slack webhook이 설정되어 있으면 알림 발송
    if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
        local message="🔥 VoLTE Production Fuzzing Completed!\\n📊 $total_cases cases processed\\n🚨 $total_issues critical issues found\\n📂 Results: $OUTPUT_BASE"
        
        curl -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"$message\"}" 2>/dev/null || true
    fi
}

cleanup_on_exit() {
    log "Performing cleanup..."
    stop_monitoring
    
    # 임시 파일 정리
    # (필요한 경우 여기에 추가)
    
    log "Cleanup completed"
}

# ============================================================================
# 메인 실행 로직
# ============================================================================

main() {
    local START_TIME=$(date +%s)
    
    echo -e "${BLUE}🔥 VolteMutationFuzzer Production Mode${NC}"
    echo -e "${BLUE}Mode: $RUN_MODE | Target: $TARGET_MSISDN | Max Cases: $MAX_CASES${NC}"
    echo -e "${BLUE}Output: $OUTPUT_BASE${NC}"
    echo
    
    # 신호 핸들러 등록
    trap cleanup_on_exit EXIT INT TERM
    
    # 전제조건 확인
    if ! check_prerequisites; then
        log_error "Prerequisites check failed. Aborting."
        exit 1
    fi
    
    # 모니터링 시작
    start_monitoring
    
    # Phase 1: Baseline validation
    if ! run_fuzzing_phase "Phase1_Baseline" "INVITE" "wire" "identity" 5 ""; then
        log_error "Baseline validation failed. Aborting campaign."
        exit 1
    fi
    
    # Phase 2: Core MT-INVITE fuzzing
    local core_cases=$((MAX_CASES * 60 / 100))  # 60% of total
    if ! run_fuzzing_phase "Phase2_Core" "INVITE" "wire,byte" "identity,default" "$core_cases" ""; then
        log_warning "Core phase failed, but continuing..."
    fi
    
    # Phase 3: Multi-method exploration
    local multi_cases=$((MAX_CASES * 30 / 100))  # 30% of total
    if ! run_fuzzing_phase "Phase3_Multi" "OPTIONS,MESSAGE,REGISTER" "wire,byte" "default" "$multi_cases" ""; then
        log_warning "Multi-method phase failed, but continuing..."
    fi
    
    # Phase 4: Aggressive byte fuzzing
    local aggressive_cases=$((MAX_CASES * 10 / 100))  # 10% of total
    if ! run_fuzzing_phase "Phase4_Aggressive" "INVITE" "byte" "default" "$aggressive_cases" "--cooldown 0.01"; then
        log_warning "Aggressive phase failed, but continuing..."
    fi
    
    # 최종 분석 및 리포트
    generate_final_report
    
    # 통계 기반 알림
    local total_issues=$((
        $(find "$OUTPUT_BASE" -name "*.jsonl" -exec grep -c '"verdict":"crash"' {} + 2>/dev/null || echo 0) +
        $(find "$OUTPUT_BASE" -name "*.jsonl" -exec grep -c '"verdict":"stack_failure"' {} + 2>/dev/null || echo 0)
    ))
    
    send_completion_notification "$total_issues"
    
    log_success "Production fuzzing campaign completed successfully!"
    
    if [ "$total_issues" -gt 0 ]; then
        echo -e "\n${RED}🚨 ATTENTION: $total_issues critical issues found!${NC}"
        echo -e "${YELLOW}📋 Review the report: $OUTPUT_BASE/PRODUCTION_REPORT.txt${NC}"
    else
        echo -e "\n${GREEN}✅ No critical issues found in this campaign.${NC}"
    fi
}

# 실행
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
```

### 퀵스타트 래퍼

**파일**: `scripts/quick_fuzzer.sh`
```bash
#!/bin/bash
# 빠른 시작용 래퍼 스크립트

echo "🚀 VolteMutationFuzzer Quick Start"
echo "=================================="

# 사용법 출력
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    cat << EOF
사용법: $0 [옵션] [케이스수]

옵션:
  baseline    - 기본 연결성 테스트 (5 cases)
  quick       - 빠른 퍼징 (100 cases)
  standard    - 표준 퍼징 (1000 cases) [기본값]
  intensive   - 집중 퍼징 (5000 cases)
  overnight   - 야간 배치 (10000+ cases)

예시:
  $0 baseline           # 기본 테스트
  $0 quick              # 100 케이스 빠른 퍼징
  $0 standard 2000      # 2000 케이스 표준 퍼징
  $0 intensive          # 5000 케이스 집중 퍼징
  $0 overnight          # 야간 배치 실행

환경변수:
  VMF_A31_SERIAL       - A31 시리얼 번호 (기본: SM_A315F_12345)
  VMF_TARGET_MSISDN    - 대상 MSISDN (기본: 111111)
  SLACK_WEBHOOK_URL    - 완료 알림용 Slack webhook URL
EOF
    exit 0
fi

# 파라미터 파싱
MODE="${1:-standard}"
CUSTOM_CASES="$2"

# 모드별 설정
case "$MODE" in
    "baseline")
        export VMF_MAX_CASES=5
        export VMF_RUN_MODE="thorough"
        echo "🔍 Baseline connectivity test"
        ;;
    "quick")
        export VMF_MAX_CASES="${CUSTOM_CASES:-100}"
        export VMF_RUN_MODE="turbo"
        echo "⚡ Quick fuzzing mode"
        ;;
    "standard")
        export VMF_MAX_CASES="${CUSTOM_CASES:-1000}"
        export VMF_RUN_MODE="balanced"
        echo "🎯 Standard fuzzing mode"
        ;;
    "intensive")
        export VMF_MAX_CASES="${CUSTOM_CASES:-5000}"
        export VMF_RUN_MODE="turbo"
        echo "💥 Intensive fuzzing mode"
        ;;
    "overnight")
        echo "🌙 Starting overnight batch fuzzing..."
        exec ./scripts/overnight_fuzzer.sh
        ;;
    *)
        echo "❌ Unknown mode: $MODE"
        echo "Use '$0 --help' for usage information"
        exit 1
        ;;
esac

echo "📱 Target: A31 (${VMF_TARGET_MSISDN:-111111})"
echo "🎯 Cases: ${VMF_MAX_CASES}"
echo "🏃 Speed: ${VMF_RUN_MODE}"
echo

# 프로덕션 퍼저 실행
exec ./scripts/production_fuzzer.sh
```

---

## 📋 7. 통합 설치 및 설정

### 설치 스크립트

**파일**: `scripts/setup_production_fuzzer.sh`
```bash
#!/bin/bash
# VolteMutationFuzzer 야무진 퍼저 설치기

set -euo pipefail

echo "🔥 Setting up VolteMutationFuzzer Production Environment"
echo "======================================================="

# 스크립트 실행 권한 설정
chmod +x scripts/*.sh
chmod +x scripts/*.py

# Python 의존성 설치
echo "📦 Installing Python dependencies..."
pip3 install flask jq bc || true

# 디렉토리 구조 생성
echo "📁 Creating directory structure..."
mkdir -p {results,scripts,logs}
mkdir -p results/{production,adaptive,smart_campaign}

# 환경 설정 파일 생성
echo "⚙️ Creating environment configuration..."
cat > .env.production << 'EOF'
# VolteMutationFuzzer Production Configuration
VMF_A31_SERIAL=SM_A315F_12345
VMF_TARGET_MSISDN=111111
VMF_REAL_UE_PCSCF_IP=172.22.0.21
VMF_MAX_CASES=1000
VMF_RUN_MODE=balanced

# Optional: Slack notification
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF

# Crontab 엔트리 예시
echo "⏰ Setting up cron example..."
cat > crontab_example.txt << 'EOF'
# VolteMutationFuzzer 자동 실행 예시
# 매일 밤 2시에 야간 퍼징 실행
0 2 * * * cd /path/to/volte-mutation-fuzzer && ./scripts/overnight_fuzzer.sh

# 매주 일요일 오후 2시에 집중 퍼징
0 14 * * 0 cd /path/to/volte-mutation-fuzzer && ./scripts/quick_fuzzer.sh intensive

# 매시간 시스템 상태 체크
0 * * * * cd /path/to/volte-mutation-fuzzer && ./scripts/health_check.sh
EOF

# 상태 체크 스크립트
cat > scripts/health_check.sh << 'EOF'
#!/bin/bash
# 간단한 상태 체크 스크립트

LOG_FILE="logs/health_check.log"

echo "$(date): Health check started" >> "$LOG_FILE"

# A31 연결 확인
if ! adb devices | grep -q "device$"; then
    echo "$(date): WARNING - A31 not connected" >> "$LOG_FILE"
fi

# IMS 컨테이너 확인
if ! docker ps | grep -q "pcscf.*Up"; then
    echo "$(date): WARNING - IMS containers not running" >> "$LOG_FILE"
fi

# 디스크 공간 확인
DISK_USAGE=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "$(date): WARNING - Disk usage high ($DISK_USAGE%)" >> "$LOG_FILE"
fi

echo "$(date): Health check completed" >> "$LOG_FILE"
EOF

chmod +x scripts/health_check.sh

# 데모 실행 스크립트
cat > scripts/demo_fuzzer.sh << 'EOF'
#!/bin/bash
# 데모용 안전한 퍼저 실행

echo "🎭 VolteMutationFuzzer Demo Mode"
echo "빠른 데모를 위한 소규모 테스트입니다."
echo

# 안전한 설정으로 데모 실행
uv run fuzzer campaign run \
  --mode real-ue-direct \
  --target-msisdn 111111 \
  --impi 001010000123511 \
  --mt-invite-template a31 \
  --ipsec-mode null \
  --methods INVITE \
  --layer wire --strategy identity,default \
  --max-cases 10 \
  --timeout 5 \
  --output "results/demo_$(date +%Y%m%d_%H%M).jsonl" \
  --pcap --pcap-dir "results/demo_pcap"

echo "✅ Demo completed! Check results/ directory."
EOF

chmod +x scripts/demo_fuzzer.sh

echo
echo "✅ Production fuzzer setup completed!"
echo
echo "📋 Quick Start Guide:"
echo "  1. 환경 설정: source .env.production"
echo "  2. 데모 실행: ./scripts/demo_fuzzer.sh"
echo "  3. 빠른 퍼징: ./scripts/quick_fuzzer.sh quick"
echo "  4. 프로덕션: ./scripts/production_fuzzer.sh"
echo "  5. 모니터링: ./scripts/fuzzer_monitor.sh"
echo
echo "📚 Documentation:"
echo "  - Production guide: docs/PRODUCTION_FUZZER_GUIDE.md"
echo "  - A31 specific: docs/A31_REAL_UE_GUIDE.md"
echo "  - Troubleshooting: docs/TROUBLESHOOTING.md"
echo
echo "🎯 Ready for professional VoLTE fuzzing!"
```

---

## 🎯 마무리

이제 VolteMutationFuzzer가 **야무진 프로덕션 퍼저**로 업그레이드되었습니다!

### 핵심 기능
- ⚡ **고성능**: 터보 모드로 3배 빠른 처리
- 🤖 **자동화**: 야간 배치 + 적응형 전략
- 🧠 **지능형**: 실시간 결과 분석 + 전략 조정
- 📊 **가시성**: 실시간 모니터링 + 웹 대시보드
- 🔍 **정밀성**: 취약점 자동 분류 + 재현 명령어

### 즉시 사용 가능
```bash
# 설치
./scripts/setup_production_fuzzer.sh

# 빠른 시작
./scripts/quick_fuzzer.sh standard

# 프로덕션 모드
./scripts/production_fuzzer.sh
```

**이제 진짜 야무진 퍼저입니다!** 🔥🎯