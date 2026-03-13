# R-Awareness — SSoT Context Injection System

**Version:** 1.0  
**Status:** Implemented & Active  
**Extension:** `~/.openclaw/agents/main/agent/extensions/r-awareness.js`

---

## What It Is

R-Awareness is an OpenClaw extension that silently injects SSoT (Single Source of Truth) documents into the AI's system prompt based on keywords detected in conversation. The AI receives project knowledge without the human needing to manually paste documents.

The AI sees injected content as part of its system prompt — not as "here is a document to read" but as knowledge it already has.

## Core Principle

> Silent success, visible errors. R-Awareness is infrastructure, not a conversational agent.

---

## How It Works

### The Flow

```
Human sends message: "Let's work on the memory system"
        ↓
before_agent_start hook fires
        ↓
R-Awareness scans message for keywords
        ↓
"memory" matches → loads L2-R-MEMORY.md from disk
        ↓
Appends document content to system prompt
        ↓
AI receives: system prompt + SSoT content + human message
Human sees: their original message only
```

### What Gets Scanned

R-Awareness scans **only `event.prompt`** (the human's message text). It does **NOT** scan `event.systemPrompt` (AGENTS.md, SOUL.md, USER.md, MEMORY.md, etc.). This is critical: bootstrap/workspace files injected by OpenClaw into the system prompt will never trigger keyword matching, even if they contain matching words.

### Keyword Scanning

**Human → AI (immediate):** Keywords in the human message trigger injection on the same turn.

**AI → Next Turn (queued):** ⚠️ **DISABLED (2026-02-15).** AI response scanning was disabled due to a feedback loop: injected SSoT content in the AI's response contained keywords that matched other documents, causing the same docs to be re-injected every turn in a loop. The system hit the max docs limit (10) on every turn regardless of relevance. Currently, only human keyword scanning is active.

### Cold Start Mode

When `coldStartOnly: true` in config, R-Awareness behaves differently on the first turn of a session:

- **Turn 1:** Skips all keyword scanning. Only loads documents listed in `coldStartDocs` (whitelist). Default: `["L1/SSOT-L1-SYSTEM-OVERVIEW.ai.md"]` — gives the AI basic system awareness without flooding context.
- **Turn 2+:** Normal keyword-matching injection resumes. Only the human's actual message text triggers keywords.

This prevents the agent from starting every session with a full load of 10 SSoT documents. Documents are loaded on-demand as the conversation naturally references them.

### Injection Mechanism

Documents are appended to the end of the system prompt inside XML tags:

```
[existing system prompt content]

<!-- R-Awareness: SSoT Context -->
<r-awareness-context>

--- L0/L0-PHILOSOPHY.md (L0) ---
[full document content]

--- L1/L1-ARCHITECTURE.md (L1) ---
[full document content]

</r-awareness-context>
<!-- End R-Awareness -->
```

Documents are sorted by level (L0 first, then L1, then L2).

---

## OpenClaw Hooks

R-Awareness uses two OpenClaw extension hooks:

| Hook | When | What R-Awareness Does |
|------|------|----------------------|
| `before_agent_start` | Before each API call | Scans human prompt for keywords and /R commands, injects matching SSoT docs into system prompt |
| `agent_end` | After AI responds | ⚠️ **DISABLED** — AI keyword scanning disabled due to feedback loop (see Keyword Scanning section) |

The `before_agent_start` handler returns `{ systemPrompt: modifiedPrompt }` to inject content, or `{ systemPrompt, message }` for /R command responses.

---

## Keywords

Keywords map trigger words to SSoT document paths. There are two sources:

### Manual Keywords (primary)

File: `~/.openclaw/workspace/r-awareness/keywords.json`

```json
{
  "resonantos": "L0/L0-PHILOSOPHY.md",
  "architecture": "L1/L1-ARCHITECTURE.md",
  "r-memory": "L2/L2-R-MEMORY.md",
  "memory": "L2/L2-R-MEMORY.md"
}
```

Format: `"keyword": "path/relative/to/ssotRoot"`. Keywords are case-insensitive. Multiple keywords can point to the same document.

**This is the file to edit when adding or changing keywords.** The AI can edit it directly via bash.

### Auto-Generated Keywords (optional)

When `autoKeywords: true` in config, R-Awareness scans the SSoT directory and generates one keyword per document from its filename:

- `L2-R-MEMORY.md` → keyword `"r-memory"`
- `System_Overview.md` → keyword `"system overview"`
- SSOT prefix is stripped: `SSOT-L2-R-MEMORY.md` → `"r-memory"`

Only L0, L1, and L2 documents get auto-keywords. L3 and L4 are excluded. Manual keywords always override auto-generated ones.

**Currently disabled** (`autoKeywords: false` in config) — all keywords are managed manually via `keywords.json`.

### Keyword Matching Rules

- Case-insensitive
- Word-boundary aware: "memory" will NOT match inside "commemorative"
- Boundaries are any non-alphanumeric character (spaces, punctuation, hyphens, start/end of text)
- One match per keyword per message (no duplicates)
- Pure code matching — no AI inference, zero token cost

---

## SSoT Document Levels

| Level | Purpose | Auto-inject via keywords | Examples |
|-------|---------|------------------------|----------|
| **L0** | Vision, mission, philosophy | ✅ Yes | Philosophy, Business Plan, World Model |
| **L1** | Architecture, core systems | ✅ Yes | System Architecture, R-Awareness spec, R-Memory spec |
| **L2** | Active projects, specs | ✅ Yes | Project specs, feature docs |
| **L3** | Drafts, work-in-progress | ❌ Manual only (`/R load`) | Draft documents |
| **L4** | Notes, ephemeral | ❌ Manual only (`/R load`) | Scratch notes |

Priority when multiple docs match: L0 > L1 > L2 (lower number = higher priority, loaded first).

---

## Limits and Eviction

### Per-Turn Limits

| Limit | Default | Config Key |
|-------|---------|-----------|
| Max documents in context | 10 | `maxDocsPerTurn` |
| Max tokens of SSoT content | 15,000 | `tokenBudget` |

When limits are exceeded, higher-priority documents (lower L-level) are loaded first. Lower-priority documents are skipped with a warning in the log.

### TTL (Time-To-Live)

Documents expire after **15 human turns** without their keyword being mentioned again. Each time a keyword fires (from human or AI), the TTL resets for that document.

- Manually loaded documents (`/R load`) never expire
- TTL is configurable via `ttlTurns` in config

### Replace, Not Duplicate

When a keyword fires for a document already in context, R-Awareness re-reads the file from disk. If the document has been updated, the new version replaces the old one. This ensures the AI always has the latest SSoT content, even mid-conversation.

Replacement respects the token budget — if the new version is too large, the old version is kept and a warning is logged.

---

## Human Commands

Prefix: `/R` (configurable via `commandPrefix`)

| Command | Action |
|---------|--------|
| `/R load <path>` | Force-load a document (path relative to ssotRoot) |
| `/R remove <path>` | Unload a document from context |
| `/R clear` | Remove all injected documents |
| `/R list` | Show loaded documents with level, tokens, and TTL age |
| `/R pause` | Disable auto-injection (keywords stop matching) |
| `/R resume` | Re-enable auto-injection |
| `/R help` | Show available commands |

Examples:
```
/R load L3/DRAFT-NEW-FEATURE.md
/R remove L2/L2-R-MEMORY.md
/R list
/R clear
```

The `/R load` command bypasses level restrictions — it can load L3 and L4 documents that would never auto-inject. Manually loaded documents don't expire via TTL.

When a `/R` command is processed, the AI receives the command response as a message (e.g., "✅ Loaded: L3/DRAFT.md (~500 tokens)").

---

## File Locations

| File | Path | Purpose |
|------|------|---------|
| Extension | `~/.openclaw/agents/main/agent/extensions/r-awareness.js` | The code |
| Config | `~/.openclaw/workspace/r-awareness/config.json` | Settings |
| Keywords | `~/.openclaw/workspace/r-awareness/keywords.json` | Keyword → document mappings |
| Log | `~/.openclaw/workspace/r-awareness/r-awareness.log` | Activity log |
| SSoT root | `/Users/augmentor/resonantos-augmentor/ssot/` | Source documents |

---

## Configuration

File: `~/.openclaw/workspace/r-awareness/config.json`

```json
{
  "enabled": true,
  "ssotRoot": "/Users/augmentor/resonantos-augmentor/ssot",
  "autoKeywords": false,
  "maxDocsPerTurn": 10,
  "tokenBudget": 15000,
  "ttlTurns": 15,
  "commandPrefix": "/R",
  "coldStartOnly": true,
  "coldStartDocs": ["L1/SSOT-L1-SYSTEM-OVERVIEW.ai.md"]
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Master on/off switch |
| `ssotRoot` | string | `""` | Absolute path to SSoT document directory |
| `autoKeywords` | boolean | `true` | Auto-generate keywords from filenames |
| `maxDocsPerTurn` | number | `10` | Maximum documents in context simultaneously |
| `tokenBudget` | number | `15000` | Maximum tokens of SSoT content |
| `ttlTurns` | number | `15` | Turns without keyword mention before eviction |
| `commandPrefix` | string | `"/R"` | Prefix for human control commands |
| `coldStartOnly` | boolean | `false` | Turn 1: load only whitelisted docs, skip keyword scan |
| `coldStartDocs` | string[] | `[]` | Docs to load on turn 1 when coldStartOnly is true |

---

## Relationship to R-Memory

R-Awareness and R-Memory are independent extensions installed side by side. They do not interfere with each other.

- **R-Memory** handles conversation compression — keeping long conversations alive by compressing old turns
- **R-Awareness** handles knowledge injection — giving the AI access to project documentation

Both use the same OpenClaw extension API but different hooks. R-Memory uses `agent_start`, `agent_end`, and `session_before_compact`. R-Awareness uses `before_agent_start` and `agent_end`.

---

## Diagnostics

### Check if working

```bash
tail -20 ~/.openclaw/workspace/r-awareness/r-awareness.log
```

Look for:
- `R-Awareness V1.0 init` — extension loaded successfully
- `Keyword manifest built` — keywords loaded (shows manual/auto counts)
- `Human keywords matched` — a keyword was detected in a message
- `Injected` — a document was loaded into context
- `Injecting into system prompt` — content was added to system prompt

### Check what's currently injected

Send `/R list` to the AI. It will show all loaded documents with their level, token count, and TTL age.

### Check keyword manifest count

```bash
grep "Keyword manifest built" ~/.openclaw/workspace/r-awareness/r-awareness.log | tail -1
```

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| No init log entry | Extension not loading | Check file is in extensions directory, restart gateway |
| `ssotRoot not configured` | Config missing ssotRoot | Set `ssotRoot` in config.json |
| Keywords matched but no injection | Token budget exceeded | Check log for budget warnings, increase `tokenBudget` |
| Too many docs injected | Auto-keywords matching broadly | Set `autoKeywords: false`, use manual keywords only |
| Doc not updating mid-conversation | Keyword not re-mentioned | Mention the keyword again to trigger replacement |
