#!/usr/bin/env node
// ResonantOS Alpha Installer — Cross-platform (macOS, Linux, Windows)
// Usage: npx https://github.com/ResonantOS/resonantos-alpha install
//   or:  node install.js

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const REPO = "https://github.com/ResonantOS/resonantos-alpha.git";
const HOME = os.homedir();
const INSTALL_DIR = path.join(HOME, "resonantos-alpha");
const OPENCLAW_AGENT_DIR = path.join(HOME, ".openclaw", "agents", "main", "agent");
const OPENCLAW_WORKSPACE = path.join(HOME, ".openclaw", "workspace");

const isWin = process.platform === "win32";

function log(msg) { console.log(msg); }
function ok(msg) { log(`✓ ${msg}`); }
function fail(msg) { console.error(`ERROR: ${msg}`); process.exit(1); }

function hasCmd(cmd) {
  try {
    execSync(isWin ? `where ${cmd}` : `command -v ${cmd}`, { stdio: "ignore" });
    return true;
  } catch { return false; }
}

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: "inherit", ...opts });
}

function mkdirp(dir) { fs.mkdirSync(dir, { recursive: true }); }

function copyFile(src, dest) {
  mkdirp(path.dirname(dest));
  fs.copyFileSync(src, dest);
}

function copyDirContents(src, dest) {
  mkdirp(dest);
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDirContents(s, d);
    else fs.copyFileSync(s, d);
  }
}

function writeJsonIfMissing(filePath, data, label) {
  if (!fs.existsSync(filePath)) {
    mkdirp(path.dirname(filePath));
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n");
    ok(`${label} installed`);
  }
}

// ── Main ──

log("=== ResonantOS Alpha Installer ===\n");

// 1. Check dependencies
if (!hasCmd("git")) fail("git is required. Install: https://git-scm.com/");
if (!hasCmd("node")) fail("node is required. Install: https://nodejs.org/");
if (!hasCmd("python3") && !hasCmd("python"))
  fail("Python 3 is required. Install: https://www.python.org/");

const nodeVer = parseInt(process.versions.node.split(".")[0], 10);
if (nodeVer < 18) fail(`Node.js 18+ required (found v${process.versions.node})`);

const pip = hasCmd("pip3") ? "pip3" : hasCmd("pip") ? "pip" : null;
if (!pip) fail("pip3/pip is required (should come with Python 3).");

const python = hasCmd("python3") ? "python3" : "python";

// 2. Check/install OpenClaw
if (!hasCmd("openclaw")) {
  log("OpenClaw not found. Installing...");
  run("npm install -g openclaw");
}

ok("Dependencies OK");

// 3. Clone or pull repo
if (fs.existsSync(path.join(INSTALL_DIR, ".git"))) {
  log(`Directory ${INSTALL_DIR} exists. Pulling latest...`);
  run("git pull", { cwd: INSTALL_DIR });
} else {
  log("Cloning ResonantOS Alpha...");
  run(`git clone ${REPO} "${INSTALL_DIR}"`);
}

// 4. Copy extensions
log("Installing extensions...");
const extDir = path.join(OPENCLAW_AGENT_DIR, "extensions");
mkdirp(extDir);
copyFile(path.join(INSTALL_DIR, "extensions", "r-memory.js"), path.join(extDir, "r-memory.js"));
copyFile(path.join(INSTALL_DIR, "extensions", "r-awareness.js"), path.join(extDir, "r-awareness.js"));
copyFile(path.join(INSTALL_DIR, "extensions", "gateway-lifecycle.js"), path.join(extDir, "gateway-lifecycle.js"));
ok("Extensions installed");

// 5. SSoT template
log("Setting up SSoT documents...");
const ssotDir = path.join(OPENCLAW_WORKSPACE, "resonantos-alpha", "ssot");
mkdirp(ssotDir);
const ssotEmpty = fs.readdirSync(ssotDir).length === 0;
if (ssotEmpty) {
  copyDirContents(path.join(INSTALL_DIR, "ssot-template"), ssotDir);
  ok("SSoT template installed");
} else {
  log("  SSoT directory not empty — skipping (won't overwrite your docs)");
}

