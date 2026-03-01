/**
 * R-Memory V5.0.1 — High-Fidelity Compression Extension for OpenClaw
 * @version 5.0.1
 * @date 2026-02-20
 *
 * Changes from V4.8.1:
 * - Fix 1: Narrative tracker quality upgrade: structured prompt (Task/Decisions/Pending/State)
 * - Fix 1: Narrative model: dedicated gpt-4o via camouflage.backgroundModels["openai-narrative"]
 * - Fix 1: Previous thread state fed into prompt for continuity across updates
 * - Fix 2: No-op swap filter: blocks < minSwapTokens (default 50) skipped in compaction
 * - Fix 3: Background pre-compression disabled (75% cache miss rate due to hash mismatch)
 *   Compression now on-demand at compaction time only, saving wasted API calls
 *
 * Changes from V4.7.0:
 * - Camouflage integration: routes background LLM calls (compression, narrative)
 *   to non-Anthropic providers when camouflage.enabled=true
 *   Config: r-memory/camouflage.json
 * - Behavioral jitter: adds random delay to background calls
 * - Concurrency cap: limits parallel background calls per camouflage config
 * - All camouflage elements toggleable via camouflage.json elements{}
 *
 * Changes from V4.6.3:
 * - Narrative Tracker: writes SESSION_THREAD.md after each AI response via Haiku
 *   (~200-word working memory summary: current task, direction, blockers, state)
 *   Survives compaction (workspace file, not transcript). Fire-and-forget.
 *
 * V4.6.3 changes:
 * - Archive-to-memory bridge: FIFO-evicted blocks now written to memory/archive/
 *   as searchable .md files (indexed by memory_search)
 * - Multi-provider API key resolution (anthropic/openai/google auto-discovery)
 *
 * V4.6.2 changes:
 * - Fixed: background compression now caches ALL blocks (was skipping last block)
 * - Added: hash comparison logging, cache miss diagnostics
 *
 * V4.6.1 changes:
 * - Restored blockSize (default 4k tokens) from original spec
 * - Turns larger than blockSize are split at message boundaries
 * - Single messages larger than blockSize are hard-split
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ============================================================================
// Dependencies from pi-ai
// ============================================================================
let completeSimple = null;
let getModel = null;
for (const p of [
  "@mariozechner/pi-ai",
  "/opt/homebrew/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai",
  "/usr/local/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai",
]) {
  try { completeSimple = require(p).completeSimple; break; } catch (e) {}
}
for (const p of [
  "@mariozechner/pi-ai",
  "/opt/homebrew/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai",
  "/usr/local/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai",
]) {
  try { getModel = require(p).getModel; break; } catch (e) {}
}

// ============================================================================
// Config
// ============================================================================
const DEFAULT_CONFIG = {
  evictTrigger: 80000,
  compressTrigger: 36000,
  blockSize: 4000,
  minCompressChars: 200,
  minSwapTokens: 50,
  compressionModel: "minimax/MiniMax-M2.5",
  narrativeModel: "minimax/MiniMax-M2.5", // MiniMax for narrative
  narrativeUseToolMode: false, // true = force write_narrative tool (for models that hallucinate tool calls in text)
  maxParallelCompressions: 4,
  storageDir: "r-memory",
  archiveDir: "r-memory/archive",
  logFile: "r-memory/r-memory.log",
  enabled: true,
};

let config = { ...DEFAULT_CONFIG };
let workspaceDir = "";
let resolvedApiKey = null;
let currentSessionId = null;
let compactionHistory = [];
let messageCache = new Map();
let lastProcessedBlockCount = 0;
const MAX_CACHE_SIZE = 2000;
let compressionQueue = [];
let activeCompressions = 0;
let deferredCompactionMinBlocks = 0; // Step 3: cancel-loop reduction

// ============================================================================
// Camouflage — Traffic Origin Segregation
// ============================================================================
const DEFAULT_CAMOUFLAGE = {
  enabled: false,
  routeCompressionOffAnthro: true,
  routeNarrativeOffAnthro: true,
  preferredBackgroundProvider: "openai",
  backgroundModels: {
    openai: "openai/gpt-4o-mini",
    google: "google/gemini-2.0-flash",
  },
  jitterMs: { min: 200, max: 2500 },
  maxConcurrentBackgroundCalls: 2,
  logRoutingDecisions: true,
  elements: {
    trafficSegregation: true,
    behavioralJitter: true,
    concurrencyLimit: true,
  },
};
let camouflage = { ...DEFAULT_CAMOUFLAGE };

// ============================================================================
// Background Agent Usage Tracking
// ============================================================================
const usageStats = {
  compression: { calls: 0, inputTokens: 0, outputTokens: 0, errors: 0, lastCall: null },
  narrative: { calls: 0, inputTokens: 0, outputTokens: 0, errors: 0, lastCall: null },
  // heartbeat tracked separately by dashboard via gateway logs
};

function loadUsageStats() {
  try {
    const p = path.join(workspaceDir, config.storageDir, "usage-stats.json");
    if (fs.existsSync(p)) {
      const saved = JSON.parse(fs.readFileSync(p, "utf-8"));
      if (saved.compression) Object.assign(usageStats.compression, saved.compression);
      if (saved.narrative) Object.assign(usageStats.narrative, saved.narrative);
    }
  } catch (e) { log("WARN", "Could not load usage stats", { error: e.message }); }
}

function saveUsageStats() {
  try {
    const p = path.join(workspaceDir, config.storageDir, "usage-stats.json");
    fs.writeFileSync(p, JSON.stringify(usageStats, null, 2));
  } catch (e) { /* non-critical */ }
}

function trackUsage(agentType, inputTokens, outputTokens, isError = false) {
  const s = usageStats[agentType];
  if (!s) return;
  s.calls++;
  s.inputTokens += inputTokens;
  s.outputTokens += outputTokens;
  if (isError) s.errors++;
  s.lastCall = new Date().toISOString();
  saveUsageStats();
}

function loadCamouflage() {
  try {
    const p = path.join(workspaceDir, config.storageDir, "camouflage.json");
    if (fs.existsSync(p)) {
      const raw = JSON.parse(fs.readFileSync(p, "utf-8"));
      const cleaned = {};
      for (const [k, v] of Object.entries(raw)) {
        if (!k.startsWith("//")) cleaned[k] = v;
      }
      camouflage = { ...DEFAULT_CAMOUFLAGE, ...cleaned };
      if (cleaned.elements) camouflage.elements = { ...DEFAULT_CAMOUFLAGE.elements, ...cleaned.elements };
      if (cleaned.jitterMs) camouflage.jitterMs = { ...DEFAULT_CAMOUFLAGE.jitterMs, ...cleaned.jitterMs };
      if (cleaned.backgroundModels) camouflage.backgroundModels = { ...DEFAULT_CAMOUFLAGE.backgroundModels, ...cleaned.backgroundModels };
    }
    log("INFO", "Camouflage config loaded", {
      enabled: camouflage.enabled,
      elements: camouflage.elements,
      preferredProvider: camouflage.preferredBackgroundProvider,
    });
  } catch (e) {
    log("WARN", "Camouflage config load failed — using defaults", { error: e.message });
  }
}

/**
 * Resolve background model + API key for camouflage routing.
 * When camouflage is active, routes away from Anthropic.
 * Returns { model, apiKey, provider, routed } or null.
 */
function resolveCamouflageModel(callType) {
  // callType: "compression" | "narrative"
  const shouldRoute = camouflage.enabled && camouflage.elements.trafficSegregation && (
    (callType === "compression" && camouflage.routeCompressionOffAnthro) ||
    (callType === "narrative" && camouflage.routeNarrativeOffAnthro)
  );

  if (!shouldRoute) {
    // Use default compression model (Anthropic Haiku)
    return { model: config.compressionModel, apiKey: resolvedApiKey, provider: "anthropic", routed: false };
  }

  // Try preferred provider first
  const preferred = camouflage.preferredBackgroundProvider;
  const modelStr = camouflage.backgroundModels[preferred];
  if (modelStr) {
    const key = resolveApiKeyForProvider(preferred);
    if (key) {
      if (camouflage.logRoutingDecisions) {
        log("INFO", `CAMOUFLAGE: Routed ${callType} → ${preferred}`, { model: modelStr });
      }
      return { model: modelStr, apiKey: key, provider: preferred, routed: true };
    }
  }

  // Fallback: any non-Anthropic provider with a key
  for (const [prov, model] of Object.entries(camouflage.backgroundModels)) {
    if (prov === "anthropic") continue;
    const key = resolveApiKeyForProvider(prov);
    if (key) {
      if (camouflage.logRoutingDecisions) {
        log("INFO", `CAMOUFLAGE: Routed ${callType} → ${prov} (fallback)`, { model });
      }
      return { model, apiKey: key, provider: prov, routed: true };
    }
  }

  // Last resort: use Anthropic (camouflage degraded)
  log("WARN", `CAMOUFLAGE: No non-Anthropic provider available for ${callType} — falling back to Anthropic`);
  return { model: config.compressionModel, apiKey: resolvedApiKey, provider: "anthropic", routed: false };
}

/**
 * Apply behavioral jitter — random delay before background LLM calls.
 */
function applyJitter() {
  if (!camouflage.enabled || !camouflage.elements.behavioralJitter) return Promise.resolve();
  const { min, max } = camouflage.jitterMs;
  const delay = min + Math.floor(Math.random() * (max - min));
  return new Promise(resolve => setTimeout(resolve, delay));
}

/**
 * Get effective max parallel compressions (respects camouflage concurrency cap).
 */
function getMaxParallel() {
  if (camouflage.enabled && camouflage.elements.concurrencyLimit) {
    return Math.min(config.maxParallelCompressions, camouflage.maxConcurrentBackgroundCalls);
  }
  return config.maxParallelCompressions;
}

