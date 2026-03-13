#!/bin/bash
# Watchdog Handler — Restricted command for SSH forced-command access
# This script is the ONLY thing the watchdog SSH key can execute.
# Called by: SSH authorized_keys command= restriction
# 
# The original SSH command is in $SSH_ORIGINAL_COMMAND
# Allowed actions: health, restart-gateway, restart-node, restart-dashboard, version
#
# Security: NO shell access, NO file read, NO arbitrary commands.
# This script validates the action and executes only whitelisted operations.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DASHBOARD_DIR="${REPO_ROOT}/dashboard"
LOG_FILE="/tmp/watchdog-handler.log"
LAUNCH_AGENT_LABEL="ai.openclaw.gateway"
NODE_LAUNCH_AGENT="ai.openclaw.node"
DASHBOARD_PORT="${DASHBOARD_PORT:-19100}"
DASHBOARD_LOG="/tmp/dashboard.log"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*" >> "$LOG_FILE"
}

# Parse action from SSH_ORIGINAL_COMMAND or first argument
ACTION="${SSH_ORIGINAL_COMMAND:-${1:-help}}"

# Strip any arguments after the action (security: no injection)
ACTION=$(echo "$ACTION" | awk '{print $1}')

log "Action requested: ${ACTION} (from: ${SSH_CONNECTION:-local})"

case "$ACTION" in
    health)
        # Run health sensors and return JSON
        if [ -x "${SCRIPT_DIR}/health-sensors.sh" ]; then
            "${SCRIPT_DIR}/health-sensors.sh" json
        else
            echo '{"error": "health-sensors.sh not found", "overall": "critical"}'
            exit 2
        fi
        ;;
    
    restart-gateway)
        log "Restarting gateway service"
        # Bootout (stop) then bootstrap (start) the LaunchAgent
        UID_VAL=$(id -u)
        launchctl bootout "gui/${UID_VAL}/${LAUNCH_AGENT_LABEL}" 2>/dev/null || true
        sleep 2
        PLIST="${HOME}/Library/LaunchAgents/${LAUNCH_AGENT_LABEL}.plist"
        if [ -f "$PLIST" ]; then
            launchctl bootstrap "gui/${UID_VAL}" "$PLIST" 2>/dev/null
            sleep 3
            # Verify it came back
            if "${SCRIPT_DIR}/health-sensors.sh" json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['sensors']['gateway_http']['status']=='ok' else 1)" 2>/dev/null; then
                echo '{"action": "restart-gateway", "result": "success", "message": "Gateway restarted and responding"}'
                log "Gateway restart: SUCCESS"
            else
                echo '{"action": "restart-gateway", "result": "partial", "message": "Gateway restarted but not yet responding — may need time"}'
                log "Gateway restart: PARTIAL — not responding yet"
            fi
        else
            echo '{"action": "restart-gateway", "result": "failed", "message": "LaunchAgent plist not found"}'
            log "Gateway restart: FAILED — plist not found"
            exit 1
        fi
        ;;
    
    restart-node)
        log "Restarting node service"
        UID_VAL=$(id -u)
        launchctl bootout "gui/${UID_VAL}/${NODE_LAUNCH_AGENT}" 2>/dev/null || true
        sleep 2
        PLIST="${HOME}/Library/LaunchAgents/${NODE_LAUNCH_AGENT}.plist"
        if [ -f "$PLIST" ]; then
            launchctl bootstrap "gui/${UID_VAL}" "$PLIST" 2>/dev/null
            echo '{"action": "restart-node", "result": "success", "message": "Node service restarted"}'
            log "Node restart: SUCCESS"
        else
            echo '{"action": "restart-node", "result": "skipped", "message": "Node LaunchAgent not installed (expected if this IS the orchestrator)"}'
            log "Node restart: SKIPPED — plist not found"
        fi
        ;;

    restart-dashboard)
        log "Restarting dashboard service"

        if [ ! -d "$REPO_DASHBOARD_DIR" ]; then
            echo "{\"action\": \"restart-dashboard\", \"result\": \"failed\", \"message\": \"Dashboard directory not found: ${REPO_DASHBOARD_DIR}\"}"
            log "Dashboard restart: FAILED — dashboard directory missing"
            exit 1
        fi

        pkill -f "server_v2.py" 2>/dev/null || true
        sleep 2

        (
            cd "$REPO_DASHBOARD_DIR"
            nohup python3 server_v2.py >> "$DASHBOARD_LOG" 2>&1 &
        )

        sleep 3
        if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 \
            "http://127.0.0.1:${DASHBOARD_PORT}/api/health" 2>/dev/null | grep -q "^200$"; then
            echo '{"action": "restart-dashboard", "result": "success", "message": "Dashboard restarted and responding"}'
            log "Dashboard restart: SUCCESS"
        else
            echo '{"action": "restart-dashboard", "result": "partial", "message": "Dashboard restart attempted but not yet responding"}'
            log "Dashboard restart: PARTIAL — not responding yet"
        fi
        ;;
    
    version)
        # Return OpenClaw version and basic system info
        local_version=$(openclaw --version 2>/dev/null || echo "unknown")
        echo "{\"version\": \"${local_version}\", \"hostname\": \"$(hostname)\", \"uptime\": \"$(uptime | sed 's/.*up //' | sed 's/,.*//')\"}"
        ;;
    
    help)
        echo "Watchdog Handler — Allowed actions:"
        echo "  health           — Run health sensors (JSON output)"
        echo "  restart-gateway  — Restart OpenClaw gateway service"
        echo "  restart-node     — Restart OpenClaw node service"
        echo "  restart-dashboard — Restart dashboard service"
        echo "  version          — Show version and uptime"
        echo ""
        echo "This script is called via SSH forced-command restriction."
        echo "No other commands are permitted."
        ;;
    
    *)
        log "BLOCKED: Unknown action '${ACTION}'"
        echo '{"error": "Unknown action", "allowed": ["health", "restart-gateway", "restart-node", "restart-dashboard", "version"]}'
        exit 1
        ;;
esac
