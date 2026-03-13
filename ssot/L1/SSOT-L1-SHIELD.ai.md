# Shield Security System [AI-OPTIMIZED]
<!-- src: SSOT-L1-SHIELD.md | ~600 tokens -->

## Purpose
Multi-component deterministic security layer. No AI in security decisions.

## Enforcement Chain
```
Tool Call → shield-gate.js (before_tool_call) → ALLOW/BLOCK
Git Push → pre-push hook:
  1. data_leak_scanner.py (credential/secret scan)
  2. Logician gRPC (safe_path + can_use_tool)
  3. verification_gate.py (test evidence for code files)
Files → file_guard.py (chflags/chattr/chmod)
Hooks → hook_guardian.sh (self-healing monitor)
Lock → shield_lock.py (password-protected, human-only)
```

## Components

| Component | Location | Purpose | Fail Mode |
|-----------|----------|---------|-----------|
| shield-gate.js | OpenClaw extension | Block destructive exec commands | OPEN |
| data_leak_scanner.py | shield/ | Scan diffs for credentials/secrets | CLOSED |
| verification_gate.py | shield/ | Require test evidence for code | CLOSED |
| file_guard.py | shield/ | Lock/unlock critical files | N/A |
| hook_guardian.sh | shield/ | Restore tampered hooks | N/A |
| shield_lock.py | shield/ | Password gate for Shield disable | N/A |

## Detection Categories
- **Credentials**: Anthropic/OpenAI/GitHub/Slack keys, PEM, Solana keypairs, seed phrases
- **Private content**: MEMORY.md, USER.md, SOUL.md markers, auth-profiles
- **Business**: Internal financial docs, strategic plans, pitch materials
- **Destructive**: rm -rf, DROP TABLE, mkfs, dd, fork bombs
- **Protected paths**: openclaw.json, solana/id.json, auth-profiles.json, .ssh/, ssot/private/

## Logician Queries
| Query | Purpose |
|-------|---------|
| `safe_path("<repo>")` | Repo approved for push? |
| `can_use_tool(/main, /git)` | Agent allowed git? |
| `protected_path("<path>")` | Path write-protected? |
| `forbidden_output_type(<type>)` | Data type blocked? |

## Design: Deterministic, fail-closed (git), fail-open (exec), self-healing hooks, human-only unlock, cross-platform (macOS+Linux).