// ============================================================================
// Utilities
// ============================================================================
function log(level, msg, data) {
  if (!workspaceDir) return;
  const ts = new Date().toISOString();
  const line = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  try { fs.appendFileSync(path.join(workspaceDir, config.logFile), line + "\n"); } catch (e) {}
}

function ensureDir(d) { if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true }); }
function hashText(text) { return crypto.createHash("sha256").update(text).digest("hex").slice(0, 32); }
function estimateTokens(text) { return Math.ceil((text || "").length / 4); }

function buildModelObject(modelString) {
  const parts = (modelString || "anthropic/claude-haiku-4-5").split("/");
  const provider = parts[0] || "anthropic";
  const modelId = parts.slice(1).join("/") || "claude-haiku-4-5";
  if (getModel) {
    try { const m = getModel(provider, modelId); log("DEBUG", "Model resolved via getModel", { id: m.id, provider: m.provider }); return m; }
    catch (e) { log("WARN", "getModel failed", { error: e.message }); }
  }
  return { provider, id: modelId, contextWindow: 200000, inputModalities: ["text"] };
}

// ============================================================================
// Config loading
// ============================================================================
function loadConfig() {
  try {
    const p = path.join(workspaceDir, config.storageDir, "config.json");
    if (fs.existsSync(p)) {
      const userConfig = JSON.parse(fs.readFileSync(p, "utf-8"));
      const cleaned = {};
      for (const [key, val] of Object.entries(userConfig)) {
        if (!key.startsWith("//")) cleaned[key] = val;
      }
      config = { ...DEFAULT_CONFIG, ...cleaned };
    } else {
      ensureDir(path.join(workspaceDir, config.storageDir));
      fs.writeFileSync(p, JSON.stringify(DEFAULT_CONFIG, null, 2));
    }
    log("INFO", "Config loaded", { compressTrigger: config.compressTrigger, evictTrigger: config.evictTrigger, blockSize: config.blockSize });
  } catch (e) { log("ERROR", "Config load failed", { error: e.message }); }
}

// ============================================================================
// Message text extraction
// ============================================================================
function extractMessageText(msg) {
  const parts = [];
  switch (msg.role) {
    case "user": {
      parts.push("[Human]:");
      if (typeof msg.content === "string") { parts.push(msg.content); }
      else if (Array.isArray(msg.content)) {
        for (const b of msg.content) {
          if (b.type === "text" && b.text) parts.push(b.text);
          if (b.type === "image") parts.push("[Image: ~1200 tokens]");
        }
      }
      break;
    }
    case "assistant": {
      parts.push("[AI]:");
      if (Array.isArray(msg.content)) {
        for (const b of msg.content) {
          if (b.type === "text") parts.push(b.text);
          else if (b.type === "thinking") {
            const t = b.thinking || "";
            if (t.length > 2000) { parts.push(`[Thinking]: ${t.slice(0, 500)}\n...[truncated]...\n${t.slice(-500)}`); }
            else { parts.push(`[Thinking]: ${t}`); }
          }
          else if (b.type === "toolCall") {
            parts.push(`[Tool: ${b.name}]`);
            try { parts.push(`<PRESERVE_VERBATIM>\n${JSON.stringify(b.arguments, null, 2)}\n</PRESERVE_VERBATIM>`); }
            catch (e) { parts.push("[args]"); }
          }
        }
      }
      break;
    }
    case "toolResult": {
      parts.push("[Tool Result]:");
      if (typeof msg.content === "string") {
        const c = msg.content;
        parts.push(c.length > 8000 ? c.slice(0, 4000) + "\n...[truncated]...\n" + c.slice(-2000) : c);
      } else if (Array.isArray(msg.content)) {
        for (const b of msg.content) {
          if (b.type === "text" && b.text) { const t = b.text; parts.push(t.length > 8000 ? t.slice(0, 4000) + "\n...[truncated]...\n" + t.slice(-2000) : t); }
          if (b.type === "image") parts.push("[Image: ~1200 tokens]");
        }
      }
      break;
    }
    case "bashExecution": {
      parts.push("[Bash]:");
      parts.push(`$ ${msg.command || ""}`);
      const out = msg.output || "";
      parts.push(out.length > 8000 ? out.slice(0, 4000) + "\n...[truncated]...\n" + out.slice(-2000) : out);
      break;
    }
    case "compactionSummary": { parts.push("[Previous Compressed]:"); parts.push(msg.summary || ""); break; }
    case "branchSummary": { parts.push("[Branch Context]:"); parts.push(msg.summary || ""); break; }
    case "custom": { parts.push("[Custom]:"); if (typeof msg.content === "string") parts.push(msg.content); break; }
    default: { parts.push(`[${msg.role || "unknown"}]:`); if (typeof msg.content === "string") parts.push(msg.content); break; }
  }
  return parts.join("\n");
}

// ============================================================================
// Block creation helpers
// ============================================================================

/**
 * Create a finalized block from messages.
 */
function finalizeBlock(messages) {
  const textParts = messages.map(m => extractMessageText(m));
  const text = textParts.join("\n\n");
  return { messages, text, hash: hashText(text), tokens: estimateTokens(text) };
}

/**
 * Create a finalized block from entry objects [{index, id, message}].
 */
function finalizeEntryBlock(entries) {
  const textParts = entries.map(e => extractMessageText(e.message));
  const text = textParts.join("\n\n");
  return {
    entries,
    firstEntryId: entries[0].id,
    firstEntryIndex: entries[0].index,
    text,
    hash: hashText(text),
    tokens: estimateTokens(text),
  };
}

/**
 * Hard-split a single long text into chunks of ~blockSize tokens.
 * Used when a single message exceeds blockSize.
 */
function hardSplitText(text, maxChars) {
  const chunks = [];
  let remaining = text;
  while (remaining.length > maxChars) {
    // Try to split at a newline near the boundary
    let splitAt = maxChars;
    const newlinePos = remaining.lastIndexOf("\n", maxChars);
    if (newlinePos > maxChars * 0.7) splitAt = newlinePos + 1;
    chunks.push(remaining.slice(0, splitAt));
    remaining = remaining.slice(splitAt);
  }
  if (remaining.length > 0) chunks.push(remaining);
  return chunks;
}

// ============================================================================
// Block grouping from flat messages (for background compression)
//
// Step 1: Group into turns (human prompt + all AI replies)
// Step 2: Split any turn > blockSize at message boundaries
// Step 3: Hard-split any single message > blockSize
// ============================================================================

function groupMessagesIntoBlocks(messages) {
  // Step 1: Group into turns
  const turns = [];
  let currentMsgs = [];
  for (const msg of messages) {
    if (msg.role === "compactionSummary" || msg.role === "branchSummary") continue;
    if (msg.role === "user" && currentMsgs.length > 0) {
      turns.push(currentMsgs);
      currentMsgs = [msg];
    } else {
      currentMsgs.push(msg);
    }
  }
  if (currentMsgs.length > 0) turns.push(currentMsgs);

  // Step 2 & 3: Split oversized turns into blocks
  const blocks = [];
  const maxTokens = config.blockSize || 4000;
  const maxChars = maxTokens * 4;

  for (const turnMsgs of turns) {
    const turnText = turnMsgs.map(m => extractMessageText(m)).join("\n\n");
    const turnTokens = estimateTokens(turnText);

    if (turnTokens <= maxTokens) {
      // Small turn — single block
      blocks.push(finalizeBlock(turnMsgs));
      continue;
    }

    // Oversized turn — split at message boundaries
    let blockMsgs = [];
    let blockTokens = 0;

    for (const msg of turnMsgs) {
      const msgText = extractMessageText(msg);
      const msgTokens = estimateTokens(msgText);

      if (msgTokens > maxTokens) {
        // Finalize current block if any
        if (blockMsgs.length > 0) {
          blocks.push(finalizeBlock(blockMsgs));
          blockMsgs = [];
          blockTokens = 0;
        }
        // Hard-split this single large message
        const chunks = hardSplitText(msgText, maxChars);
        for (const chunk of chunks) {
          const syntheticMsg = { ...msg, _chunkText: chunk };
          blocks.push({
            messages: [syntheticMsg],
            text: chunk,
            hash: hashText(chunk),
            tokens: estimateTokens(chunk),
          });
        }
        continue;
      }

      if (blockTokens + msgTokens > maxTokens && blockMsgs.length > 0) {
        // Current block would exceed limit — finalize and start new
        blocks.push(finalizeBlock(blockMsgs));
        blockMsgs = [msg];
        blockTokens = msgTokens;
      } else {
        blockMsgs.push(msg);
        blockTokens += msgTokens;
      }
    }
    // Finalize remaining
    if (blockMsgs.length > 0) {
      blocks.push(finalizeBlock(blockMsgs));
    }
  }
  return blocks;
}

// ============================================================================
// Block grouping from branchEntries (for compaction handler)
// Same logic but preserves entry IDs for firstKeptEntryId
// ============================================================================

