#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve, relative, extname } from "node:path";
import { execSync } from "node:child_process";

const MEMORY_DB = "/Users/augmentor/.openclaw/memory/main.sqlite";
const SSOT_DIR = "/Users/augmentor/resonantos-augmentor/ssot";
const RESEARCH_DIR = "/Users/augmentor/resonantos-augmentor/research";
const ALLOWED_DIRS = [SSOT_DIR, RESEARCH_DIR];
const MD_EXTENSIONS = new Set([".md", ".txt", ".json", ".yaml", ".yml"]);

let db = null;
function getDb() {
  if (!db) db = new DatabaseSync(MEMORY_DB, { open: true, readOnly: true });
  return db;
}

function isPathSafe(p) {
  const r = resolve(p);
  return ALLOWED_DIRS.some(d => r.startsWith(resolve(d)));
}

function resolveDocPath(p) {
  if (existsSync(p) && isPathSafe(p)) return resolve(p);
  for (const dir of ALLOWED_DIRS) {
    const full = join(dir, p);
    if (existsSync(full) && isPathSafe(full)) return resolve(full);
  }
  return null;
}

function listFiles(dir, base = dir) {
  const results = [];
  if (!existsSync(dir)) return results;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...listFiles(full, base));
    else if (MD_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
      const stat = statSync(full);
      results.push({ path: relative(base, full), size: stat.size, modified: stat.mtime.toISOString() });
    }
  }
  return results;
}

const TOOLS = [
  { name: "memory_search", description: "Full-text search across the ResonantOS knowledge base (21K+ indexed chunks). Returns matching text chunks with file paths.", inputSchema: { type: "object", properties: { query: { type: "string", description: "Search query" }, maxResults: { type: "number", description: "Max results (default 10)" } }, required: ["query"] } },
  { name: "read_document", description: "Read an SSoT or research document by path.", inputSchema: { type: "object", properties: { path: { type: "string", description: "Document path" } }, required: ["path"] } },
  { name: "list_documents", description: "List available documents in SSoT and research directories.", inputSchema: { type: "object", properties: { folder: { type: "string", enum: ["ssot", "research", "all"], description: "Folder (default: all)" } } } },
  { name: "search_documents", description: "Grep-style search across documents.", inputSchema: { type: "object", properties: { pattern: { type: "string", description: "Search pattern" }, folder: { type: "string", enum: ["ssot", "research", "all"] }, maxResults: { type: "number" } }, required: ["pattern"] } },
  { name: "system_status", description: "Get ResonantOS system overview.", inputSchema: { type: "object", properties: {} } },
];

function handleMemorySearch({ query, maxResults = 10 }) {
  const database = getDb();
  const rows = database.prepare("SELECT c.path, c.text, c.start_line, c.end_line, rank * -1 as score FROM chunks_fts f JOIN chunks c ON c.id = f.id WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?").all(query, maxResults);
  if (!rows.length) return { content: [{ type: "text", text: "No results found for: " + query }] };
  const fmt = rows.map((r, i) => "### Result " + (i+1) + "\n**File:** " + r.path + " (lines " + r.start_line + "-" + r.end_line + ")\n\n" + r.text).join("\n\n---\n\n");
  return { content: [{ type: "text", text: "Found " + rows.length + " results:\n\n" + fmt }] };
}

function handleReadDocument({ path: docPath }) {
  const resolved = resolveDocPath(docPath);
  if (!resolved) return { content: [{ type: "text", text: "Not found: " + docPath }], isError: true };
  return { content: [{ type: "text", text: readFileSync(resolved, "utf-8") }] };
}

function handleListDocuments({ folder = "all" } = {}) {
  const files = [];
  if (folder === "ssot" || folder === "all") files.push(...listFiles(SSOT_DIR).map(f => ({ ...f, source: "ssot" })));
  if (folder === "research" || folder === "all") files.push(...listFiles(RESEARCH_DIR).map(f => ({ ...f, source: "research" })));
  const summary = files.map(f => "- [" + f.source + "] " + f.path + " (" + (f.size/1024).toFixed(1) + "KB)").join("\n");
  return { content: [{ type: "text", text: "Documents (" + files.length + "):\n\n" + summary }] };
}

function handleSearchDocuments({ pattern, folder = "all", maxResults = 50 }) {
  const dirs = [];
  if (folder === "ssot" || folder === "all") dirs.push(SSOT_DIR);
  if (folder === "research" || folder === "all") dirs.push(RESEARCH_DIR);
  const results = [];
  const regex = new RegExp(pattern, "i");
  for (const dir of dirs) {
    for (const file of listFiles(dir)) {
      if (results.length >= maxResults) break;
      try {
        const lines = readFileSync(join(dir, file.path), "utf-8").split("\n");
        for (let i = 0; i < lines.length; i++) {
          if (regex.test(lines[i])) { results.push({ file: file.path, line: i+1, text: lines[i].trim() }); if (results.length >= maxResults) break; }
        }
      } catch {}
    }
  }
  if (!results.length) return { content: [{ type: "text", text: "No matches for: " + pattern }] };
  return { content: [{ type: "text", text: "Found " + results.length + " matches:\n\n" + results.map(r => "- " + r.file + ":" + r.line + " - " + r.text).join("\n") }] };
}

function handleSystemStatus() {
  let status = "";
  try { status = execSync("openclaw status 2>/dev/null", { timeout: 10000, encoding: "utf-8" }); } catch { status = "openclaw not available"; }
  let mem = "";
  try {
    const d = getDb();
    const cc = d.prepare("SELECT COUNT(*) as cnt FROM chunks").get();
    const fc = d.prepare("SELECT COUNT(DISTINCT path) as cnt FROM chunks").get();
    mem = "\n\nMemory: " + cc.cnt + " chunks, " + fc.cnt + " files indexed";
  } catch { mem = "\nMemory: unavailable"; }
  return { content: [{ type: "text", text: "ResonantOS Status\n\n" + status + mem }] };
}

const server = new Server({ name: "resonantos-mcp", version: "0.1.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const handlers = { memory_search: handleMemorySearch, read_document: handleReadDocument, list_documents: handleListDocuments, search_documents: handleSearchDocuments, system_status: handleSystemStatus };
  if (handlers[name]) return handlers[name](args);
  return { content: [{ type: "text", text: "Unknown tool: " + name }], isError: true };
});
const transport = new StdioServerTransport();
await server.connect(transport);
