[AI-OPTIMIZED] ~850 tokens | src: SSOT-L1-R-AWARENESS.md

# R-Awareness — SSoT Context Injection

**V1.0 | Active | Extension:** `~/.openclaw/agents/main/agent/extensions/r-awareness.js`

## What

Silent OpenClaw extension: injects SSoT docs into system prompt based on keyword detection in human messages. AI sees injected content as native knowledge. Human chat unchanged.

> Silent success, visible errors. Infrastructure, not agent.

## Flow

```
Human msg → before_agent_start hook → keyword scan on event.prompt only
→ load matching docs from disk → append to system prompt in XML tags
```

**Critical:** Scans ONLY `event.prompt` (human message text). Does NOT scan `event.systemPrompt` (AGENTS.md, SOUL.md, USER.md, MEMORY.md, workspace files). Bootstrap/workspace content never triggers keywords.

Injection format (sorted L0→L1→L2):
```
<!-- R-Awareness: SSoT Context -->
<r-awareness-context>
--- L0/doc.md (L0) ---
[content]
</r-awareness-context>
```

## Cold Start Mode

When `coldStartOnly: true`:
- **Turn 1:** Skip all keyword scanning. Load only `coldStartDocs` whitelist (default: system overview). Agent starts clean.
- **Turn 2+:** Normal keyword-matching resumes. Only human message text triggers keywords.

Prevents session flooding — docs load on-demand as conversation references them.

## Keyword Scanning

**Human→AI (active):** Keywords in human msg trigger same-turn injection.

**AI→Next Turn: ⚠️ DISABLED (2026-02-15).** Feedback loop: injected SSoT content contained keywords → re-injected every turn → hit max docs (10) regardless of relevance. Only human scanning active.

## Hooks

| Hook | When | Action |
|------|------|--------|
| `before_agent_start` | Before API call | Scan keywords + /R cmds, inject SSoTs. Returns `{systemPrompt}` or `{systemPrompt, message}` |
| `agent_end` | After response | ⚠️ DISABLED — feedback loop |

## Keywords

### Manual (primary) — `~/.openclaw/workspace/r-awareness/keywords.json`
```json
{ "resonantos": "L0/L0-PHILOSOPHY.md", "memory": "L2/L2-R-MEMORY.md" }
```
Case-insensitive. Multiple keywords → same doc OK. **Edit this file to change keywords.**

### Auto-Generated (optional, currently disabled)
When `autoKeywords: true`: scans SSoT dir, generates keyword per filename. SSOT prefix stripped. L0-L2 only. Manual overrides auto.

### Matching Rules
- Case-insensitive, word-boundary aware ("memory" won't match "commemorative")
- One match per keyword per msg, no duplicates
- Pure code — zero token cost

## SSoT Levels

| Level | Auto-inject | Purpose |
|-------|-------------|---------|
| L0 | ✅ | Vision/philosophy |
| L1 | ✅ | Architecture/core |
| L2 | ✅ | Active projects |
| L3 | ❌ manual `/R load` | Drafts/WIP |
| L4 | ❌ manual `/R load` | Notes/ephemeral |

Priority: L0 > L1 > L2

## Limits & Eviction

| Limit | Default | Config Key |
|-------|---------|-----------|
| Max docs | 10 | `maxDocsPerTurn` |
| Max tokens | 15,000 | `tokenBudget` |
| TTL | 15 turns | `ttlTurns` |

Budget exceeded → higher-priority first, lower skipped. TTL resets on keyword re-mention. `/R load` docs never expire. Re-mentioned doc re-reads from disk.

## /R Commands

| Cmd | Action |
|-----|--------|
| `/R load <path>` | Force-load (bypasses level restrictions, no TTL) |
| `/R remove <path>` | Unload doc |
| `/R clear` | Remove all |
| `/R list` | Show loaded (level, tokens, TTL age) |
| `/R pause/resume` | Disable/enable auto-injection |

## Config — `~/.openclaw/workspace/r-awareness/config.json`

```json
{ "enabled": true, "ssotRoot": "/Users/augmentor/resonantos-augmentor/ssot",
  "autoKeywords": false, "maxDocsPerTurn": 10, "tokenBudget": 15000,
  "ttlTurns": 15, "commandPrefix": "/R",
  "coldStartOnly": true, "coldStartDocs": ["L1/SSOT-L1-SYSTEM-OVERVIEW.ai.md"] }
```

| Key | Type | Default | Desc |
|-----|------|---------|------|
| `enabled` | bool | `true` | Master switch |
| `ssotRoot` | string | `""` | Abs path to SSoT dir |
| `autoKeywords` | bool | `true` | Auto-gen keywords from filenames |
| `maxDocsPerTurn` | number | `10` | Max simultaneous docs |
| `tokenBudget` | number | `15000` | Max SSoT tokens |
| `ttlTurns` | number | `15` | Turns before eviction |
| `commandPrefix` | string | `"/R"` | Command prefix |
| `coldStartOnly` | bool | `false` | Turn 1: whitelist only, no keyword scan |
| `coldStartDocs` | string[] | `[]` | Docs to load on cold start turn 1 |

## Files

| File | Path |
|------|------|
| Extension | `~/.openclaw/agents/main/agent/extensions/r-awareness.js` |
| Config | `~/.openclaw/workspace/r-awareness/config.json` |
| Keywords | `~/.openclaw/workspace/r-awareness/keywords.json` |
| Log | `~/.openclaw/workspace/r-awareness/r-awareness.log` |
| SSoT root | `/Users/augmentor/resonantos-augmentor/ssot/` |

## Relationship to R-Memory

Independent. R-Awareness = knowledge injection. R-Memory = conversation compression. Different hooks.

## Diagnostics

```bash
tail -20 ~/.openclaw/workspace/r-awareness/r-awareness.log
```

| Symptom | Fix |
|---------|-----|
| No init log | Check extensions dir, restart gateway |
| Keywords match, no injection | Check token budget in log |
| Too many docs | `autoKeywords: false`, use manual |
| Doc not updating | Re-mention keyword |