function groupEntriesIntoBlocks(branchEntries, startIndex) {
  // Step 0: Detect tool call/result pairs so they are NEVER split across blocks.
  // OpenClaw internal format: assistant content[].type==="toolCall" + role==="toolResult" messages.
  // Also handles raw Anthropic (tool_use/tool_result) and OpenAI (tool_calls[]/role==="tool")
  // formats in case un-normalized messages appear. Splitting pairs causes API errors.
  function hasToolUse(msg) {
    if (!msg) return false;
    // OpenClaw internal format: content[].type === "toolCall"
    if (Array.isArray(msg.content) && msg.content.some(b => b.type === "toolCall")) return true;
    // Anthropic API format (in case raw messages leak through): content[].type === "tool_use"
    if (Array.isArray(msg.content) && msg.content.some(b => b.type === "tool_use")) return true;
    // OpenAI API format (in case raw messages leak through): assistant message with tool_calls[]
    if (Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) return true;
    return false;
  }
  function hasToolResult(msg) {
    if (!msg) return false;
    // OpenClaw internal format: role === "toolResult"
    if (msg.role === "toolResult") return true;
    // Anthropic API format (in case raw messages leak through): content[].type === "tool_result"
    if (Array.isArray(msg.content) && msg.content.some(b => b.type === "tool_result")) return true;
    // OpenAI API format (in case raw messages leak through): role === "tool" with tool_call_id
    if (msg.role === "tool" && msg.tool_call_id) return true;
    return false;
  }

  // Step 1: Group into turns, but keep tool_use + tool_result together
  const turns = [];
  let currentEntries = [];

  for (let i = startIndex; i < branchEntries.length; i++) {
    const entry = branchEntries[i];
    const msg = getMessageFromEntry(entry);
    if (!msg) continue;
    if (msg.role === "compactionSummary" || msg.role === "branchSummary") continue;

    if (msg.role === "user" && currentEntries.length > 0) {
      // Check: is this user message a tool_result paired with a preceding tool_use?
      const prevMsg = currentEntries.length > 0 ? currentEntries[currentEntries.length - 1].message : null;
      if (hasToolResult(msg) && prevMsg && (hasToolUse(prevMsg) || hasToolResult(prevMsg))) {
        // Keep tool_result with its tool_use — don't start a new turn
        currentEntries.push({ index: i, id: entry.id, message: msg });
      } else {
        turns.push(currentEntries);
        currentEntries = [{ index: i, id: entry.id, message: msg }];
      }
    } else {
      currentEntries.push({ index: i, id: entry.id, message: msg });
    }
  }
  if (currentEntries.length > 0) turns.push(currentEntries);

  // Step 2 & 3: Split oversized turns into blocks, respecting tool_use/tool_result pairs
  const blocks = [];
  const maxTokens = config.blockSize || 4000;
  const maxChars = maxTokens * 4;

  for (const turnEntries of turns) {
    const turnText = turnEntries.map(e => extractMessageText(e.message)).join("\n\n");
    const turnTokens = estimateTokens(turnText);

    if (turnTokens <= maxTokens) {
      blocks.push(finalizeEntryBlock(turnEntries));
      continue;
    }

    // Oversized turn — split at message boundaries, keeping tool pairs together
    let blockEntries = [];
    let blockTokens = 0;

    for (let j = 0; j < turnEntries.length; j++) {
      const entry = turnEntries[j];
      const msgText = extractMessageText(entry.message);
      const msgTokens = estimateTokens(msgText);

      // Check if this entry starts a tool_use pair (assistant with tool_use + next is tool_result)
      // OpenAI can have MULTIPLE tool results (role:"tool") following one assistant tool_calls.
      // Anthropic wraps all results in a single user message. Handle both.
      let pairedEntries = [entry];
      let pairedTokens = msgTokens;
      if (hasToolUse(entry.message)) {
        while (j + 1 < turnEntries.length && hasToolResult(turnEntries[j + 1].message)) {
          const nextEntry = turnEntries[j + 1];
          const nextText = extractMessageText(nextEntry.message);
          pairedEntries.push(nextEntry);
          pairedTokens += estimateTokens(nextText);
          j++; // skip the tool_result(s) in the next iteration
        }
      }

      // If paired entries are themselves larger than maxTokens, they still go together
      // (splitting a tool_use from its tool_result is worse than having an oversized block)
      if (pairedTokens > maxTokens && pairedEntries.length > 1) {
        // Flush current block first
        if (blockEntries.length > 0) {
          blocks.push(finalizeEntryBlock(blockEntries));
          blockEntries = [];
          blockTokens = 0;
        }
        // Keep the pair together as one oversized block (safe: no API error)
        blocks.push(finalizeEntryBlock(pairedEntries));
        continue;
      }

      if (pairedTokens > maxTokens && pairedEntries.length === 1) {
        if (blockEntries.length > 0) {
          blocks.push(finalizeEntryBlock(blockEntries));
          blockEntries = [];
          blockTokens = 0;
        }
        // Hard-split single large message — each chunk keeps the entry's ID
        const chunks = hardSplitText(msgText, maxChars);
        for (let c = 0; c < chunks.length; c++) {
          blocks.push({
            entries: [entry],
            firstEntryId: entry.id,
            firstEntryIndex: entry.index,
            text: chunks[c],
            hash: hashText(chunks[c]),
            tokens: estimateTokens(chunks[c]),
          });
        }
        continue;
      }

      if (blockTokens + pairedTokens > maxTokens && blockEntries.length > 0) {
        blocks.push(finalizeEntryBlock(blockEntries));
        blockEntries = [...pairedEntries];
        blockTokens = pairedTokens;
      } else {
        blockEntries.push(...pairedEntries);
        blockTokens += pairedTokens;
      }
    }
    if (blockEntries.length > 0) {
      blocks.push(finalizeEntryBlock(blockEntries));
    }
  }
  return blocks;
}

/**
 * Extract message from a branchEntry (mirrors OpenClaw's getMessageFromEntry)
 */
function getMessageFromEntry(entry) {
  if (entry.type === "message" && entry.message) return entry.message;
  // Skip OpenClaw metadata entries — they are NOT conversation content and should not
  // be counted as blocks or cause "0 blocks" cancellation when they're the only entries.
  if (entry.type === "custom") {
    const ct = entry.customType || "";
    const METADATA_TYPES = ["model-snapshot", "openclaw.cache-ttl", "openclaw.metadata"];
    if (METADATA_TYPES.includes(ct)) return null; // explicitly skip, no debug log needed
    log("DEBUG", "Custom entry structure", { keys: Object.keys(entry), customType: ct, dataType: typeof entry.data, dataPreview: JSON.stringify(entry.data).slice(0, 200) });
    if (entry.data) return { role: "assistant", content: typeof entry.data === "string" ? entry.data : JSON.stringify(entry.data) };
  }
  if (entry.type === "custom_message") return { role: "custom", content: entry.content || "" };
  if (entry.type === "compaction") return { role: "compactionSummary", summary: entry.summary || "" };
  if (entry.type === "branch_summary") return { role: "branchSummary", summary: entry.summary || "" };
  return null;
}

/**
 * Scan raw entries for orphaned tool_result references.
 * Returns adjusted firstKeptEntryId that ensures all tool_results
 * have matching tool_uses within the kept range.
 */
function validateToolPairs(branchEntries, firstKeptEntryId) {
  const firstKeptIdx = branchEntries.findIndex(e => e.id === firstKeptEntryId);
  if (firstKeptIdx < 0) return firstKeptEntryId;

  // Collect all tool_use IDs in the kept range
  const toolUseIds = new Set();
  const toolResultIds = new Set();

  for (let i = firstKeptIdx; i < branchEntries.length; i++) {
    const msg = getMessageFromEntry(branchEntries[i]);
    if (!msg) continue;

    // Collect tool_use IDs from assistant messages
    if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        if (block.type === "toolCall" && block.toolCallId) toolUseIds.add(block.toolCallId);
        if (block.type === "tool_use" && block.id) toolUseIds.add(block.id);
        if (block.type === "tool_result" && block.tool_use_id) toolResultIds.add(block.tool_use_id);
      }
    }
    if (Array.isArray(msg.tool_calls)) {
      for (const tc of msg.tool_calls) {
        if (tc.id) toolUseIds.add(tc.id);
      }
    }

    // Collect tool_result IDs
    if (msg.role === "toolResult" && msg.toolCallId) toolResultIds.add(msg.toolCallId);
    if (msg.role === "tool" && msg.tool_call_id) toolResultIds.add(msg.tool_call_id);
  }

  // Find orphaned tool_result IDs (reference tool_use not in kept range)
  const orphaned = [];
  for (const id of toolResultIds) {
    if (!toolUseIds.has(id)) orphaned.push(id);
  }

  if (orphaned.length === 0) return firstKeptEntryId;

  // Walk firstKeptEntryId backward to include the missing tool_uses
  let adjustedIdx = firstKeptIdx;
  const stillMissing = new Set(orphaned);

  for (let k = firstKeptIdx - 1; k >= 0 && stillMissing.size > 0; k--) {
    const msg = getMessageFromEntry(branchEntries[k]);
    if (!msg) continue;

    let foundInEntry = false;
    if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        if ((block.type === "toolCall" && stillMissing.has(block.toolCallId)) ||
            (block.type === "tool_use" && stillMissing.has(block.id))) {
          stillMissing.delete(block.toolCallId || block.id);
          foundInEntry = true;
        }
      }
    }
    if (Array.isArray(msg.tool_calls)) {
      for (const tc of msg.tool_calls) {
        if (stillMissing.has(tc.id)) {
          stillMissing.delete(tc.id);
          foundInEntry = true;
        }
      }
    }

    if (foundInEntry) {
      adjustedIdx = k;
    }

    // Stop at a user message without tool content (turn boundary)
    if (msg.role === "user" && !msg.tool_call_id && !(msg.role === "toolResult") &&
        !(Array.isArray(msg.content) && msg.content.some(b => b.type === "tool_result"))) {
      if (stillMissing.size > 0) {
        // Can't find the tool_uses — they're from a previous compaction. Log and accept the orphans.
        log("WARN", "Cannot resolve all orphaned tool_results — unreachable tool_uses", {
          orphanedIds: [...stillMissing],
          adjustedIdx,
          firstKeptIdx
        });
      }
      break;
    }
  }

  if (adjustedIdx < firstKeptIdx) {
    log("WARN", "validateToolPairs: adjusted firstKeptEntryId backward", {
      firstKeptIdx,
      adjustedIdx,
      orphanedCount: orphaned.length,
      resolved: orphaned.length - stillMissing.size,
      unresolved: stillMissing.size
    });
    return branchEntries[adjustedIdx].id;
  }

  // If we couldn't resolve orphans by walking back, log it
  if (stillMissing.size > 0) {
    log("WARN", "validateToolPairs: unresolvable orphaned tool_results", {
      orphanedIds: [...stillMissing]
    });
  }

  return firstKeptEntryId;
}

