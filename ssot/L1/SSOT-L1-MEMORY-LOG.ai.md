# Shared Memory Log — Protocol

Location: `~/.openclaw/workspace/memory/shared-log/`
Files: `MEMORY-LOG-YYYY-MM-DD.md` (current), `YYYY-MM-DD.md` (legacy pre-2026)
Preamble: `0000-PREAMBLE.md`

## 3-Part Format (ALL mandatory)

**PART 1: PROCESS LOG** — Human's core input, Augmentor's analysis/vector, The Struggle (decisions/pivots/failures), Final Artifacts (timestamped, with paths/hashes), System Upgrades.

**PART 2: TRILEMMA DIAGNOSIS** — Failure event description + primary cause: F1 (rule gap), F2 (protocol violation), F3 (bad prompt). If clean session: "No failure events."

**PART 3: DNA SEQUENCING** — Fine-tuning correction pairs. Per lesson: `[DNA: TAG]` with CONTEXT, MECHANISM (the "why"), PROMPT_VIOLATION (bad output), CORRECTED_POLICY (correct behavior). Tags: descriptive (e.g., HARDEN_VIOLATION, BACKUP_FAILURE).

## Rules
- All 3 parts required, every entry
- Timestamps + commit hashes + file paths on artifacts
- NEVER publish to GitHub (identity data, local/encrypted only)
- Created: end of day (cron 05:30 Rome) or on explicit request
