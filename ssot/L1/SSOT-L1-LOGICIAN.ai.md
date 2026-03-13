# Logician Policy Engine [AI-OPTIMIZED]
<!-- src: SSOT-L1-LOGICIAN.md | ~500 tokens -->

## Purpose
Deterministic policy engine on Google Mangle (Datalog). Provable, auditable decisions.

## Stack
```
Shield/scanner/gate → gRPC :8080 → mangle-server (Go) → production_rules.mg (213+ facts)
```

## Rule Categories

| Category | Examples | Count |
|----------|---------|-------|
| Agent registry | agent(/main), trust_level(/main,5) | 9 agents |
| Spawn control | can_spawn(/main,/coder), blocked_spawn(/coder,/strategist) | Derived: spawn_allowed() |
| Delegation | must_delegate_to(/strategist,/code,/coder) | Task routing |
| Tool permissions | can_use_tool(/coder,/exec), dangerous_tool(/solana_cli) | 13 tools |
| Security patterns | injection_pattern(13), destructive_pattern(10) | Detection |
| Sensitive data | forbidden_output_type(/api_key,/private_key,/seed_phrase,/password) | Output gate |
| File protection | protected_path(openclaw.json, solana/id.json, .ssh/, ssot/private/) | Write gate |
| Blockchain safety | mainnet_approval_required(/transfer,/mint); token caps | Safety |
| Cost policy | model_tier(/opus,/expensive); preferred_model(/compression,/haiku) | Budget |
| Push enforcement | push_requires_evidence(/resonantos_augmentor) | CI gate |

## Access
- **Python bridge**: `LogicianShieldBridge().verify_spawn("coder","strategist")` → .allowed, .proof
- **gRPC direct**: `grpcurl -plaintext -d '{"query":"...", "program":""}' localhost:8080 mangle.Mangle.Query`
- **Scanner**: `query_logician('safe_path("...")')` → answer or None

## Monitoring
- **logician_monitor.sh**: 60s TCP+gRPC check; auto-restart via launchctl
- **Dashboard**: `/api/logician/status` → green/yellow/red indicator
- **Perf**: ~9ms avg latency, ~50µs startup

## Services
| Plist | Purpose |
|-------|---------|
| com.resonantos.logician | Mangle gRPC :8080 |
| com.resonantos.logician-monitor | Health check (60s) |

## Design: Provable, deterministic, fail-closed (security), <10ms, self-monitored, extensible via .mg rules.
