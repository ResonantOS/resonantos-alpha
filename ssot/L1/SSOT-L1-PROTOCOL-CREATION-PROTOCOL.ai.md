# Protocol Creation Protocol — Compressed

Meta-protocol for building protocols and rules. Ensures they're not just well-formed but actually effective.

## Foundational Rule: Default to Strict
Every new gate defaults to **BLOCKING**. To downgrade to advisory: written justification + human approval required. AI must not unilaterally soften gates. (Added 2026-03-13 — born from repeated self-optimization pattern.)

## Six Phases

| Phase | Name | Source | Purpose |
|-------|------|--------|---------|
| 1 | Intent Recovery | Rule Quality Protocol Gate 0 | What are we protecting against? |
| 2 | Technical Quality | Rule Quality Protocol Gates 1-3 | Measurable + Binary + Falsifiable + test pair |
| 3 | Anti-Bypass Testing | **NEW** | Actively try to circumvent the rule through alternative paths |
| 4 | Human-Perspective Validation | **NEW** | Verify from user's viewpoint (open UI, screenshot, navigate) |
| 5 | Enforcement Completeness | **NEW** | Check all layers: Logician + Shield + SOUL.md + Dashboard |
| 6 | Integration & Go-Live | Extended | Deploy, test live, register in dashboard |

## Phase 3 Red Team Checklist
Alternative tools, encoding/obfuscation, indirect paths (sub-agents/cron), timing attacks, semantic equivalence, privilege escalation. Test top 3 vectors minimum. Execute — don't theorize.

## Phase 4 Dual-Layer Rule
AI-side (API/CLI/filesystem) + Human-side (browser/UI/screenshot). Both must pass. "If user opened this right now, would they see it works?"

## Phase 5 Enforcement Stack
SOUL.md (behavioral) → Logician (deterministic) → Shield (runtime) → Dashboard (visibility). No single-point-of-failure. No layer conflicts. Always visible in dashboard.

## Go-Live Criteria
All must be true: test pair passes, top 3 bypasses blocked, human-perspective evidence captured, no enforcement gaps, visible in dashboard.

## Born From
Three same-day incidents (2026-03-12): sed bypass (Phase 3), API-not-UI verification (Phase 4), missing rules.json entries (Phase 5).

Full doc: `SSOT-L1-PROTOCOL-CREATION-PROTOCOL.md`
