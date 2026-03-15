# SSOT-L1-LOGICIAN — Logician Policy Engine

| Field | Value |
|-------|-------|
| ID | SSOT-L1-LOGICIAN-V3 |
| Created | 2026-02-19 |
| Updated | 2026-03-15 |
| Author | Augmentor |
| Level | L1 (Architecture) |
| Type | Truth |
| Status | Active |
| Replaces | SSOT-L1-LOGICIAN-V2 |
| Stale After | 90 days |

---

## 1. Overview

Logician is ResonantOS's deterministic policy engine. Built on Google Mangle (a Datalog extension), it provides provable, auditable policy enforcement for agent orchestration, security, and governance.

**Key principle:** Deterministic over probabilistic. No AI decides policy — rules are explicit, queryable, and provable.

## 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                Logician Service Stack                     │
│                                                          │
│  Shield (Python)  ──► logician-proxy ──► mangle-server   │
│  shield-gate.js   ──► (Node, :8081)  ──► (Go, Unix sock) │
│  data_leak_scanner──►                ──►                  │
│  logician_bridge.py──►               ──► production_rules.mg
│                                                          │
│  Dashboard ──► /api/logician/rules (parses production_rules.mg)
│            ──► /api/logician/status (reads status.json)  │
│            ──► /policy-graph (visual rule browser)        │
│                                                          │
│  Monitor ──► logician_monitor.sh (60s interval)          │
│           ──► status.json (health state)                 │
│           ──► launchd auto-restart                       │
└──────────────────────────────────────────────────────────┘
```

**Connection path:** Consumers → logician-proxy (HTTP :8081) → mangle-server (Unix socket `/tmp/mangle.sock`) → production_rules.mg

## 3. Engine: Google Mangle

**What:** Datalog extension supporting aggregation, recursion, function calls, and type-checking.
**Source:** https://github.com/google/mangle
**Server:** https://github.com/burakemir/mangle-service (gRPC wrapper)

**Query protocol:** gRPC over Unix socket (`/tmp/mangle.sock`)
- `Query(program, query)` — evaluate query against loaded rules
- `Update(program)` — add new facts/rules at runtime

**Evaluation:** Semi-naive strategy (efficient for recursive rules).

## 4. Rule Source: production_rules.mg

**Single source file:** `logician/poc/production_rules.mg` (393 lines, 238 facts, 10 derived rules)

This is the ONLY file loaded by mangle-server (via `-source` flag in launchd plist). All policy enforcement flows through this file.

### 4.1 Agent Registry (10 agents)
```prolog
agent(/main).          # trust_level 5
agent(/researcher).    # trust_level 4
agent(/voice).         # trust_level 4
agent(/creative).      # trust_level 4
agent(/dao).           # trust_level 3
agent(/deputy).        # trust_level 3
agent(/website).       # trust_level 3
agent(/acupuncturist). # trust_level 2
agent(/blindspot).     # trust_level 2
agent(/setup).         # trust_level 2
```

**Agent categories:**
- Stateful (persistent memory): main, deputy, voice, setup, website, dao
- Tool (narrow function): acupuncturist, blindspot
- Task (spawned on demand): researcher, creative

**Note:** Codex CLI is NOT an agent — it's an external process (gpt-5.4). The former `coder` agent was removed 2026-03-11.

### 4.2 Spawn Control (23 facts, 1 rule)
```prolog
can_spawn(/main, /researcher).
can_spawn(/main, /creative).
can_spawn(/deputy, /researcher).
# ... 15 can_spawn rules covering cross-agent permissions

# Derived rule
spawn_allowed(From, To) :- can_spawn(From, To), !blocked_spawn(From, To).
```

### 4.3 Delegation Rules (20 facts, 1 rule)
```prolog
requires_delegation(/main, /code).
should_delegate(/main, /code, /codex_cli).
```

### 4.4 Tool Permissions (64 facts, 1 rule)
```prolog
can_use_tool(/researcher, /brave_api).
can_use_tool(/deputy, /brave_api).
can_use_tool(/deputy, /sessions_spawn).
dangerous_tool(/exec). dangerous_tool(/solana_cli). dangerous_tool(/nft_minter).
# Derived: can_use_dangerous requires trust_level >= 3
```

### 4.5 Sensitive Data & Forbidden Output (23 facts)
```prolog
sensitive_type(/api_key). sensitive_type(/token). sensitive_type(/private_key).
sensitive_type(/seed_phrase). sensitive_type(/password). sensitive_type(/keypair).
forbidden_output_type(/api_key). forbidden_output_type(/private_key).
forbidden_output_type(/seed_phrase). forbidden_output_type(/password).
```

### 4.6 Injection Detection (13 facts)
```prolog
injection_pattern("ignore previous instructions").
injection_pattern("DAN mode").
injection_pattern("jailbreak").
# ... 10 more patterns
```

### 4.7 Destructive Patterns (11 facts)
```prolog
destructive_pattern("rm -rf"). destructive_pattern("drop table").
destructive_pattern("format c:"). destructive_pattern("mkfs").
# ... 7 more patterns
```

### 4.8 Blockchain Safety (11 facts)
```prolog
mainnet_approval_required(/transfer).
mainnet_approval_required(/mint).
token_yearly_cap(/rct, 10000).
token_yearly_cap(/res, 1000000).
```

### 4.9 File Protection (7 facts, 1 rule)
```prolog
protected_path("/Users/augmentor/.openclaw/openclaw.json").
protected_path("/Users/augmentor/.config/solana/id.json").
safe_path("/Users/augmentor/.openclaw/workspace/").
safe_path("/Users/augmentor/resonantos-augmentor/").
# Derived: ai_writable(P) :- safe_path(P), !protected_path(P).
```

### 4.10 Cost Policy (13 facts)
```prolog
model_tier(/opus, /expensive).
model_tier(/sonnet, /moderate).
model_tier(/haiku, /cheap).
preferred_model(/heartbeat, /haiku).
preferred_model(/compression, /haiku).
preferred_model(/reasoning, /opus).
```

### 4.11 Verification Gate (26 facts, 6 rules)
```prolog
push_requires_evidence(/resonantos_augmentor).
push_requires_evidence(/resonantos_alpha).
# 6 derived rules for verification enforcement
```

### 4.12 Gateway Lifecycle Rules (7 facts)
Gateway state management rules for service health and restart behavior.

## 5. Section Summary

| Section | Facts | Rules | Description |
|---------|-------|-------|-------------|
| Agent Registry | 20 | 0 | Agent definitions + trust levels |
| Spawn Rules | 23 | 1 | Cross-agent spawn permissions |
| Delegation Rules | 20 | 1 | Code delegation requirements |
| Tool Permissions | 64 | 1 | Per-agent tool access |
| Sensitive Data | 23 | 0 | Forbidden output types |
| Injection Detection | 13 | 0 | Prompt injection patterns |
| Destructive Patterns | 11 | 0 | Dangerous command patterns |
| Blockchain Safety | 11 | 0 | Mainnet approval + token caps |
| File Protection | 7 | 1 | Path-based write control |
| Cost Policy | 13 | 0 | Model tier preferences |
| Verification Gate | 26 | 6 | Push evidence requirements |
| Gateway Lifecycle | 7 | 0 | Service state management |
| **Total** | **238** | **10** | **12 sections** |

## 6. Access Methods

### 6.1 Logician Proxy (HTTP, primary)
```bash
curl -s http://localhost:8081/query -d '{"query": "agent(/main)."}'
```
Node.js proxy at `logician-proxy/proxy.js` translates HTTP to gRPC over Unix socket.

### 6.2 Python Bridge (`logician_bridge.py`)
```python
from logician_bridge import LogicianShieldBridge