// ============================================================================
// API key resolution (provider-aware)
// ============================================================================
function resolveApiKeyForProvider(provider) {
  if (!provider) provider = "anthropic";
  // 1. Check env vars per provider
  const envMap = { anthropic: "ANTHROPIC_API_KEY", openai: "OPENAI_API_KEY", google: "GOOGLE_API_KEY" };
  if (envMap[provider] && process.env[envMap[provider]]) {
    log("INFO", `API key from env (${provider})`); return process.env[envMap[provider]];
  }
  try {
    // 2. Check auth-profiles.json — match by provider name in profile key
    const agentAuth = path.join(process.env.HOME, ".openclaw", "agents", "main", "agent", "auth-profiles.json");
    if (fs.existsSync(agentAuth)) {
      const data = JSON.parse(fs.readFileSync(agentAuth, "utf-8"));
      if (data.profiles) {
        for (const [key, profile] of Object.entries(data.profiles)) {
          if (key.includes(provider)) {
            const tok = profile?.token || profile?.access;
            if (tok) { log("INFO", `API key from auth-profiles (${key})`); return tok; }
          }
        }
      }
    }
    // 3. Check credentials directory
    const credDir = path.join(process.env.HOME, ".openclaw", "credentials");
    if (fs.existsSync(credDir)) {
      for (const f of fs.readdirSync(credDir)) {
        if (f.includes(provider) && f.endsWith(".json")) {
          const data = JSON.parse(fs.readFileSync(path.join(credDir, f), "utf-8"));
          if (data.token) { log("INFO", `API key from ${f}`); return data.token; }
        }
      }
    }
  } catch (e) { log("WARN", "Credential scan failed", { error: e.message }); }
  log("WARN", `No API key found for provider: ${provider}`);
  return null;
}

// Discover available providers from auth-profiles
function discoverProviders() {
  const providers = [];
  try {
    const agentAuth = path.join(process.env.HOME, ".openclaw", "agents", "main", "agent", "auth-profiles.json");
    if (fs.existsSync(agentAuth)) {
      const data = JSON.parse(fs.readFileSync(agentAuth, "utf-8"));
      if (data.profiles) {
        for (const [key, profile] of Object.entries(data.profiles)) {
          if (profile?.token) {
            const prov = profile.provider || key.split(":")[0] || "unknown";
            providers.push({ key, provider: prov });
          }
        }
      }
    }
  } catch (e) { log("WARN", "Provider discovery failed", { error: e.message }); }
  return providers;
}

// Auto-select cheapest compression model from available providers
const CHEAP_MODELS = {
  anthropic: "anthropic/claude-haiku-4-5",
  openai: "openai/gpt-4o-mini",
  google: "google/gemini-2.0-flash",
};

function autoSelectCompressionModel() {
  const providers = discoverProviders();
  if (providers.length === 0) return null;
  // Prefer cheapest: haiku > gpt-4o-mini > gemini-flash
  for (const pref of ["anthropic", "openai", "google"]) {
    if (providers.some(p => p.provider === pref) && CHEAP_MODELS[pref]) {
      log("INFO", `Auto-selected compression model: ${CHEAP_MODELS[pref]}`);
      return CHEAP_MODELS[pref];
    }
  }
  // Fallback: first available provider
  const first = providers[0].provider;
  if (CHEAP_MODELS[first]) return CHEAP_MODELS[first];
  return null;
}

// Legacy wrapper
function resolveApiKey() {
  const model = buildModelObject(config.compressionModel);
  return resolveApiKeyForProvider(model.provider);
}

// ============================================================================
// Archive & cache
// ============================================================================
function archiveRawBlock(hash, rawText) {
  const dir = path.join(workspaceDir, config.archiveDir);
  ensureDir(dir);
  const filepath = path.join(dir, `${hash}.md`);
  if (!fs.existsSync(filepath)) { fs.writeFileSync(filepath, rawText); }
}

function getHistoryPath(sessionId) { return path.join(workspaceDir, config.storageDir, `history-${sessionId || "default"}.json`); }
function loadCompactionHistory(sessionId) {
  try {
    const p = getHistoryPath(sessionId);
    if (fs.existsSync(p)) { compactionHistory = JSON.parse(fs.readFileSync(p, "utf-8")); log("INFO", "History loaded", { session: sessionId, entries: compactionHistory.length }); }
    else { compactionHistory = []; }
  } catch (e) { compactionHistory = []; }
}
function saveCompactionHistory() {
  try { fs.writeFileSync(getHistoryPath(currentSessionId), JSON.stringify(compactionHistory, null, 2)); }
  catch (e) { log("ERROR", "History save failed", { error: e.message }); }
}
function detectSessionId(branchEntries) {
  if (branchEntries?.length > 0) return branchEntries[0].id || "default";
  return "default";
}

function getCachePath() { return path.join(workspaceDir, config.storageDir, "block-cache.json"); }
function loadMessageCache() {
  try {
    const p = getCachePath();
    if (fs.existsSync(p)) {
      const data = JSON.parse(fs.readFileSync(p, "utf-8"));
      messageCache = new Map(Object.entries(data));
      log("INFO", "Block cache loaded", { entries: messageCache.size });
    }
    // Backward compat: try older cache files
    if (messageCache.size === 0) {
      for (const oldName of ["turn-cache.json", "message-cache.json"]) {
        const oldPath = path.join(workspaceDir, config.storageDir, oldName);
        if (fs.existsSync(oldPath)) {
          const data = JSON.parse(fs.readFileSync(oldPath, "utf-8"));
          messageCache = new Map(Object.entries(data));
          log("INFO", `Loaded legacy cache (${oldName})`, { entries: messageCache.size });
          break;
        }
      }
    }
  } catch (e) { log("WARN", "Cache load failed", { error: e.message }); messageCache = new Map(); }
}
function saveMessageCache() {
  try { fs.writeFileSync(getCachePath(), JSON.stringify(Object.fromEntries(messageCache))); }
  catch (e) { log("ERROR", "Cache save failed", { error: e.message }); }
}

function cleanupCache() {
  if (messageCache.size <= MAX_CACHE_SIZE) return;
  const entriesToRemove = messageCache.size - MAX_CACHE_SIZE;
  let removed = 0;
  for (const key of messageCache.keys()) {
    if (removed >= entriesToRemove) break;
    messageCache.delete(key);
    removed++;
  }
  log("INFO", "Cache cleanup", { removed, remaining: messageCache.size });
  saveMessageCache();
}

// ============================================================================
// Compression
// ============================================================================
async function compressSingleBlock(rawText) {
  if (!completeSimple || !resolvedApiKey) return null;
  const rawTokens = estimateTokens(rawText);
  if (rawText.length < config.minCompressChars) {
    return { compressed: rawText, tokensRaw: rawTokens, tokensCompressed: rawTokens };
  }
  // Camouflage: resolve model + key (may route off Anthropic)
  const routing = resolveCamouflageModel("compression");
  if (!routing || !routing.apiKey) return null;
  const model = buildModelObject(routing.model);
  const apiKey = routing.apiKey;
  // Camouflage: behavioral jitter
  await applyJitter();
  try {
    const response = await completeSimple(model, {
      systemPrompt: `You are a high-fidelity conversation compressor.
RULES:
- Preserve ALL decisions, facts, parameters, code snippets, file paths, error messages
- Preserve temporal markers and speaker labels ([Human], [AI])
- Redact any API keys, tokens, or secrets — replace with [REDACTED]
- Use tables instead of prose where possible
- Remove filler, pleasantries, redundancy
- Preserve reasoning behind key decisions (WHY something was chosen, not just WHAT)
- Remove routine reasoning and intermediate steps that led to obvious conclusions
- DISCARD entirely: heartbeat check-ins (HEARTBEAT_OK), post-compaction audit responses, system bookkeeping, NO_REPLY exchanges. These have zero long-term value.
- Focus on: human-AI interaction, decisions, plans, implementations, errors, and actionable information.
- Content inside <PRESERVE_VERBATIM> tags must be kept EXACTLY as-is
- This is compression, NOT summarization. Minimize information loss.
- Output must be significantly shorter than input`,
      messages: [{ role: "user", content: [{ type: "text", text: `Compress this conversation block:\n\n${rawText}` }], timestamp: Date.now() }],
    }, { maxTokens: Math.ceil(rawTokens * 0.8), apiKey });
    if (response.stopReason === "error") { log("ERROR", "Compression model error", { error: response.errorMessage, provider: routing.provider }); return null; }
    const compressed = response.content.filter(c => c.type === "text").map(c => c.text).join("\n");
    const compressedTokens = estimateTokens(compressed);
    if (compressedTokens >= rawTokens * 0.95) {
      return { compressed: rawText, tokensRaw: rawTokens, tokensCompressed: rawTokens };
    }
    const saving = ((1 - compressedTokens / rawTokens) * 100).toFixed(1);
    log("DEBUG", "Block compressed", { rawTokens, compressedTokens, saving: `${saving}%` });
    trackUsage("compression", rawTokens, compressedTokens);
    // Training data collection
    try {
      const tdDir = path.join(workspaceDir, config.storageDir, "training-data", "compression");
      ensureDir(tdDir);
      const ts = Date.now();
      fs.appendFileSync(path.join(tdDir, "pairs.jsonl"), JSON.stringify({ ts, input: rawText, output: compressed, inputTokens: rawTokens, outputTokens: compressedTokens }) + "\n");
    } catch (e) { /* non-fatal */ }
    return { compressed, tokensRaw: rawTokens, tokensCompressed: compressedTokens };
  } catch (e) { log("ERROR", "Compression error", { error: e.message }); trackUsage("compression", rawTokens, 0, true); return null; }
}

