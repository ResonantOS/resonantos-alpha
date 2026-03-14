/**
 * Shield Gate — Tool Call Interceptor
 * 
 * OpenClaw extension that intercepts dangerous tool calls before execution.
 * Checks exec commands against destructive patterns from Logician rules.
 * 
 * Hook: before_tool_call
 * Behavior: Block destructive commands, allow safe ones, log all decisions.
 * Fail mode: OPEN (if Logician unreachable, allow with warning — opposite of git push)
 * 
 * v1.0.0 — 2026-02-19
 */

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

// --- Configuration ---
const HOME = process.env.HOME || "/Users/augmentor";
const LOGICIAN_SOCK = process.env.LOGICIAN_SOCK || "/tmp/mangle.sock";
const PROTO_PATH = path.join(process.env.HOME, "resonantos-augmentor/logician/poc/mangle-service/proto/mangle.proto");
const LOG_FILE = path.join(process.env.HOME, "resonantos-augmentor/shield/logs/shield-gate.log");
const ERROR_EXPLAIN_INSTRUCTION = "\n\n⚠️ MANDATORY: Explain this block to the user briefly. What was blocked and what you are doing instead. Never leave a block message unexplained.";

// --- Logician gRPC Client (native Node.js, no grpcurl) ---
let logicianClient = null;
function getLogicianClient() {
  if (logicianClient) return logicianClient;
  try {
    if (!fs.existsSync(LOGICIAN_SOCK)) return null;
    const grpc = require("@grpc/grpc-js");
    const protoLoader = require("@grpc/proto-loader");
    const packageDef = protoLoader.loadSync(PROTO_PATH, {
      keepCase: true, longs: String, enums: String, defaults: true, oneofs: true
    });
    const proto = grpc.loadPackageDefinition(packageDef).mangle;
    logicianClient = new proto.Mangle(
      `unix://${LOGICIAN_SOCK}`,
      grpc.credentials.createInsecure()
    );
    return logicianClient;
  } catch (e) {
    return null;
  }
}

// --- Coherence Gate Integration ---
const CG_TASK_DIR = path.join(process.env.HOME, "resonantos-augmentor/coherence-gate/tasks");
const CG_CONFIG_FILE = path.join(process.env.HOME, "resonantos-augmentor/coherence-gate/config.json");
const CG_LOG_FILE = path.join(process.env.HOME, "resonantos-augmentor/coherence-gate/logs/coherence-gate.log");

// Tools that require an active CG task (mirrors config.significantTools)
const CG_SIGNIFICANT_TOOLS = ["write", "edit", "exec", "message", "sessions_spawn", "gateway"];

// Tools always exempt from CG enforcement
const CG_EXEMPT_TOOLS = [
  "read", "web_search", "web_fetch", "memory_search", "memory_get",
  "session_status", "image", "tts", "browser", "cron",
  "sessions_list", "sessions_history", "subagents", "agents_list"
];

// Exec commands exempt from CG enforcement (read-only operations)
const CG_SAFE_EXEC = [
  /^ls\b/, /^cat\b/, /^head\b/, /^tail\b/, /^grep\b/, /^find\b/,
  /^echo\b/, /^pwd\b/, /^whoami\b/, /^date\b/, /^which\b/,
  /^wc\b/, /^sort\b/, /^uniq\b/, /^awk\b/, /^test\b/,
  /^git\s+(status|log|diff|show|branch)\b/,
  /^python3?\s+-c\b/, /^node\s+-e\b/, /^curl\s/,
  /^launchctl\s+(list|print)\b/, /^lsof\b/, /^ps\b/,
  /^openclaw\s+(plugins|status|doctor)\b/,
  /node\s+.*cg-cli\.js\b/,                            // CG task management (bootstrap exempt)
  /^mkdir\b/, /^touch\b/, /^cp\b/,
];

// Paths excluded from CG scope checking
const CG_EXCLUDE_PATHS = ["coherence-gate/", "r-memory/", "/tmp/", "shield/logs/"];

// --- Destructive Patterns (deterministic, no AI) ---
// Mirrors production_rules.mg destructive_pattern facts
const DESTRUCTIVE_PATTERNS = [
  /\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive)\b/,          // rm -rf variants
  /\brm\s+(-[a-zA-Z]*f[a-zA-Z]*r)\b/,                       // rm -fr variants
  /\brm\s+-rf\s+[\/~]/,                                       // rm -rf /path
  /\bdrop\s+(table|database|schema)\b/i,                       // SQL drop
  /\bformat\s+[a-zA-Z]:/i,                                    // format drive
  /\bmkfs\b/,                                                  // make filesystem
  /\bdd\s+if=.*of=\/dev\//,                                   // dd to device
  /\b>\s*\/dev\/sd[a-z]/,                                     // overwrite block device
  /\bchmod\s+(-R\s+)?777\s+\//,                               // chmod 777 /
  /\bchown\s+(-R\s+)?.*\s+\//,                                // chown -R /
  /\bkill\s+-9\s+-1\b/,                                       // kill all processes
  /\bkillall\b/,                                               // killall
  /\b:(){ :|:& };:/,                                          // fork bomb
  /\bshutdown\b/,                                              // shutdown
  /\breboot\b/,                                                // reboot
];

const GATEWAY_STOP_PATTERNS = [
  /openclaw\s+gateway\s+(restart|stop)/,
  /pkill.*openclaw/,
  /launchctl\s+unload.*openclaw/
];

// --- Protected File Patterns ---
// Matches protected_path() facts in production_rules.mg
const PROTECTED_PATHS = [
  /\.openclaw\/openclaw\.json/,
  /\.config\/solana\/id\.json/,
  /auth-profiles\.json/,
  /\.ssh\//,
  /\/\.env\b/,
  /ssot\/private\//,
];

