"use strict";

const fs = require("fs");
const path = require("path");

const BASE_DIR = "/Users/augmentor/resonantos-augmentor/coherence-gate";
const TASK_DIR = path.join(BASE_DIR, "tasks");
const AUDIT_DIR = path.join(BASE_DIR, "audit");
const LOG_DIR = path.join(BASE_DIR, "logs");
const LOG_FILE = path.join(LOG_DIR, "coherence-gate.log");
const CONFIG_FILE = path.join(BASE_DIR, "config.json");

const DEFAULT_CONFIG = {
  mode: "advisory",
  logLevel: "info",
  significantTools: ["write", "edit", "exec", "message", "sessions_spawn"],
  readOnlyExecPatterns: [
    "^ls\\b",
    "^cat\\b",
    "^head\\b",
    "^tail\\b",
    "^grep\\b",
    "^find\\b",
    "^echo\\b",
    "^pwd\\b",
    "^whoami\\b",
    "^date\\b",
    "^which\\b",
    "^wc\\b",
    "^sort\\b",
    "^git\\s+(status|log|diff|show|branch)\\b",
    "^test\\b"
  ],
  excludePaths: ["coherence-gate/", "r-memory/", "/tmp/", "shield/logs/"],
  maxActiveTaskAgeSeconds: 7200,
  driftThreshold: 2
};

const ALWAYS_SKIP_TOOLS = new Set([
  "read",
  "memory_search",
  "memory_get",
  "web_search",
  "web_fetch",
  "session_status"
]);

const STOP_WORDS = new Set([
  "the", "and", "for", "with", "from", "this", "that", "what", "will", "into",
  "your", "you", "are", "was", "were", "have", "has", "had", "about", "task",
  "docs", "doc", "file", "files", "write", "edit", "update", "create", "then",
  "todo", "done", "none", "minor", "major", "all", "any", "not", "only", "out",
  "log", "logs", "mode", "send", "message", "tool", "action"
]);

function ensureDirs() {
  for (const dir of [BASE_DIR, TASK_DIR, AUDIT_DIR, LOG_DIR]) {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  }
}

function mergeConfig(parsed) {
  return {
    ...DEFAULT_CONFIG,
    ...(parsed || {}),
    significantTools: parsed?.significantTools || DEFAULT_CONFIG.significantTools,
    readOnlyExecPatterns: parsed?.readOnlyExecPatterns || DEFAULT_CONFIG.readOnlyExecPatterns,
    excludePaths: parsed?.excludePaths || DEFAULT_CONFIG.excludePaths
  };
}

function loadConfig() {
  ensureDirs();
  if (!fs.existsSync(CONFIG_FILE)) {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(DEFAULT_CONFIG, null, 2) + "\n");
    return { ...DEFAULT_CONFIG };
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(CONFIG_FILE, "utf8"));
    return mergeConfig(parsed);
  } catch (_) {
    return { ...DEFAULT_CONFIG };
  }
}

function shouldLog(config, level) {
  const levels = { debug: 10, info: 20, warn: 30, error: 40 };
  const current = levels[String(config.logLevel || "info").toLowerCase()] || 20;
  const target = levels[String(level || "info").toLowerCase()] || 20;
  return target >= current;
}

function log(config, level, message, data) {
  try {
    if (!shouldLog(config, level)) return;
    ensureDirs();
    const ts = new Date().toISOString();
    const entry = `[${ts}] [${String(level).toUpperCase()}] ${message}${data ? ` ${JSON.stringify(data)}` : ""}`;
    fs.appendFileSync(LOG_FILE, `${entry}\n`);
  } catch (_) {
    // logging should never crash the gate
  }
}

