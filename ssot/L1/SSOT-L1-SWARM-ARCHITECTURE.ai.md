[AI-OPTIMIZED] ~320 tokens | src: SSOT-L1-SWARM-ARCHITECTURE.md

| Field | Value |
|-------|-------|
| Level | L1 | Created | 2026-02-28 | Status | Active | Stale After | 90 days |

## Vision
Orchestrator (Mac Mini) manages node network: AI workers (autonomous), Human+AI workers (employee machines), Cloud VPS, Local hardware. One orchestrator coordinates multiple workers across envs/OSes.

## Network Topology
| Machine | Role | OS | IP (Eth) | IP (WiFi) | Connection |
|---------|------|----|----------|-----------|------------|
| Mac Mini | Orchestrator | macOS 26.3 arm64 | 10.0.0.1 | 192.168.1.206 | Always-on |
| BeeAMD | Node | Windows 11 Pro x64 | 10.0.0.2 | — | Direct Ethernet cable |

**Physical link:** Direct Ethernet (point-to-point, no router/switch).

## Connection Architecture
**Layer 1: SSH Tunnel (transport)**
`ssh -N -L 18789:127.0.0.1:18789 augmentor@10.0.0.1`
- Direction: Windows → Mac Mini (outbound from node)
- Auth: Key-based ed25519, no passphrase
- Windows key: `C:\Users\danze\.ssh\id_ed25519` | Mac Mini: `~/.ssh/authorized_keys`

**Layer 2: OpenClaw Node**
`openclaw node run --host 127.0.0.1 --port 18789`
- Node ID: `773c82428f519ad199561a079736963e6ebf01d61032b03493f355dde5e28dd8`
- Display Name: "Windows PC"

**Why SSH tunnel:** Gateway binds loopback only. OpenClaw blocks plaintext `ws://` to remote IPs. No cert management. Works through NAT.

## Reboot Resilience
**Mac Mini:** pmset autorestart=1, sleep=0; sysadminctl autologin (augmentor); LaunchAgent (KeepAlive=true); SSH always running.
FileVault: DISABLED to enable auto-login. Apple Silicon M4 hardware encryption still active.

**BeeAMD:** AutoAdminLogon=1 registry; Scheduled Task `OpenClaw-AutoConnect` (AtLogon) starts SSH tunnel then openclaw node; gsudo CacheMode=Auto (no UAC).
Startup script: `C:\Users\danze\openclaw-autostart.ps1`

## BeeAMD Hardware
AMD Ryzen 5 5560U, 6C/12T, 12.9GB RAM, Windows 11 Pro x64, ~307GB free, user: danze

## Node Onboarding (Proven Procedure)
1. Install Node.js + OpenClaw on node
2. `ssh-keygen -t ed25519 -N "" -C "openclaw-node@hostname"`
3. Add pubkey to Mac Mini `~/.ssh/authorized_keys`
4. Test: `ssh -o BatchMode=yes augmentor@10.0.0.1 echo OK`
5. `ssh -N -L 18789:127.0.0.1:18789 augmentor@10.0.0.1`
6. `openclaw node run --host 127.0.0.1 --port 18789`
7. Approve pairing (first connection only)
8. Create startup script + scheduled task for persistence

## Known Issues During First Setup (~2.5h total)
| Problem | Cause | Fix |
|---------|-------|-----|
| PS scripts blocked | ExecutionPolicy=Restricted | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| SECURITY ERROR | Old remote IP in config | Use `--host 127.0.0.1 --port 18789` |
| Permission denied port 18789 | Old process holding port | `taskkill /PID <pid> /F` |
| SSH timeout to 192.168.1.206 | Windows on Ethernet, not WiFi subnet | Use 10.0.0.1 |
| gsudo UAC timeout | CacheMode not set | Set CacheMode=Auto after one approval |
| Version mismatch | 2025.x gateway vs 2026.x node | Upgrade both to match |
| Clock drift | "device signature expired" | `w32tm /resync` |
| No reconnect after reboot | No auto-start existed | Scheduled Task + startup script |
| Auto-login blocked | FileVault enabled | Disable FileVault |

## Troubleshooting
`nc -z 10.0.0.1 22` — check SSH | `netstat -ano | findstr 18789` — port conflict | `w32tm /resync` — clock drift | `ssh-keygen` permissions: `chmod 600 ~/.ssh/authorized_keys`

## Future Expansion
- Ubuntu VM on BeeAMD (deferred)
- Cloud nodes: reverse SSH or Tailscale
- Each new node: SSH key + authorized_keys + startup script + route to orchestrator + auto-login

**References:** `memory/2026-02-28.md` | `~/.openclaw/openclaw.json` | `C:\Users\danze\openclaw-autostart.ps1`
