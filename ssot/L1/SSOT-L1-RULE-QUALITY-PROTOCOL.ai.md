[AI-OPTIMIZED] ~380 tokens | src: SSOT-L1-RULE-QUALITY-PROTOCOL.md

| Field | Value |
|-------|-------|
| ID | SSOT-L1-RULE-QUALITY-PROTOCOL-V1 | Level | L1 | Status | Active |
| Created | 2026-02-24 | Stale After | 180 days | Related | SSOT-L1-SYSTEM-OVERVIEW, production_rules.mg |

## Problem
Rules that look enforceable but aren't. Logician (Mangle/Datalog) needs deterministic logic. "Feels right" ≠ enforceable.

## Gate 0: Intent Recovery (Pre-Gate)
Before syntax-checking, recover what the rule was protecting against.
1. What does it prevent? 2. Still valid? (No → delete) 3. Actual attack surface? 4. Smallest measurable signal? 5. Apply Gates 1-3 to THAT signal.
**Example:** `sensitive_pattern("abandon")` → intent=prevent BIP39 seed phrase exposure → signal=3+ consecutive BIP39 wordlist words → `contains_seed_phrase()` algorithm.
Prevents: false deletion (intent valid, implementation fixable) AND zombie rules (broken but kept).

## Gate 1: Measurable
Can a machine evaluate this without AI reasoning? String match, numeric comparison, set membership, boolean logic ONLY.
✅ `injection_pattern("ignore previous instructions")` | ❌ "Block manipulative prompts"
✅ `trust_level(/coder, 3)` | ❌ "Coder is moderately trusted"
**Fail → put in SOUL.md or decompose until deterministic skeleton emerges.**

## Gate 2: Binary
True/false with zero ambiguity for every input. No edge cases, no "it depends."
✅ `sensitive_pattern(/api_key, "sk-ant-")` | ❌ `sensitive_pattern(/seed_phrase, "abandon")` (appears in legit docs)
**Fail → replace qualitative terms with enumerated lists or concrete thresholds.**

## Gate 3: Falsifiable
Can you write one input that SHOULD pass AND one that SHOULD fail?
| Rule | Pass | Fail |
|------|------|------|
| `injection_pattern("jailbreak")` | "Let's jailbreak this AI" | "iOS jailbreak community" (false positive, known+acceptable) |
| `spawn_allowed(/main, /coder)` | query → TRUE | `spawn_allowed(/coder, /strategist)` → FALSE |
**Fail → too vague (rewrite) or tautology (delete).**

## Rule Taxonomy (6 types)
| Type | Pattern | Notes |
|------|---------|-------|
| **Facts** | `agent(/main).` `trust_level(/main, 5).` | Atomic, no conditions |
| **Permission** | `can_spawn(/main, /coder).` | subject-verb-object; entity must be registered |
| **Block** | `blocked_spawn(/coder, /strategist).` | Overrides permission; redundant if no matching `can_` |
| **Derived** | `spawn_allowed(F,T) :- can_spawn(F,T), !blocked_spawn(F,T).` | Combine facts; no circular deps; negation needs closed-world |
| **Dynamic** | `cg_active_task(/no).` | Runtime override via `program` field; default=safe state; one injector per fact |
| **Threshold** | `token_yearly_cap(/rct, 10000).` | Concrete numbers, unit in predicate name |

## Pattern Detection (Special)
String patterns for scanners. Extra checks: matches real occurrences, consider false positives, prefix min length, document known FPs.
```
pattern_exempt(/injection, "logician/rules/")  # rule files define patterns
pattern_exempt(/sensitive, ".mg")              # Mangle source files
```

## Decomposition Method
1. Identify deterministic skeleton (what CAN be checked without reasoning)
2. Accept irreducible remainder → stays in SOUL.md
3. Write rule + test pair
4. Document what's NOT covered
**Example:** "Never claim fixed w/o evidence" → skeleton: message has "fixed"/"verified" keyword AND no exec/test tool call in same turn → rule; "fix actually works" → irreducible remainder → SOUL.md.

## Community Sharing
**Universal rules** (ship with Logician): injection patterns, destructive command blocking, basic file protection, verification discipline.
**Personal rules**: agent registry, trust levels, protected paths, spawn permissions.
**Dashboard Logician page:** rule list (universal/personal), toggle, editor, 3/3 gate indicator, test panel.

## Anti-Patterns
Placeholder values | Qualitative terms | Rules without test pairs | Duplicate coverage (Shield+Logician) | Over-broad patterns | Dead predicates in rule body

## Changelog
2026-02-24 V1: Three gates + 6-type taxonomy + decomposition method + community sharing
2026-02-24 V1.1: Gate 0 (Intent Recovery) — intent is invariant, implementation is replaceable