bridge = LogicianShieldBridge()
result = bridge.verify_spawn("coder", "strategist")
# result.allowed → False
# result.proof → "blocked_spawn(/coder, /strategist)"
```

**Features:**
- 500ms timeout per query
- LRU cache (60s TTL)
- Fallback mode when Logician offline (configurable: allow or deny)
- Telemetry (query count, latency, fallback rate)

### 6.3 Direct gRPC (via grpcurl, Unix socket)
```bash
~/go/bin/grpcurl -plaintext -unix /tmp/mangle.sock \
  -import-path proto -proto mangle.proto \
  -d '{"query": "spawn_allowed(/main, /researcher)", "program": ""}' \
  mangle.Mangle.Query
```

## 7. Dashboard Integration

### 7.1 Policy Graph (`/policy-graph`)
Visual n8n-style rule browser showing categories, fact/rule counts, and enforcement status.

### 7.2 API Endpoint (`/api/logician/rules`)
Parses `production_rules.mg` directly (since v0.5.1), extracting sections via `# ===` delimiters. Returns categories with fact/rule counts. Previously read from 16 separate `logician/rules/*.mg` files (now deprecated — those files may be stale).

### 7.3 Status (`/api/logician/status`)
Reads `logician/monitor/status.json` for service health.

## 8. Monitoring

### 8.1 Health Monitor (`logician_monitor.sh`)
- **Schedule:** Every 60 seconds (launchd: `com.resonantos.logician-monitor`)
- **Checks:** Unix socket reachable + gRPC test query (`agent(/main)`)
- **Auto-restart:** `launchctl kickstart` if service down
- **State file:** `logician/monitor/status.json`
- **Log:** `logician/logs/monitor.log`

## 9. Deployment

| Component | Path |
|-----------|------|
| Binary | `logician/poc/mangle-service/mangle-server` |
| Rules | `logician/poc/production_rules.mg` |
| Proto | `logician/poc/mangle-service/proto/mangle.proto` |
| Proxy | `logician-proxy/proxy.js` |
| Python bridge | `shield/logician_bridge.py` |
| Monitor script | `logician/monitor/logician_monitor.sh` |
| Monitor status | `logician/monitor/status.json` |
| Logs | `logician/logs/` |

### launchd Services
| Service | Plist | Purpose |
|---------|-------|---------|
| `com.resonantos.logician` | `~/Library/LaunchAgents/` | Mangle server on Unix socket `/tmp/mangle.sock` |
| `com.resonantos.logician-proxy` | `~/Library/LaunchAgents/` | HTTP proxy on :8081 |
| `com.resonantos.logician-monitor` | `~/Library/LaunchAgents/` | Health monitor (60s) |

## 10. Query Performance

| Metric | Value |
|--------|-------|
| Average latency | ~9ms |
| Startup (load 238 facts) | ~50µs |
| Rule compilation | ~60µs |
| Bridge fallback rate | 0% (when service healthy) |

## 11. Design Principles

1. **Provable** — every policy decision has an auditable proof trace
2. **Deterministic** — same inputs always produce same outputs
3. **Fail-closed for security** — if Logician unreachable, deny by default
4. **Single source** — one file (`production_rules.mg`), one server, one truth
5. **Fast** — gRPC queries under 10ms; no bottleneck on tool execution
6. **Decoupled** — Shield consumes Logician; they're independent services
7. **Self-monitored** — health check every 60s; auto-restart on failure

## 12. Adding New Rules

1. Edit `production_rules.mg`
2. Restart Logician: `launchctl stop com.resonantos.logician && launchctl start com.resonantos.logician`
3. Verify: query via proxy or grpcurl
4. Dashboard will reflect changes immediately (parses file on each request)

Rules are pure Datalog — facts and derived rules. No procedural logic.