// 6. Workspace templates (AGENTS.md, SOUL.md, USER.md, MEMORY.md, TOOLS.md)
log("Setting up workspace templates...");
const workspaceTemplatesDir = path.join(INSTALL_DIR, "workspace-templates");
const memoryDir = path.join(OPENCLAW_WORKSPACE, "memory");
mkdirp(memoryDir);

const templates = ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md", "TOOLS.md", "IDENTITY.md", "HEARTBEAT.md"];
let templatesInstalled = 0;
for (const tpl of templates) {
  const dest = path.join(OPENCLAW_WORKSPACE, tpl);
  const src = path.join(workspaceTemplatesDir, tpl);
  if (!fs.existsSync(dest) && fs.existsSync(src)) {
    fs.copyFileSync(src, dest);
    templatesInstalled++;
  }
}
if (templatesInstalled > 0) {
  ok(templatesInstalled + " workspace templates installed (won't overwrite existing files)");
} else {
  log("  Workspace templates already exist — skipping");
}

// 7. R-Memory & R-Awareness configs
mkdirp(path.join(OPENCLAW_WORKSPACE, "r-memory"));
mkdirp(path.join(OPENCLAW_WORKSPACE, "r-awareness"));

writeJsonIfMissing(
  path.join(OPENCLAW_WORKSPACE, "r-awareness", "keywords.json"),
  {
    system: ["L1/SSOT-L1-IDENTITY-STUB.ai.md"],
    openclaw: ["L1/SSOT-L1-IDENTITY-STUB.ai.md"],
    philosophy: ["L0/PHILOSOPHY.md"],
    augmentatism: ["L0/PHILOSOPHY.md"],
    constitution: ["L0/CONSTITUTION.md"],
    architecture: ["L1/SYSTEM-ARCHITECTURE.md"],
    memory: ["L1/R-MEMORY.md"],
    awareness: ["L1/R-AWARENESS.md"],
  },
  "Default keywords"
);

writeJsonIfMissing(
  path.join(OPENCLAW_WORKSPACE, "r-awareness", "config.json"),
  {
    ssotRoot: "resonantos-alpha/ssot",
    coldStartOnly: true,
    coldStartDocs: ["L1/SSOT-L1-IDENTITY-STUB.ai.md"],
    tokenBudget: 15000,
    maxDocs: 10,
    ttlTurns: 15,
  },
  "R-Awareness config"
);

writeJsonIfMissing(
  path.join(OPENCLAW_WORKSPACE, "r-memory", "config.json"),
  {
    compressTrigger: 36000,
    evictTrigger: 50000,
    blockSize: 4000,
    minCompressChars: 200,
    compressionModel: "anthropic/claude-haiku-4-5",
    maxParallelCompressions: 4,
  },
  "R-Memory config"
);

// 8. Setup Agent (onboarding for new users)
log("Installing Setup Agent...");
const setupSrc = path.join(INSTALL_DIR, "agents", "setup");
const setupDest = path.join(HOME, ".openclaw", "agents", "setup", "agent");
if (fs.existsSync(setupSrc)) {
  mkdirp(setupDest);
  for (const f of fs.readdirSync(setupSrc)) {
    copyFile(path.join(setupSrc, f), path.join(setupDest, f));
  }
  ok("Setup Agent installed");
} else {
  log("  Setup Agent source not found — skipping");
}

// 9. Logician binary (Windows)
if (process.platform === "win32") {
  const logSrc = path.join(INSTALL_DIR, "bin", "mangle-server.exe");
  const logDest = path.join(HOME, ".openclaw", "bin", "mangle-server.exe");
  if (fs.existsSync(logSrc)) {
    mkdirp(path.dirname(logDest));
    copyFile(logSrc, logDest);
    ok("Logician binary installed");
  } else {
    log("  Logician binary not found — skipping");
  }
}

