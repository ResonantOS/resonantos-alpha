#!/bin/bash
# Health Sensors — Deterministic diagnostic checks for OpenClaw orchestrator
# Returns JSON with structured health data: status + reason for each sensor
# Usage: ./health-sensors.sh [json|human]
# Exit codes: 0 = all healthy, 1 = degraded, 2 = critical

set -euo pipefail

# Ensure PATH includes homebrew (not set in SSH forced-command environment)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

FORMAT="${1:-json}"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
DASHBOARD_PORT="${DASHBOARD_PORT:-19100}"
OPENCLAW_USER="${OPENCLAW_USER:-augmentor}"
OPENCLAW_HOME="/Users/${OPENCLAW_USER}/.openclaw"
LAUNCH_AGENT_LABEL="ai.openclaw.gateway"
LAUNCH_AGENT_PLIST="${HOME}/Library/LaunchAgents/${LAUNCH_AGENT_LABEL}.plist"

# --- Sensor Functions ---
# Each returns: status (ok|degraded|critical), reason, details

sensor_gateway_process() {
    local pids
    pids=$(ps aux 2>/dev/null | grep "[o]penclaw-gateway" | awk '{print $2}' || true)
    if [ -n "$pids" ]; then
        local pid_count
        pid_count=$(echo "$pids" | wc -l | tr -d ' ')
        local first_pid
        first_pid=$(echo "$pids" | head -1)
        local uptime_info
        uptime_info=$(ps -o etime= -p "$first_pid" 2>/dev/null | tr -d ' ' || echo "unknown")
        echo "ok|Gateway process running (${pid_count} pid(s), uptime: ${uptime_info})|pids:${pids//$'\n'/,}"
    else
        echo "critical|Gateway process NOT running — no 'openclaw-gateway' process found|"
    fi
}

sensor_gateway_http() {
    local http_code
    # OpenClaw gateway health check
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 \
        "http://127.0.0.1:${GATEWAY_PORT}/api/health" 2>/dev/null || true)
    [ -n "$http_code" ] || http_code="000"
    
    if [ "$http_code" = "200" ]; then
        echo "ok|Gateway HTTP responding (200 on /api/health)|port:${GATEWAY_PORT}"
    elif [[ "$http_code" =~ ^0+$ ]]; then
        echo "critical|Gateway HTTP unreachable — connection refused or timeout on port ${GATEWAY_PORT}|http_code:000"
    else
        echo "degraded|Gateway HTTP returned unexpected status ${http_code}|http_code:${http_code}"
    fi
}

sensor_dashboard() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 \
        "http://127.0.0.1:${DASHBOARD_PORT}/api/health" 2>/dev/null || true)
    [ -n "$http_code" ] || http_code="000"

    if [ "$http_code" = "200" ]; then
        echo "ok|Dashboard HTTP responding (200 on /api/health)|port:${DASHBOARD_PORT}"
    elif [[ "$http_code" =~ ^0+$ ]]; then
        echo "critical|Dashboard HTTP unreachable — connection refused or timeout on port ${DASHBOARD_PORT}|http_code:000"
    else
        echo "degraded|Dashboard HTTP returned unexpected status ${http_code}|http_code:${http_code}"
    fi
}

sensor_launchagent() {
    if [ ! -f "$LAUNCH_AGENT_PLIST" ]; then
        echo "degraded|LaunchAgent plist not found at ${LAUNCH_AGENT_PLIST}|"
        return
    fi
    
    local status
    status=$(launchctl list 2>/dev/null | grep "$LAUNCH_AGENT_LABEL" || true)
    if [ -n "$status" ]; then
        local exit_code
        exit_code=$(echo "$status" | awk '{print $2}')
        if [ "$exit_code" = "0" ] || [ "$exit_code" = "-" ]; then
            echo "ok|LaunchAgent '${LAUNCH_AGENT_LABEL}' loaded and running|exit:${exit_code}"
        else
            echo "degraded|LaunchAgent loaded but last exit code: ${exit_code}|exit:${exit_code}"
        fi
    else
        echo "critical|LaunchAgent '${LAUNCH_AGENT_LABEL}' not loaded — service not registered|"
    fi
}

