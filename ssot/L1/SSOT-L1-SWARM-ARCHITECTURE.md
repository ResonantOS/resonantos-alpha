# SSOT-L1-SWARM-ARCHITECTURE — Node Network Architecture

> **Level:** L1 (Architecture)
> **Created:** 2026-02-28
> **Status:** Active
> **Stale After:** 90 days

---

## 1. Vision

The orchestrator (Mac Mini running ResonantOS) manages a network of nodes. Nodes can be:

- **AI Workers:** Fully autonomous machines running tasks delegated by the orchestrator
- **Human+AI Workers:** Employee machines where a human and their AI collaborate, connected to the swarm
- **Cloud Servers:** Remote VPS/cloud instances running as headless nodes
- **Local Hardware:** Physical machines connected via LAN, Ethernet, or VPN

This is a **professional/power-user feature** — the foundation for AI-managed infrastructure where one orchestrator coordinates multiple workers across environments and operating systems.

**Product picture:** User installs ResonantOS on a central machine. Connects other machines (local, remote, cloud) as nodes. The orchestrator manages them — deploying tasks, running tests, monitoring health. Each node can be purely autonomous or paired with a human operator.

```
┌─────────────────────────────────────┐
│     Mac Mini (Orchestrator)         │
│     192.168.1.206 (Wi-Fi)           │
│     10.0.0.1 (Ethernet)             │
│     Gateway: ws://127.0.0.1:18789   │
│     LaunchAgent: KeepAlive=true     │
├─────────────────────────────────────┤
│         ↕ Direct Ethernet Cable     │
├─────────────────────────────────────┤
│     BeeAMD (Windows PC)             │
│     10.0.0.2 (Ethernet)             │
│     User: danze                     │
│     SSH tunnel → localhost:18789    │
│     Node: openclaw node run         │
└─────────────────────────────────────┘
```

## 2. Network Topology

| Machine | Role | OS | IP (Ethernet) | IP (Wi-Fi) | Connection |
|---------|------|----|---------------|------------|------------|
| Mac Mini | Orchestrator | macOS 26.3 (arm64) | 10.0.0.1 | 192.168.1.206 | Always-on |
| BeeAMD | Node | Windows 11 Pro x64 | 10.0.0.2 | — | Direct Ethernet to Mac Mini |

**Physical link:** Direct Ethernet cable between Mac Mini and BeeAMD. No router, no switch. Point-to-point.

## 3. Connection Architecture

### Layer 1: SSH Tunnel (Transport)
- **Purpose:** Securely forward gateway port through encrypted channel
- **Direction:** Windows → Mac Mini (outbound from node)
- **Command:** `ssh -N -L 18789:127.0.0.1:18789 augmentor@10.0.0.1`
- **Auth:** Key-based (ed25519, no passphrase)
- **Key location (Windows):** `C:\Users\danze\.ssh\id_ed25519`
- **Authorized on Mac Mini:** `~/.ssh/authorized_keys`

### Layer 2: OpenClaw Node (Control)
- **Purpose:** Native tool integration (exec, browser, camera, etc.)
- **Command:** `openclaw node run --host 127.0.0.1 --port 18789`
- **Protocol:** WebSocket to localhost (forwarded by SSH tunnel)
- **Node ID:** `773c82428f519ad199561a079736963e6ebf01d61032b03493f355dde5e28dd8`
- **Display Name:** "Windows PC"

### Why SSH Tunnel (not direct WSS)?
- Gateway binds to loopback only (security default — OpenClaw enforces this)
- OpenClaw blocks plaintext `ws://` to remote IPs with a hard security error
- Self-signed TLS certificates cause trust chain issues on nodes
- SSH provides proven encryption + key auth + no certificate management
- No additional ports to open, no firewall changes needed
- Works through any NAT (SSH is universally supported)

### Alternative approaches tested and rejected
| Approach | Why it failed |
|----------|--------------|
| Direct `ws://` to remote IP | OpenClaw blocks with "SECURITY ERROR: Cannot connect over plaintext" |
| `gateway config.patch` for TLS binding | `openclaw gateway` CLI doesn't support `config patch` subcommand |
| Binding gateway to `0.0.0.0` with self-signed cert | Even if config supported it, self-signed certs cause trust issues |
| SSH tunnel via Wi-Fi (192.168.1.206) | Connection timed out — Windows PC is on Ethernet (10.0.0.x), not Wi-Fi subnet |