// 10. Skills
log("Installing skills...");
const skillsSrc = path.join(INSTALL_DIR, "skills");
const skillsDest = path.join(OPENCLAW_WORKSPACE, "skills");
if (fs.existsSync(skillsSrc)) {
  for (const entry of fs.readdirSync(skillsSrc, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      const src = path.join(skillsSrc, entry.name);
      const dest = path.join(skillsDest, entry.name);
      copyDirContents(src, dest);
    }
  }
  ok("Skills installed");
} else {
  log("  No skills directory found — skipping");
}

// Register setup agent in openclaw.json if not already present
const openclawCfgPath = path.join(HOME, ".openclaw", "openclaw.json");
if (fs.existsSync(openclawCfgPath)) {
  try {
    const cfg = JSON.parse(fs.readFileSync(openclawCfgPath, "utf-8"));
    const agentsList = cfg.agents && cfg.agents.list ? cfg.agents.list : [];
    const hasSetup = agentsList.some(a => a.id === "setup");
    if (!hasSetup) {
      // Use the user's primary model for setup agent (don't assume a specific provider)
      const primaryModel = (cfg.agents && cfg.agents.defaults && cfg.agents.defaults.model && cfg.agents.defaults.model.primary)
        || "anthropic/claude-haiku-4-5";
      agentsList.push({ id: "setup", model: primaryModel });
      if (!cfg.agents) cfg.agents = {};
      cfg.agents.list = agentsList;
      fs.writeFileSync(openclawCfgPath, JSON.stringify(cfg, null, 2) + "\n");
      ok("Setup Agent registered in openclaw.json");
    } else {
      log("  Setup Agent already registered in openclaw.json");
    }
  } catch (e) {
    log("  Warning: Could not update openclaw.json: " + e.message);
  }
}

// 10. Dashboard dependencies
log("Installing dashboard dependencies...");
const dashDir = path.join(INSTALL_DIR, "dashboard");
const dashDeps = "flask flask-cors psutil websocket-client solana solders";
try {
  // Try venv first (works on all platforms, avoids PEP 668 issues on Ubuntu 24.04+)
  const venvDir = path.join(dashDir, "venv");
  if (!fs.existsSync(venvDir)) {
    run(`${python} -m venv "${venvDir}"`, { cwd: dashDir });
  }
  const venvPip = isWin ? path.join(venvDir, "Scripts", "pip") : path.join(venvDir, "bin", "pip");
  run(`"${venvPip}" install -q ${dashDeps}`, { cwd: dashDir });
  ok("Dashboard ready (venv)");
} catch {
  // Fallback: try system pip with --break-system-packages (PEP 668 override)
  try {
    run(`${pip} install -q --break-system-packages ${dashDeps}`, { cwd: dashDir });
    ok("Dashboard ready (system packages)");
  } catch {
    // Last resort: plain pip install
    try {
      run(`${pip} install ${dashDeps}`, { cwd: dashDir });
      ok("Dashboard ready");
    } catch {
      log("  Warning: Could not install dashboard dependencies. Install manually:");
      log(`  ${pip} install ${dashDeps}`);
    }
  }
}

// 11. Config from example
const cfgPath = path.join(INSTALL_DIR, "dashboard", "config.json");
const cfgExample = path.join(INSTALL_DIR, "dashboard", "config.example.json");
if (!fs.existsSync(cfgPath) && fs.existsSync(cfgExample)) {
  fs.copyFileSync(cfgExample, cfgPath);
  ok("Dashboard config created from template (edit config.json with your addresses)");
}

log(`
=== Installation Complete ===

Next steps:
  1. Edit ~/resonantos-alpha/dashboard/config.json with your Solana addresses
  2. Start OpenClaw:  openclaw gateway start
  3. Start Dashboard: cd ~/resonantos-alpha/dashboard && ${python} server_v2.py
  4. Open http://localhost:19100

Docs: https://github.com/ResonantOS/resonantos-alpha
`);
