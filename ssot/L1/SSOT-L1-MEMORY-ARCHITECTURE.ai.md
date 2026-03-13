[AI-OPTIMIZED] ~130 tokens | src: SSOT-L1-MEMORY-ARCHITECTURE.md

| Field | Value |
|-------|-------|
| Level | L1 | Status | Active | Updated | 2026-03-07 |

## Three Memory Systems

| System | Purpose | Storage | Access |
|--------|---------|---------|--------|
| R-Memory | Conversation compression/context management | In-context | Automatic |
| Memory Log | Long-term decisions/insights/sessions | `memory/shared-log/YYYY-MM-DD.md` | Read by archivist |
| Knowledge Base (RAG) | Semantic vector search per-agent | `~/.openclaw/memory/{agent}.sqlite` | RAG queries |

## R-Memory
**Status:** Temporarily disabled (2026-03-06) — incompatible with latest OpenClaw. Under investigation.
**Function:** Compresses old conversation blocks on context fill. Lossy compression. FIFO eviction.
**Location:** `~/.openclaw/extensions/r-memory.js`

## Memory Log
**Format:** YYYY-MM-DD.md with LOG ENTRY + MEMORY LOG ENTRY sections (strategic view + fine-tuning dataset pairs)
**Location:** `~/.openclaw/workspace/memory/shared-log/`
**Created by:** Memory Archivist cron (05:30 Rome daily, ID: `6d2e225f-26ca-4d53-9d3f-742b59b200c6`)

## Knowledge Base (RAG)
**Stack:** SQLite + Ollama nomic-embed-text embeddings (local)
**Schema:** files, chunks, embedding_cache, chunks_fts tables per agent
**SSoT access:** L0/L1/L2 toggleable per agent via Dashboard
**Common KB:** `~/.openclaw/knowledge/common/` — shared across agents
**Current data:** main=1,246 files/20,806 chunks; voice=166 files/1,067 chunks
**Access:** Dashboard → Settings → Knowledge Base

## Memory Archivist (cron)
Runs 05:30 Rome: scans SSoT L1-L4 → drift detection → extracts 24h decisions → creates Memory Log entry

## Related
- SSOT-L1-R-MEMORY.md — R-Memory tech spec
- SSOT-L1-RAG-SYSTEM.md — KB/RAG details