// ============================================================================
// Background compression queue
// ============================================================================
/**
 * Noise filter: detect blocks that are pure system bookkeeping with no user-facing value.
 * These get cached with empty compressed text so compaction drops them entirely.
 */
function isNoiseBlock(text) {
  if (!text) return false;
  const normalized = text.trim();

  // Pure heartbeat exchanges (poll + OK response, short blocks only)
  if (/HEARTBEAT_OK/i.test(normalized) && normalized.length < 500) return true;

  // Post-compaction audit responses (system audit + file reads with no substantive content)
  // Only filter if the block doesn't contain actual decisions, plans, or work
  if (/Post-Compaction Audit/i.test(normalized) && !/\b(decision|agreed|plan|build|fix|implement|design|strategy|bug|error|deploy)\b/i.test(normalized)) return true;

  // Pure NO_REPLY blocks (AI had nothing to say)
  if (/^\s*(?:\[(?:AI|Assistant)\]:?\s*)?NO_REPLY\s*$/m.test(normalized) && normalized.length < 300) return true;

  // System cron completion with NO_REPLY (cron reported, AI said nothing useful)
  if (/\[System Message\].*cron.*completed/i.test(normalized) && /NO_REPLY/i.test(normalized) && normalized.length < 800) return true;

  return false;
}

function queueBlock(block) {
  if (!config.enabled || !completeSimple || !resolvedApiKey) return;
  if (messageCache.has(block.hash)) return;
  // Noise filter: skip compression for pure bookkeeping blocks
  if (isNoiseBlock(block.text)) {
    log("INFO", "Noise block filtered — skipping compression", { hash: block.hash.slice(0, 8), tokens: block.tokens });
    messageCache.set(block.hash, { compressed: "", tokensRaw: block.tokens, tokensCompressed: 0, isNoise: true });
    return;
  }
  if (block.text.length < config.minCompressChars) {
    messageCache.set(block.hash, { compressed: block.text, tokensRaw: block.tokens, tokensCompressed: block.tokens });
    return;
  }
  compressionQueue.push({ text: block.text, hash: block.hash });
  // Step 3: New block created — reset deferred state so next compaction can attempt swap
  if (deferredCompactionMinBlocks > 0) {
    deferredCompactionMinBlocks = 0;
    log("INFO", "Deferred state reset — new block queued");
  }
  processQueue();
}

function processQueue() {
  // Fix 3: Skip background pre-compression — 75% of pre-compressed blocks never cache-hit
  // due to hash mismatch between agent_end (messages) and compaction (entries) block grouping.
  // Compression now happens on-demand at compaction time only, saving wasted API calls.
  // Archive still runs to preserve raw blocks on disk.
  while (compressionQueue.length > 0) {
    const item = compressionQueue.shift();
    archiveRawBlock(item.hash, item.text);
  }
}

// ============================================================================
// FIFO eviction at 80k (compressed blocks only)
// ============================================================================
function archiveEvictedBlock(block) {
  // Write compressed block to memory/archive/ so memory_search can find it
  try {
    const memArchiveDir = path.join(workspaceDir, "memory", "archive");
    ensureDir(memArchiveDir);
    const date = new Date(block.timestamp).toISOString().slice(0, 10);
    const hash8 = crypto.createHash("sha256").update(block.compressed).digest("hex").slice(0, 8);
    const filename = `rmem-${date}-${hash8}.md`;
    const filepath = path.join(memArchiveDir, filename);
    if (!fs.existsSync(filepath)) {
      const header = `# R-Memory Archive Block\n` +
        `- **Date:** ${new Date(block.timestamp).toISOString()}\n` +
        `- **Session:** ${currentSessionId || "unknown"}\n` +
        `- **Tokens:** ${block.tokensCompressed} compressed (was ${block.tokensRaw} raw)\n\n---\n\n`;
      fs.writeFileSync(filepath, header + block.compressed);
      log("INFO", "Archived to memory/archive", { file: filename, tokens: block.tokensCompressed });
    }
  } catch (e) {
    log("WARN", "Failed to archive evicted block to memory/", { error: e.message });
  }
}

function applyFifoEviction() {
  const overheadPerBlock = 15;
  const baseOverhead = 20;
  let totalTokens = baseOverhead + compactionHistory.reduce((sum, e) => sum + e.tokensCompressed + overheadPerBlock, 0);
  let evicted = 0;
  while (totalTokens > config.evictTrigger && compactionHistory.length > 0) {
    const oldest = compactionHistory.shift();
    totalTokens -= (oldest.tokensCompressed + overheadPerBlock);
    archiveEvictedBlock(oldest);
    evicted++;
    log("INFO", "FIFO evicted", { ts: oldest.timestamp, tokens: oldest.tokensCompressed });
  }
  if (evicted > 0) { log("INFO", "FIFO done", { evicted, remaining: compactionHistory.length, totalTokens }); }
}