## 4. Reboot Resilience

### Mac Mini (Orchestrator)
| Component | Mechanism | Survives Reboot? |
|-----------|-----------|-----------------|
| Power restore | `autorestart=1` (pmset) | ✅ Auto-powers on |
| Sleep prevention | `sleep=0` (pmset) | ✅ Never sleeps |
| Auto-login | `sysadminctl -autologin` (augmentor) | ✅ No password needed |
| Gateway | LaunchAgent, RunAtLoad=true, KeepAlive=true | ✅ Starts with user session |
| SSH server | System service, port 22 | ✅ Always running |

**FileVault decision (2026-02-28):** Disabled FileVault to enable auto-login. Apple Silicon (M4) has always-on hardware encryption independent of FileVault — data is still encrypted at the hardware level. The tradeoff (removing software encryption layer) is acceptable for a dedicated always-on server that rarely leaves the home.

### BeeAMD (Windows PC)
| Component | Mechanism | Survives Reboot? |
|-----------|-----------|-----------------|
| Auto-login | `AutoAdminLogon=1` (registry) | ✅ Logs in as danze |
| SSH tunnel | Scheduled Task `OpenClaw-AutoConnect` (AtLogon) | ✅ Starts tunnel |
| OpenClaw node | Same scheduled task (after tunnel) | ✅ Starts node |
| Elevation | gsudo CacheMode=Auto | ✅ No UAC prompts |

**Startup script:** `C:\Users\danze\openclaw-autostart.ps1`
- Kills any existing process on port 18789
- Starts SSH tunnel to 10.0.0.1 (key auth, no password)
- Runs `openclaw node run` (blocks until stopped)
- Cleanup on exit

## 5. Elevation (Windows)

- **Tool:** gsudo (installed via winget, user-scope)
- **CacheMode:** Auto (credentials cached per session, no UAC prompts)
- **Use cases:** Auto-login setup, BIOS config, service installation
- **Security note:** CacheMode=Auto means any process in the user session can elevate. Acceptable for a dedicated test/worker node.

## 6. Hardware Specs

### Mac Mini (Orchestrator)
- Apple M4, 16GB RAM, 256GB SSD
- macOS 26.3 (arm64)
- Hostname: Resonants-Mac-mini.local

### BeeAMD (Windows Node)
- AMD Ryzen 5 5560U, 6C/12T, 12.9GB RAM
- Windows 11 Pro x64
- User: danze
- Free space: ~307GB

## 7. Node Onboarding Procedure

### What worked (final proven procedure for Windows)
1. Install Node.js + OpenClaw on the node machine
2. Generate SSH key: `ssh-keygen -t ed25519 -N "" -C "openclaw-node@hostname"`
3. Add public key to orchestrator's `~/.ssh/authorized_keys`
4. Test SSH: `ssh -o BatchMode=yes augmentor@<orchestrator_ip> echo OK`
5. Open SSH tunnel: `ssh -N -L 18789:127.0.0.1:18789 augmentor@<orchestrator_ip>`
6. Run node: `openclaw node run --host 127.0.0.1 --port 18789`
7. Approve pairing on orchestrator (first connection only)
8. Create startup script + scheduled task for persistence

### What went wrong during first setup (know-how log)

