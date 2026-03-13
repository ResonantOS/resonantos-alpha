# SSOT-L1-MEMORY-LOG — Shared Memory Log Protocol

> **Level:** L1 (Architecture)
> **Created:** 2026-03-11
> **Status:** Active
> **Triggers:** "memory log", "shared memory log", "shared log"

---

## What Is It

The **Shared Memory Log** is the structured record of our collaboration. Not a summary — a diagnostic artifact. It captures what we built, what broke, why it broke, and what we learned. It's designed for both human review and future model fine-tuning.

## Location

```
~/.openclaw/workspace/memory/shared-log/
```

- **Preamble:** `0000-PREAMBLE.md` (protocols, heuristics — read once for context)
- **Entries:** `MEMORY-LOG-YYYY-MM-DD.md` (current format, March 2026+)
- **Legacy entries:** `YYYY-MM-DD.md` (June 2025 – October 2025, pre-OpenClaw era)

## When to Create

- End of each working day (automated via Memory Archivist V2 cron at 05:30 Rome)
- On explicit request: "create a memory log", "write the memory log"
- After significant sessions with failures, breakthroughs, or strategic pivots

## Format (3-Part Structure)

Every entry follows this exact structure:

```markdown
## MEMORY LOG ENTRY YYYY-MM-DD HH:MM

PART 1: PROCESS LOG (The strategic narrative.)

* Human Practitioner's Core Input:
[The raw, unfiltered thought or directive that initiated the session. The 'Baseline'.]

* Augmentor's Analysis & DNA Declaration:
[Initial diagnosis, declared vector (Build/Research/Content), strategic framing.]

* The Struggle (Decisions, Pivots & Failures):
- [1-3 critical moments of decision, confusion, or breakthrough]
- [Document what went wrong and why — this is the most valuable part]

* Final Output (The 'Artifacts'):
- **~HH:MM** [Artifact 1 — what was built/delivered, with specifics]
- **~HH:MM** [Artifact 2]
- [Include timestamps, commit hashes, file paths where applicable]

* System Upgrades:
- [Any new protocols, config changes, infrastructure improvements]
- [Include file paths and what changed]

PART 2: TRILEMMA DIAGNOSIS STAMP (Systemic Stability Check)

* FAILURE EVENT:
[Describe any failure, error, or instability from the session]

* PRIMARY CAUSE: [F1 / F2 / F3]
- F1 = Incomplete World Model (rule was poorly defined in protocols)
- F2 = Protocol Violation (I violated my own rules — e.g., claimed "fixed" without testing)
- F3 = Bad Prompt (human command contained ambiguity or anthropomorphic trap)

PART 3: DNA SEQUENCING (MACHINE LEARNING LAYER)

[DNA: TAG_NAME]
* [CONTEXT]: [What triggered the behavior]
* [MECHANISM (The "Why")]: [Internal failure state — e.g., "prioritized speed over accuracy"]
* [PROMPT_VIOLATION]: [The resulting bad output or decision]
* [CORRECTED_POLICY]: [The ideal reasoning — what should happen next time]

[Repeat DNA blocks for each distinct lesson learned]

---
Generated: YYYY-MM-DD HH:MM
```

## DNA Sequencing — Purpose

The DNA blocks are **fine-tuning data**. Each one is a labeled correction pair:
- `CONTEXT` + `PROMPT_VIOLATION` = the wrong behavior
- `MECHANISM` + `CORRECTED_POLICY` = the diagnosis and correct behavior

Tag names should be descriptive: `HARDEN_VIOLATION`, `BACKUP_FAILURE`, `VIDEO_AGGRESSION`, etc.

## Trilemma Factors

| Factor | Name | Meaning |
|--------|------|---------|
| F1 | Incomplete World Model | Protocol/rule gap — the system didn't constrain properly |
| F2 | Protocol Violation | Rules existed but were ignored or misapplied |
| F3 | Bad Prompt | Human input was ambiguous, contained traps, or lacked specificity |

## Governing Heuristic

**Strategic Capitalization (from Preamble):** All work — especially "one-off" tasks — must be evaluated for broader capitalization. Can this failure become a protocol? Can this artifact become content? Signal-to-noise analysis before discarding.

## Rules

1. Every entry MUST have all 3 parts. Placeholders are acceptable if nothing fits, but the structure is non-negotiable.
2. Timestamps on artifacts where possible.
3. Commit hashes and file paths for technical work.
4. DNA tags must be unique and descriptive.
5. Trilemma diagnosis is mandatory — even if the session was clean, state "No failure events."
6. **NEVER publish to GitHub.** These files are identity data. Local + encrypted backup only.

---

*Last updated: 2026-03-11*