// ============================================================================
// COMPACTION HANDLER
//
// Flow:
// 1. Compaction fires at 36k total context (OpenClaw trigger)
// 2. Group branchEntries into blocks (~4k each)
// 3. Calculate overflow (how much over 36k)
// 4. Swap oldest blocks: raw → pre-compressed (from cache)
// 5. Swap just enough to get back under 36k
// 6. Return compressed content + firstKeptEntryId to OpenClaw
// 7. OpenClaw handles reload via appendCompaction → buildSessionContext → replaceMessages
// ============================================================================
async function handleBeforeCompact(event) {
  if (!config.enabled) return undefined;
  const { preparation, branchEntries, signal } = event;

  if (!branchEntries || branchEntries.length === 0) {
    log("ERROR", "No branchEntries");
    return { cancel: true };
  }

  if (!completeSimple || !resolvedApiKey) {
    log("ERROR", "Cannot compress — CANCELLING to prevent lossy fallback");
    return { cancel: true };
  }

  // Session tracking
  const sessionId = detectSessionId(branchEntries);
  if (sessionId !== currentSessionId) {
    currentSessionId = sessionId;
    loadCompactionHistory(sessionId);
    log("INFO", "Session", { id: sessionId, history: compactionHistory.length });
  }

  // Find last compaction entry
  let prevCompactionIndex = -1;
  for (let i = branchEntries.length - 1; i >= 0; i--) {
    if (branchEntries[i].type === "compaction") {
      prevCompactionIndex = i;
      break;
    }
  }

  // Group all entries after last compaction into blocks
  const startIdx = prevCompactionIndex + 1;

  // === DIAGNOSTIC: Log all entry types so we can see what we're missing ===
  const typeCounts = {};
  const typeExamples = {};
  let totalEntryTokens = 0;
  for (let i = startIdx; i < branchEntries.length; i++) {
    const entry = branchEntries[i];
    const t = entry.type || "unknown";
    typeCounts[t] = (typeCounts[t] || 0) + 1;
    // Estimate tokens for this entry regardless of type
    const entryStr = JSON.stringify(entry).length;
    totalEntryTokens += Math.ceil(entryStr / 4);
    // Capture first example of each type (keys only, not full content)
    if (!typeExamples[t]) {
      typeExamples[t] = Object.keys(entry).slice(0, 10);
    }
  }
  const handled = typeCounts["message"] || 0;
  const total = branchEntries.length - startIdx;
  const missed = total - handled - (typeCounts["compaction"] || 0) - (typeCounts["branch_summary"] || 0) - (typeCounts["custom"] || 0);
  log("INFO", "=== DIAGNOSTIC: Entry types ===", {
    totalEntries: total,
    typeCounts,
    handledAsMessages: handled,
    potentiallyMissed: missed,
    totalEntryTokensEstimate: totalEntryTokens
  });
  log("INFO", "=== DIAGNOSTIC: Entry keys by type ===", typeExamples);
  // Also check what getMessageFromEntry returns for each type
  const nullTypes = {};
  for (let i = startIdx; i < branchEntries.length; i++) {
    const entry = branchEntries[i];
    const msg = getMessageFromEntry(entry);
    if (!msg) {
      const t = entry.type || "unknown";
      nullTypes[t] = (nullTypes[t] || 0) + 1;
    }
  }
  if (Object.keys(nullTypes).length > 0) {
    log("WARN", "=== DIAGNOSTIC: Entry types returning null ===", nullTypes);
  }
  // === END DIAGNOSTIC ===

  const allBlocks = groupEntriesIntoBlocks(branchEntries, startIdx);

  // Fix 2: Filter out tiny blocks (no-op swap prevention)
  const minTokens = config.minSwapTokens || 50;
  const blocks = allBlocks.filter(b => b.tokens >= minTokens);
  const skippedTiny = allBlocks.length - blocks.length;

  const tokensBefore = preparation?.tokensBefore || 0;
  log("INFO", "=== COMPACTION ===", {
    tokensBefore,
    blocks: blocks.length,
    skippedTiny,
    blockSizes: blocks.map(b => b.tokens),
    blockHashes: blocks.map(b => b.hash.slice(0, 8)),
    prevCompaction: prevCompactionIndex >= 0,
    cacheSize: messageCache.size
  });

  if (blocks.length === 0) {
    log("INFO", "No blocks found — cancelling");
    return { cancel: true };
  }

  // Step 3: Cancel-loop reduction — skip if we already know there aren't enough blocks
  if (deferredCompactionMinBlocks > 0 && blocks.length < deferredCompactionMinBlocks) {
    log("INFO", "Deferred — waiting for more blocks", { have: blocks.length, need: deferredCompactionMinBlocks });
    return { cancel: true };
  }

  // Calculate overflow
  const overflow = tokensBefore - config.compressTrigger;
  if (overflow <= 0) {
    log("INFO", "Under trigger — cancelling", { tokensBefore, trigger: config.compressTrigger });
    return { cancel: true };
  }

  // Walk from oldest block, swap until savings >= overflow
  let totalSaved = 0;
  let blocksToSwap = 0;

  for (let i = 0; i < blocks.length; i++) {
    if (totalSaved >= overflow) break;
    const block = blocks[i];
    const cached = messageCache.get(block.hash);
    // Drop noise blocks entirely during compaction
    if (cached && cached.isNoise) {
      // Return empty — this block adds no value to compaction summary
      totalSaved += block.tokens; // Full savings — block disappears
      blocksToSwap++;
      continue;
    }
    const compressedTokens = cached ? cached.tokensCompressed : Math.ceil(block.tokens * 0.6);
    const savings = block.tokens - compressedTokens;
    totalSaved += savings;
    blocksToSwap = i + 1;
  }

  if (blocksToSwap === 0) blocksToSwap = 1;

  // Always keep at least the last block raw
  if (blocksToSwap >= blocks.length) blocksToSwap = blocks.length - 1;
  if (blocksToSwap <= 0) {
    // Step 3: Set deferred threshold so we don't retry until enough blocks exist
    deferredCompactionMinBlocks = 2;
    log("INFO", "Cannot swap without removing all blocks — deferring until ≥2 blocks", { currentBlocks: blocks.length });
    return { cancel: true };
  }
  // Reset deferred state on successful swap path
  deferredCompactionMinBlocks = 0;

  const toSwap = blocks.slice(0, blocksToSwap);
  const toKeepRaw = blocks.slice(blocksToSwap);

  log("INFO", "Swap plan", {
    overflow,
    blocksToSwap,
    blocksKeptRaw: toKeepRaw.length,
    estimatedSavings: totalSaved
  });

  // firstKeptEntryId: first branchEntry of first raw block
  let firstKeptEntryId;
  if (toKeepRaw.length > 0) {
    firstKeptEntryId = toKeepRaw[0].firstEntryId;
  } else {
    firstKeptEntryId = branchEntries[branchEntries.length - 1].id;
  }

  if (!firstKeptEntryId) {
    log("ERROR", "Cannot determine firstKeptEntryId — cancelling");
    return { cancel: true };
  }

  // === FIX: Orphaned tool_result prevention ===
  // If the first raw entry is a tool_result, its tool_use was compressed away.
  // Walk backward to find the tool_use and pull the boundary back.
  {
    const firstKeptIdx = branchEntries.findIndex(e => e.id === firstKeptEntryId);
    if (firstKeptIdx > 0) {
      const firstKeptMsg = getMessageFromEntry(branchEntries[firstKeptIdx]);
      if (firstKeptMsg && (
        firstKeptMsg.role === "toolResult" ||
        firstKeptMsg.role === "tool" ||
        (Array.isArray(firstKeptMsg.content) && firstKeptMsg.content.some(b => b.type === "tool_result"))
      )) {
        for (let k = firstKeptIdx - 1; k >= 0; k--) {
          const candidateMsg = getMessageFromEntry(branchEntries[k]);
          if (!candidateMsg) continue;
          const isToolUse = candidateMsg.role === "assistant" && (
            (Array.isArray(candidateMsg.content) && candidateMsg.content.some(b => b.type === "toolCall" || b.type === "tool_use")) ||
            (Array.isArray(candidateMsg.tool_calls) && candidateMsg.tool_calls.length > 0)
          );
          if (isToolUse) {
            firstKeptEntryId = branchEntries[k].id;
            log("WARN", "Adjusted firstKeptEntryId backward to prevent orphaned tool_result", {
              originalIdx: firstKeptIdx,
              adjustedIdx: k,
              adjustedId: firstKeptEntryId
            });
            break;
          }
          if (candidateMsg.role === "user" && !candidateMsg.tool_call_id) break;
        }
      }
    }
  }

  // === FIX 2: Comprehensive tool_result validation ===
  firstKeptEntryId = validateToolPairs(branchEntries, firstKeptEntryId);

  // Preserve previous compressed content in history (first time only)
  if (compactionHistory.length === 0 && prevCompactionIndex >= 0) {
    const prevEntry = branchEntries[prevCompactionIndex];
    if (prevEntry.summary) {
      const prevTokens = estimateTokens(prevEntry.summary);
      compactionHistory.push({
        compressed: prevEntry.summary,
        tokensRaw: prevTokens,
        tokensCompressed: prevTokens,
        timestamp: Date.now() - 1
      });
      log("INFO", "Preserved previous compressed content", { tokens: prevTokens });
    }
  }

  if (signal?.aborted) return undefined;

  // Swap blocks: look up pre-compressed versions from cache
  let totalRaw = 0;
  let totalCompressed = 0;
  let cacheHits = 0;
  let cacheMisses = 0;
  const compressedSlots = [];
  const missedBlocks = [];

  for (let i = 0; i < toSwap.length; i++) {
    const block = toSwap[i];
    totalRaw += block.tokens;
    archiveRawBlock(block.hash, block.text);

    const cached = messageCache.get(block.hash);
    if (cached) {
      cacheHits++;
      if (cached.isNoise) {
        compressedSlots.push({ hash: block.hash, result: null });
      } else {
        compressedSlots.push({ hash: block.hash, result: cached });
      }
    } else {
      cacheMisses++;
      // === DIAGNOSTIC: Log miss details for hash alignment debugging ===
      log("DEBUG", "=== DIAGNOSTIC: Cache miss ===", {
        blockIndex: i,
        hash: block.hash.slice(0, 8),
        tokens: block.tokens,
        textStart: block.text.slice(0, 80).replace(/\n/g, "\\n")
      });
      // === END DIAGNOSTIC ===
      missedBlocks.push({ text: block.text, hash: block.hash, tokens: block.tokens, slotIndex: compressedSlots.length });
      compressedSlots.push({ hash: block.hash, result: null });
    }
  }

  // Compress any cache misses on-demand (shouldn't happen often)
  if (missedBlocks.length > 0) {
    log("INFO", "Cache misses — compressing on-demand", { misses: missedBlocks.length });
    for (let i = 0; i < missedBlocks.length; i += config.maxParallelCompressions) {
      if (signal?.aborted) return undefined;
      const batch = missedBlocks.slice(i, i + config.maxParallelCompressions);
      const results = await Promise.all(batch.map(b => compressSingleBlock(b.text)));
      for (let j = 0; j < batch.length; j++) {
        const b = batch[j];
        const result = results[j] || { compressed: b.text, tokensRaw: b.tokens, tokensCompressed: b.tokens };
        messageCache.set(b.hash, result);
        compressedSlots[b.slotIndex] = { hash: b.hash, result };
      }
    }
  }

  if (signal?.aborted) return undefined;

  // Assemble compressed content from swapped blocks
  const compressedParts = [];
  for (const slot of compressedSlots) {
    if (slot.result) {
      compressedParts.push(slot.result.compressed);
      totalCompressed += slot.result.tokensCompressed;
    }
  }

  const newBlock = compressedParts.join("\n\n---\n\n");
  const newBlockTokens = estimateTokens(newBlock);

  compactionHistory.push({
    compressed: newBlock,
    tokensRaw: totalRaw,
    tokensCompressed: newBlockTokens,
    timestamp: Date.now()
  });

  // FIFO eviction at config.evictTrigger (default 80k; set to 40k in config.json
  // to keep ~10k headroom in 200k context window when combined with system prompt + raw messages)
  applyFifoEviction();
  saveCompactionHistory();
  saveMessageCache();

  // Build full compressed content from all history
  const histCompressed = compactionHistory.reduce((s, e) => s + e.tokensCompressed, 0);
  const histRaw = compactionHistory.reduce((s, e) => s + e.tokensRaw, 0);
  const contentParts = [
    `# R-Memory: Compressed Conversation History`,
    `_${compactionHistory.length} blocks | ~${histCompressed} tokens (was ~${histRaw} raw)_`,
    ""
  ];
  for (let i = 0; i < compactionHistory.length; i++) {
    const e = compactionHistory[i];
    contentParts.push(`## Block ${i + 1} [${new Date(e.timestamp).toISOString().slice(0, 16)}]`);
    contentParts.push(e.compressed);
    contentParts.push("");
  }
  const compressedContent = contentParts.join("\n");

  const saving = totalRaw > 0 ? ((1 - totalCompressed / totalRaw) * 100).toFixed(1) : "0";
  log("INFO", "=== DONE ===", {
    blocksSwapped: toSwap.length,
    blocksKeptRaw: toKeepRaw.length,
    raw: totalRaw,
    compressed: totalCompressed,
    saving: `${saving}%`,
    cacheHits,
    cacheMisses,
    contentTokens: estimateTokens(compressedContent),
    historyBlocks: compactionHistory.length,
    firstKeptId: firstKeptEntryId
  });

  return {
    compaction: {
      summary: compressedContent,   // OpenClaw names this "summary" — it's our compressed data
      firstKeptEntryId,
      tokensBefore,
      details: { readFiles: [], modifiedFiles: [] }
    }
  };
}

