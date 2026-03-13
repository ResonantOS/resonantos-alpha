const fs = require("fs");
const path = require("path");

const USAGE_DIR = path.join(
  process.env.HOME || process.env.USERPROFILE || "/tmp",
  ".openclaw",
  "workspace",
  "usage-tracker"
);
const USAGE_FILE = path.join(USAGE_DIR, "usage.jsonl");

module.exports = function (api) {
  // Ensure directory exists on load
  try {
    fs.mkdirSync(USAGE_DIR, { recursive: true });
  } catch (_) {}

  api.on("llm_output", (event, ctx) => {
    const usage = event.usage;
    if (!usage) return;

    const input = parseInt(usage.input, 10) || 0;
    const output = parseInt(usage.output, 10) || 0;
    const cacheRead = parseInt(usage.cacheRead, 10) || 0;
    const cacheWrite = parseInt(usage.cacheWrite, 10) || 0;

    if (input + output + cacheRead + cacheWrite <= 0) return;

    const entry = {
      ts: new Date().toISOString(),
      agent: (ctx && ctx.agentId) || "unknown",
      model: event.model || "",
      provider: event.provider || "",
      input,
      output,
      cacheRead,
      cacheWrite,
    };

    try {
      fs.appendFileSync(USAGE_FILE, JSON.stringify(entry) + "\n");
    } catch (err) {
      // Silent fail — don't break the agent loop
    }
  });
};
