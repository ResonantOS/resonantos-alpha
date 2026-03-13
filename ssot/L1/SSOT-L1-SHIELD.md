# SSOT-L1-SHIELD — Shield Security System

| Field | Value |
|-------|-------|
| ID | SSOT-L1-SHIELD-V2 |
| Created | 2026-02-19 |
| Updated | 2026-02-19 |
| Author | Augmentor |
| Level | L1 (Architecture) |
| Type | Truth |
| Status | Active |
| Replaces | SSOT-L1-SHIELD-OLD |
| Stale After | 90 days |

---

## 1. Overview

Shield is ResonantOS's security enforcement layer. It operates as a multi-component system that:

1. **Gates git pushes** — blocks pushes containing leaked credentials, unverified code, or Logician-denied repos
2. **Gates tool execution** — intercepts dangerous shell commands before they run (via OpenClaw extension hook)
3. **Protects files** — locks critical files (cross-platform: macOS `chflags`, Linux `chattr`, POSIX `chmod`)
4. **Scans for data leaks** — regex-based detection of credentials, private content, business secrets
5. **Self-heals** — monitors its own enforcement hooks and restores them if tampered with

Shield is **deterministic** — no AI involved in security decisions. Pure regex, pattern matching, and Logician queries.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ENFORCEMENT CHAIN                     │
│                                                          │
│  Tool Call ──► shield-gate.js ──► ALLOW / BLOCK          │
│                    │                                     │
│  Git Push ──► pre-push hook                              │
│                 ├── data_leak_scanner.py (scan diff)     │
│                 ├── Logician query (safe_path + git)     │
│                 └── verification_gate.py (test evidence) │
│                                                          │
│  Files ──► file_guard.py ──► chflags/chattr/chmod        │
│                                                          │
│  Hooks ──► hook_guardian.sh ──► self-healing monitor      │
│                                                          │
│  Lock State ──► shield_lock.py ──► password-protected     │
└─────────────────────────────────────────────────────────┘
         │
         ▼
    Logician (gRPC :8080) — policy queries
