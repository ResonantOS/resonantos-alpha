# ResonantOS MCP Server

Expose ResonantOS knowledge (SSoT docs, research, RAG memory) to any MCP-compatible AI client.

## Tools

| Tool | Description |
|------|-------------|
| `memory_search` | Full-text search across 21K+ indexed chunks |
| `read_document` | Read SSoT or research documents |
| `list_documents` | List available documents with metadata |
| `search_documents` | Grep-style search across document files |
| `system_status` | ResonantOS system health overview |

## Setup

```bash
cd mcp-server
npm install
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "resonantos": {
      "command": "node",
      "args": ["/Users/augmentor/resonantos-augmentor/mcp-server/src/index.js"]
    }
  }
}
```

## Test

```bash
# Verify server starts without errors
node src/index.js &
PID=$!
sleep 1
kill $PID 2>/dev/null
echo "Server starts OK"
```

## Architecture

```
External AI (Claude Desktop / ChatGPT / Gemini)
    ↓ MCP protocol (stdio)
ResonantOS MCP Server (this)
    ↓ queries
├── SQLite RAG (FTS5 full-text search)
├── SSoT docs (217+ markdown files)
└── Research knowledge (21+ files)
```

## Security

- Read-only: no write operations exposed
- Path traversal blocked: only ssot/ and research/ accessible
- SQLite opened in read-only mode
- No authentication (localhost only)
