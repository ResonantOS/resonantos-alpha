# SSOT-L1-WATCHDOG-ARCHITECTURE — Cross-Node Emergency Recovery

| Field | Value |
|-------|-------|
| ID | SSOT-L1-WATCHDOG-ARCHITECTURE-V1 |
| Level | L1 (Architecture — Truth) |
| Created | 2026-03-01 |
| Status | Active |
| Stale After | 90 days |
| Related | SSOT-L1-SWARM-ARCHITECTURE, SSOT-L1-SYSTEM-OVERVIEW |

---

## The Problem

The orchestrator (Mac Mini) is a single point of failure. If the OpenClaw gateway crashes, extensions break, disk fills up, or the system enters a bad state — nothing detects it, nothing fixes it, and Manolo discovers the outage hours later by noticing silence.

A second machine (BeeAMD) is already connected as a worker node but has zero reverse visibility. It blindly trusts that the orchestrator is healthy.

## The Solution: Deterministic Watchdog with Diagnostic Sensors

Three-layer architecture — each layer activates only when the previous is insufficient:

### Layer 1: Health Sensors (Diagnosis)
Nine deterministic sensors that diagnose WHY something is wrong, not just IF:

| Sensor | What | Critical Threshold | Diagnostic Value |
|--------|------|-------------------|------------------|
| gateway_process | Is `openclaw-gateway` running? | Process absent | "No process found" vs "process exists but unresponsive" |
| gateway_http | Does /api/health return 200? | Connection refused/timeout | Distinguishes crash vs hang vs port conflict |
| launchagent | Is the LaunchAgent loaded? | Not registered | "Not loaded" vs "loaded but crashed (exit code)" |
| disk_space | Available GB on / | < 5 GB | Exact GB + percentage for trend analysis |
| memory | System memory pressure | < 10% free | macOS pressure level + free percentage |
| network | DNS + HTTPS to Anthropic API | DNS fails | "DNS down" vs "HTTPS blocked" vs "API unreachable" |
| node_tunnel | BeeAMD SSH tunnel status | (informational) | "Tunnel active" vs "reachable but no tunnel" vs "unreachable" |
| openclaw_config | JSON validity of config | Invalid JSON | Catches corrupted config before gateway restart fails |
| extensions | JS syntax check on all extensions | (informational) | Catches broken extension that would crash gateway on load |

**Key design principle:** Every sensor returns status + reason + details. "Gateway is down because the process isn't running" is actionable. "Gateway is down" is not.

### Layer 2: Automated Restart (Recovery)
When health sensors detect a critical gateway failure:
1. Attempt `launchctl bootout` + `launchctl bootstrap` (service restart)
2. Wait 10 seconds, re-run health sensors
3. If recovered → log + notify (informational)
4. If still critical → retry up to 3 times
5. After 3 failures → escalate to Layer 3

**Scope restriction:** Can ONLY restart `ai.openclaw.gateway` and `ai.openclaw.node` LaunchAgent services. Cannot modify files, read data, or execute arbitrary commands.

### Layer 3: Alert (Escalation to Human)
When automated restart fails or non-restartable issues are detected:
- Send Telegram message with diagnostic report
- Include which sensors are critical and their reasons
- Include time since last healthy check
- Rate-limited to one alert per 30 minutes (no spam)

### Layer 4: AI Diagnosis (NOT IMPLEMENTED — deliberate)
An AI agent on BeeAMD that could SSH into the Mac Mini, read logs, and attempt complex fixes. **Intentionally excluded** because:
- The blast radius of a compromised AI agent with SSH access is too high
- L1-L3 handle 95%+ of failures (service crash → restart)
- The remaining 5% genuinely need human judgment
- Adding AI reasoning to the recovery path introduces the exact failure mode we're guarding against

## Security Architecture

### Threat Model

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| BeeAMD compromised → attacker reaches Mac Mini | SSH `restrict,command=,from=` limits to one script from one IP | Attacker can restart gateway (low impact) |
| Watchdog SSH key stolen | Key only works from 10.0.0.2, only runs handler script | Useless outside local Ethernet |
| authorized_keys modification | File owned by root, watchdog user has no write access | Requires root compromise on Mac Mini |
| SFTP/SCP bypass of command restriction | `restrict` keyword + sshd_config `Match User` block disables all forwarding | Double enforcement (key + config) |
| Privilege escalation via sudoers | Sudoers allows ONLY specific launchctl commands, nothing else | Validated with `visudo -cf` |
| Man-in-the-middle on Ethernet | Direct cable (no switch/router), SSH encryption | Physical access required |