// --- Safe Command Prefixes (always allow) ---
const SAFE_PREFIXES = [
  /^ls\b/, /^cat\b/, /^head\b/, /^tail\b/, /^grep\b/, /^find\b/,
  /^echo\b/, /^pwd\b/, /^whoami\b/, /^date\b/, /^which\b/,
  /^git\s+(status|log|diff|branch|show)\b/,
  /^python3?\s+-c\b/,
  /^node\s+-e\b/,
  /^curl\s/,
  /^test\b/, /^\[\s/,
  /^wc\b/, /^sort\b/, /^uniq\b/, /^awk\b/,
  /^mkdir\b/, /^touch\b/,
  /^cd\b/, /^source\b/,
  /^solana\s+(config|balance|address|account)\b/,
  /^go\s+(version|env)\b/,
  /^brew\s+(list|info|search)\b/,
];

// --- Helper: Strip false-positive content from commands ---
// Removes content inside quotes, comments, heredocs, and read-only command args
// to prevent grep/cat patterns from triggering false blocks.
function stripFalsePositiveContent(command) {
  if (!command || typeof command !== "string") return command;
  
  let stripped = command;
  
  // Strip heredoc bodies (<<EOF ... EOF) - both quoted and unquoted
  stripped = stripped.replace(/<<-?\s*'?(\w+)'?[\s\S]*?\n\1\b/gm, "<<HEREDOC");
  
  // Strip single-quoted strings ('...')
  stripped = stripped.replace(/'[^']*'/g, "'SQ'");
  
  // Strip double-quoted strings ("...") with escaped quotes support
  stripped = stripped.replace(/"(?:[^"\\]|\\.)*"/g, '"DQ"');
  
  // Strip shell comments (# to end of line)
  stripped = stripped.replace(/(^|[\s;|&()])#[^\n]*/gm, "$1");
  
  // Strip arguments to read-only/search commands (grep, cat, head, tail, less, etc.)
  // Their args are search patterns, not commands to execute
  stripped = stripped.replace(
    /\b(grep|egrep|fgrep|rg|ag|ack|cat|head|tail|less|more|wc|file|stat)\b(\s+-[^\s|;&#]*)*\s+[^|;&#\n]*/g,
    "$1 STRIPPED"
  );
  
  return stripped;
}

// --- Logging ---
function log(level, msg, data) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  try {
    const dir = path.dirname(LOG_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(LOG_FILE, entry + "\n");
  } catch (_) { /* logging should never crash the gate */ }
}

// --- Logician Query (native gRPC, synchronous via callback cache) ---
// Since before_tool_call is sync, we use a pre-warmed cache approach.
// For critical real-time queries, we use execSync as fallback.
const _logicianCache = new Map(); // key: query string, value: { answers: string[], ts: number }
const LOGICIAN_CACHE_TTL_MS = 30000; // 30s cache

// Synchronous query via execSync + Node gRPC (hybrid approach)
function queryLogicianSync(query, program) {
  try {
    if (!fs.existsSync(LOGICIAN_SOCK)) return null;
    const escaped = query.replace(/'/g, "'\\''");
    const progEscaped = program ? program.replace(/'/g, "'\\''") : "";
    const script = `
      const grpc = require('@grpc/grpc-js');
      const protoLoader = require('@grpc/proto-loader');
      const pd = protoLoader.loadSync('${PROTO_PATH}', { keepCase: true, longs: String, enums: String, defaults: true, oneofs: true });
      const proto = grpc.loadPackageDefinition(pd).mangle;
      const client = new proto.Mangle('unix://${LOGICIAN_SOCK}', grpc.credentials.createInsecure());
      const call = client.Query({ query: '${escaped}'${progEscaped ? `, program: '${progEscaped}'` : ""} });
      const r = [];
      call.on('data', d => r.push(d.answer));
      call.on('end', () => { console.log(JSON.stringify(r)); process.exit(0); });
      call.on('error', () => process.exit(1));
      setTimeout(() => process.exit(1), 600);
    `;
    const result = execSync(`node -e "${script.replace(/"/g, '\\"')}"`, {
      timeout: 800,
      stdio: ["pipe", "pipe", "pipe"],
      cwd: path.join(process.env.HOME, ".openclaw/workspace")
    });
    return JSON.parse(result.toString().trim());
  } catch (_) {
    return null;
  }
}

// Cached synchronous query
function queryLogician(query) {
  const cached = _logicianCache.get(query);
  if (cached && Date.now() - cached.ts < LOGICIAN_CACHE_TTL_MS) return cached.answers;
  const answers = queryLogicianSync(query) || [];
  _logicianCache.set(query, { answers, ts: Date.now() });
  return answers;
}

// Check if Logician proves a specific fact
function logicianProves(query) {
  const answers = queryLogician(query);
  return answers && answers.length > 0;
}

// --- Core Check ---
function checkExecCommand(command) {
  if (!command || typeof command !== "string") {
    return { block: false };
  }

  const trimmed = command.trim();

  // Fast-path: safe commands (only if no pipe/redirect to dangerous ops)
  // BUT: even safe-prefix commands must be checked against protected paths
  //       (python3 -c can write to any file, bypassing writeOps detection)
  const hasPipe = /\|/.test(trimmed);
  const hasRedirect = />{1,2}\s/.test(trimmed);
  const expanded = trimmed.replace(/~/g, process.env.HOME || "/Users/augmentor");
  if (!hasPipe && !hasRedirect) {
    let isSafe = false;
    for (const safe of SAFE_PREFIXES) {
      if (safe.test(trimmed)) { isSafe = true; break; }
    }
    if (isSafe) {
      // Even safe commands: block if they reference protected paths AND contain write indicators
      // This catches: python3 -c "json.dump(..., open('openclaw.json','w'))"
      const hasWriteIndicator = /\bopen\s*\([^)]*['\"]w['\"]|write|dump.*open|>|>>|\.write\s*\(|fs\.writeFile/i.test(trimmed);
      if (hasWriteIndicator) {
        for (const protPath of PROTECTED_PATHS) {
          if (protPath.test(trimmed) || protPath.test(expanded)) {
            log("BLOCK", "Safe-prefix command writes to protected path", { command: trimmed.slice(0, 150), path: protPath.source });
            return {
              block: true,
              blockReason: `🛡️ Shield Gate: Even safe commands cannot write to protected paths (${protPath.source}). Use gateway config.patch for config changes.` + ERROR_EXPLAIN_INSTRUCTION
            };
          }
        }
      }
      return { block: false, reason: "safe_prefix" };
    }
  }

  // Check for destructive patterns
  // Strip content that shouldn't trigger pattern matching:
  // 1. Heredoc bodies (<<EOF ... EOF) - both quoted and unquoted delimiters
  // 2. Single-quoted strings ('...') - including escaped quotes
  // 3. Double-quoted strings ("...") - including escaped quotes  
  // 4. Shell comments (# ...) - anywhere in the command
  // This prevents false positives on grep "killall", # rm -rf, cat "file-with-rm.txt", etc.
  let cmdForPatterns = trimmed;
  
  // Order matters: heredocs first, then quotes (so # inside strings isn't
  // mistaken for a comment), then comments last.
  
  // Strip heredoc bodies (handles both <<EOF and <<'EOF' styles)
  cmdForPatterns = cmdForPatterns.replace(/<<-?\s*'?(\w+)'?[\s\S]*?\n\1\b/gm, "<<HEREDOC_STRIPPED");
  
  // Strip single-quoted strings (bash doesn't interpret escapes in single quotes, so simple is fine)
  cmdForPatterns = cmdForPatterns.replace(/'[^']*'/g, "'STRIPPED'");
  
  // Strip double-quoted strings (handle escaped quotes: \")
  // Use a more robust regex that handles \" inside strings
  cmdForPatterns = cmdForPatterns.replace(/"(?:[^"\\]|\\.)*"/g, '"STRIPPED"');
  
  // Strip shell comments (# to end of line or end of string)
  // Handles both newline-terminated and end-of-string cases
  cmdForPatterns = cmdForPatterns.replace(/(^|[\s;|&()])#[^\n]*/gm, "$1");
  
  // Strip arguments to read-only/search commands — their args are search patterns,
  // not commands to execute. Handles: grep killall file, rg "shutdown" src/, etc.
  // Replaces everything after the command+flags with STRIPPED so pattern words in
  // grep/ack/rg/ag/cat/head/tail/less/more/wc/file/stat arguments don't trigger blocks.
  // Preserves pipes so downstream commands are still checked.
  cmdForPatterns = cmdForPatterns.replace(
    /\b(grep|egrep|fgrep|rg|ag|ack)\b(\s+-[^\s|;&#]*)*\s+[^|;&#\n]*/g,
    "$1 STRIPPED"
  );
  
  for (const pattern of DESTRUCTIVE_PATTERNS) {
    if (pattern.test(cmdForPatterns)) {
      log("BLOCK", "Destructive command intercepted", { command: trimmed.slice(0, 100), pattern: pattern.source });
      return {
        block: true,
        blockReason: `🛡️ Shield Gate: Destructive command blocked (${pattern.source.slice(0, 40)}). Use 'trash' instead of 'rm -rf', or get human approval.` + ERROR_EXPLAIN_INSTRUCTION
      };
    }
  }

  // Check for protected file writes
  // Only block if it looks like a write operation (>, >>, rm, mv, sed, tee, etc.)
  const writeOps = /\b(rm|mv|>|>>|tee|sed\b|truncate|shred)\b/;
  // expanded already computed above
  if (writeOps.test(trimmed)) {
    for (const protPath of PROTECTED_PATHS) {
      if (protPath.test(trimmed) || protPath.test(expanded)) {
        log("BLOCK", "Protected file write intercepted", { command: trimmed.slice(0, 100), path: protPath.source });
        return {
          block: true,
          blockReason: `🛡️ Shield Gate: Write to protected path blocked (${protPath.source}). This file requires human approval to modify.` + ERROR_EXPLAIN_INSTRUCTION
        };
      }
    }
  }

  // Block cp/mv into code files unless destination path is explicitly exempt.
  const cpMvMatch = trimmed.match(/\b(cp|mv)\s+(?:-[^\s]*\s+)*(\S+)\s+(\S+)/);
  if (cpMvMatch) {
    const dest = cpMvMatch[3];
    const expandedDest = dest.replace(/^~(?=\/|$)/, process.env.HOME || "/Users/augmentor");

    if (CODE_EXTENSIONS.test(expandedDest)) {
      let isExempt = false;
      for (const exempt of CODING_GATE_EXEMPT_PATHS) {
        if (exempt.test(dest) || exempt.test(expandedDest)) {
          isExempt = true;
          break;
        }
      }

      if (!isExempt) {
        log("BLOCK", "Direct Coding Gate blocked cp/mv to code file", {
          command: trimmed.slice(0, 100),
          dest: expandedDest
        });
        return {
          block: true,
          blockReason: `[Direct Coding Gate] Blocked cp/mv to code file "${dest.split("/").pop()}". Writing code files must go through Codex delegation, not cp/mv from temp files.` + ERROR_EXPLAIN_INSTRUCTION
        };
      }
    }
  }

  // Allow everything else
  log("ALLOW", "Command passed", { command: trimmed.slice(0, 80) });
  return { block: false };
}

// --- Tool Path Extraction ---
function extractToolPath(toolName, params) {
  if (!params) return null;
  if (toolName === "write" || toolName === "read" || toolName === "edit") {
    return params.file_path || params.path || null;
  }
  if (toolName === "exec" && params.command) {
    // Extract first file path from command (heuristic)
    const match = params.command.match(/(?:^|\s)(\/\S+|~\/\S+|\.\.\S+)/);
    return match ? match[1] : null;
  }
  return null;
}

// --- Coherence Gate Enforcement ---

/**
 * Read CG task state from disk. Returns { hasActiveTask, taskTitle, taskScope, taskAge }
 * Deterministic: file presence + content parsing, no AI.
 */
function getCgTaskState() {
  try {
    if (!fs.existsSync(CG_TASK_DIR)) return { hasActiveTask: false };
    
    const taskFiles = fs.readdirSync(CG_TASK_DIR)
      .filter(name => /^TASK-.*\.md$/.test(name))
      .map(name => path.join(CG_TASK_DIR, name));
    
    for (const filePath of taskFiles) {
      const content = fs.readFileSync(filePath, "utf8");
      // Parse YAML-like frontmatter from task file
      // Support both formats: "status: active" and "- Status: active" and "# Task: title"
      const statusMatch = content.match(/^-?\s*status:\s*(.+)$/im);
      const status = statusMatch ? statusMatch[1].trim().toLowerCase() : "";
      
      if (status === "active") {
        const titleMatch = content.match(/^(?:-?\s*title:\s*|#\s*Task:\s*)(.+)$/im);
        const scopeMatch = content.match(/^-?\s*scope:\s*(.+)$/im);
        const createdMatch = content.match(/^-?\s*created:\s*(.+)$/im);
        
        const title = titleMatch ? titleMatch[1].trim() : "unknown";
        const scope = scopeMatch ? scopeMatch[1].trim().split(/\s*,\s*/) : [];
        const created = createdMatch ? Date.parse(createdMatch[1].trim()) : 0;
        const ageSeconds = created ? Math.floor((Date.now() - created) / 1000) : 0;
        
        return { hasActiveTask: true, taskTitle: title, taskScope: scope, taskAge: ageSeconds, filePath };
      }
    }
    return { hasActiveTask: false };
  } catch (err) {
    log("ERROR", "CG task state read failed", { error: err.message });
    return { hasActiveTask: false, error: err.message };
  }
}

/**
 * Check if a tool call is exempt from CG enforcement.
 * Exec commands that are read-only are exempt.
 */
function isCgExempt(toolName, params) {
  if (CG_EXEMPT_TOOLS.includes(toolName)) return true;
  if (!CG_SIGNIFICANT_TOOLS.includes(toolName)) return true;
  
  // For exec: read-only commands are exempt
  if (toolName === "exec" && params?.command) {
    const cmd = params.command.trim();
    for (const pattern of CG_SAFE_EXEC) {
      if (pattern.test(cmd)) return true;
    }
  }
  
  // Bootstrap exemption: ANY operation targeting CG task dir (prevents deadlock)
  // Covers write, edit, AND exec commands that create/modify task files
  if (params) {
    const p = params.file_path || params.path || "";
    const cmd = params.command || "";
    if (p.includes("coherence-gate/tasks/") || cmd.includes("coherence-gate/tasks/")) return true;
  }
  
  return false;
}

/**
 * Check if path is within CG scope exclusions (infrastructure paths)
 */
function isCgExcludedPath(actionPath) {
  if (!actionPath) return false;
  for (const excl of CG_EXCLUDE_PATHS) {
    if (actionPath.includes(excl)) return true;
  }
  return false;
}

/**
 * Check Coherence Gate enforcement. Uses deterministic logic:
 * - File presence check for active task (fully deterministic)
 * - Logician query for rule provability (auditable)
 * - CG log parsing for drift scores (deterministic threshold)
 * 
 * Architecture: Shield Gate reads runtime state → queries Logician for rule evaluation.
 * Logician provides the provable rule; Shield Gate provides the dynamic facts.
 * If Logician is down, Shield Gate enforces the same rules locally (fail-safe).
 */
function checkCoherenceGate(toolName, params) {
  const state = getCgTaskState();
  const toolAtom = `/${toolName.replace(/[^a-z_]/g, "_")}`;
  
  // --- Check 1: No active task → block significant tools ---
  if (!state.hasActiveTask && CG_SIGNIFICANT_TOOLS.includes(toolName)) {
    // Query Logician for provability (audit trail)
    const logicianResult = queryLogician(`cg_block_no_task(${toolAtom}).`);
    const provable = logicianResult && logicianResult.includes("cg_block_no_task");
    
    log("CG-BLOCK", "No active task — significant tool blocked", { 
      tool: toolName, logicianProof: provable ? "confirmed" : "unavailable" 
    });
    return {
      block: true,
      reason: `🔒 Coherence Gate: No active task registered. Create a task first:\n  node ~/resonantos-augmentor/coherence-gate/cg-cli.js create "Your task description"`
    };
  }
  
  // --- Check 2: Drift detection (from CG log) ---
  if (state.hasActiveTask) {
    try {
      if (fs.existsSync(CG_LOG_FILE)) {
        const logLines = fs.readFileSync(CG_LOG_FILE, "utf8").split("\n").slice(-30);
        const driftEntries = logLines.filter(l => l.includes("drift_score"));
        
        if (driftEntries.length > 0) {
          const lastEntry = driftEntries[driftEntries.length - 1];
          const scoreMatch = lastEntry.match(/drift_score["\s:]+(\d+)/);
          const driftScore = scoreMatch ? parseInt(scoreMatch[1]) : 0;
          
          if (driftScore >= 2) {
            // Query Logician for audit
            queryLogician(`cg_block_drift(${toolAtom}).`);
            log("CG-BLOCK", "High drift detected", { tool: toolName, driftScore, task: state.taskTitle });
            return {
              block: true,
              reason: `🔒 Coherence Gate: Drift score ${driftScore} — actions misaligned with task "${state.taskTitle}". Refocus or update task scope.`
            };
          }
          
          if (driftScore === 1) {
            log("CG-WARN", "Mild drift", { tool: toolName, driftScore, task: state.taskTitle });
            return { block: false, warn: true, reason: "drift_mild" };
          }
        }
      }
    } catch (_) { /* drift check is advisory */ }
  }
  
  // --- Check 3: Stale task warning ---
  if (state.hasActiveTask && state.taskAge > 1800) {
    log("CG-WARN", "Stale task", { task: state.taskTitle, ageMin: Math.round(state.taskAge / 60) });
    return { block: false, warn: true, reason: `stale_task_${Math.round(state.taskAge / 60)}min` };
  }
  
  return { block: false };
}

// --- Delegation Gate (Codex Task Quality Validator) ---
// Fail-CLOSED: if validation can't run, block the delegation.
// Rationale: false positive costs minutes; false negative costs tokens + broken code.

let delegationGate = null;
try {
  delegationGate = require(path.join(
    process.env.HOME, "resonantos-augmentor/shield/delegation-gate.js"
  ));
} catch (e) {
  // Will be checked at call time
}

function checkDelegation(command, execWorkdir) {
  if (!delegationGate) {
    return {
      block: true,
      blockReason: "🛡️ Delegation Gate: Cannot load delegation-gate.js module. Fix the module before delegating to Codex." + ERROR_EXPLAIN_INSTRUCTION
    };
  }

  if (!delegationGate.isCodexExec(command)) {
    return { block: false };
  }

  // --- Layer 1.5 Enhancement: Query Logician for delegation rules ---
  // Check if this agent/task is allowed to delegate per Logician rules
  const delegator = "main"; // Assuming main orchestrator
  const taskType = delegationGate.inferTaskType ? delegationGate.inferTaskType(command) : "unknown";
  if (taskType !== "unknown") {
    const logicianResult = queryLogician(`must_delegate_to(${delegator}, ${taskType}, Target).`);
    if (logicianResult && logicianResult.length > 0) {
      log("INFO", `Delegation Gate: Logician confirms delegation allowed for task type ${taskType}`);
    }
    // Note: If Logician query fails or returns nothing, we don't block - delegation-gate.js does the actual validation
  }

  const workDir = delegationGate.resolveWorkDir(command, execWorkdir);
  const taskPath = path.join(workDir, "TASK.md");

  log("INFO", "Delegation Gate: codex exec detected", { workDir, taskPath });

  const result = delegationGate.validateTaskMd(taskPath);

  if (!result.valid) {
    const errorList = result.errors.map((e, i) => `  ${i + 1}. ${e}`).join("\n");
    const warningList = result.warnings.length > 0
      ? "\n⚠️ Warnings:\n" + result.warnings.map((w, i) => `  ${i + 1}. ${w}`).join("\n")
      : "";

    log("BLOCK", "Delegation Gate: TASK.md validation failed", {
      workDir,
      errors: result.errors.length,
      warnings: result.warnings.length
    });

    return {
      block: true,
      blockReason:
        `🛡️ Delegation Gate: TASK.md validation failed.\n` +
        `📍 Checked: ${taskPath}\n` +
        `❌ Errors:\n${errorList}${warningList}\n\n` +
        `Fix TASK.md before delegating. Read DELEGATION_PROTOCOL.md for the required format.`
    };
  }

  if (result.warnings.length > 0) {
    log("WARN", "Delegation Gate: TASK.md passed with warnings", {
      warnings: result.warnings
    });
  }

  log("ALLOW", "Delegation Gate: TASK.md validated", { workDir });
  return { block: false };
}

// --- Layer 3: Direct Coding Gate ---
const CODE_EXTENSIONS = /\.(js|py|ts|html|css|sh|rs|go|jsx|tsx|mjs|cjs)$/i;
const CODING_GATE_EXEMPT_PATHS = [
  /shield\//i,
  /coherence-gate\//i,
  /\.openclaw\/extensions\//i,
  /logician\//i,
];
const CODING_GATE_MAX_CHARS = 300;

function checkDirectCoding(toolName, params) {
  if (toolName !== "write" && toolName !== "edit") return { block: false };

  const filePath = params?.file_path || params?.path || "";
  if (!CODE_EXTENSIONS.test(filePath)) return { block: false };

  // Exempt enforcement infrastructure paths
  for (const exempt of CODING_GATE_EXEMPT_PATHS) {
    if (exempt.test(filePath)) return { block: false };
  }

  const content = params?.content || params?.new_string || params?.newText || "";
  if (content.length <= CODING_GATE_MAX_CHARS) return { block: false };

  return {
    block: true,
    blockReason: `[Direct Coding Gate] Blocked writing ${content.length} chars to code file "${filePath.split("/").pop()}". This is by design — edits over ${CODING_GATE_MAX_CHARS} chars must go through Codex delegation. The AI will use an alternative method (exec/sed or Codex). No action needed from you.` + ERROR_EXPLAIN_INSTRUCTION
  };
}

function checkExecCodeWrite(command) {
  if (!command || typeof command !== "string") return { block: false };

  const trimmed = command.trim();
  const codePathToken = /['"]?([^'"`\s|;&]+\.(?:js|py|ts|html|css|sh|rs|go|jsx|tsx|mjs|cjs))['"]?/ig;

  const normalizePath = (rawPath) => {
    if (!rawPath) return "";
    let filePath = String(rawPath).trim().replace(/^['"]|['"]$/g, "");
    if (filePath.startsWith("~/")) {
      filePath = path.join(process.env.HOME || "/Users/augmentor", filePath.slice(2));
    }
    return filePath;
  };

  const checkTarget = (rawPath) => {
    const filePath = normalizePath(rawPath);
    if (!filePath || !CODE_EXTENSIONS.test(filePath)) return null;
    for (const exempt of CODING_GATE_EXEMPT_PATHS) {
      if (exempt.test(filePath)) return null;
    }
    const filename = filePath.split("/").pop() || filePath;
    return {
      block: true,
      blockReason: `[Direct Coding Gate] Blocked exec command writing to code file "${filename}". Code file modifications must go through Codex delegation, even via exec/sed/echo. Use: codex exec "your task"`
    };
  };

  // 1) sed -i <file>
  if (/\bsed\b/.test(trimmed) && /(?:^|\s)-i(?:\s|$|['"])/.test(trimmed)) {
    const matches = [...trimmed.matchAll(codePathToken)];
    for (let i = matches.length - 1; i >= 0; i -= 1) {
      const blocked = checkTarget(matches[i][1]);
      if (blocked) return blocked;
    }
  }

  // 2) echo/printf ... > file
  const echoOrPrintfRedirect = trimmed.match(/\b(?:echo|printf)\b[\s\S]*?(?:>|>>)\s*(['"]?[^'"`\s|;&]+['"]?)/i);
  if (echoOrPrintfRedirect) {
    const blocked = checkTarget(echoOrPrintfRedirect[1]);
    if (blocked) return blocked;
  }

  // 3) cat ... > file (including heredoc)
  const catRedirect = trimmed.match(/\bcat\b[\s\S]*?(?:>|>>)\s*(['"]?[^'"`\s|;&]+['"]?)/i);
  if (catRedirect) {
    const blocked = checkTarget(catRedirect[1]);
    if (blocked) return blocked;
  }

  // 4) tee / tee -a file
  const teeTarget = trimmed.match(/\btee\b(?:\s+-a\b)?\s+(['"]?[^'"`\s|;&]+['"]?)/i);
  if (teeTarget) {
    const blocked = checkTarget(teeTarget[1]);
    if (blocked) return blocked;
  }

  // 5) python3 -c "... open('file.py', 'w') ..."
  if (/\bpython3?\b[^\n]*\s-c\b/.test(trimmed)) {
    const pythonWrite = trimmed.match(/open\s*\(\s*['"]([^'"]+\.(?:js|py|ts|html|css|sh|rs|go|jsx|tsx|mjs|cjs))['"]\s*,\s*['"][^'"]*w[^'"]*['"]/i);
    if (pythonWrite) {
      const blocked = checkTarget(pythonWrite[1]);
      if (blocked) return blocked;
    }
  }

  // 6) mv/cp ... <destination>
  const moveOrCopySegments = trimmed.match(/\b(?:mv|cp)\b[^\n|;&]*/ig) || [];
  for (const segment of moveOrCopySegments) {
    const tokens = segment.match(/"[^"]*"|'[^']*'|\S+/g) || [];
    const args = tokens.slice(1).filter((token) => !token.startsWith("-"));
    if (args.length < 2) continue;
    const blocked = checkTarget(args[args.length - 1]);
    if (blocked) return blocked;
  }

  // 7) Generic redirect > code_file (catch-all for pipes like `cmd | cmd2 > file.py`)
  const genericRedirect = trimmed.match(/(?:>|>>)\s*(['"]?[^'"`\s|;&]+['"]?)\s*$/i);
  if (genericRedirect) {
    const blocked = checkTarget(genericRedirect[1]);
    if (blocked) return blocked;
  }

  return { block: false };
}

// --- Post-Compaction Recovery State ---
const COMPACTION_STATE_FILE = "/tmp/openclaw_compaction_recovery.json";
const COMPACTION_RECOVERY_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes max
const RECOVERY_REQUIRED_FILES = ["WORKFLOW_AUTO.md", /memory\/\d{4}-\d{2}-\d{2}\.md/];

function getCompactionState() {
  try {
    if (!fs.existsSync(COMPACTION_STATE_FILE)) return null;
    const state = JSON.parse(fs.readFileSync(COMPACTION_STATE_FILE, "utf8"));
    // Auto-expire stale state (prevents permanent lockout)
    if (Date.now() - state.ts > COMPACTION_RECOVERY_TIMEOUT_MS) {
      fs.unlinkSync(COMPACTION_STATE_FILE);
      return null;
    }
    return state;
  } catch (_) { return null; }
}

function updateCompactionState(state) {
  try { fs.writeFileSync(COMPACTION_STATE_FILE, JSON.stringify(state)); } catch (_) {}
}

function clearCompactionState() {
  try { if (fs.existsSync(COMPACTION_STATE_FILE)) fs.unlinkSync(COMPACTION_STATE_FILE); } catch (_) {}
}

// --- Extension Entry ---
module.exports = function shieldGateExtension(api) {
  log("INFO", "Shield Gate extension loaded" + (delegationGate ? " (delegation gate active)" : " (delegation gate NOT loaded)"));

  // --- Verification Claim Gate: Turn-level tool tracking ---
  // Tracks recent calls per session-turn so message_sending can check
  // whether claims have evidence.
  const turnEvidence = new Map(); // sessionKey → { execCalls: [{cmd, ts}], toolCalls: [{toolName, command, ts}], readFiles: Set, lastReset: ts }
  const TURN_EVIDENCE_TTL_MS = 10 * 60 * 1000; // 10 min — evidence window per turn
  const MAX_VERIFICATION_TOOL_CALLS = 20;

  function getTurnEvidence(sessionKey) {
    if (!sessionKey) return null;
    let ev = turnEvidence.get(sessionKey);
    const now = Date.now();
    if (!ev || (now - ev.lastReset) > TURN_EVIDENCE_TTL_MS) {
      ev = { execCalls: [], toolCalls: [], readFiles: new Set(), lastReset: now };
      turnEvidence.set(sessionKey, ev);
    }
    if (!Array.isArray(ev.toolCalls)) ev.toolCalls = [];
    return ev;
  }

  function recordExecEvidence(sessionKey, command) {
    const ev = getTurnEvidence(sessionKey);
    if (!ev) return;
    ev.execCalls.push({ cmd: (command || "").slice(0, 200), ts: Date.now() });
    // Cap memory: keep last 50 entries per session
    if (ev.execCalls.length > 50) ev.execCalls = ev.execCalls.slice(-50);
  }

  function recordReadEvidence(sessionKey, filePath) {
    const ev = getTurnEvidence(sessionKey);
    if (!ev || !filePath) return;
    ev.readFiles.add(filePath);
  }

  function hasReadFile(sessionKey, substring) {
    const ev = getTurnEvidence(sessionKey);
    if (!ev) return false;
    for (const f of ev.readFiles) {
      if (f.includes(substring)) return true;
    }
    return false;
  }

  function hasTestEvidence(sessionKey) {
    if (!sessionKey) return false;
    const ev = turnEvidence.get(sessionKey);
    if (!ev) return false;
    if ((Date.now() - ev.lastReset) > TURN_EVIDENCE_TTL_MS) return false;
    // Any exec call counts as potential test evidence
    // (the point is: SOME testing was attempted, not that it was perfect)
    return ev.execCalls.length > 0;
  }

  function recordToolCall(sessionKey, toolName, params) {
    const ev = getTurnEvidence(sessionKey);
    if (!ev || !toolName) return;
    const entry = { toolName, ts: Date.now() };
    if (toolName === "exec") {
      entry.command = String(params?.command || "").slice(0, 300);
    }
    ev.toolCalls.push(entry);
    if (ev.toolCalls.length > MAX_VERIFICATION_TOOL_CALLS) {
      ev.toolCalls = ev.toolCalls.slice(-MAX_VERIFICATION_TOOL_CALLS);
    }
  }

  // Verification claim trigger words (case-insensitive)
  const VERIFICATION_CLAIM_PATTERNS = [
    /\bfixed\b/i,
    /✅\s*verified/i,
    /\bits?\s+(?:is\s+)?fixed\b/i,
    /\bbug\s+(?:is\s+)?(?:fixed|resolved|squashed)\b/i,
    /\bpushed.*(?:fix|patch)\b/i,
    /\bdone\b/i,
    /\bsorted\b/i,
    /\bcomplete[d]?\b/i,
  ];

  // Patterns that indicate the message is NOT a verification claim
  // (e.g., "needs testing", "code-reviewed", asking about fixing)
  const VERIFICATION_EXEMPT_PATTERNS = [
    /needs?\s+testing/i,
    /needs?\s+manual/i,
    /code[- ]reviewed/i,
    /untested/i,
    /⚠️/,
    /❓/,
    /\?/,  // Questions aren't claims
    /should\s+(?:we\s+)?fix/i,
    /want\s+(?:me\s+to\s+)?fix/i,
    /will\s+fix/i,
    /todo.*fix/i,
    /plan.*fix/i,
  ];

  function containsVerificationClaim(text) {
    if (!text) return false;
    // Check exemptions first
    for (const exempt of VERIFICATION_EXEMPT_PATTERNS) {
      if (exempt.test(text)) return false;
    }
    // Check for claim patterns
    for (const pattern of VERIFICATION_CLAIM_PATTERNS) {
      if (pattern.test(text)) return pattern.toString();
    }
    return false;
  }

  // State claims (counts/version/status) from verification-gate.js
  const STATE_CLAIM_PATTERNS = [
    /\b(\d+)\s+(agents?|skills?|sessions?|cron\s+jobs?|plugins?|routes?|stores?|files?)\b/i,
    /\b(running|active|enabled|disabled|installed)\b.*\b(agents?|services?|plugins?)\b/i,
    /\bport\s+\d+\b/i,
    /\b(version|v)\s*\d+\.\d+/i,
  ];

  // Verification commands from verification-gate.js
  const VERIFICATION_COMMANDS = [
    /openclaw\s+(status|agents|skills|plugins|cron|memory)/,
    /ps\s+aux/,
    /grep.*server_v2\.py/,
    /ls.*\.sqlite/,
    /cat.*openclaw\.json/,
    /find.*\.md.*wc/,
    /openclaw\s+doctor/,
  ];

  function containsStateClaim(text) {
    if (!text || typeof text !== "string") return false;
    for (const pattern of STATE_CLAIM_PATTERNS) {
      if (pattern.test(text)) return pattern.toString();
    }
    return false;
  }

  function hasRecentVerificationCommand(sessionKey) {
    const ev = getTurnEvidence(sessionKey);
    if (!ev) return false;
    const recent = ev.toolCalls.slice(-MAX_VERIFICATION_TOOL_CALLS);
    return recent.some((call) => {
      if (call.toolName !== "exec") return false;
      const command = call.command || "";
      return VERIFICATION_COMMANDS.some((pattern) => pattern.test(command));
    });
  }

  const BEHAVIORAL_OVERCLAIM_PATTERN = /\b(I\s+always|I\s+never|I\s+constantly|every\s+single\s+time|without\s+exception|100%\s+of\s+the\s+time)\b/i;
  const BEHAVIORAL_SELF_ASSESSMENT_PATTERN = /\bI\b[\s\S]*\b(check|verify|ensure|do|run|test)\b/i;

  function stripQuotedAndCodeBlocks(text) {
    if (!text || typeof text !== "string") return "";
    const noCode = text.replace(/```[\s\S]*?```/g, " ");
    return noCode
      .split("\n")
      .filter((line) => !line.trim().startsWith(">"))
      .join("\n");
  }

  function containsBehavioralOverclaim(text) {
    const sanitized = stripQuotedAndCodeBlocks(text);
    if (!sanitized) return false;
    const sentences = sanitized.split(/[.!?]\s+|\n+/).map((s) => s.trim()).filter(Boolean);
    for (const sentence of sentences) {
      if (!BEHAVIORAL_OVERCLAIM_PATTERN.test(sentence)) continue;
      if (!BEHAVIORAL_SELF_ASSESSMENT_PATTERN.test(sentence)) continue;
      return {
        pattern: BEHAVIORAL_OVERCLAIM_PATTERN.toString(),
        preview: sentence.slice(0, 120)
      };
    }
    return false;
  }

  api.on("before_tool_call", (event, ctx) => {
    try {
      log("DEBUG", "before_tool_call fired", { tool: event?.toolName, agentId: ctx?.agentId, sessionKey: ctx?.sessionKey?.slice(0, 30) });
      const { toolName, params } = event;
      recordToolCall(ctx?.sessionKey, toolName, params);
      let advisoryWarning = null;

      // --- Layer 8: Post-Compaction Recovery Gate ---
      // After compaction, force reading context files before any other action.
      const compState = getCompactionState();
      if (compState && ctx?.agentId === "main") {
        const filePath = params?.file_path || params?.path || "";
        if (toolName === "read") {
          // Track which required files have been read
          let updated = false;
          if (/WORKFLOW_AUTO\.md/i.test(filePath) && !compState.readWorkflow) {
            compState.readWorkflow = true; updated = true;
          }
          if (/memory\/\d{4}-\d{2}-\d{2}\.md/i.test(filePath) && !compState.readMemory) {
            compState.readMemory = true; updated = true;
          }
          if (updated) {
            if (compState.readWorkflow && compState.readMemory) {
              clearCompactionState();
              log("INFO", "Post-Compaction Recovery complete — all context files read");
            } else {
              updateCompactionState(compState);
            }
          }
          // Always allow reads during recovery
        } else {
          // Block non-read tools until context is restored
          const missing = [];
          if (!compState.readWorkflow) missing.push("WORKFLOW_AUTO.md");
          if (!compState.readMemory) missing.push("memory/YYYY-MM-DD.md (today)");
          log("BLOCK", "Post-Compaction Recovery Gate", { tool: toolName, missing });
          return { block: true, blockReason: `[Post-Compaction Recovery] AI context was reset (compaction). It must re-read its configuration files before acting. This is automatic — no action needed from you.` + ERROR_EXPLAIN_INSTRUCTION };
        }
      }

      // --- Track file reads for delegation protocol enforcement ---
      if (toolName === "read") {
        const readPath = params?.file_path || params?.path || "";
        if (readPath) recordReadEvidence(ctx?.sessionKey, readPath);
      }

      // --- Layer 1: Destructive command check (exec only) ---
      if (toolName === "exec") {
        const command = params?.command;
        if (command) {
          // --- Gateway Lifecycle Gate ---
          // Only test the actual command line, not heredoc/string content
          const trimmed = command.trim();
          const cmdOnly = trimmed.split(/\n/)[0].split(/<<[\s'"]*\w+/)[0].trim();
          let gatewayLifecyclePattern = null;
          for (const pattern of GATEWAY_STOP_PATTERNS) {
            if (pattern.test(cmdOnly)) {
              gatewayLifecyclePattern = pattern;
              break;
            }
          }
          if (gatewayLifecyclePattern) {
            const configPath = path.join(HOME, ".openclaw/openclaw.json");
            try {
              JSON.parse(fs.readFileSync(configPath, "utf8"));
            } catch (err) {
              log("BLOCK", "Gateway Lifecycle Gate", {
                command: trimmed.slice(0, 100),
                pattern: gatewayLifecyclePattern.source,
                configPath,
                error: String(err)
              });
              return {
                block: true,
                blockReason: "[Gateway Lifecycle Gate] Config file is invalid JSON — fix before restarting." + ERROR_EXPLAIN_INSTRUCTION
              };
            }

            try {
              execSync("launchctl print gui/501/ai.openclaw.gateway 2>/dev/null");
            } catch (err) {
              log("WARN", "Gateway Lifecycle Gate: launchd service not found", {
                command: trimmed.slice(0, 100),
                pattern: gatewayLifecyclePattern.source,
                error: String(err)
              });
            }

            log("ALLOW", "Gateway Lifecycle Gate", {
              command: trimmed.slice(0, 100),
              pattern: gatewayLifecyclePattern.source,
              configPath
            });
          }

          const result = checkExecCommand(command);
          if (result.block) {
            log("BLOCK", `Blocked ${toolName}`, { command: command.slice(0, 100), reason: result.blockReason });
            return { block: true, blockReason: result.blockReason };
          }

          // --- Layer 1.5: Delegation Gate (codex exec only) ---
          const delegationResult = checkDelegation(command, params?.workdir);
          if (delegationResult.block) {
            log("BLOCK", `Delegation Gate blocked ${toolName}`, { command: command.slice(0, 100) });
            return { block: true, blockReason: delegationResult.blockReason };
          }

          const execCodeWriteResult = checkExecCodeWrite(command);
          if (execCodeWriteResult.block) {
            log("BLOCK", "Direct Coding Gate (exec)", { command: command.slice(0, 100) });
            return { block: true, blockReason: execCodeWriteResult.blockReason };
          }

          // --- Verification Claim Gate: record exec evidence ---
          recordExecEvidence(ctx?.sessionKey, command);
        }
      }

      // --- Layer 2: Coherence Gate enforcement (all significant tools) ---
      if (!isCgExempt(toolName, params)) {
        // Skip CG check for paths in the exclude list
        const actionPath = extractToolPath(toolName, params);
        if (!isCgExcludedPath(actionPath)) {
          const cgResult = checkCoherenceGate(toolName, params);
          if (cgResult.block) {
            return { block: true, blockReason: cgResult.reason };
          }
          if (cgResult.warn) {
            log("CG-WARN", cgResult.reason, { tool: toolName });
          }
        }
      }

      // --- Layer 3: Direct Coding Gate ---
      const codingResult = checkDirectCoding(toolName, params);
      if (codingResult.block) {
        log("BLOCK", "Direct Coding Gate", { tool: toolName, file: (params?.file_path || params?.path || "").slice(-60) });
        return { block: true, blockReason: codingResult.blockReason };
      }

      // --- Layer 4: Context Isolation Gate (Memory Safety) ---
      // Trusted agents can read/write memory. Untrusted (group chats, unknown agents) cannot.
      // Allowlist is intentionally hardcoded — adding an agent here is a security decision.
      if (toolName === "read" || toolName === "write" || toolName === "edit") {
        const filePath = params?.file_path || params?.path || "";
        const isMemoryFile = /MEMORY\.md$/i.test(filePath) || /memory\/\d{4}-\d{2}-\d{2}\.md$/i.test(filePath);
        if (isMemoryFile) {
          const MEMORY_TRUSTED_AGENTS = ["main", "resonant-voice", "content-voice", "researcher", "voice"];
          const agentId = ctx?.agentId || "";
          if (!MEMORY_TRUSTED_AGENTS.includes(agentId)) {
            log("BLOCK", "Context Isolation Gate", { tool: toolName, file: filePath.slice(-40), agentId });
            return { block: true, blockReason: `[Context Isolation Gate] Blocked ${toolName} on "${filePath.split("/").pop()}" — memory files are restricted to trusted agents. Agent "${agentId}" is not in the allowlist. This is a security feature preventing unauthorized memory access.` + ERROR_EXPLAIN_INSTRUCTION };
          }
        }
      }

      // --- Layer 5: Research Discipline Gate ---
      if (toolName === "web_search") {
        const query = params?.query || "";
        const words = query.trim().split(/\s+/).length;
        const RESEARCH_KEYWORDS = /\b(compare|analyze|research|investigate|state of the art|technical details|best approach|how does .+ work|architecture of|deep dive|comprehensive|evaluate|assessment)\b/i;
        if (words > 15 && RESEARCH_KEYWORDS.test(query)) {
          log("BLOCK", "Research Discipline Gate", { query: query.slice(0, 80), words });
          return { block: true, blockReason: `[Research Discipline Gate] Query too complex for basic web_search (${words} words). The AI will delegate this to the researcher agent instead for higher-quality results. No action needed.` + ERROR_EXPLAIN_INSTRUCTION };
        }
      }

      // --- Layer 7: External Action Gate ---
      // Blocks exec commands that send emails, tweets, or public posts.
      // Also blocks `message` tool targeting channels other than Telegram DM.
      if (toolName === "exec") {
        let cmd = (params?.command || "").trim();
        // Strip heredoc content — only check the command portion, not data
        cmd = cmd.replace(/<<\s*'?(\w+)'?[\s\S]*?\n\1\b/g, "<<HEREDOC_STRIPPED");
        const EXTERNAL_ACTION_PATTERNS = [
          /\bgog\s+mail\s+send\b/i,
          /\bgog\s+calendar\s+create\b/i,
          /\btweet\b/i,
          /\bsendmail\b/i,
          /\bmail\s+-s\b/i,
          /\bcurl\s.*api\.twitter/i,
          /\bcurl\s.*api\.x\.com/i,
        ];
        for (const pat of EXTERNAL_ACTION_PATTERNS) {
          if (pat.test(cmd)) {
            log("BLOCK", "External Action Gate — exec", { command: cmd.slice(0, 80), pattern: pat.toString() });
            return { block: true, blockReason: `[External Action Gate] Blocked external action (${cmd.slice(0, 40)}...). This gate prevents the AI from sending emails, tweets, or public posts without your explicit approval. Tell the AI to proceed if you want this action taken.` + ERROR_EXPLAIN_INSTRUCTION };
          }
        }
      }
      if (toolName === "message" && params?.action === "send") {
        const target = params?.target || params?.to || "";
        // Allow sending to Manolo's Telegram DM only
        if (target && !["7825655623", "telegram:7825655623"].some(d => target.includes(d))) {
          log("BLOCK", "External Action Gate — message", { target: target.slice(0, 30), action: params?.action });
          return { block: true, blockReason: `[External Action Gate] Blocked message to "${target}". Only your Telegram DM is auto-allowed. Tell the AI to proceed if you approve sending to this target.` + ERROR_EXPLAIN_INSTRUCTION };
        }
      }

      // --- Layer 6c: State Claim Gate (message tool) ---
      // Explicit `message` tool sends bypass `message_sending`, so enforce here too.
      if (toolName === "message" && params?.action === "send") {
        const content = params?.message || params?.text || "";
        const stateClaimPattern = containsStateClaim(content);
        if (stateClaimPattern) {
          const sessionKey = ctx?.sessionKey || "";
          const hasRecentVerification = hasRecentVerificationCommand(sessionKey);
          if (!hasRecentVerification) {
            log("BLOCK", "State Claim Gate (message tool) — state claim without verification command", {
              pattern: stateClaimPattern,
              sessionKey: sessionKey.slice(0, 30),
              contentPreview: String(content).slice(0, 80)
            });
            return {
              block: true,
              blockReason: "🛡️ State Claim Gate: System state claim detected in message tool content without a verification command in the last 20 tool calls. Run a verification command first (for example `openclaw status`, `openclaw skills`, `openclaw agents`, `openclaw plugins`) and then report the claim." + ERROR_EXPLAIN_INSTRUCTION
            };
          }
          log("INFO", "State Claim Gate (message tool) — state claim has verification evidence ✅", {
            pattern: stateClaimPattern,
            sessionKey: sessionKey.slice(0, 30)
          });
        }
      }

      // --- Layer 6e: Behavioral Integrity Gate (message tool) ---
      if (toolName === "message" && params?.action === "send") {
        const content = params?.message || params?.text || "";
        const overclaim = containsBehavioralOverclaim(content);
        if (overclaim) {
          log("BLOCK", "Behavioral Integrity Gate — potential overclaim", {
            pattern: overclaim.pattern,
            preview: overclaim.preview
          });
          return {
            block: true,
            blockReason: "Behavioral Integrity Gate: Overclaim detected. Rephrase with evidence or qualifier."
          };
        }
      }

      // --- Layer 6f: Config Change Gate ---
      // Blocks config file modifications without prior backup evidence.
      // For exec commands, only flag actual write operations (not reads like cat, grep, python print).
      if (toolName === "write" || toolName === "edit" || toolName === "exec") {
        const CONFIG_FILE_PATTERNS = [
          /openclaw\.json/,
          /keywords\.json/,
          /config\.json/,
          /\.plist\b/,
          /launch.*\.json/i,
        ];
        const EXEMPT_CONFIG_PATHS = [
          /\.md$/i, /\.jsonl$/i, /\/memory\//i, /\/tmp\//i, /TASK\.md/i,
        ];
        let targetPath = "";
        if (toolName === "exec") {
          targetPath = String(params?.command || "");
        } else {
          targetPath = String(params?.file_path || params?.path || "");
        }
        const isConfigFile = CONFIG_FILE_PATTERNS.some(p => p.test(targetPath));
        const isExempt = EXEMPT_CONFIG_PATHS.some(p => p.test(targetPath));
        // For exec commands: only flag if the command actually writes to the config file.
        // Read-only commands (cat, grep, head, tail, python read, jq) should pass through.
        const isExecReadOnly = toolName === "exec" && isConfigFile && (() => {
          const cmd = targetPath;
          const EXEC_WRITE_PATTERNS = [
            /\s>\s/, /\s>>\s/, /\btee\b/, /\bsed\s+-i/, /\bperl\s+-[ip]/,
            /\becho\b.*>/, /\bprintf\b.*>/, /\bmv\b/, /\brm\b/, /\btrash\b/,
          ];
          return !EXEC_WRITE_PATTERNS.some(p => p.test(cmd));
        })();
        if (isConfigFile && !isExempt && !isExecReadOnly) {
          const sessionKey = ctx?.sessionKey || "";
          const ev = turnEvidence.get(sessionKey);
          const recentCalls = ev?.toolCalls || [];
          const BACKUP_PATTERNS = [/\bcp\b/, /\brsync\b/, /\.bak\b/, /backup/i, /\bcopy\b/i];
          const hasBackup = recentCalls.slice(-10).some(call => {
            const cmd = String(call.command || call.toolName || "");
            return BACKUP_PATTERNS.some(p => p.test(cmd));
          });
          if (!hasBackup) {
            log("BLOCK", "Config Change Gate — no backup evidence", {
              targetPath: targetPath.slice(0, 80),
              sessionKey: sessionKey.slice(0, 30)
            });
            return {
              block: true,
              blocked: true,
              blockReason: "🛡️ Config Change Gate: Back up config before modifying. Run: cp <file> <file>.bak" + ERROR_EXPLAIN_INSTRUCTION
            };
          }
          log("INFO", "Config Change Gate — backup evidence found ✅", { targetPath: targetPath.slice(0, 80) });
        }
      }

      // --- Layer 6d: Atomic Rebuild Gate ---
      if (toolName === "exec") {
        const command = String(params?.command || "");
        // Strip false-positive content (quotes, comments, grep args) before pattern matching
        const strippedCommand = stripFalsePositiveContent(command);
        const ATOMIC_REBUILD_PATTERNS = [
          /\bdelete_nodes\b/,
          /\brm\s/,
          /\btrash\s/,
          /DROP\s+TABLE/i,
          /\btruncate\b/i,
        ];
        const ATOMIC_REBUILD_EXEMPT_PATTERNS = [
          /\/tmp\//i,
          /\.cache\//i,
          /\.log\b/i,
          /\bnode_modules\b/i,
          /\b__pycache__\b/i,
        ];
        const destructivePattern = ATOMIC_REBUILD_PATTERNS.find((pattern) => pattern.test(strippedCommand));
        const isExempt = ATOMIC_REBUILD_EXEMPT_PATTERNS.some((pattern) => pattern.test(strippedCommand));
        if (destructivePattern && !isExempt) {
          log("BLOCK", "Atomic Rebuild Gate — destructive operation detected", {
            pattern: destructivePattern.toString(),
            commandPreview: command.slice(0, 120)
          });
          return {
            block: true,
            blocked: true,
            blockReason: "Atomic Rebuild Gate: Destructive operation detected. Ensure replacement content exists BEFORE deleting. Create → Verify → Delete."
          };
        }
      }

      // --- Layer 6g: Model Selection Hierarchy Gate ---
      // Blocks expensive model usage for routine tasks without justification.
      if (toolName === "sessions_spawn" && params?.model) {
        const model = String(params.model).toLowerCase();
        const EXPENSIVE_MODELS = [/opus/, /sonnet/, /gpt-4o/, /gpt-5(?!\.3-codex)/];
        const isExpensive = EXPENSIVE_MODELS.some(p => p.test(model));
        if (isExpensive) {
          const task = String(params?.task || params?.message || "").toLowerCase();
          const COMPLEXITY_KEYWORDS = ["architecture", "reasoning", "complex", "design-level", "strategic", "debate", "audit", "security", "protocol"];
          const hasJustification = COMPLEXITY_KEYWORDS.some(k => task.includes(k));
          if (!hasJustification) {
            log("BLOCK", "Model Selection Hierarchy Gate — expensive model for routine task", {
              model: model.slice(0, 40),
              taskPreview: task.slice(0, 80)
            });
            return {
              block: true,
              blocked: true,
              blockReason: "🛡️ Model Selection Gate: Expensive model (" + model + ") used for routine task. Use MiniMax or Haiku for non-complex work. Add complexity justification to task description if needed." + ERROR_EXPLAIN_INSTRUCTION
            };
          }
          log("INFO", "Model Selection Gate — expensive model justified ✅", { model: model.slice(0, 40) });
        }
      }

      // --- Layer 9: Logician Runtime Policy ---
      // Query Logician for injection detection and tool permission checks.
      // Fail-OPEN: if Logician is unavailable, allow with warning.
      if (fs.existsSync(LOGICIAN_SOCK)) {
        // 9a: Injection detection — scan user-facing text inputs
        if (toolName === "exec" || toolName === "sessions_spawn") {
          const textToCheck = toolName === "exec"
            ? (params?.command || "")
            : (params?.task || params?.message || "");
          if (textToCheck.length > 10) {
            const lowerText = textToCheck.toLowerCase();
            // Quick local pre-check before hitting gRPC
            const INJECTION_HINTS = ["ignore previous", "disregard", "jailbreak", "dan mode", "pretend you are", "system prompt", "reveal your"];
            const maybeInjection = INJECTION_HINTS.some(h => lowerText.includes(h));
            if (maybeInjection) {
              // Confirm with Logician
              const answers = queryLogician("injection_pattern(X)");
              const patterns = answers.map(a => {
                const m = a.match(/injection_pattern\("(.+)"\)/);
                return m ? m[1].toLowerCase() : null;
              }).filter(Boolean);
              const matched = patterns.find(p => lowerText.includes(p));
              if (matched) {
                log("BLOCK", "Logician Injection Detection", { tool: toolName, pattern: matched, textPreview: textToCheck.slice(0, 60) });
                return { block: true, blockReason: `[Logician] Injection pattern detected: "${matched}". Blocked for safety.` + ERROR_EXPLAIN_INSTRUCTION };
              }
            }
          }
        }

        // 9b: Tool permission check
        const agentId = ctx?.agentId || "main";
        const TOOL_MAP = { exec: "exec", write: "file_write", edit: "file_write", web_search: "brave_api", web_fetch: "web_fetch", browser: "browser", message: "message_send", tts: "tts", sessions_spawn: "sessions_spawn" };
        const logicianTool = TOOL_MAP[toolName];
        if (logicianTool && agentId !== "main") {
          const proves = logicianProves(`can_use_tool(/${agentId}, /${logicianTool})`);
          if (!proves) {
            log("BLOCK", "Logician: tool not in permission set", { agentId, tool: logicianTool, allowed: false });
            return { block: true, blocked: true, blockReason: "Trust Level Gate: tool '" + logicianTool + "' not in permission set for agent '" + agentId + "'" };
          }
        }

        // 9c: Spawn permission check (sessions_spawn tool)
        if (toolName === "sessions_spawn") {
          const targetAgent = params?.agentId || params?.runtime || "unknown";
          if (targetAgent !== "unknown") {
            const spawnAllowed = logicianProves(`spawn_allowed(/main, /${targetAgent})`);
            if (!spawnAllowed) {
              log("BLOCK", "Logician: spawn not in allowed set", { from: "main", to: targetAgent });
              return { block: true, blockReason: "Spawn Permission Gate: agent 'main' cannot spawn '" + targetAgent + "'" };
            }
          }
        }
      }

      return advisoryWarning ? { warning: advisoryWarning } : {};
    } catch (err) {
      // Fail-OPEN: extension errors must never block legitimate work
      log("ERROR", "Shield Gate error — failing open", { error: err.message });
      return {};
    }
  });

  // --- Layer 6: Repo Contamination Gate (outbound message scanning) ---
  const PRIVATE_PATTERNS = [
    /resonantos-augmentor/i,
    /ssot\/private/i,
    /MEMORY\.md/i,
    /memory\/\d{4}-\d{2}-\d{2}\.md/i,
    /\/Users\/augmentor\//i,
    /ManoloRemiddi\/resonantos-augmentor/i,
  ];
  // Manolo's Telegram DM — the only channel where private references are safe
  const SAFE_DESTINATIONS = ["7825655623", "telegram:7825655623"];

  api.on("message_sending", (event, ctx) => {
    try {
      const content = event?.content || "";
      const to = String(event?.to || "");
      const isSafeDest = SAFE_DESTINATIONS.some(d => to.includes(d));
      let outboundWarning = null;

      // --- Layer 6a: Repo Contamination Gate (skip for Manolo's DM) ---
      if (!isSafeDest) {
        for (const pattern of PRIVATE_PATTERNS) {
          if (pattern.test(content)) {
            log("BLOCK", "Repo Contamination Gate — cancelled outbound message", {
              to: to.slice(0, 30),
              pattern: pattern.toString(),
              contentPreview: content.slice(0, 80)
            });
            return { cancel: true };
          }
        }
      }

      // --- Layer 6b: Verification Claim Gate (all destinations including DM) ---
      // If message claims something is "fixed"/"verified", check for exec evidence.
      // This is the #1 failure mode: saying "fixed" without running a test.
      const claimPattern = containsVerificationClaim(content);
      if (claimPattern) {
        const sessionKey = ctx?.sessionKey || "";
        const hasEvidence = hasTestEvidence(sessionKey);
        if (!hasEvidence) {
          // HARD BLOCK: Block the message when "fixed" is claimed without exec evidence
          log("BLOCK", "Verification Claim Gate — 'fixed' claim without exec evidence", {
            pattern: claimPattern,
            sessionKey: sessionKey.slice(0, 30),
            contentPreview: content.slice(0, 80)
          });
          return {
            block: true,
            blockReason: "🛡️ Verification Gate: You claimed 'fixed' without running a test. Run a test first, then report results. Do not claim something is fixed without evidence." + ERROR_EXPLAIN_INSTRUCTION
          };
        } else {
          log("INFO", "Verification Claim Gate — claim has exec evidence ✅", {
            pattern: claimPattern,
            sessionKey: sessionKey.slice(0, 30)
          });
        }
      }

      // --- Layer 6c: State Claim Gate (all destinations including DM) ---
      // If message claims system state counts/status/version, require recent verification command.
      const stateClaimPattern = containsStateClaim(content);
      if (stateClaimPattern) {
        const sessionKey = ctx?.sessionKey || "";
        const hasRecentVerification = hasRecentVerificationCommand(sessionKey);
        if (!hasRecentVerification) {
          log("BLOCK", "State Claim Gate — state claim without verification command", {
            pattern: stateClaimPattern,
            sessionKey: sessionKey.slice(0, 30),
            contentPreview: content.slice(0, 80)
          });
          return {
            block: true,
            blockReason: "🛡️ State Claim Gate: System state claim detected without a verification command in the last 20 tool calls. Run a verification command first (for example `openclaw status`, `openclaw skills`, `openclaw agents`, `openclaw plugins`) and then report the claim." + ERROR_EXPLAIN_INSTRUCTION
          };
        } else {
          log("INFO", "State Claim Gate — state claim has verification evidence ✅", {
            pattern: stateClaimPattern,
            sessionKey: sessionKey.slice(0, 30)
          });
        }
      }

      // --- Layer 6e: Behavioral Integrity Gate ---
      const overclaim = containsBehavioralOverclaim(content);
      if (overclaim) {
        log("BLOCK", "Behavioral Integrity Gate — potential overclaim", {
          pattern: overclaim.pattern,
          preview: overclaim.preview
        });
        return {
          block: true,
          blocked: true,
          blockReason: "Behavioral Integrity Gate: Overclaim detected. Rephrase with evidence or qualifier."
        };
      }

      // --- Layer 6d: Decision Bias Gate ---
      // Detects when the agent presents multiple options where SOUL.md decision
      // filters would narrow to one. If options are presented but one clearly
      // wins on safety/cost/simplicity, warn to just act instead of asking.
      const OPTION_PATTERNS = [
        /\bOption\s+[A-C]\b/g,                          // Option A, Option B, Option C
        /\b(?:option|choice)\s*(?:#?\s*)?[1-3]\b/ig,    // option 1, choice #2
        /\*\*(?:Option|Choice)\s+[A-C1-3]\b/g,          // **Option A (markdown bold)
        /^\s*[-•]\s*\*?\*?(?:Option|Choice)\s+/im,      // bullet lists with Option
      ];
      const ASKING_PATTERNS = [
        /\bwant me to\b/i,
        /\bwhich (?:would you|do you|option)\b/i,
        /\bwhat do you (?:think|prefer|want)\b/i,
        /\byour (?:call|choice|preference)\b/i,
        /\bshould I\b/i,
        /\blet me know\b/i,
      ];
      // Count distinct options
      let optionCount = 0;
      for (const pat of OPTION_PATTERNS) {
        const matches = content.match(pat);
        if (matches) optionCount = Math.max(optionCount, matches.length);
      }
      const isAskingUser = ASKING_PATTERNS.some(p => p.test(content));
      if (optionCount >= 2 && isAskingUser) {
        log("BLOCK", "Decision Bias Gate — presenting options instead of acting", {
          optionCount,
          contentPreview: content.slice(0, 120)
        });
        return { block: true, blockReason: "Decision Bias Gate: You presented " + optionCount + " options. Apply SOUL.md decision bias filters. If one option clearly wins, act — don't ask." };
      }

      // --- Layer 6h: Autonomous Development Gate ---
      // Blocks design-level implementation claims without self-debate evidence.
      const DESIGN_TRIGGERS = [
        /\bnew\s+(?:system|architecture|protocol|framework|engine)\b/i,
        /\bstrategic\s+decision\b/i,
        /\bdesign-level\b/i,
        /\bredesign(?:ing)?\b/i,
      ];
      const IMPLEMENTATION_INTENT = [
        /\b(?:i(?:'ll|'m going to|'m)\s+(?:build|create|implement|design|architect))\b/i,
        /\bbuilding\s+(?:a\s+)?new\b/i,
        /\bcreating\s+(?:a\s+)?new\b/i,
        /\bimplementing\s+(?:a\s+)?new\b/i,
        /\blet me (?:build|create|implement)\b/i,
      ];
      const hasDesignTrigger = DESIGN_TRIGGERS.some(p => p.test(content));
      const hasImplementationIntent = IMPLEMENTATION_INTENT.some(p => p.test(content));
      if (hasDesignTrigger && hasImplementationIntent && content.length > 100) {
        const sessionKey = ctx?.sessionKey || "";
        const ev = turnEvidence.get(sessionKey);
        const recentCalls = ev?.toolCalls || [];
        const DEBATE_EVIDENCE = [/self-debate/i, /debate/i, /adversarial/i];
        const hasDebate = recentCalls.slice(-20).some(call => {
          const cmd = String(call.command || call.toolName || "");
          return DEBATE_EVIDENCE.some(p => p.test(cmd));
        });
        if (!hasDebate) {
          log("BLOCK", "Autonomous Development Gate — design-level work without self-debate", {
            contentPreview: content.slice(0, 120),
            sessionKey: sessionKey.slice(0, 30)
          });
          return {
            block: true,
            blocked: true,
            blockReason: "🛡️ Autonomous Development Gate: Design-level implementation detected without self-debate evidence. Run self-debate (≥5 rounds) before building new systems/architectures. See SOUL.md." + ERROR_EXPLAIN_INSTRUCTION
          };
        }
        log("INFO", "Autonomous Development Gate — debate evidence found ✅", {
          sessionKey: sessionKey.slice(0, 30)
        });
      }

      // --- Layer 6e: Research Gate — Force Perplexity via browser ---
      // Block any research task that doesn't use Perplexity
      const RESEARCH_PATTERNS = [
        /\bresearch\b/i,
        /\binvestigate\b/i,
        /\bdeep\s+dive\b/i,
        /\banalyze\b.*\blandscape\b/i,
        /\btrends?\b/i,
      ];
      const researchMatch = RESEARCH_PATTERNS.some(p => p.test(content));
      const hasPerplexity = content.toLowerCase().includes("perplexity") || (content.toLowerCase().includes("browser") && content.toLowerCase().includes("search"));
      if (researchMatch && !hasPerplexity) {
        log("BLOCK", "Research Gate: Research requested without Perplexity", { content: content.slice(0, 80) });
        return {
          block: true,
          blockReason: "🛡️ Research Gate: All research must use Perplexity via browser. Use browser tool to navigate to perplexity.ai and run deep research there." + ERROR_EXPLAIN_INSTRUCTION
        };
      }

      return outboundWarning ? { warning: outboundWarning } : {};
    } catch (err) {
      log("ERROR", "Message Gate error — failing open", { error: err.message });
      return {};
    }
  });

  // --- Layer 10: Spawn Permission Gate (Logician-backed) ---
  // --- Layer 10: Spawn Permission Gate (Logician-backed) + Codex-Only Coding Gate ---

  // Coding task indicators — if task contains these, it's a coding task
  const CODING_TASK_PATTERNS = [
    /\bimplement\b/i, /\bbuild\s+(?:a\s+)?(?:feature|component|module|page|route)\b/i,
    /\bfix\b.*\b(?:bug|issue|error|crash)\b/i, /\brefactor\b/i,
    /\bwrite\s+(?:the\s+)?(?:code|function|class|module|test)\b/i,
    /\bcoding\s+(?:task|agent)\b/i, /\bcreate\s+(?:a\s+)?(?:script|file|component)\b/i,
    /\bcodex\b/i, /\bcode\s+review\b/i,
    /\bTASK\.md\b/,  // Delegation protocol reference = coding task
  ];

  // Known coding agent labels/ids (non-Codex coders that should be blocked)
  const BLOCKED_CODER_AGENTS = ["opus_coder", "claude_coder", "coder"];

  // The ONLY allowed coding agent
  const ALLOWED_CODING_METHOD = "codex";  // Must use codex exec, not sub-agent coders

  function isCodingTask(task) {
    if (!task) return false;
    return CODING_TASK_PATTERNS.some(p => p.test(task));
  }

  api.on("subagent_spawning", (event, ctx) => {
    try {
      const parentAgent = ctx?.agentId || "main";
      const childAgent = event?.agentId || event?.label || "";
      const task = event?.task || "";
      if (!childAgent) return {};

      log("DEBUG", "subagent_spawning", { parent: parentAgent, child: childAgent, taskPreview: task.slice(0, 80) });

      // --- Layer 10a: Codex-Only Coding Gate ---
      // SOUL.md: "Delegate ALL implementation to OpenAI Codex CLI (codex exec).
      // NEVER use Opus-based coder sub-agents."
      const childLower = childAgent.toLowerCase();
      if (BLOCKED_CODER_AGENTS.some(b => childLower.includes(b))) {
        log("BLOCK", "Codex-Only Gate — blocked non-Codex coding agent", {
          parent: parentAgent,
          child: childAgent,
          taskPreview: task.slice(0, 100)
        });
        return { block: true, blockReason: `[Codex-Only Gate] Coding agent "${childAgent}" is not allowed. Use Codex CLI (codex exec) for all implementation tasks. See SOUL.md orchestrator rules.` + ERROR_EXPLAIN_INSTRUCTION };
      }

      // If it's a coding task spawned as a generic sub-agent, warn
      // (can't block because the task might be delegated correctly via codex exec inside)
      if (isCodingTask(task) && !childLower.includes("codex")) {
        log("WARN", "Codex-Only Gate — coding task spawned as non-codex agent (warn only)", {
          parent: parentAgent,
          child: childAgent,
          taskPreview: task.slice(0, 100)
        });
      }

      // --- Layer 10c: Delegation Protocol Read Check ---
      // SOUL.md + DELEGATION_PROTOCOL.md: "Read DELEGATION_PROTOCOL.md before EVERY delegation."
      // If spawning a coding task and the orchestrator hasn't read the protocol this turn → BLOCK.
      if (isCodingTask(task) && parentAgent === "main") {
        const hasReadProtocol = hasReadFile(ctx?.sessionKey, "DELEGATION_PROTOCOL");
        if (!hasReadProtocol) {
          log("BLOCK", "Delegation Protocol Gate — protocol not read before coding delegation", {
            parent: parentAgent,
            child: childAgent,
            taskPreview: task.slice(0, 100)
          });
          return {
            block: true,
            blockReason: `[Delegation Protocol Gate] You must read DELEGATION_PROTOCOL.md before delegating coding tasks. This prevents the "throw task over the wall" failure mode. Read it, complete the checklist, then spawn again.` + ERROR_EXPLAIN_INSTRUCTION
          };
        } else {
          log("INFO", "Delegation Protocol Gate — protocol read confirmed", {
            parent: parentAgent,
            child: childAgent
          });
        }
      }

      // --- Layer 10d: Model Cost Enforcement ---
      // Checks if the model assigned to this spawn is appropriate for the task type.
      // Uses model-pricing.json (updated daily by deterministic collector).
      const spawnModel = (event?.model || "").toLowerCase();
      if (spawnModel) {
        try {
          const pricingPath = path.join(process.env.HOME, "resonantos-augmentor/shield/model-pricing.json");
          if (fs.existsSync(pricingPath)) {
            const pricing = JSON.parse(fs.readFileSync(pricingPath, "utf8"));
            const taskLower = task.toLowerCase();

            // Determine task type from content
            let taskType = "unknown";
            if (/heartbeat|routine\s*check|periodic/i.test(taskLower)) taskType = "heartbeat";
            else if (/compress|compaction|swap/i.test(taskLower)) taskType = "compression";
            else if (/background|overnight|batch/i.test(taskLower)) taskType = "background";
            else if (/research|investigate|search/i.test(taskLower)) taskType = "research";
            else if (isCodingTask(task)) taskType = "coding";

            const policy = pricing.task_policy?.[taskType];
            if (policy) {
              const maxTier = policy.max_tier;
              const tierOrder = ["free", "cheap", "moderate", "expensive"];
              const maxIdx = tierOrder.indexOf(maxTier);

              // Find the tier of the requested model
              let modelTier = null;
              for (const [tierName, tierData] of Object.entries(pricing.tiers)) {
                if (tierData.models?.some(m => spawnModel.includes(m.split("/").pop()))) {
                  modelTier = tierName;
                  break;
                }
              }
              const modelIdx = tierOrder.indexOf(modelTier);

              if (modelTier && modelIdx > maxIdx) {
                log("WARN", "Model Cost Gate — model too expensive for task type", {
                  model: spawnModel,
                  modelTier,
                  taskType,
                  maxTier,
                  reason: policy.reason
                });
                // Warn mode — log but don't block (subscription makes some "expensive" models free)
                // TODO: switch to block for non-subscription models after validation
              } else if (modelTier) {
                log("DEBUG", "Model Cost Gate — model within budget", {
                  model: spawnModel, modelTier, taskType, maxTier
                });
              }
            }
          }
        } catch (costErr) {
          log("ERROR", "Model Cost Gate error — failing open", { error: costErr.message });
        }
      }

      // --- Layer 10b: Logician spawn permission check ---
      if (fs.existsSync(LOGICIAN_SOCK)) {
        const proves = logicianProves(`spawn_allowed(/${parentAgent}, /${childAgent})`);
        if (!proves) {
          log("BLOCK", "Logician: spawn not in permission set", {
            parent: parentAgent,
            child: childAgent,
            allowed: false
          });
          return { block: true, blockReason: "Spawn Permission Gate: agent '" + parentAgent + "' cannot spawn '" + childAgent + "'" };
        } else {
          log("INFO", "Logician: spawn permitted", { parent: parentAgent, child: childAgent });
        }
      }

      return {};
    } catch (err) {
      log("ERROR", "Spawn Permission Gate error — failing open", { error: err.message });
      return {};
    }
  });

  // --- Post-Compaction Recovery: set state flag after compaction ---
  api.on("after_compaction", (event, ctx) => {
    try {
      log("INFO", "Compaction detected — setting recovery state", {
        messageCount: event?.messageCount,
        agentId: ctx?.agentId
      });
      // Only set recovery for main session
      if (ctx?.agentId === "main") {
        updateCompactionState({
          ts: Date.now(),
          readWorkflow: false,
          readMemory: false,
          agentId: ctx.agentId
        });
      }
    } catch (err) {
      log("ERROR", "after_compaction handler error", { error: err.message });
    }
  });
};
