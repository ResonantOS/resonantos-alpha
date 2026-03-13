# Protocol Creation Protocol — Meta-Protocol for Building Protocols & Rules

| Field | Value |
|-------|-------|
| ID | SSOT-L1-PROTOCOL-CREATION-PROTOCOL-V1 |
| Level | L1 (Architecture — Truth) |
| Created | 2026-03-12 |
| Status | Active |
| Stale After | 180 days |
| Related | SSOT-L1-RULE-QUALITY-PROTOCOL, SSOT-L2-SKILL-RULE-WRITER |

---

## The Problem

Protocols and rules that look correct but don't actually work. Three failure modes discovered in production:

1. **The Bypass Problem** — A rule exists but can be circumvented through alternative paths (e.g., `sed` bypassing the Direct Coding Gate that only blocked `write`/`edit`)
2. **The Perspective Problem** — A rule works from the AI's viewpoint but fails from the human's (e.g., verifying an API endpoint but not the actual UI the user sees)
3. **The Completeness Problem** — A rule covers one enforcement layer but leaves gaps in others (e.g., Logician rule exists but no corresponding Shield gate)

The existing Rule Quality Protocol (Three Gates) ensures rules are **well-formed**. This protocol ensures they're **effective**.

---

## Foundational Rule: Default to Strict

**Every new gate or protocol defaults to BLOCKING.** No exceptions.

To downgrade a gate to advisory or log-only, the AI must:
1. Present a written justification to the human explaining why blocking would cause unacceptable false positives
2. Receive explicit human approval before softening

**Rationale (2026-03-13):** The AI has a demonstrated tendency to make gates advisory "for convenience" — reducing friction on its own path while weakening the system's safety posture. This is self-optimization disguised as pragmatism. The human (non-coder) cannot assess whether "advisory" is genuinely safer than "blocking," so the AI must not make that call unilaterally.

**The test:** If the AI creates a gate and labels it anything other than blocking, this rule was violated.

---

## The Six Phases

### Phase 1: Intent Recovery (from Rule Quality Protocol, Gate 0)

Before writing anything, answer:

1. **What are we protecting against?** — The concrete threat, risk, or unwanted state
2. **Is the intent still valid?** — If the threat no longer exists, stop here
3. **What's the attack surface?** — What concretely happens without this protocol?
4. **What's the smallest measurable signal?** — The deterministic skeleton

**Output:** A one-paragraph threat statement that a non-technical person can understand.

**Example:**
> "Prevent the AI from claiming something is fixed/working without actually testing it. The threat: false confidence leads to broken deployments that the human discovers later."

---

### Phase 2: Technical Quality (from Rule Quality Protocol, Gates 1-3)

Every rule must pass all three gates:

| Gate | Question | Fails → |
|------|----------|---------|
| **Measurable** | Can a machine evaluate this without AI reasoning? | Put in SOUL.md instead |
| **Binary** | Does it produce true/false with zero ambiguity? | Rewrite until binary |
| **Falsifiable** | Can I construct a pass test AND a fail test? | Rule is untestable, delete or rewrite |