### Access Controls

| Component | Owner | Permissions | Purpose |
|-----------|-------|-------------|---------|
| `/var/empty/.ssh/authorized_keys` | root:wheel | 600 | Prevents watchdog from modifying own key restrictions |
| `/etc/sudoers.d/watchdog` | root:wheel | 440 | Scoped sudo for launchctl only |
| `watchdog-handler.sh` | augmentor | 755 | SSH forced-command target |
| `health-sensors.sh` | augmentor | 755 | Called by handler |
| Watchdog user shell | `/usr/bin/false` | N/A | No interactive shell access |

### What the watchdog user CANNOT do
- Read `/Users/augmentor/` (no home directory access)
- Read `~/.config/solana/id.json` (wallet)
- Read `auth-profiles.json` (API keys)
- Read `MEMORY.md` or any memory files
- Execute arbitrary commands (forced-command restriction)
- Forward ports (restrict keyword)
- Allocate PTY (restrict keyword)
- Modify its own SSH restrictions (root-owned authorized_keys)

## Integration Points

### With Swarm Architecture (SSOT-L1-SWARM-ARCHITECTURE)
The watchdog is a **reverse health channel** in the swarm:
- Normal direction: Orchestrator → Node (task delegation, exec commands)
- Watchdog direction: Node → Orchestrator (health monitoring, emergency restart)
- Both use SSH as transport, both have key-based auth, both are scoped

### With Shield (Security)
Health sensors extend Shield's monitoring to infrastructure level:
- Shield: guards against bad AI decisions (exec gating, verification)
- Watchdog: guards against infrastructure failures (process crashes, disk, memory)
- Both are deterministic, code-enforced, zero AI reasoning

## Implementation

### Files
```
shield/watchdog/
├── health-sensors.sh       # 9 diagnostic sensors (bash, runs on Mac Mini)
├── watchdog-handler.sh     # SSH forced-command handler (bash, Mac Mini)
├── watchdog-client.ps1     # Monitoring client (PowerShell, BeeAMD)
├── SETUP.md                # Step-by-step setup instructions
└── README.md               # Quick reference for alpha users
```

### Monitoring Cycle (every 5 minutes)
```
BeeAMD: ping orchestrator
  ├─ unreachable → increment failure counter → alert after threshold
  └─ reachable → SSH health check
       ├─ SSH fails → increment failure counter → alert after threshold
       └─ SSH succeeds → parse JSON health report
            ├─ ok → reset counters, log
            ├─ degraded → log warnings, monitor
            └─ critical → attempt restart → verify → alert if failed
```

## Anti-Patterns

| Pattern | Why It Fails |
|---------|-------------|
| Giving watchdog user a real shell | Entire security model collapses — any command becomes possible |
| Watchdog user owns its authorized_keys | Can remove `command=` restriction via SFTP |
| AI agent with SSH access for "smart fixing" | Unbounded scope, compromised AI = insider threat |
| Monitoring via gateway API only | If gateway is down, monitoring is blind |
| Single check with no diagnosis | "Offline" without "why" delays recovery |
| Alerting on every check failure | Alert fatigue → alerts get ignored |

## What's Next

1. **Setup:** Manolo runs the sudo-requiring commands from SETUP.md
2. **Test:** Verify SSH from BeeAMD with restricted key
3. **Activate:** Enable scheduled task on BeeAMD
4. **Monitor:** Review logs after 48 hours
5. **Cross-platform generalization:** Abstract for alpha users (Linux systemd, Windows services)

## Change Log

| Date | Change |
|------|--------|
| 2026-03-01 | V1 created. 9 sensors, 3-layer architecture, security threat model, setup instructions. |

## REFERENCES
- Swarm Architecture: `SSOT-L1-SWARM-ARCHITECTURE.md`
- System Overview: `SSOT-L1-SYSTEM-OVERVIEW.md`
- Shield Gate: `shield-gate.js` (same security philosophy)
- Setup: `shield/watchdog/SETUP.md`
