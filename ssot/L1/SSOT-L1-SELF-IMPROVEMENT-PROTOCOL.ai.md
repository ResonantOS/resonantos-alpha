[AI-OPTIMIZED] ~420 tokens | src: SSOT-L1-SELF-IMPROVEMENT-PROTOCOL.md

| Field | Value |
|-------|-------|
| ID | SSOT-L1-SELF-IMPROVEMENT-PROTOCOL-V1 | Level | L1 | Status | Active |
| Created | 2026-02-27 | Stale After | Review quarterly |
| Related | SSOT-L1-ALIGNMENT-PROTOCOL, SSOT-L1-SYSTEM-OVERVIEW |

## Problem
Lessons written to MEMORY.md = hope-based enforcement. 42% Wall: LLMs override documented lessons unless enforcement is rigid/procedural. Unprocessed lessons decay via compaction. Need: zero-friction capture → auto-classify → route to correct enforcement layer w/o human intervention.

**Design constraint (deterministic-first):** 8/14 pipeline steps fully deterministic (no hallucination, no tokens, 42%-Wall-proof). AI called only 3x per nightly run.

## Core Principles
1. **Repetition = signal.** First occurrence: track. Second: rule candidate. One-offs cost nothing.
2. **Minimize human involvement.** Technical/optimization → AI decides, silent. Behavioral → daily digest, silence=consent. Major shift → explicit approval.
3. **Daily cadence.** Nightly processing, 10-second morning digest.
4. **Audit existing rules.** Dead/high-FP rules removed weekly.

## Three Capture Sources
| Source | Method | Signal |
|--------|--------|--------|
| A: AI self-detection | Append 1 line to queue during work | Mistakes/insights noticed in real-time |
| B: Human feedback | Any correction/"you should have" → mandatory capture | AI doesn't decide if Manolo's feedback is worth logging — it always is |
| C: Archivist retroactive | Nightly diff: errors→silent retries, repeated attempts, topic revisits | Safety net; catches what A+B miss |

**Queue file:** `memory/lessons-queue.jsonl`
**Format:** `{ts, source, lesson, context, existingRule, severity, category, status}`
**Severity:** critical (data/repo/destructive → hard block immediately, skip repetition threshold) | standard (advisory-first) | low (advisory only)

## Repetition Detection
Semantic similarity (embedding cosine >0.8 = same lesson) + keyword overlap.
1st → `status: tracked` (no action) | 2nd → `status: pattern-detected` → classify | 3rd+ → escalate priority
**Exception:** critical severity → immediate classification on first occurrence.

## Classification (nightly, pattern-detected or critical only)
**Questions:** Existing rule should have caught this? → Enforcement Failure. Only this Augmentor? → Personal. Any agent? → Organizational. Entire ecosystem? → Ecosystem. Regex-detectable? → Enforceable | not → Document only.
**Output tags:** scope(personal/org/ecosystem), enforceable(T/F), layer, escalation(none/digest/human-approval), candidateRule
**Validation:** Dual-pass disagreement detection → consensus=auto-route, disagreement=human decides.

## Enforcement Failure Tracking
File: `memory/enforcement-failures.jsonl` — lesson, existingRule, ruleLayer, failureReason, fix, status
**Higher priority than new lessons** (known problem, broken fix).

## Rule Generation
**Shield Gate candidates:** `{layer, name, trigger, condition, action, mode="advisory", graduation}`
**Smart contract candidates:** `{layer, name, trigger, condition, action, mode="blocking from deploy"}`

## Graduation Path (severity-based)
| Severity | Start | Path |
|----------|-------|------|
| Critical | Hard block (immediate) | Already max |
| Standard | Advisory | Advisory(5 catches, 0FP) → Soft block(10 catches, 0FP) → Hard block(human approval) |
| Low | Advisory | May stay advisory permanently |

## Deterministic Map
Deterministic: repetition detection, occurrence counting, classification enforceability(partial), rule deployment, rule graduation, digest, audit, trend detection
AI-only: lesson extraction from transcripts, scope classification, rule candidate design

## Self-Improver Agent
**Model:** gpt-4o-mini | **Schedule:** Nightly 22:55, Weekly Sunday, Monthly 1st
**Daily digest format:** Captured N lessons (X AI/Y human/Z archivist) | New patterns N | Rules deployed N | Escalations N | Active rules N

## Scope Boundaries
Personal → Shield Gate/Logician (this machine only) | Organizational → Solana smart contracts | Ecosystem → Alignment Protocol (DAO governance)

## Implementation Phases
1. Bootstrap: queue/failure files, capture Sources A+B (DONE)
2. Retroactive mining: sub-agent reads all memory/*.md, seeds queue
3. Self-improver agent (week 2): Source C + repetition + classification + digest
4. Rule generation + graduation (week 2-3)
5. Audit + org queue (week 3-4)

## Anti-Patterns
Stop work to process lessons | Rule from first occurrence | Blocking rules w/o advisory period | Personal rules on-chain | Human approval for technical fixes | Weekly review sessions | Skip enforcement failure tracking | Keep rules w/o auditing | Classify everything "unenforceable" | Process in main session

## Changelog
V1: capture+classify+generate+graduate. V1.1: 3-source capture, dual-pass validation, trend detection, retroactive mining, severity graduation, archivist safety net. V1.2: repetition threshold, minimize human involvement, dedicated agent, rule audit. V1.3: deterministic-first — 8/14 steps deterministic.
