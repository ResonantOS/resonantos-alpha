## Root Cause

ResonantOS data (RAG memory, SSoT docs, research knowledge) is locked to OpenClaw. External AIs (Claude Desktop, ChatGPT, Gemini) cannot access our knowledge base. We need an MCP server that exposes this data via the standard Model Context Protocol, making ResonantOS a platform-agnostic knowledge layer.

## Fix

Build a Node.js MCP server using `@modelcontextprotocol/sdk` that exposes ResonantOS data through MCP tools. The server uses stdio transport (standard for Claude Desktop integration).

### Architecture

```
External AI Client (Claude Desktop, etc.)
    ↓ MCP protocol (stdio)
ResonantOS MCP Server (Node.js, this project)
    ↓ queries
SQLite RAG (21K+ chunks, vec0 vector search, FTS5)
SSoT docs (filesystem, 217+ markdown files)
Research knowledge (filesystem, 21+ files)
System status (openclaw CLI)
```

### MCP Tools to implement

1. **`memory_search`** — Semantic search across RAG memory store
   - Input: `{ query: string, maxResults?: number, minScore?: number }`
   - Queries: FTS5 full-text search on `chunks_fts` table (vector search requires Ollama embedding call which adds complexity — start with FTS5 only)
   - Returns: matching chunks with path, text, score, line numbers

2. **`read_document`** — Read any SSoT or research document by path
   - Input: `{ path: string }` (relative to ssot/ or research/)
   - Returns: file contents as markdown
   - Security: only allow reads within ssot/ and research/ directories (no path traversal)

3. **`list_documents`** — List available SSoT and research documents
   - Input: `{ folder?: "ssot" | "research" | "all" }`
   - Returns: list of file paths with sizes and last modified dates

4. **`search_documents`** — Grep-style search across document files
   - Input: `{ pattern: string, folder?: "ssot" | "research" | "all" }`
   - Returns: matching lines with file path and line number

5. **`system_status`** — Get ResonantOS system overview
   - Input: none
   - Returns: agent count, memory stats, uptime, component health
   - Implementation: runs `openclaw status --json` and parses output

### Technical Requirements

- **Runtime:** Node.js 25+ (already installed)
- **SQLite:** Use `node:sqlite` (built-in module) — NOT better-sqlite3
- **Vector extension:** Load vec0.dylib from `/opt/homebrew/lib/node_modules/openclaw/node_modules/sqlite-vec-darwin-arm64/vec0.dylib`
- **MCP SDK:** `@modelcontextprotocol/sdk` (install via npm)
- **Transport:** stdio (standard for Claude Desktop)
- **Entry point:** `src/index.js` (plain JS, no TypeScript build step needed)

### SQLite Schema (main.sqlite)

```sql
-- Chunks table (main data)
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'memory',
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  hash TEXT NOT NULL,
  model TEXT NOT NULL,
  text TEXT NOT NULL,
  embedding TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

-- FTS5 index for full-text search
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text, id UNINDEXED, path UNINDEXED, source UNINDEXED,
  model UNINDEXED, start_line UNINDEXED, end_line UNINDEXED
);

-- Vec0 index for vector search (768-dim, nomic-embed-text)
CREATE VIRTUAL TABLE chunks_vec USING vec0(
  id TEXT PRIMARY KEY,
  embedding FLOAT[768]
);
```

### File Paths (constants)

```javascript
const MEMORY_DB = '/Users/augmentor/.openclaw/memory/main.sqlite';
const VEC0_PATH = '/opt/homebrew/lib/node_modules/openclaw/node_modules/sqlite-vec-darwin-arm64/vec0.dylib';
const SSOT_DIR = '/Users/augmentor/resonantos-augmentor/ssot';
const RESEARCH_DIR = '/Users/augmentor/resonantos-augmentor/research';
```

### Package.json

```json
{
  "name": "resonantos-mcp-server",
  "version": "0.1.0",
  "description": "ResonantOS MCP Server — expose knowledge to external AIs",
  "type": "module",
  "bin": { "resonantos-mcp": "./src/index.js" },
  "dependencies": {
    "@modelcontextprotocol/sdk": "latest"
  }
}
```

## Files to Modify

- CREATE `mcp-server/package.json`
- CREATE `mcp-server/src/index.js` — main MCP server entry point
- CREATE `mcp-server/README.md` — usage instructions (how to add to Claude Desktop config)

All files in `/Users/augmentor/resonantos-augmentor/mcp-server/`.

## Data Context

- Main SQLite store has 21,208 chunks across 1,344 files
- SSoT directory has 217+ markdown files across L0-L4
- Research directory has 21 markdown files
- Node.js v25.6.1, npm available
- `node:sqlite` built-in module works (tested)
- vec0.dylib exists and works at the path above

## Preferences

- Plain JavaScript (ES modules), no TypeScript — simpler, no build step
- Minimal dependencies — only `@modelcontextprotocol/sdk`
- Start with FTS5 text search (reliable), add vector search later if vec0 loads cleanly
- Clean error handling — if SQLite fails, return useful error message, don't crash
- Security: sanitize all file paths, no path traversal outside allowed directories

## Test Command

```bash
cd /Users/augmentor/resonantos-augmentor/mcp-server && npm install && node src/index.js --help 2>&1 || echo "Server loads"
```

## Acceptance Criteria

1. `npm install` succeeds with zero errors
2. `node src/index.js` starts MCP server on stdio without crashing
3. Server registers 5 tools (memory_search, read_document, list_documents, search_documents, system_status)
4. FTS5 search returns results when queried
5. read_document returns file contents for valid SSoT paths
6. Path traversal attempts (../../etc/passwd) are rejected
7. README.md includes Claude Desktop config snippet

## Out of Scope

- Vector/semantic search (future — requires Ollama embedding call)
- Authentication/authorization
- HTTP/SSE transport (stdio only for now)
- Dashboard integration (separate task)
- Write operations (read-only server)

## Escalation Triggers

- If `node:sqlite` cannot load vec0.dylib, skip vector search entirely — FTS5 is sufficient
- If `@modelcontextprotocol/sdk` has breaking API changes, check their GitHub README
- If file permissions block SQLite reads, flag and continue with document tools only
