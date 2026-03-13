# SSOT-L1-LOGICIAN — Logician Policy Engine

| Field | Value |
|-------|-------|
| ID | SSOT-L1-LOGICIAN-V2 |
| Created | 2026-02-19 |
| Updated | 2026-02-19 |
| Author | Augmentor |
| Level | L1 (Architecture) |
| Type | Truth |
| Status | Active |
| Replaces | SSOT-L1-LOGICIAN-OLD |
| Stale After | 90 days |

---

## 1. Overview

Logician is ResonantOS's deterministic policy engine. Built on Google Mangle (a Datalog extension), it provides provable, auditable policy enforcement for agent orchestration, security, and governance.

**Key principle:** Deterministic over probabilistic. No AI decides policy — rules are explicit, queryable, and provable.

## 2. Architecture

```
┌──────────────────────────────────────────────────┐
│              Logician Service Stack               │
│                                                    │
│  Shield (Python)  ──► gRPC :8080 ──► mangle-server │
│  shield-gate.js   ──►            ──► (Go binary)   │
│  data_leak_scanner──►            ──►                │
│  logician_bridge.py──►           ──► production_rules.mg
│                                                    │
│  Monitor ──► logician_monitor.sh (60s interval)    │
│           ──► status.json (health state)           │
│           ──► launchd auto-restart                 │
└──────────────────────────────────────────────────┘
```

## 3. Engine: Google Mangle

**What:** Datalog extension supporting aggregation, recursion, function calls, and type-checking.
**Source:** https://github.com/google/mangle
**Server:** https://github.com/burakemir/mangle-service (gRPC wrapper)

**Query protocol:** gRPC (proto: `mangle.proto`)
- `Query(program, query)` — evaluate query against loaded rules
- `Update(program)` — add new facts/rules at runtime

**Evaluation:** Semi-naive strategy (efficient for recursive rules).

## 4. Rule Categories (production_rules.mg)

### 4.1 Agent Registry
```prolog
agent(/main). agent(/strategist). agent(/coder). agent(/researcher).
agent(/tester). agent(/designer). agent(/creative). agent(/guardian).
agent(/archivist).
trust_level(/main, 5). trust_level(/coder, 3). trust_level(/researcher, 2).
```

### 4.2 Spawn Control
```prolog
can_spawn(/main, /coder).        # main can spawn coder
can_spawn(/main, /strategist).   # main can spawn strategist
blocked_spawn(/coder, /strategist). # coder cannot spawn strategist

# Derived rule
spawn_allowed(From, To) :- can_spawn(From, To), !blocked_spawn(From, To).
```

### 4.3 Delegation
```prolog
requires_delegation(/strategist, /code).
should_delegate(/strategist, /code, /coder).
# Query: must_delegate_to(/strategist, /code, X)? → X = /coder
```

### 4.4 Tool Permissions
```prolog
can_use_tool(/researcher, /brave_api).
can_use_tool(/coder, /exec).
can_use_tool(/coder, /git).
dangerous_tool(/exec). dangerous_tool(/solana_cli). dangerous_tool(/nft_minter).
# Derived: can_use_dangerous requires trust_level >= 3
```

### 4.5 Security Patterns
```prolog
# Sensitive data types
sensitive_type(/api_key). sensitive_type(/token). sensitive_type(/private_key).
sensitive_type(/seed_phrase). sensitive_type(/password). sensitive_type(/keypair).

# Forbidden for output
forbidden_output_type(/api_key). forbidden_output_type(/private_key).
forbidden_output_type(/seed_phrase). forbidden_output_type(/password).

# Injection detection (13 patterns)
injection_pattern("ignore previous instructions").
injection_pattern("DAN mode").
injection_pattern("jailbreak").
# ... 10 more patterns

# Destructive command detection (10 patterns)
destructive_pattern("rm -rf"). destructive_pattern("drop table").
destructive_pattern("format c:"). destructive_pattern("mkfs").
# ... 6 more patterns
```

### 4.6 File Protection
```prolog
protected_path("/Users/augmentor/.openclaw/openclaw.json").
protected_path("/Users/augmentor/.config/solana/id.json").
protected_path("/Users/augmentor/.openclaw/agents/main/agent/auth-profiles.json").
protected_path("/Users/augmentor/.ssh/").
protected_path("ssot/private/").

safe_path("/Users/augmentor/.openclaw/workspace/").
safe_path("/Users/augmentor/resonantos-augmentor/").
safe_path("/Users/augmentor/resonantos-alpha/").

# Derived: ai_writable(P) :- safe_path(P), !protected_path(P).
```