| # | Problem | Root Cause | Solution | Time Wasted |
|---|---------|-----------|----------|-------------|
| 1 | PowerShell scripts won't run | Windows defaults ExecutionPolicy to Restricted | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` | 5 min |
| 2 | `openclaw node run` errors "SECURITY ERROR" | Node config had old remote IP, not localhost | Add `--host 127.0.0.1 --port 18789` | 10 min |
| 3 | SSH tunnel "Permission denied" on port 18789 | Old process (PID 4456) holding the port from previous attempt | `taskkill /PID <pid> /F` before starting tunnel | 5 min |
| 4 | SSH tunnel to 192.168.1.206 times out | Windows PC is on Ethernet (10.0.0.x), Mac Mini Wi-Fi is 192.168.1.x — different subnets | Use Ethernet IP 10.0.0.1 instead | 15 min |
| 5 | Tried `gateway config.patch` to bind 0.0.0.0 | CLI doesn't support this subcommand | Abandoned — SSH tunnel is the right approach | 10 min |
| 6 | Tried generating self-signed TLS certs | Even if gateway supported TLS binding, cert trust is a pain | Abandoned — SSH tunnel handles encryption | 5 min |
| 7 | gsudo elevation times out | Each gsudo call triggers UAC prompt on Secure Desktop | Need human to approve, then set CacheMode=Auto | 20 min |
| 8 | Gateway version mismatch on first setup | 2025.x gateway vs 2026.x node = signature validation failure | Upgrade gateway to match node version | 15 min |
| 9 | Clock drift causes "device signature expired" | Windows PC was offline, clock drifted 2 minutes | Manual time sync | 5 min |
| 10 | After reboot, node doesn't reconnect | No auto-start mechanism existed | Scheduled Task + startup script + SSH key auth | 30 min |
| 11 | Auto-login blocked on Mac Mini | FileVault was enabled | Disable FileVault (hardware encryption still active on Apple Silicon) | 10 min |
| 12 | Bootstrap script had syntax errors | PowerShell heredoc escaping differs from bash | Rewrite script with proper PS syntax | 15 min |

**Total time debugging: ~2.5 hours** for what should be a 15-minute setup. The know-how above reduces this to <15 min for the next node.

### Critical lesson: Network topology awareness
The orchestrator MUST know its own network topology — which IPs are reachable from which interfaces. Attempting connections via Wi-Fi IP when the node is on Ethernet wastes significant time. The architecture doc must always document the physical link type and IP assignments.

## 8. Future Expansion

- **Ubuntu VM on BeeAMD:** Planned, deferred until base Windows connectivity is solid and proven through a reboot cycle
- **Cloud nodes:** Same SSH tunnel pattern, but tunnel direction reverses (cloud → orchestrator via reverse SSH or Tailscale)
- **Additional local nodes:** Same pattern — SSH tunnel + OpenClaw node

### Each new node needs:
1. SSH key generated on node
2. Public key added to Mac Mini `~/.ssh/authorized_keys`
3. Startup script + scheduled task (Windows) or systemd service (Linux)
4. Ethernet or network route to orchestrator
5. Auto-login configured (eliminate human dependency at boot)

### Node types (future):
| Type | Description | Auto-login | Human needed? |
|------|------------|------------|---------------|
| Worker (autonomous) | Runs AI tasks, no human interaction | Required | No |
| Worker (human+AI) | Employee machine, human + AI collaborate | Optional | Yes (at workstation) |
| Cloud worker | VPS/cloud instance | N/A (always running) | No |
| Test node | Multi-OS testing (our BeeAMD) | Required | No |

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Node disconnected after reboot | Auto-login or scheduled task failed | Check `Get-ScheduledTask OpenClaw-AutoConnect` |
| SSH tunnel won't connect | Mac Mini SSH not running or IP changed | `nc -z 10.0.0.1 22` from Windows |
| "SECURITY ERROR: plaintext ws://" | Node trying remote IP instead of localhost | Use `--host 127.0.0.1` |
| "Permission denied" on port 18789 | Old process holding port | `netstat -ano | findstr 18789` then `taskkill /PID <pid> /F` |
| gsudo prompts UAC | CacheMode reset | `gsudo config CacheMode Auto` (one UAC click) |
| PowerShell scripts blocked | Execution policy reset (Windows Update) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| "device signature invalid" | Gateway/node version mismatch | Upgrade both to same version |
| "device signature expired" | Clock drift >60s | Sync time: `w32tm /resync` (Windows) or `sntp -sS time.apple.com` (macOS) |
| SSH key auth fails | Wrong permissions on authorized_keys | `chmod 600 ~/.ssh/authorized_keys` |

## REFERENCES
- Memory: `memory/2026-02-28.md` (full setup log with timestamps)
- Gateway config: `~/.openclaw/openclaw.json`
- Windows startup script: `C:\Users\danze\openclaw-autostart.ps1`
- Windows alpha test results: `memory/L4-WINDOWS-ALPHA-TEST-2026-02-28.md`
