---
name: node-deploy
description: >
  Deploy and provision ResonantOS on remote machines via OpenClaw node system.
  Use when: (1) setting up a new node (Windows, Linux, macOS), (2) deploying
  a swarm member or fleet machine, (3) provisioning a VM for ResonantOS,
  (4) user says "deploy", "provision", "set up a machine", "install on remote",
  "add a node", or "swarm setup". NOT for: local OpenClaw installation (that's
  install.js), configuration changes on existing nodes, or simple SSH tasks.
---

# Node Deployment Skill

Deploy ResonantOS on a remote machine via OpenClaw's node system. The orchestrator
(you) runs this procedure — no human intervention needed after initial access.

## Deployment Roles

| Role | Human | Install Path | Use Case |
|------|-------|-------------|----------|
| **Sovereign** | Paired | Full setup interview | Human's primary AI |
| **Partner** | Paired | Light interview | Employee AI assistant |
| **Specialist** | No | Config from orchestrator | Coder, researcher |
| **Worker** | No | Minimal | Build server, CI |
| **Sentinel** | No | Monitor only | Security, health |

Default role for swarm nodes: **Specialist**. Default for human use: **Sovereign**.

## Pre-Flight Checks (MANDATORY)

Before attempting any installation, run ALL four checks. See [references/preflight.md](references/preflight.md).

Failure on any check = STOP and resolve before proceeding. Do not skip.

## Deployment Procedure

### Phase 1: Access & Reconnaissance

1. Verify node connectivity: `nodes run --node <name> "echo OK"`
2. Detect OS: `uname -s` (Linux/macOS) or `systeminfo` (Windows)
3. Detect arch: `uname -m` or `wmic os get osarchitecture`
4. Check RAM, disk, existing software
5. Record findings — these determine which OS playbook to follow

### Phase 2: Prerequisites

Based on OS detected, follow the appropriate reference:
- **Windows**: [references/windows.md](references/windows.md)
- **Linux (Ubuntu/Debian)**: [references/linux.md](references/linux.md)
- **macOS**: Same as local install (install.js handles it)

Key prerequisites: Node.js 18+, Python 3, Git, pip3.

### Phase 3: OpenClaw + ResonantOS Installation

```bash
# Clone alpha repo
git clone https://github.com/ResonantOS/resonantos-alpha.git ~/resonantos-alpha

# Run installer
node ~/resonantos-alpha/install.js
```

If the node already has OpenClaw installed and paired, skip to install.js.
If not, install OpenClaw first: `npm install -g openclaw`

### Phase 4: Node Registration (Swarm/Fleet only)

For non-sovereign roles, the orchestrator pushes config instead of running the
setup interview:

1. Set the node's model based on available providers
2. Push workspace templates pre-filled with role-appropriate content
3. Configure extensions (R-Memory, R-Awareness, gateway-lifecycle)
4. Register node in fleet registry: `memory/fleet/nodes.json`

### Phase 5: Verification

Run the verification checklist for EVERY deployment. No exceptions.

```
[ ] OpenClaw gateway responds: openclaw status
[ ] Extensions loaded: check agent extensions dir
[ ] Dashboard starts: python3 server_v2.py (sovereign/partner only)
[ ] R-Awareness config valid: keywords.json parseable
[ ] R-Memory config valid: config.json parseable
[ ] Node can execute commands from orchestrator
[ ] Python scripts run without errors (test: sanitize-audit.py --help)
```

Mark each as ✅ or ❌ with error details. Report results.

## VM Deployment (Special Case)

When deploying inside a VM on an existing node:

1. Use the host node to create/start the VM
2. Install OS in VM (or use pre-built image)
3. Set up networking (NAT or bridged)
4. Install OpenClaw node inside VM
5. Pair VM node to orchestrator gateway (may need port forwarding)
6. Run standard deployment phases 2-5 inside VM

See [references/linux.md](references/linux.md) for Ubuntu VM specifics.

## Fleet Registry

After successful deployment, update `memory/fleet/nodes.json`:

```json
{
  "id": "<node-name>",
  "name": "<display-name>",
  "role": "<sovereign|partner|specialist|worker|sentinel>",
  "os": "<windows|linux|macos>",
  "status": "online",
  "deployed_at": "<ISO-8601>",
  "openclaw_version": "<version>",
  "resonantos_version": "alpha-0.1",
  "model": "<configured-model>",
  "issues": []
}
```

## Failure Handling

When a step fails:
1. Capture full error output
2. Check known issues in the OS-specific reference
3. Attempt auto-remediation if a known fix exists
4. If unresolvable: log the failure, skip this node, continue with others
5. Report all failures at the end with context for human review

## Lessons Log

After each deployment, append lessons to [references/lessons.md](references/lessons.md).
Format: `- <date>: <OS>: <what happened> → <fix/workaround>`
This accumulates institutional knowledge for future deployments.