### 4.7 Blockchain Safety
```prolog
# Mainnet requires human approval for: transfer, mint, deploy, close
mainnet_approval_required(/transfer).
mainnet_approval_required(/mint).

# Token caps
token_yearly_cap(/rct, 10000).
token_yearly_cap(/res, 1000000).
```

### 4.8 Cost Policy
```prolog
model_tier(/opus, /expensive).
model_tier(/sonnet, /moderate).
model_tier(/haiku, /cheap).
preferred_model(/heartbeat, /haiku).
preferred_model(/compression, /haiku).
preferred_model(/reasoning, /opus).
```

### 4.9 Push Enforcement
```prolog
push_requires_evidence(/resonantos_augmentor).
push_requires_evidence(/resonantos_alpha).
```

**Total facts:** 213+

## 5. Access Methods

### 5.1 Python Bridge (`logician_bridge.py`)
```python
from logician_bridge import LogicianShieldBridge

bridge = LogicianShieldBridge()
result = bridge.verify_spawn("coder", "strategist")
# result.allowed → False
# result.proof → "blocked_spawn(/coder, /strategist)"
# result.blocking_rule → "blocked_spawn"
```

**Features:**
- 500ms timeout per query
- LRU cache (60s TTL)
- Fallback mode when Logician offline (configurable: allow or deny)
- Telemetry (query count, latency, fallback rate)

### 5.2 Direct gRPC (via grpcurl)
```bash
~/go/bin/grpcurl -plaintext \
  -import-path proto -proto mangle.proto \
  -d '{"query": "spawn_allowed(/main, /coder)", "program": ""}' \
  localhost:8080 mangle.Mangle.Query
```

### 5.3 Data Leak Scanner Integration
```python
# In data_leak_scanner.py
answer = query_logician('safe_path("/Users/augmentor/resonantos-augmentor/")')
# Returns result or None if unreachable
```

## 6. Monitoring

### 6.1 Health Monitor (`logician_monitor.sh`)
- **Schedule:** Every 60 seconds (launchd: `com.resonantos.logician-monitor`)
- **Checks:** TCP port 8080 reachable + gRPC test query (`agent(/main)`)
- **Auto-restart:** `launchctl kickstart` if service down
- **State file:** `logician/monitor/status.json`
- **Log:** `logician/logs/monitor.log`

### 6.2 Dashboard
- **Endpoint:** `GET /api/logician/status` — reads `status.json`
- **UI:** Indicator in nav bar (green=healthy, yellow=degraded, red=down)

## 7. Deployment

| Component | Path |
|-----------|------|
| Binary | `~/resonantos-augmentor/logician/poc/mangle-service/mangle-server` |
| Rules | `~/resonantos-augmentor/logician/poc/production_rules.mg` |
| Proto | `~/resonantos-augmentor/logician/poc/mangle-service/proto/mangle.proto` |
| Python bridge | `~/resonantos-augmentor/shield/logician_bridge.py` |
| Monitor script | `~/resonantos-augmentor/logician/monitor/logician_monitor.sh` |
| Monitor status | `~/resonantos-augmentor/logician/monitor/status.json` |
| Logs | `~/resonantos-augmentor/logician/logs/` |

### launchd Services
| Service | Plist | Purpose |
|---------|-------|---------|
| `com.resonantos.logician` | `~/Library/LaunchAgents/` | Mangle gRPC server on :8080 |
| `com.resonantos.logician-monitor` | `~/Library/LaunchAgents/` | Health monitor (60s) |

## 8. Query Performance

| Metric | Value |
|--------|-------|
| Average latency | ~9ms |
| Startup (load 213 facts) | ~50µs |
| Rule compilation | ~60µs |
| Bridge fallback rate | 0% (when service healthy) |

## 9. Design Principles

1. **Provable** — every policy decision has an auditable proof trace
2. **Deterministic** — same inputs always produce same outputs
3. **Fail-closed for security** — if Logician unreachable, deny by default (in push context)
4. **Extensible** — new rules added to `production_rules.mg`, server reloaded
5. **Fast** — gRPC queries under 10ms; no bottleneck on tool execution
6. **Decoupled** — Shield consumes Logician; they're independent services
7. **Self-monitored** — health check every 60s; auto-restart on failure

## 10. Adding New Rules

1. Edit `production_rules.mg`
2. Restart Logician: `launchctl stop com.resonantos.logician && launchctl start com.resonantos.logician`
3. Verify: `~/go/bin/grpcurl -plaintext -import-path proto -proto mangle.proto -d '{"query": "<new_query>", "program": ""}' localhost:8080 mangle.Mangle.Query`

Rules are pure Datalog — facts and derived rules. No procedural logic.