sensor_disk_space() {
    local avail_kb
    avail_kb=$(df -k / 2>/dev/null | tail -1 | awk '{print $4}')
    local avail_gb
    avail_gb=$((avail_kb / 1048576))
    local pct_used
    pct_used=$(df -k / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
    
    if [ "$avail_gb" -lt 5 ]; then
        echo "critical|Disk critically low: ${avail_gb}GB free (${pct_used}% used)|avail_gb:${avail_gb},pct_used:${pct_used}"
    elif [ "$avail_gb" -lt 20 ]; then
        echo "degraded|Disk space low: ${avail_gb}GB free (${pct_used}% used)|avail_gb:${avail_gb},pct_used:${pct_used}"
    else
        echo "ok|Disk space adequate: ${avail_gb}GB free (${pct_used}% used)|avail_gb:${avail_gb},pct_used:${pct_used}"
    fi
}

sensor_memory() {
    # Use memory_pressure command (macOS native)
    local free_pct
    free_pct=$(memory_pressure 2>/dev/null | grep "System-wide memory free percentage" | awk '{print $NF}' | tr -d '%' || echo "-1")
    
    if [ "$free_pct" = "-1" ]; then
        # Fallback to vm_stat
        local free_pages
        free_pages=$(vm_stat 2>/dev/null | grep "Pages free" | awk '{print $3}' | tr -d '.' || echo "0")
        local free_mb=$(( (free_pages * 16384) / 1048576 ))
        if [ "$free_mb" -lt 512 ]; then
            echo "critical|Memory critically low: ${free_mb}MB free (vm_stat fallback)|free_mb:${free_mb}"
        elif [ "$free_mb" -lt 2048 ]; then
            echo "degraded|Memory low: ${free_mb}MB free (vm_stat fallback)|free_mb:${free_mb}"
        else
            echo "ok|Memory adequate: ${free_mb}MB free (vm_stat fallback)|free_mb:${free_mb}"
        fi
    elif [ "$free_pct" -lt 10 ]; then
        echo "critical|Memory pressure CRITICAL: ${free_pct}% free|free_pct:${free_pct}"
    elif [ "$free_pct" -lt 25 ]; then
        echo "degraded|Memory pressure elevated: ${free_pct}% free|free_pct:${free_pct}"
    else
        echo "ok|Memory healthy: ${free_pct}% free|free_pct:${free_pct}"
    fi
}

sensor_network() {
    # Check internet connectivity (DNS + HTTP)
    local dns_ok=false
    local http_ok=false
    
    if host -W 3 api.anthropic.com >/dev/null 2>&1; then
        dns_ok=true
    fi
    
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 \
        "https://api.anthropic.com" 2>/dev/null || echo "000")
    if [ "$http_code" != "000" ]; then
        http_ok=true
    fi
    
    if $dns_ok && $http_ok; then
        echo "ok|Internet connectivity OK (DNS + HTTPS to api.anthropic.com)|http_code:${http_code}"
    elif $dns_ok; then
        echo "degraded|DNS resolves but HTTPS failed (HTTP ${http_code}) — possible firewall or API issue|http_code:${http_code}"
    else
        echo "critical|No internet connectivity — DNS resolution failed for api.anthropic.com|"
    fi
}

sensor_node_tunnel() {
    # Check if BeeAMD node is reachable via Ethernet
    # Uses TCP port check (SSH port 22) instead of ICMP ping (blocked by Windows firewall)
    local ssh_ok=false
    if bash -c "echo >/dev/tcp/10.0.0.2/22" 2>/dev/null; then
        ssh_ok=true
    fi
    
    # Also check for active SSH sessions from BeeAMD
    local tunnel_pids
    tunnel_pids=$(pgrep -f "sshd.*10.0.0.2" 2>/dev/null || true)
    
    if $ssh_ok && [ -n "$tunnel_pids" ]; then
        echo "ok|BeeAMD reachable (SSH port open) with active tunnel (pids: ${tunnel_pids//$'\n'/,})|"
    elif $ssh_ok; then
        echo "ok|BeeAMD reachable (SSH port 22 open on 10.0.0.2)|"
    else
        echo "degraded|BeeAMD unreachable (SSH port 22 closed on 10.0.0.2) — node may be offline|"
    fi
}

