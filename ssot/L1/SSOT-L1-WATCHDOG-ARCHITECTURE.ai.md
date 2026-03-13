[AI-OPTIMIZED] ~260 tokens | src: SSOT-L1-WATCHDOG-ARCHITECTURE.md

| Field | Value |
|-------|-------|
| ID | SSOT-L1-WATCHDOG-ARCHITECTURE-V1 | Level | L1 | Status | Active |
| Created | 2026-03-01 | Stale After | 90 days |
| Related | SSOT-L1-SWARM-ARCHITECTURE, SSOT-L1-SYSTEM-OVERVIEW |

## Problem
Mac Mini = single point of failure. Gateway crash/broken extensions/disk full → nothing detects, nothing fixes, Manolo discovers hours later. BeeAMD has zero reverse visibility into orchestrator health.

## Solution: 3-Layer Architecture (Layer 4 deliberately excluded)

### Layer 1: Health Sensors (9 sensors, diagnosis not just detection)
| Sensor | Critical Threshold | Diagnostic Value |
|--------|-------------------|-----------------|
| gateway_process | Process absent | vs crash vs unresponsive |
| gateway_http | /api/health non-200 | refused vs timeout vs hang |
| launchagent | Not registered | vs loaded-but-crashed (exit code) |
| disk_space | <5GB on / | Exact GB + percentage |
| memory | <10% free | macOS pressure level |
| network | DNS/HTTPS to Anthropic fails | DNS vs HTTPS vs API unreachable |
| node_tunnel | (informational) | Active vs reachable-no-tunnel vs unreachable |
| openclaw_config | Invalid JSON | Pre-restart config validation |
| extensions | JS syntax error | Catches broken extension before load |

### Layer 2: Automated Restart
`launchctl bootout` + `bootstrap` → wait 10s → re-check → retry up to 3× → Layer 3 if failed.
**Scope:** ONLY restarts `ai.openclaw.gateway` and `ai.openclaw.node` — cannot modify files/read data/arbitrary commands.

### Layer 3: Alert (human escalation)
Telegram message with diagnostic report. Rate-limited: 1 alert/30 min.

### Layer 4: AI with SSH (NOT IMPLEMENTED — intentional)
Blast radius too high. L1-L3 handles 95%+ of failures. Remaining 5% needs human judgment.

## Security Model
**Threat → Mitigation → Residual:**
- BeeAMD compromised: SSH `restrict,command=,from=10.0.0.2` → can only restart gateway (low impact)
- Key stolen: Only works from 10.0.0.2, only runs handler script → useless elsewhere
- Watchdog user capabilities: NO home dir, NO wallet/API key access, NO arbitrary commands, NO port forwarding, NO PTY
- sudoers: ONLY specific launchctl commands, validated with `visudo -cf`
- authorized_keys: root-owned (600) — watchdog cannot modify own restrictions

## File Layout
```
shield/watchdog/
├── health-sensors.sh       # 9 sensors (bash, Mac Mini)
├── watchdog-handler.sh     # SSH forced-command handler (bash, Mac Mini)
├── watchdog-client.ps1     # Monitoring client (PowerShell, BeeAMD)
├── SETUP.md                # Step-by-step setup
└── README.md               # Quick reference
```

## Monitoring Cycle (every 5 min)
BeeAMD ping → reachable? → SSH health check → JSON health report → ok/degraded/critical → restart if critical → verify → alert if restart failed

## What's Next
1. Manolo runs sudo commands from SETUP.md
2. Test SSH from BeeAMD with restricted key
3. Enable scheduled task on BeeAMD
4. Review logs after 48h
5. Cross-platform generalization (Linux systemd, Windows services)

## Anti-Patterns
Watchdog user with real shell | User owns authorized_keys | AI SSH for "smart fixing" | Monitor via gateway API only | No diagnosis (just "offline") | Alert every check failure

## Changelog
2026-03-01 V1: 9 sensors, 3-layer arch, security threat model, setup instructions.