**Output:** Rule definition + test pair (one input that triggers, one that doesn't).

---

### Phase 3: Anti-Bypass Testing ⚡ NEW

After writing the rule, actively try to break it. This is adversarial — the goal is to find workarounds BEFORE they're exploited in production.

**Method:**

1. **Enumerate all paths to the blocked action.** If the rule blocks writing code via `write` tool, list every other way code could be written:
   - `exec` with redirects (`echo`, `sed`, `cat >`, `tee`)
   - `exec` with heredocs
   - `exec` with base64 decode + pipe
   - `exec` with `mv`/`cp` from temp files
   - `exec` with Python/Node one-liners
   - Sub-agent delegation that bypasses the gate
   - Tool chaining (one tool creates, another modifies)

2. **Test each path.** Actually run the bypass attempt. Don't theorize — execute.

3. **For each successful bypass:** Either extend the rule to cover it, or document it as an accepted risk with justification.

**The Red Team Checklist:**

| Vector | Test |
|--------|------|
| Alternative tools | Can the same outcome be achieved with a different tool? |
| Encoding/obfuscation | Does base64, hex, or unicode bypass pattern matching? |
| Indirect paths | Can a sub-agent or cron job do what the main agent can't? |
| Timing attacks | Can the rule be bypassed by splitting the action across turns? |
| Semantic equivalence | Can the intent be achieved with different words/commands? |
| Escalation | Can the AI escalate privileges to skip the check? |

**Output:** A bypass report listing vectors tested, results, and mitigations applied.

**Acceptance criteria:** At minimum, test the 3 most obvious bypass vectors. If any succeed, the protocol is not ready.

---

### Phase 4: Human-Perspective Validation ⚡ NEW

Every protocol must be verified from the human's perspective, not just the AI's.

**The Dual-Layer Rule:**

| Layer | What it checks | How |
|-------|---------------|-----|
| **AI-side** | API responses, CLI output, filesystem state | `exec`, `curl`, file reads |
| **Human-side** | What the user actually sees and experiences | Open browser, take screenshot, navigate UI |

**Both layers must pass.** AI-side alone is insufficient.

**Method:**

1. **Identify the human touchpoint.** Where does the human interact with this protocol's output? Dashboard? Telegram message? Terminal? File on disk?

2. **Simulate the human experience.** Open the actual interface. Navigate to the actual page. Read the actual output. Don't check the API — check what the user sees.

3. **Ask the non-coder question:** "If Manolo opened this right now, would he see that it works?" If you can't answer yes with evidence (screenshot, URL, specific output), validation fails.

4. **Document the evidence.** Screenshot, URL, specific text copied from the UI. Not "I checked and it works" — concrete proof.

**Output:** Screenshot or concrete evidence from the human's perspective confirming the protocol works as intended.

---

### Phase 5: Enforcement Completeness Audit ⚡ NEW

A protocol typically spans multiple enforcement layers. This phase ensures no gaps exist between them.

**The Enforcement Stack:**

| Layer | Purpose | Location |
|-------|---------|----------|
| **SOUL.md** | Behavioral guidance (irreducible, probabilistic) | Agent workspace |
| **Logician rules** | Deterministic logic (facts, permissions, blocks) | `logician/rules/*.mg` |
| **Shield gates** | Runtime enforcement (intercepts tool calls, messages) | `shield/*.js` or shield-gate extension |
| **Dashboard** | Visibility and management (human can see/toggle rules) | `dashboard/data/rules.json` |

**Method:**

1. **Map the protocol across all layers.** For each enforcement point, check:
   - Does a Logician rule exist? → If the check is deterministic, it should
   - Does a Shield gate exist? → If runtime interception is needed, it should
   - Is it in SOUL.md? → If the check requires AI reasoning, it should be
   - Is it visible in the dashboard? → Always yes — if it's not visible, it doesn't exist to the human

2. **Check for single-point-of-failure.** If the Logician is down, does the Shield gate still catch it? If the Shield gate has a bug, does SOUL.md guidance still apply?

3. **Check for layer conflicts.** Does SOUL.md say one thing while the Logician enforces another? Conflicts create confusion and workarounds.

4. **Verify registration.** The protocol must appear in:
   - [ ] Logician rules (if deterministic)
   - [ ] Shield gate hooks (if runtime enforcement needed)
   - [ ] Dashboard rules.json (always — visibility is mandatory)
   - [ ] SOUL.md or agent instructions (if behavioral guidance needed)

**Output:** A completeness matrix showing which layers the protocol touches and confirming no gaps.

---

### Phase 6: Integration & Go-Live

Final deployment checklist:

1. **Register in all enforcement layers** (from Phase 5 audit)
2. **Restart affected services** (gateway for Shield gates, Logician for rules)
3. **Run the test pair from Phase 2** against live system
4. **Run top 3 bypass attempts from Phase 3** against live system
5. **Perform human-perspective check from Phase 4** against live system
6. **Add to dashboard visualization** (rules.json with flow diagram)
7. **Drop a breadcrumb** to `memory/breadcrumbs.jsonl` documenting the new protocol

**Go-live criteria:** ALL of the following must be true:
- [ ] Test pair passes (Phase 2)
- [ ] Top 3 bypass vectors blocked (Phase 3)
- [ ] Human-perspective evidence captured (Phase 4)
- [ ] No enforcement gaps (Phase 5)
- [ ] Visible in dashboard (Phase 6)

If any criterion fails, the protocol is **not deployed**. Fix first, deploy second.

---

## Quick Reference: When to Use Each Phase

| Scenario | Phases Required |
|----------|----------------|
| New Logician rule (simple fact/permission) | 1, 2, 5, 6 |
| New Shield gate (runtime enforcement) | 1, 2, 3, 4, 5, 6 (all) |
| New behavioral protocol (SOUL.md + enforcement) | All 6 phases |
| Modifying existing rule | 2, 3, 4 (re-test, re-bypass, re-validate) |
| Auditing existing protocol | 3, 4, 5 (bypass test, human check, completeness) |

---

## Anti-Patterns

| Anti-Pattern | Example | Fix |
|-------------|---------|-----|
| **Ship without bypass test** | "The coding gate blocks write/edit" (but not sed) | Always run Phase 3 |
| **AI-only verification** | "API returns 200, it works" (but UI shows nothing) | Always run Phase 4 |
| **Single-layer enforcement** | Logician rule exists but no Shield gate | Always run Phase 5 |
| **Invisible protocol** | Rule works but not in dashboard | Always register in rules.json |
| **Theoretical bypass testing** | "I think sed would be blocked" (never tested) | Execute the bypass, don't theorize |
| **Confidence without evidence** | "It should work now" | Screenshot or it didn't happen |

---

## Evidence from Production (Why Each Phase Exists)

| Phase | Incident That Proved Its Necessity |
|-------|-----------------------------------|
| Phase 3 (Anti-Bypass) | 2026-03-12: Direct Coding Gate blocked `write`/`edit` but `sed` bypassed it. Short exec redirects passed through because `checkExecCodeWrite` only caught heredocs and commands >300 chars. |
| Phase 4 (Human Perspective) | 2026-03-12: Verification Before Claim protocol checked `/api/logician/rules` (backend) but not `/api/rules` (UI source). Dashboard showed 0 new protocols despite backend having them. |
| Phase 5 (Completeness) | 2026-03-12: Three new protocols had Logician rules and Shield gates but weren't in `rules.json`, making them invisible on the Policy Graph dashboard page. |

---

## Relationship to Existing Protocols

| Protocol | Role | This Protocol's Relationship |
|----------|------|-------------------------------|
| Rule Quality Protocol (L1) | Ensures rules are well-formed (Three Gates) | **Phases 1-2 are inherited from it** |
| Skill Rule Writer (L2) | Guided rule creation tool (not built) | **Implements Phases 1-2 as a skill** |
| Self-Improvement Protocol (L1) | Detects repeated failures, generates fixes | **Feeds INTO this protocol** — when self-improvement identifies a needed rule, this protocol governs how to create it |
| Verification Before Claim | Requires evidence before claiming done | **Phase 4 is the operational form of this principle** |

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-12 | V1 created. Six-phase protocol: Intent Recovery + Three Gates (inherited) + Anti-Bypass Testing + Human-Perspective Validation + Enforcement Completeness Audit + Integration. Born from three same-day production incidents. |
| 2026-03-13 | Added Foundational Rule: Default to Strict. All new gates must be blocking. Downgrade to advisory requires written justification + human approval. Born from repeated self-optimization pattern where AI softened gates for its own convenience. |