sensor_openclaw_config() {
    local config_file="${OPENCLAW_HOME}/openclaw.json"
    if [ ! -f "$config_file" ]; then
        echo "critical|OpenClaw config not found at ${config_file}|"
        return
    fi
    
    # Check if config is valid JSON
    if python3 -c "import json; json.load(open('${config_file}'))" 2>/dev/null; then
        local size
        size=$(wc -c < "$config_file" | tr -d ' ')
        echo "ok|OpenClaw config valid (${size} bytes)|path:${config_file}"
    else
        echo "critical|OpenClaw config is INVALID JSON — gateway will fail to start|path:${config_file}"
    fi
}

sensor_extensions() {
    local ext_dir="${OPENCLAW_HOME}/agents/main/agent/extensions"
    if [ ! -d "$ext_dir" ]; then
        echo "degraded|Extensions directory not found|path:${ext_dir}"
        return
    fi
    
    local total=0
    local valid=0
    local broken=""
    local has_node=false
    
    # Check if node is available for syntax validation
    if command -v node >/dev/null 2>&1; then
        has_node=true
    fi
    
    for f in "$ext_dir"/*.js; do
        [ -f "$f" ] || continue
        # Skip backups
        [[ "$f" == *.backup* ]] && continue
        [[ "$f" == *.save ]] && continue
        total=$((total + 1))
        
        if $has_node; then
            # Full syntax check
            if node -c "$f" 2>/dev/null; then
                valid=$((valid + 1))
            else
                broken="${broken}$(basename "$f"),"
            fi
        else
            # Fallback: check file is non-empty and readable
            if [ -s "$f" ] && head -1 "$f" >/dev/null 2>&1; then
                valid=$((valid + 1))
            else
                broken="${broken}$(basename "$f"),"
            fi
        fi
    done
    
    local check_type="syntax checked"
    $has_node || check_type="file check only, node not in PATH"
    
    if [ -n "$broken" ]; then
        echo "degraded|${valid}/${total} extensions valid (${check_type}), broken: ${broken%,}|total:${total},valid:${valid}"
    else
        echo "ok|${valid}/${total} extensions valid (${check_type})|total:${total},valid:${valid}"
    fi
}

# --- Run All Sensors ---

declare -a SENSORS=(
    "gateway_process"
    "gateway_http"
    "dashboard"
    "launchagent"
    "disk_space"
    "memory"
    "network"
    "node_tunnel"
    "openclaw_config"
    "extensions"
)

OVERALL="ok"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
HOSTNAME=$(hostname)

if [ "$FORMAT" = "json" ]; then
    echo "{"
    echo "  \"timestamp\": \"${TIMESTAMP}\","
    echo "  \"hostname\": \"${HOSTNAME}\","
    echo "  \"sensors\": {"
fi

FIRST=true
for sensor in "${SENSORS[@]}"; do
    result=$(sensor_"$sensor" 2>/dev/null || echo "degraded|Sensor '${sensor}' threw an error|")
    status=$(echo "$result" | cut -d'|' -f1)
    reason=$(echo "$result" | cut -d'|' -f2)
    details=$(echo "$result" | cut -d'|' -f3)
    
    # Update overall status
    if [ "$status" = "critical" ]; then
        OVERALL="critical"
    elif [ "$status" = "degraded" ] && [ "$OVERALL" != "critical" ]; then
        OVERALL="degraded"
    fi
    
    if [ "$FORMAT" = "json" ]; then
        [ "$FIRST" = true ] || echo ","
        FIRST=false
        # Escape quotes in reason/details
        reason_escaped=$(echo "$reason" | sed 's/"/\\"/g')
        details_escaped=$(echo "$details" | sed 's/"/\\"/g')
        printf '    "%s": {"status": "%s", "reason": "%s", "details": "%s"}' \
            "$sensor" "$status" "$reason_escaped" "$details_escaped"
    else
        printf "%-20s [%-8s] %s\n" "$sensor" "$status" "$reason"
    fi
done

if [ "$FORMAT" = "json" ]; then
    echo ""
    echo "  },"
    echo "  \"overall\": \"${OVERALL}\""
    echo "}"
else
    echo ""
    echo "OVERALL: ${OVERALL}"
fi

# Exit code based on overall status
case "$OVERALL" in
    ok)       exit 0 ;;
    degraded) exit 1 ;;
    critical) exit 2 ;;
    *)        exit 1 ;;
esac