function escapeRegex(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parseTask(content, filePath) {
  const getField = (name) => {
    const match = content.match(new RegExp(`^- ${escapeRegex(name)}:\\s*(.*)$`, "mi"));
    return match ? match[1].trim() : "";
  };
  const desc = (content.match(/^# Task:\s*(.*)$/mi) || [null, ""])[1].trim();
  return {
    filePath,
    content,
    description: desc,
    created: getField("Created"),
    status: getField("Status"),
    refs: getField("SSoT refs"),
    intent: getField("Intent"),
    successCriteria: getField("Success criteria")
  };
}

function getTaskFiles(dirPath) {
  if (!fs.existsSync(dirPath)) return [];
  return fs
    .readdirSync(dirPath)
    .filter((name) => /^TASK-.*\.md$/.test(name))
    .map((name) => path.join(dirPath, name));
}

function getActiveTask() {
  const tasks = getTaskFiles(TASK_DIR)
    .map((filePath) => parseTask(fs.readFileSync(filePath, "utf8"), filePath))
    .filter((task) => String(task.status).toLowerCase() === "active");

  tasks.sort((a, b) => {
    const aTs = Date.parse(a.created || "") || fs.statSync(a.filePath).mtimeMs;
    const bTs = Date.parse(b.created || "") || fs.statSync(b.filePath).mtimeMs;
    return bTs - aTs;
  });
  return tasks[0] || null;
}

function addExecutionEntry(taskFilePath, entryText) {
  let content = fs.readFileSync(taskFilePath, "utf8");
  if (!content.includes("## Completion")) {
    content = `${content.trimEnd()}\n\n## Completion\n- Evidence: \n- Drift: none\n- Drift detail: \n`;
  }

  const completionMarker = "\n## Completion";
  const completionIndex = content.indexOf(completionMarker);
  let head = content.slice(0, completionIndex).trimEnd();
  const tail = content.slice(completionIndex);

  if (!head.includes("## Execution Log")) {
    head = `${head}\n\n## Execution Log`;
  }

  head = `${head}\n- ${entryText}`;
  const merged = `${head}\n${tail.replace(/^\n+/, "\n")}`;
  fs.writeFileSync(taskFilePath, `${merged.trimEnd()}\n`);
}

function getToolName(event) {
  return String(event?.toolName || event?.tool || "").trim();
}

function normalizePath(p) {
  return String(p || "").replace(/\\/g, "/");
}

function extractActionPath(toolName, params) {
  const directPathKeys = [
    "path", "filePath", "filepath", "targetPath", "destination", "dest", "to", "from"
  ];
  for (const key of directPathKeys) {
    if (typeof params?.[key] === "string" && params[key].trim()) {
      return normalizePath(params[key].trim());
    }
  }

  if (toolName === "exec") {
    const command = String(params?.command || params?.cmd || "").trim();
    const tokens = command
      .split(/\s+/)
      .map((token) => token.replace(/^['"]|['"]$/g, ""))
      .filter(Boolean);
    for (const token of tokens) {
      if (token.startsWith("-")) continue;
      if (token.includes("/") || token.includes("\\")) return normalizePath(token);
      if (/\.(md|txt|json|js|ts|tsx|jsx|py|sh|yml|yaml|toml|ini|cfg)$/i.test(token)) {
        return normalizePath(token);
      }
    }
  }

  return "";
}

function matchesExcludePath(actionPath, config) {
  if (!actionPath) return false;
  const normalized = normalizePath(actionPath).toLowerCase();
  return (config.excludePaths || []).some((prefix) => normalized.includes(String(prefix).toLowerCase()));
}

function isReadOnlyExec(command, config) {
  const trimmed = String(command || "").trim();
  if (!trimmed) return true;

  const obviousWrite = /(^|[\s;&|])(cp|mv|mkdir|rm|touch|chmod|chown|tee|sed|truncate|shred)\b|>{1,2}\s|git\s+push\b/i;
  if (obviousWrite.test(trimmed)) return false;

  const patterns = (config.readOnlyExecPatterns || []).map((source) => new RegExp(source, "i"));
  return patterns.some((pattern) => pattern.test(trimmed));
}

function execHasSideEffects(command, config) {
  const trimmed = String(command || "").trim();
  if (!trimmed) return false;
  if (isReadOnlyExec(trimmed, config)) return false;

  const sideEffectPatterns = [
    /\bgit\s+push\b/i,
    /(^|[\s;&|])(cp|mv|mkdir|rm|touch|chmod|chown|tee|sed|truncate|shred)\b/i,
    />{1,2}\s/,
    /\bpython3?\b/i,
    /\bnode\b/i,
    /\bnpm\b/i,
    /\bcodex\b/i
  ];
  return sideEffectPatterns.some((pattern) => pattern.test(trimmed));
}

function summarizeAction(toolName, params, actionPath) {
  if (toolName === "exec") {
    const command = String(params?.command || params?.cmd || "").trim();
    return `command=${command.slice(0, 140)}`;
  }
  if (toolName === "message") {
    return `action=${params?.action || "unknown"}`;
  }
  if (toolName === "sessions_spawn") {
    return `spawn target=${params?.name || params?.agent_type || "unknown"}`;
  }
  if (actionPath) return `path=${actionPath}`;
  return "action=unknown";
}

function evaluateSignificance(event, config) {
  const toolName = getToolName(event);
  const params = event?.params || {};
  const actionPath = extractActionPath(toolName, params);
  const actionSummary = summarizeAction(toolName, params, actionPath);

  if (ALWAYS_SKIP_TOOLS.has(toolName)) {
    return { significant: false, toolName, actionPath, actionSummary };
  }

  if (toolName === "cron") {
    const action = String(params?.action || "").toLowerCase();
    if (action === "list" || action === "status") {
      return { significant: false, toolName, actionPath, actionSummary };
    }
  }

  if (toolName === "write" || toolName === "edit") {
    if (matchesExcludePath(actionPath, config)) {
      return { significant: false, toolName, actionPath, actionSummary };
    }
    return { significant: true, toolName, actionPath, actionSummary };
  }

  if (toolName === "exec") {
    const command = params?.command || params?.cmd || "";
    return { significant: execHasSideEffects(command, config), toolName, actionPath, actionSummary };
  }

  if (toolName === "message") {
    return {
      significant: String(params?.action || "").toLowerCase() === "send",
      toolName,
      actionPath,
      actionSummary
    };
  }

  if (toolName === "sessions_spawn") {
    return { significant: true, toolName, actionPath, actionSummary };
  }

  const configuredSignificant = new Set(config.significantTools || []);
  return { significant: configuredSignificant.has(toolName), toolName, actionPath, actionSummary };
}

function extractKeywords(text) {
  return new Set(
    String(text || "")
      .toLowerCase()
      .replace(/[^a-z0-9_./-]+/g, " ")
      .split(/\s+/)
      .map((token) => token.trim())
      .filter((token) => token.length >= 3 && !STOP_WORDS.has(token))
  );
}

function extractPathHints(text) {
  const matches = String(text || "").match(/[a-z0-9._-]+(?:\/[a-z0-9._/-]+)+/gi) || [];
  return matches.map((item) => normalizePath(item.toLowerCase()));
}

function hasKeywordOverlap(aSet, bSet) {
  for (const item of aSet) {
    if (bSet.has(item)) return true;
  }
  return false;
}

function evaluateDrift(task, significance, event) {
  const params = event?.params || {};
  const actionPath = significance.actionPath || "";
  const toolName = significance.toolName;
  const commandText = toolName === "exec" ? String(params?.command || params?.cmd || "") : "";
  const actionText = `${actionPath} ${significance.actionSummary} ${commandText}`;

  const taskKeywords = extractKeywords(`${task.intent} ${task.description} ${task.refs}`);
  const actionKeywords = extractKeywords(actionText);
  const taskPathHints = extractPathHints(`${task.intent} ${task.description}`);
  const normalizedActionPath = normalizePath(actionPath.toLowerCase());

  const keywordAligned = hasKeywordOverlap(taskKeywords, actionKeywords);
  const pathAligned = taskPathHints.some(
    (hint) => normalizedActionPath && (normalizedActionPath.includes(hint) || hint.includes(normalizedActionPath))
  );

  let score = 0;
  let detail = "aligned";
  if (!keywordAligned && !pathAligned) {
    if (normalizedActionPath) {
      score = 2;
      detail = "action path and keywords do not overlap task intent";
    } else {
      score = 1;
      detail = "action keywords are weakly aligned with task intent";
    }
  }

  const label = score === 0 ? "aligned" : score === 1 ? "minor" : "major";
  return { score, label, detail };
}

function summarizeResult(event) {
  if (event?.error) {
    const errorText = String(event.error?.message || event.error);
    return `error=${errorText.slice(0, 160)}`;
  }

  const result = event?.result;
  if (result == null) return "ok";
  if (typeof result === "string") return `ok=${result.slice(0, 120)}`;
  if (typeof result === "object") {
    if (result.error) return `error=${String(result.error).slice(0, 160)}`;
    if (Object.prototype.hasOwnProperty.call(result, "status")) return `status=${String(result.status).slice(0, 120)}`;
    if (Object.prototype.hasOwnProperty.call(result, "success")) return `success=${String(result.success)}`;
  }
  return "ok";
}

function isTaskStale(task, config) {
  const maxAge = Number(config.maxActiveTaskAgeSeconds || 0);
  if (!maxAge) return false;
  const createdMs = Date.parse(task.created || "");
  if (!createdMs) return false;
  const ageSeconds = Math.floor((Date.now() - createdMs) / 1000);
  return ageSeconds > maxAge;
}

module.exports = function coherenceGateExtension(api) {
  ensureDirs();
  log(loadConfig(), "info", "Coherence Gate extension loaded");

  api.on("before_agent_start", () => {
    log(loadConfig(), "info", "Agent start observed");
    return {};
  });

  api.on("agent_end", () => {
    log(loadConfig(), "info", "Agent end observed");
    return {};
  });

  api.on("before_tool_call", (event) => {
    const config = loadConfig();
    try {
      log(config, "debug", "before_tool_call fired", { tool: getToolName(event) });
      const significance = evaluateSignificance(event, config);
      if (!significance.significant) return {};

      const task = getActiveTask();
      if (!task) {
        const mode = String(config.mode || "advisory").toLowerCase();
        const guidance = "Coherence Gate: No active task. Create one first with `node coherence-gate/cg-cli.js create ...`.";
        log(config, "warn", "Significant action without active task", {
          mode,
          tool: significance.toolName,
          action: significance.actionSummary
        });

        const shouldBlockStrict = mode === "strict";
        const shouldBlockGated = mode === "gated" && (
          significance.toolName === "message" || significance.toolName === "sessions_spawn"
        );

        if (shouldBlockStrict || shouldBlockGated) {
          return {
            block: true,
            blockReason: `${guidance} (mode=${mode})`
          };
        }

        if (mode === "advisory") return { warning: guidance };
        return {};
      }

      if (isTaskStale(task, config)) {
        log(config, "warn", "Active task exceeds max age", {
          task: path.basename(task.filePath),
          created: task.created,
          maxActiveTaskAgeSeconds: config.maxActiveTaskAgeSeconds
        });
      }

      const drift = evaluateDrift(task, significance, event);
      addExecutionEntry(
        task.filePath,
        `${new Date().toISOString()}: ${significance.toolName} -> ${significance.actionSummary} (drift=${drift.score})`
      );
      log(config, "info", "Significant action logged", {
        task: path.basename(task.filePath),
        tool: significance.toolName,
        driftScore: drift.score
      });

      if (drift.score >= Number(config.driftThreshold || 2)) {
        log(config, "warn", "Potential drift detected", {
          task: path.basename(task.filePath),
          drift
        });

        if (String(config.mode || "advisory").toLowerCase() === "advisory") {
          return {
            warning: `Coherence Gate: potential drift detected (${drift.label}). ${drift.detail}`
          };
        }
      }

      return {};
    } catch (error) {
      log(config, "error", "before_tool_call error (fail-open)", { error: String(error.message || error) });
      return {};
    }
  });

  api.on("after_tool_call", (event) => {
    const config = loadConfig();
    try {
      const significance = evaluateSignificance(event, config);
      if (!significance.significant) return {};

      const task = getActiveTask();
      if (!task) return {};

      const resultSummary = summarizeResult(event);
      addExecutionEntry(
        task.filePath,
        `${new Date().toISOString()}: ${significance.toolName} result -> ${resultSummary}`
      );
      log(config, "info", "Tool result logged", {
        task: path.basename(task.filePath),
        tool: significance.toolName,
        result: resultSummary
      });
      return {};
    } catch (error) {
      log(config, "error", "after_tool_call error (fail-open)", { error: String(error.message || error) });
      return {};
    }
  });
};