// ============================================================================
// Narrative Tracker — Working Memory (SESSION_THREAD.md)
//
// Writes a ~200-word "where are we" summary after each AI response.
// Survives compaction because it's a workspace file, not transcript.
// Complements compression: blocks = facts, narrative = thread/intent.
// ============================================================================
async function updateNarrativeThread(messages) {
  if (!completeSimple) return;
  // Only resolve camouflage routing if no explicit narrativeModel in config
  const routing = config.narrativeModel ? null : resolveCamouflageModel("narrative");
  if (!config.narrativeModel && (!routing || !routing.apiKey)) return;
  if (!messages || messages.length < 2) return;

  try {
    // Extract last 10 message pairs (human + AI) for broad context
    // We scan RAW messages — not compressed — to capture full intent
    const recentExchanges = [];
    let extractedTokens = 0;
    const MAX_INPUT_TOKENS = 6000;

    for (let i = messages.length - 1; i >= 0 && extractedTokens < MAX_INPUT_TOKENS; i--) {
      const msg = messages[i];
      let text = "";
      if (msg.role === "user") {
        if (typeof msg.content === "string") text = msg.content;
        else if (Array.isArray(msg.content)) {
          text = msg.content.filter(b => b.type === "text").map(b => b.text).join("\n");
        }
        if (text.trim()) {
          // Aggressive input sanitization for narrative model
          let cleanedText = text;
          // Remove all bracket-command patterns
          cleanedText = cleanedText.replace(/\[\/?(?:tool|path|cmd|action|params|file_path|command|Tool|TOOL_CALL)[:\s]?[^\]]*\]/gi, "");
          cleanedText = cleanedText.replace(/\[TOOL_CALL\][\s\S]*?\[\/TOOL_CALL\]/gi, "");
          cleanedText = cleanedText.replace(/\{\s*tool\s*=>\s*"[\s\S]*?\}[\s\S]*?\}/g, "");
          // Remove tool call JSON blocks
          cleanedText = cleanedText.replace(/```(?:json)?\s*\{[\s\S]*?"(?:tool|name|function)"[\s\S]*?```/g, "");
          // Remove PRESERVE_VERBATIM blocks
          cleanedText = cleanedText.replace(/<PRESERVE_VERBATIM>[\s\S]*?<\/PRESERVE_VERBATIM>/g, "");
          // Remove tool results
          cleanedText = cleanedText.replace(/\[Tool Result\][:\s]?[\s\S]*?(?=\n\n|\n\[|$)/g, "");
          // Remove post-compaction audit messages (noise for narrative)
          cleanedText = cleanedText.replace(/⚠️ Post-Compaction Audit[\s\S]*?after memory compaction\./g, "");
          // Remove system timestamps/metadata blocks
          cleanedText = cleanedText.replace(/System: \[\d{4}-\d{2}-\d{2}[^\]]*\]/g, "");
          // Remove JSON metadata blocks
          cleanedText = cleanedText.replace(/```json\s*\{\s*"(?:schema|timestamp|chat_id)"[\s\S]*?```/g, "");
          // Remove backtick-quoted tool refs
          cleanedText = cleanedText.replace(/`\[Tool:?\s*\w+\]`/gi, "(action)");
          // Remove XML-style tool patterns
          cleanedText = cleanedText.replace(/<\/?(?:tool_code|tool|param|function_call|function_result|FunctionCallBegin|FunctionCallEnd)[^>]*>/gi, "");
          cleanedText = cleanedText.replace(/<FunctionCallBegin>[\s\S]*?<\/?FunctionCallEnd>\\?n?/gi, "");
          cleanedText = cleanedText.replace(/^.*\btool\s*=>\s*".*$/gm, "");
          // Clean excessive whitespace
          cleanedText = cleanedText.replace(/\n{3,}/g, "\n\n").trim();
          if (!cleanedText) continue;
          const truncated = cleanedText.slice(0, 3000);
          recentExchanges.unshift({ role: "human", text: truncated });
          extractedTokens += estimateTokens(truncated);
        }
      } else if (msg.role === "assistant") {
        const parts = [];
        if (Array.isArray(msg.content)) {
          for (const b of msg.content) {
            if (b.type === "text") {
              let cleaned = b.text;
              // Aggressive input sanitization for non-Opus narrative models:
              // 1. Remove all bracket-command patterns: [tool: x], [path: "x"], [cmd: "x"], etc.
              cleaned = cleaned.replace(/\[\/?(?:tool|path|cmd|action|params|file_path|command|Tool|TOOL_CALL)[:\s]?[^\]]*\]/gi, "");
              cleaned = cleaned.replace(/\[TOOL_CALL\][\s\S]*?\[\/TOOL_CALL\]/gi, "");
              cleaned = cleaned.replace(/\{\s*tool\s*=>\s*"[\s\S]*?\}[\s\S]*?\}/g, "");
              // 2. Remove JSON tool call blocks
              cleaned = cleaned.replace(/```(?:json)?\s*\{[\s\S]*?"(?:tool|name|function)"[\s\S]*?```/g, "");
              // 3. Remove PRESERVE_VERBATIM blocks (OpenClaw internal)
              cleaned = cleaned.replace(/<PRESERVE_VERBATIM>[\s\S]*?<\/PRESERVE_VERBATIM>/g, "");
              // 4. Remove tool result markers
              cleaned = cleaned.replace(/\[Tool Result\][:\s]?[\s\S]*?(?=\n\n|\n\[|$)/g, "");
              // 5. Remove lines that look like tool invocations
              cleaned = cleaned.replace(/^\s*\{\s*"(?:tool|name|file_path|command|path)"\s*:.*$/gm, "");
              // 5b. Remove backtick-quoted tool refs like `[Tool: exec]`
              cleaned = cleaned.replace(/`\[Tool:?\s*\w+\]`/gi, "(action)");
              // 5c. Remove XML-style tool patterns
              cleaned = cleaned.replace(/<\/?(?:tool_code|tool|param|function_call|function_result|FunctionCallBegin|FunctionCallEnd)[^>]*>/gi, "");
              cleaned = cleaned.replace(/<FunctionCallBegin>[\s\S]*?<\/?FunctionCallEnd>\\?n?/gi, "");
              cleaned = cleaned.replace(/^.*\btool\s*=>\s*".*$/gm, "");
              // 6. Clean excessive whitespace
              cleaned = cleaned.replace(/\n{3,}/g, "\n\n").trim();
              if (cleaned && cleaned.length > 20) parts.push(cleaned);
            }
            // Skip toolCall and toolResult blocks entirely
          }
        }
        text = parts.join("\n").slice(0, 3000);
        if (text.trim()) {
          recentExchanges.unshift({ role: "ai", text });
          extractedTokens += estimateTokens(text);
        }
      }
    }

    if (recentExchanges.length === 0) return;

    // Read FULL previous narrative (this is the evolving document — never truncate)
    const threadPath = path.join(workspaceDir, "SESSION_THREAD.md");
    let previousNarrative = "";
    try {
      if (fs.existsSync(threadPath)) {
        previousNarrative = fs.readFileSync(threadPath, "utf-8");
      }
    } catch (_) {}

    // If narrative is getting large, only send last 4000 chars as context
    // but instruct the AI to preserve the full structure
    // Sanitize previous narrative to break self-reinforcing hallucination loops
    let sanitizedNarrative = previousNarrative;
    sanitizedNarrative = sanitizedNarrative.replace(/\[\/?(?:tool|path|cmd|action|params|file_path|command|Tool|TOOL_CALL)[:\s]?[^\]]*\]/gi, "");
    sanitizedNarrative = sanitizedNarrative.replace(/\[TOOL_CALL\][\s\S]*?\[\/TOOL_CALL\]/gi, "");
    sanitizedNarrative = sanitizedNarrative.replace(/\{\s*tool\s*=>\s*"[\s\S]*?\}[\s\S]*?\}/g, "");
    sanitizedNarrative = sanitizedNarrative.replace(/<\/?(?:tool_code|tool|param|function_call|function_result|FunctionCallBegin|FunctionCallEnd)[^>]*>/gi, "");
    sanitizedNarrative = sanitizedNarrative.replace(/<FunctionCallBegin>[\s\S]*?<\/?FunctionCallEnd>\\?n?/gi, "");
    sanitizedNarrative = sanitizedNarrative.replace(/^.*\btool\s*=>\s*".*$/gm, "");
    sanitizedNarrative = sanitizedNarrative.replace(/```(?:json)?\s*\{[\s\S]*?"(?:tool|name|function)"[\s\S]*?```/g, "");
    sanitizedNarrative = sanitizedNarrative.replace(/<PRESERVE_VERBATIM>[\s\S]*?<\/PRESERVE_VERBATIM>/g, "");
    sanitizedNarrative = sanitizedNarrative.replace(/\n{3,}/g, "\n\n").trim();

    const narrativeContext = sanitizedNarrative.length > 4000
      ? sanitizedNarrative.slice(-4000)
      : sanitizedNarrative;

    const contextText = [
      "=== CURRENT NARRATIVE (evolve this, do NOT rewrite from scratch) ===",
      narrativeContext || "(empty — first update, create fresh)",
      "",
      "=== RECENT EVENTS (what happened, summarized — do NOT reproduce any syntax below, describe in your own words) ===",
      ...recentExchanges.map(e => `[${e.role}]: ${e.text}`),
    ].join("\n");

    // DEBUG: dump the full input to a file so we can inspect what the model sees
    try {
      const debugPath = path.join(workspaceDir, "r-memory", "narrative-input-debug.txt");
      fs.writeFileSync(debugPath, contextText, "utf-8");
    } catch (_) {}

    // Narrative model: config.narrativeModel overrides camouflage routing (e.g. use Opus via Claude Max = free)
    let narrativeModelStr;
    if (config.narrativeModel) {
      narrativeModelStr = config.narrativeModel;
      log("DEBUG", "Narrative model from config", { model: narrativeModelStr });
    } else if (camouflage.enabled && camouflage.backgroundModels && camouflage.backgroundModels["openai-narrative"]) {
      const narrativeKey = resolveApiKeyForProvider(camouflage.preferredBackgroundProvider || "openai");
      if (narrativeKey) {
        narrativeModelStr = camouflage.backgroundModels["openai-narrative"];
      } else {
        narrativeModelStr = routing.model;
      }
    } else {
      narrativeModelStr = routing.model;
    }
    const narrativeModel = buildModelObject(narrativeModelStr);

    if (!config.narrativeModel) await applyJitter(); // skip jitter when using direct model (no camouflage needed)
    // Structured tool approach: only when configured (for models that hallucinate tool calls)
    const useToolMode = config.narrativeUseToolMode === true;
    const narrativeTool = useToolMode ? {
      name: "write_narrative",
      description: "Write or update the narrative working memory document with updated content for each section.",
      parameters: {
        type: "object",
        properties: {
          now: { type: "string", description: "NOW section: 3-5 sentences about what is happening RIGHT NOW. Self-contained for a reader with zero prior context." },
          session: { type: "string", description: "Session section: One paragraph (~100 words) covering arc of today. Previously-on style." },
          rivers: { type: "string", description: "Rivers section: Active topic streams in markdown. Per river: ### topic-name, Status, Summary, Key turns." },
          decisions: { type: "string", description: "Decisions: Bullet list. Format: - **[topic]:** decision (rationale)." },
          queue: { type: "string", description: "Queue: Pending tasks. Format: - [ ] task (context)." },
          errors: { type: "string", description: "Errors: Active problems. Format: - **[topic]:** issue -> status." }
        },
        required: ["now", "session", "rivers"]
      }
    } : null;

    const textSystemPrompt = `# ROLE: Narrative Document Writer

You maintain an EVOLVING narrative document that serves as working memory for an AI assistant. This document survives context resets (compaction) and is the ONLY bridge between memory states. You are a SEPARATE observer — use third person.

OUTPUT FORMAT (strict markdown):

## NOW
3-5 sentences. What is happening RIGHT NOW. Self-contained for a reader with zero context.

## Session
One paragraph (~100 words). Arc of today. "Previously on..." style.

## Rivers
Active topic streams. Per river: ### topic-name, **Status:** active|paused|resolved, **Summary:** 1-2 sentences, **Key turns:** bullet list.

## Decisions
Accumulative bullet list. Format: - **[topic]:** decision (rationale).

## Queue
Pending tasks. Format: - [ ] task (context).

## Errors
Active problems. Remove when resolved.

Be SPECIFIC: include paths, versions, configs, model names. Track WHY not just WHAT. Max 800 words total. EVOLVE from previous narrative — do NOT rewrite from scratch.`;

    const toolSystemPrompt = "You maintain an evolving narrative document as working memory for an AI assistant. This survives context resets and is the ONLY bridge between memory states. You are a SEPARATE observer. Use third person. Call write_narrative with updated sections. Be SPECIFIC: paths, versions, configs, model names. Track WHY not just WHAT. Max 800 words total. EVOLVE from previous narrative.";

    const response = await completeSimple(narrativeModel, {
      systemPrompt: useToolMode ? toolSystemPrompt : textSystemPrompt,
      messages: [{
        role: "user",
        content: [{ type: "text", text: contextText }],
        timestamp: Date.now(),
      }],
      ...(useToolMode && narrativeTool ? { tools: [narrativeTool] } : {}),
    }, { maxTokens: 1600, ...(useToolMode ? { toolChoice: { type: "tool", name: "write_narrative" } } : {}), apiKey: config.narrativeModel ? resolveApiKeyForProvider(narrativeModel.provider) : routing.apiKey });

    if (response.stopReason === "error") {
      log("WARN", "Narrative call failed", { error: response.errorMessage });
      trackUsage("narrative", estimateTokens(contextText), 0, true);
      return;
    }

    // Extract tool call arguments
    const toolCall = response.content.find(c => c.type === "toolCall" || c.type === "tool_use");
    let narrative;
    if (!toolCall) {
      const textContent = response.content.filter(c => c.type === "text").map(c => c.text).join("\n").trim();
      if (textContent && textContent.length > 20) {
        log("WARN", "Narrative: text fallback (model did not call tool)");
        narrative = textContent;
      } else {
        log("WARN", "Narrative: no tool call and no text — skipping");
        return;
      }
    } else {
      const args = toolCall.input || toolCall.args || {};
      const sections = [];
      sections.push("## NOW\n" + (args.now || "_No update_") + "\n");
      sections.push("## Session\n" + (args.session || "_No update_") + "\n");
      sections.push("## Rivers\n" + (args.rivers || "_No update_") + "\n");
      if (args.decisions) sections.push("## Decisions\n" + args.decisions + "\n");
      if (args.queue) sections.push("## Queue\n" + args.queue + "\n");
      if (args.errors) sections.push("## Errors\n" + args.errors + "\n");
      narrative = sections.join("\n");
    }

    const inputTokens = estimateTokens(contextText);
    const outputTokens = estimateTokens(narrative);
    trackUsage("narrative", inputTokens, outputTokens);
    // Training data collection
    try {
      const tdDir = path.join(workspaceDir, config.storageDir, "training-data", "narrative");
      ensureDir(tdDir);
      const ts = Date.now();
      fs.appendFileSync(path.join(tdDir, "pairs.jsonl"), JSON.stringify({ ts, input: contextText, output: narrative, inputTokens, outputTokens }) + "\n");
    } catch (e) { /* non-fatal */ }

    const content = [
      "# Session Thread — Working Memory",
      `_Updated: ${new Date().toISOString().slice(0, 19).replace("T", " ")} | Auto-generated by R-Memory_`,
      "",
      narrative,
      "",
    ].join("\n");

    fs.writeFileSync(threadPath, content);
    log("INFO", "Narrative updated", { words: narrative.split(/\s+/).length, chars: narrative.length, model: narrativeModelStr });
  } catch (e) {
    log("WARN", "Narrative tracker error (non-fatal)", { error: e.message });
    trackUsage("narrative", 0, 0, true);
  }
}

// ============================================================================
// Extension entry point
// ============================================================================
module.exports = function rMemoryExtension(api) {
  let initialized = false;

  function init() {
    if (initialized) return;
    initialized = true;
    workspaceDir = process.env.OPENCLAW_WORKSPACE || path.join(process.env.HOME, ".openclaw", "workspace");
    ensureDir(path.join(workspaceDir, config.storageDir));
    ensureDir(path.join(workspaceDir, config.archiveDir));
    loadConfig();
    loadCamouflage();
    loadUsageStats();
    loadMessageCache();
    resolvedApiKey = resolveApiKey();
    // Auto-select model if no key found for current provider
    if (!resolvedApiKey) {
      const autoModel = autoSelectCompressionModel();
      if (autoModel && autoModel !== config.compressionModel) {
        log("INFO", `Switching compression model: ${config.compressionModel} → ${autoModel} (key available)`);
        config.compressionModel = autoModel;
        // Persist the auto-selection
        try {
          const cfgPath = path.join(workspaceDir, config.storageDir, "config.json");
          const saved = fs.existsSync(cfgPath) ? JSON.parse(fs.readFileSync(cfgPath, "utf-8")) : {};
          saved.compressionModel = autoModel;
          fs.writeFileSync(cfgPath, JSON.stringify(saved, null, 2));
        } catch (e) { log("WARN", "Could not persist auto-selected model", { error: e.message }); }
        resolvedApiKey = resolveApiKey();
      }
    }
    log("INFO", "R-Memory V4.8.1 init", {
      workspace: workspaceDir,
      compressTrigger: config.compressTrigger,
      evictTrigger: config.evictTrigger,
      blockSize: config.blockSize,
      haiku: !!completeSimple,
      apiKey: !!resolvedApiKey,
      cachedBlocks: messageCache.size,
      camouflage: camouflage.enabled,
      camouflageElements: camouflage.enabled ? camouflage.elements : "disabled",
      backgroundProvider: camouflage.enabled ? camouflage.preferredBackgroundProvider : "n/a",
    });
  }

  api.on("agent_start", () => {
    try { init(); lastProcessedBlockCount = 0; }
    catch (e) { console.error("[R-Memory] Init:", e.message); }
  });

  /**
   * Background compression: group messages into blocks (~4k each),
   * compress all complete blocks.
   * A block = messages from a turn, split at blockSize boundaries.
   * The last block is skipped (may still be in progress).
   */
  api.on("agent_end", async (event) => {
    try {
      init();
      if (!config.enabled) return;
      const messages = event.messages || [];
      if (messages.length === 0) return;

      // === DIAGNOSTIC: Log message roles from agent_end ===
      const roleCounts = {};
      let totalMsgTokens = 0;
      for (const msg of messages) {
        const r = msg.role || "unknown";
        roleCounts[r] = (roleCounts[r] || 0) + 1;
        totalMsgTokens += estimateTokens(extractMessageText(msg));
      }
      log("INFO", "=== DIAGNOSTIC: agent_end messages ===", {
        totalMessages: messages.length,
        roleCounts,
        totalTokensEstimate: totalMsgTokens
      });
      // === END DIAGNOSTIC ===

      const blocks = groupMessagesIntoBlocks(messages);

      // agent_end fires when the AI finishes responding — the turn IS complete.
      // Cache ALL blocks. queueBlock() deduplicates via hash check.
      // Log hashes so we can verify alignment with compaction path.
      const blockHashes = blocks.map(b => b.hash.slice(0, 8));
      for (const block of blocks) {
        queueBlock(block);
      }

      cleanupCache();
      log("DEBUG", "Queued blocks", {
        totalBlocks: blocks.length,
        blockHashes,
        queue: compressionQueue.length,
        cache: messageCache.size
      });

      // Narrative tracker: update SESSION_THREAD.md (fire and forget)
      updateNarrativeThread(messages).catch(e =>
        log("WARN", "Narrative async error", { error: e.message })
      );
    } catch (e) { log("ERROR", "agent_end error", { error: e.message }); }
  });

  /**
   * Compaction interception: swap oldest raw blocks with pre-compressed versions.
   * On failure: returns {cancel: true} to PREVENT OpenClaw's lossy fallback.
   */
  api.on("session_before_compact", async (event) => {
    try { init(); return await handleBeforeCompact(event); }
    catch (e) {
      log("ERROR", "Handler error — CANCELLING to prevent lossy fallback", { error: e.message });
      return { cancel: true };
    }
  });
};
