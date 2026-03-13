[AI-OPTIMIZED] ~280 tokens | src: SSOT-L1-SSOT-QUALITY-STANDARD.md

| Field | Value |
|-------|-------|
| ID | SSOT-L1-SSOT-QUALITY-STANDARD-V1 | Level | L1 | Status | Active |
| Created | 2026-02-27 | Stale After | Review quarterly |
| Related | SSOT-L1-SYSTEM-OVERVIEW, SSOT-L1-AUTONOMOUS-DEVELOPMENT-PROTOCOL |

## Problem
No spec for what a valid SSoT looks like → only orchestrator can write them → onboarding agents can't produce them → quality degrades. Need machine-readable validation.

## Universal Requirements (All Levels)
**1. Metadata header:**
```
| ID | SSOT-L{n}-{NAME}-V{version} |
| Level | L{0-4} ({level name} — {type}) |
| Created | YYYY-MM-DD |
| Status | Active/Draft/Deprecated |
| Stale After | {cadence} |
| Related | {doc IDs} |
```
ID regex: `SSOT-L[0-4]-[A-Z0-9-]+-V\d+`

**2. Problem Statement:** Section "The Problem"/"Problem"/"Why This Exists". ≥50 chars. Specific, not vague.
**3. Solution Section:** Section "The Solution"/"Architecture"/"Design". ≥100 chars. Concrete mechanisms.
**4. No Orphan References:** All docs in Related + inline refs must exist.

## Level-Specific Requirements

| Level | Extra Requirements |
|-------|-------------------|
| **L0** | Audience section; ≥3 principles with rationale; review ≥6mo; declarative tone |
| **L1** | Component table or architecture diagram; Integration section; Enforcement section (if behavioral); Change Log; Anti-patterns recommended |
| **L2** | Status enum (Design/Building/Production/Paused/Deprecated); Current state; What's Next (≥1 item); Metrics if production; Version history |
| **L3** | Metadata req'd (Status=Draft); Problem req'd; Solution can be partial/speculative (labeled); No enforcement/changelog req'd; **Promotion criteria** required |
| **L4** | Date in filename/header; ≥1 structural element; No metadata required |

## Compressed Variants (.ai.md)
For L0+L1: `.ai.md` SHOULD exist. Header: `[AI-OPTIMIZED] ~{tokens} tokens | src: {original}`. Preserve ALL technical details/numbers/parameters/decisions. Remove filler/redundancy. Target 50-80% smaller.

## 16 Validation Rules (All Deterministic)
| Rule | Level | Check |
|------|-------|-------|
| Metadata header | All | Regex (table pattern) |
| ID matches pattern | All | Regex |
| Status valid enum | All | String match |
| Problem ≥50 chars | All | Regex+length |
| Solution ≥100 chars | All | Regex+length |
| No broken Related refs | All | File existence |
| Audience section | L0 | Regex |
| ≥3 principles | L0 | Regex+count |
| Component table/diagram | L1 | Regex |
| Integration section | L1 | Regex |
| Change Log | L1 | Regex |
| Status field | L2 | Regex |
| Current state | L2 | Regex |
| What's Next | L2 | Regex |
| Promotion criteria | L3 | Regex |
| Date in filename/header | L4 | Regex |

## Implementation
Phase 1: `ssot-validator.js` — input: path → `{valid, errors, warnings, level, score}`. Fail-closed: unknown level → validate at L1.
Phase 2: Shield Gate extension (pre-commit) + onboarding agent + nightly cron audit.
Phase 3: Compressed variant check for L0/L1.

## Anti-Patterns
No metadata | "This document describes..." opener | Aspirational language | Missing Related | L3 content in L1 path | Monolith >5000 words | Tables with empty cells | "See above" references

## Changelog
2026-02-27 V1: Universal + level-specific requirements. 16 deterministic rules. Anti-patterns. Compressed variant spec.