```

## 3. Components

### 3.1 Shield Gate Extension (`shield-gate.js`)

**Type:** OpenClaw extension (before_tool_call hook)
**Location:** `~/.openclaw/agents/main/agent/extensions/shield-gate.js`
**Purpose:** Intercept `exec` tool calls before execution

**Detection layers:**
1. **Destructive commands** — `rm -rf`, `DROP TABLE`, `mkfs`, `dd of=/dev/*`, fork bombs, `shutdown`, `reboot`
2. **Protected file writes** — Any write to `.openclaw/openclaw.json`, `.config/solana/id.json`, `auth-profiles.json`, `.ssh/`, `.env`
3. **Safe command fast-path** — Whitelisted prefixes: `ls`, `cat`, `grep`, `git status/log/diff`, `curl`, `echo`, etc.
4. **Pipe/redirect detection** — Commands containing `|` or `>` skip safe-prefix fast-path

**Fail mode:** OPEN (extension error → allow command; opposite of git push which is fail-closed)
**Test coverage:** 18/18 test cases passing

### 3.2 Data Leak Scanner (`data_leak_scanner.py`)

**Location:** `~/resonantos-augmentor/shield/data_leak_scanner.py`
**Purpose:** Scan text, files, and git diffs for credential/secret leaks

**Detection categories:**

| Category | Patterns | Blocking |
|----------|----------|----------|
| Credentials | Anthropic (`sk-ant-*`), OpenAI (`sk-proj-*`), GitHub (`ghp_*`, `gho_*`), Slack (`xox*-*`), PEM keys, Solana keypairs, seed phrases, generic secrets | Yes |
| Private content | MEMORY.md markers, USER.md markers, SOUL.md markers, auth-profiles.json, Cosmodestiny | Yes |
| Business-sensitive | Internal financial docs, strategic plans, pitch materials | Yes |
| Warn-only | Augmentatism Manifesto (public philosophy) | No (logged) |
| Forbidden files | MEMORY.md, USER.md, `.env*`, `id.json`, `.ssh/id_*` (not .pub), `daily_claims.json`, `onboarding.json` | Yes |

**CLI commands:**
```bash
python3 data_leak_scanner.py check <text>          # scan text
python3 data_leak_scanner.py check-file <path>     # scan file
python3 data_leak_scanner.py check-diff [repo]     # scan staged diff
python3 data_leak_scanner.py pre-push [repo]       # full gate
python3 data_leak_scanner.py install-hook [repo]    # install hook
python3 data_leak_scanner.py logician-status        # check Logician
```

**Logician integration:**
- Queries `safe_path("<repo>")` — is this repo approved for push?
- Queries `can_use_tool(/main, /git)` — is main agent allowed git?
- Fail-closed: if Logician unreachable, push denied

**Exit codes:** 0=clean, 1=leak detected, 2=Logician denied, 3=error

### 3.3 Verification Gate (`verification_gate.py`)

**Location:** `~/resonantos-augmentor/shield/verification_gate.py`
**Purpose:** Block pushes of code files without test evidence

**Rules:**
- Code extensions tracked: `.py`, `.js`, `.ts`, `.html`, `.css`, `.mg`, `.rs`
- Non-code files (`.md`, `.json`, `.txt`, etc.) exempt
- Every code file requires a verification entry with method + result
- Valid methods: `curl`, `browser`, `unit`, `manual`, `script`, `code-review`, `untestable`
- Stale threshold: 24 hours (warns but allows)
- State persisted in `shield/verifications.json`

**CLI:**
```bash
python3 verification_gate.py add <file> <method> <result>
python3 verification_gate.py check
python3 verification_gate.py status
python3 verification_gate.py clear
```

### 3.4 File Guard (`file_guard.py`)

**Location:** `~/resonantos-augmentor/shield/file_guard.py` (also in `~/resonantos-alpha/shield/`)
**Purpose:** Lock/unlock critical files to prevent accidental modification

**Cross-platform support:**
- macOS: `chflags uchg/nouchg`
- Linux: `chattr +i/-i` (with `chmod` fallback)
- Generic: POSIX `chmod a-w/u+w`

**Guard manifest:** Groups of files by category (agent config, extensions, identity, dashboard, shield, ssot, github hooks)

**Git hook guard:** Can inject pre-push hooks that block pushes entirely (separate from data_leak_scanner hook)

### 3.5 Hook Guardian (`hook_guardian.sh`)

**Location:** `~/resonantos-augmentor/shield/hook_guardian.sh`
**Purpose:** Monitor pre-push hooks; restore if deleted or tampered

**Behavior:**
- Runs periodically (launchd or cron)
- Checks if pre-push hook exists and contains Shield markers
- Restores from template if missing
- Logs all events to `shield/logs/hook_guardian.log`

### 3.6 Shield Lock (`shield_lock.py`)

**Location:** `~/resonantos-augmentor/shield/shield_lock.py`
**Purpose:** Password-protected lock state for Shield enforcement

**Rules:**
- AI cannot disable Shield — password required (human-only)
- Lock state persisted to disk
- SHA-256 hash-based verification (stdlib only, no bcrypt)

## 4. Pre-Push Hook Chain

The `.git/hooks/pre-push` script executes in order:

```
1. Shield lock check (is Shield enabled?)
2. Data leak scanner (scan diff for credentials/secrets)
3. Logician approval (safe_path + can_use_tool queries)
4. Verification gate (test evidence for code files)
```

Any step failing → push blocked (exit 1).

## 5. Logician Integration Points

Shield queries Logician for:

| Query | Purpose | Used By |
|-------|---------|---------|
| `safe_path("<repo>")` | Is this repo approved for git push? | data_leak_scanner |
| `can_use_tool(/main, /git)` | Is main agent allowed to use git? | data_leak_scanner |
| `protected_path("<path>")` | Is this path write-protected? | file_guard, shield-gate |
| `forbidden_output_type(<type>)` | Should this data type be blocked from output? | data_leak_scanner |

## 6. Deployment

| Component | Location | Managed By |
|-----------|----------|------------|
| shield-gate.js | OpenClaw extensions dir | OpenClaw (loaded at agent start) |
| data_leak_scanner.py | resonantos-augmentor/shield/ | Pre-push hook |
| verification_gate.py | resonantos-augmentor/shield/ | Pre-push hook |
| file_guard.py | resonantos-augmentor/shield/ | CLI / dashboard API |
| hook_guardian.sh | resonantos-augmentor/shield/ | launchd |
| shield_lock.py | resonantos-augmentor/shield/ | CLI (human-only) |

**Hooks installed on:**
- `~/resonantos-augmentor/.git/hooks/pre-push`
- `~/resonantos-alpha/.git/hooks/pre-push`

## 7. Monitoring

- **Dashboard endpoint:** `/api/shield/status` — returns Shield lock state
- **Logician endpoint:** `/api/logician/status` — returns Logician health from monitor
- **Dashboard UI:** Shield indicator in nav bar + Logician indicator
- **Log files:** `shield/logs/shield-gate.log`, `shield/logs/hook_guardian.log`, `logician/logs/monitor.log`

## 8. Design Principles

1. **Deterministic** — no AI in the security loop; pure regex + Logician rules
2. **Fail-closed for git** — if Logician unreachable, push denied
3. **Fail-open for exec** — extension errors don't block AI from working
4. **Self-healing** — hooks auto-restored if tampered
5. **Human-only unlock** — password required to disable Shield
6. **No secrets in output** — credentials truncated in logs (`[match[:20]]...`)
7. **Cross-platform** — file locking works on macOS and Linux
