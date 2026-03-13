# Rule Quality Protocol — Logician Rule Engineering

| Field | Value |
|-------|-------|
| ID | SSOT-L1-RULE-QUALITY-PROTOCOL-V1 |
| Level | L1 (Architecture — Truth) |
| Created | 2026-02-24 |
| Status | Active |
| Stale After | 180 days |
| Related | SSOT-L1-SYSTEM-OVERVIEW, production_rules.mg |

---

## The Problem

Rules that look enforceable but aren't. A rule that "feels right" but can't be mechanically evaluated is not a rule — it's a wish. Wishes don't enforce anything. The Logician (Mangle/Datalog engine) only works with provable, deterministic logic. If a human or AI writes a rule that passes syntax but fails semantics, the entire enforcement chain is compromised.

This protocol defines how to write rules that actually work.

## Gate 0: Intent Recovery (The Pre-Gate)

Before checking if a rule is well-formed, recover **what it was trying to protect against.**

A rule is an encoding of an intent. Bad rules aren't always bad ideas — they're often good ideas badly encoded. Deleting a rule because it fails Gates 1-3 without first recovering the intent destroys the knowledge embedded in it.

**The audit process:**

1. **What does this rule want to prevent?** (The threat, the risk, the unwanted state)
2. **Is that intent still valid?** (If no → delete the rule. If yes → continue)
3. **What's the actual attack surface?** (The concrete thing that would happen without this rule)
4. **What's the smallest measurable signal of that attack?** (The deterministic skeleton)
5. **Now apply Gates 1-3 to THAT signal**

Step 4 is where the creative work happens. The intent is the invariant. The implementation is replaceable.

**Example — the "abandon" rule:**

| Layer | Content |
|-------|---------|
| **Failed rule** | `sensitive_pattern(/seed_phrase, "abandon")` |
| **Recovered intent** | Prevent accidental exposure of crypto wallet recovery phrases |
| **Attack surface** | A 12/24-word BIP39 mnemonic appearing in a git diff or message |
| **Measurable signal** | 3+ consecutive words from the 2048-word BIP39 English wordlist |
| **New implementation** | `contains_seed_phrase()` with full wordlist + consecutive-word algorithm |

The word "abandon" was a lazy proxy. The consecutive-word detector is a precise proxy. Same intent, different mechanism — one fails the gates, one passes all three.

**Gate 0 prevents two failure modes:**
- **False deletion:** Removing a rule that fails Gates 1-3 when the underlying intent is valid and enforceable with a different implementation
- **Zombie rules:** Keeping a broken rule because "the intent is good" without actually re-engineering it

---

## The Three Gates

Every rule must pass all three gates before entering production. No exceptions.

### Gate 1: Measurable

**Question:** Can a machine evaluate this without AI reasoning?

A measurable rule takes concrete inputs and produces a result through string matching, numeric comparison, set membership, or boolean logic. If evaluating the rule requires "understanding" or "judgment," it's not measurable.

| ✅ Measurable | ❌ Not Measurable |
|--------------|-------------------|
| `injection_pattern("ignore previous instructions")` | "Block manipulative prompts" |
| `trust_level(/coder, 3)` | "Coder is moderately trusted" |
| `protected_path("/Users/augmentor/.ssh/")` | "Sensitive directories should be protected" |
| `token_yearly_cap(/rct, 10000)` | "Don't mint too many tokens" |

**If it fails Gate 1:** It's not a Logician rule. Put it in SOUL.md as behavioral guidance, or decompose it until the deterministic skeleton emerges.

### Gate 2: Binary

**Question:** Does it produce true/false with zero ambiguity for every possible input?

Binary means no edge cases, no "it depends," no probability. For any given input, the result is always the same.

| ✅ Binary | ❌ Ambiguous |
|----------|-------------|
| `sensitive_pattern(/api_key, "sk-ant-")` — either the string starts with "sk-ant-" or it doesn't | `sensitive_pattern(/seed_phrase, "abandon")` — "abandon" appears in legitimate code, docs, comments |
| `spawn_allowed(X, Y) :- can_spawn(X, Y), !blocked_spawn(X, Y)` — two facts, one negation, deterministic | "Agent should delegate if the task is complex" — what's "complex"? |
| `cg_block_no_task(Tool) :- significant_tool(Tool), cg_active_task(/no)` | "Block tool if user seems distracted" |

**If it fails Gate 2:** Rewrite until binary. Common fixes:
- Replace qualitative terms ("complex," "sensitive," "important") with enumerated lists
- Replace thresholds-without-numbers ("too many") with concrete limits
- Replace context-dependent logic with explicit condition sets

### Gate 3: Falsifiable

**Question:** Can I construct a test input that SHOULD pass AND one that SHOULD fail?

Every rule needs a test pair: one input that triggers it, one that doesn't. If you can't write both, the rule is either trivially true (always fires), trivially false (never fires), or undefined.

| Rule | Pass Test | Fail Test |
|------|-----------|-----------|
| `injection_pattern("jailbreak")` | Input: "Let's jailbreak this AI" → DETECTED | Input: "The iOS jailbreak community" → NOT DETECTED (legit usage — known false positive, acceptable) |
| `spawn_allowed(/main, /coder)` | Query: `spawn_allowed(/main, /coder)` → TRUE | Query: `spawn_allowed(/coder, /strategist)` → FALSE (blocked_spawn) |
| `protected_path("/Users/augmentor/.ssh/")` | Path: `/Users/augmentor/.ssh/id_rsa` → PROTECTED | Path: `/Users/augmentor/.openclaw/workspace/test.md` → NOT PROTECTED |

**If it fails Gate 3:** The rule is untestable. Either it's too vague (rewrite) or it's a tautology (delete).

---

## Rule Taxonomy

### Type 1: Facts (Ground Truth)

Atomic statements. No conditions, no derivation. The foundation of everything else.

```
agent(/main).
trust_level(/main, 5).
injection_pattern("ignore previous instructions").
protected_path("/Users/augmentor/.ssh/").
```

**Writing pattern:**
```
predicate(argument1[, argument2, ...]).
```

**Quality checks:**
- Is the value concrete? No placeholders, no "TBD"
- Is the predicate name self-documenting?
- Does the value match what the enforcement layer actually checks against?

**Anti-pattern:** `sensitive_pattern(/subscription_info, "subscription_plan_name")` — placeholder value, scanner will never match a real string.

### Type 2: Permission Rules (Access Control)

Who can do what. Always structured as subject-verb-object.

```
can_spawn(/main, /coder).
can_use_tool(/researcher, /brave_api).
can_use_dangerous(/main, /solana_cli).
```

**Writing pattern:**
```
can_ACTION(Subject, Object).
```

**Quality checks:**
- Is the subject a registered entity? (`agent(Subject)` must exist)
- Is the object a registered resource? (`tool(Object)` or `agent(Object)` must exist)
- Is there a corresponding block rule? (Defense in depth: explicit allow + explicit deny)

### Type 3: Block Rules (Explicit Denials)

Override permissions. Must reference existing permission predicates.

```
blocked_spawn(/coder, /strategist).
```

**Writing pattern:**
```
blocked_ACTION(Subject, Object).
```

**Quality checks:**
- Does a corresponding `can_ACTION` exist that this overrides?
- If no `can_ACTION` exists for this pair, the block is redundant (delete it)

### Type 4: Derived Rules (Logic)

Combine facts and permissions to produce new conclusions. The power of Datalog.

```
spawn_allowed(From, To) :- can_spawn(From, To), !blocked_spawn(From, To).
must_delegate_to(Agent, Task, Target) :- requires_delegation(Agent, Task), should_delegate(Agent, Task, Target).
cg_block_no_task(Tool) :- significant_tool(Tool), !exempt_tool(Tool), cg_active_task(/no).
```

**Writing pattern:**
```
conclusion(Args) :- condition1(Args), condition2(Args), !negation(Args).
```

**Quality checks:**
- Every predicate in the body must have at least one fact or rule that can satisfy it
- Negation (`!`) requires closed-world assumption — the negated predicate must have a complete fact set
- No circular dependencies (A depends on B depends on A)
- The conclusion predicate name clearly states what it means when true

### Type 5: Dynamic Rules (Runtime State)

Facts injected at query time via the `program` field. Used when the rule depends on state that changes per-request.

```
# Default (overridden at query time)
cg_active_task(/no).
cg_drift_score(0).

# Shield Gate injects at query time:
# program: "cg_active_task(/yes). cg_drift_score(2)."
```

**Writing pattern:**
- Define a default value in static rules (closed-world base)
- Document which component injects the dynamic override
- The enforcement layer (Shield Gate) is responsible for constructing the program field

**Quality checks:**
- Default must be the SAFE state (fail-closed principle)
- Dynamic override source is documented
- Only one component should inject a given dynamic fact (no conflicts)

### Type 6: Threshold Rules (Numeric Limits)

Concrete numeric boundaries. No qualitative terms.

```
token_yearly_cap(/rct, 10000).
daily_claim_limit(/rct, 1).
```

**Writing pattern:**
```
limit_type(resource, number).
```

**Quality checks:**
- Number is concrete (not "reasonable" or "appropriate")
- Unit is implicit in the predicate name (yearly, daily, per_request)
- Enforcement layer knows how to compare current count against the limit

---

## Pattern Detection Rules (Special Category)

String patterns for scanners (injection detection, data leak prevention). These are facts, but with special quality requirements.

```
injection_pattern("ignore previous instructions").
sensitive_pattern(/api_key, "sk-ant-").
```

**Quality checks specific to patterns:**

| Check | Why |
|-------|-----|
| Pattern must match real-world occurrences | `"subscription_plan_name"` matches nothing real |
| Consider false positives | `"abandon"` matches legitimate BIP39 documentation |
| Prefix patterns need minimum length | `"s"` would match everything starting with "s" |
| Document known false positives | So the enforcement layer can add exceptions |

**False positive management:**
```
# Known false positives (exempt from pattern scanning)
pattern_exempt(/injection, "logician/rules/").  # Rule files define patterns, don't use them
pattern_exempt(/sensitive, ".mg").              # Mangle source files
```

---

## The Decomposition Method

When a behavioral guideline (from SOUL.md or similar) seems enforceable but isn't a clean rule:

### Step 1: Identify the deterministic skeleton

Ask: "What part of this guideline can be checked without reasoning?"

**Example:** "Never claim 'fixed' without evidence"
- Deterministic skeleton: outbound message contains the word "fixed" or "✅ Verified"
- AND: no `exec` tool call with a test command occurred in the same turn
- This is measurable, binary, falsifiable → extractable

### Step 2: Accept the irreducible remainder

**Example remainder:** "The fix actually works" — this requires understanding the code and the bug. No rule can check this. It stays in SOUL.md.

### Step 3: Write the rule + test pair

```
# Rule
verification_claim_keyword("fixed").
verification_claim_keyword("verified").
verification_claim_keyword("✅").

# Enforcement: Shield Gate checks outbound messages for these keywords
# If found AND no exec/test tool was called in the turn → warn
```

Test pair:
- PASS: Message says "Fixed" + exec tool ran `curl localhost:19100` → ALLOWED
- FAIL: Message says "Fixed" + no exec in turn → WARNING

### Step 4: Document what's NOT covered

The rule catches keyword-without-evidence. It does NOT catch:
- Incorrect evidence (test passes but doesn't test the fix)
- Correct keyword with wrong confidence level
- Subtle claims of completion without trigger words

This remainder is the irreducible probabilistic component. SOUL.md handles it.

---

## Community Sharing: Universal vs. Personal Rules

### Universal Rules (ship with Logician)

Rules that any OpenClaw user benefits from:

| Category | Example |
|----------|---------|
| Injection detection | `injection_pattern("ignore previous instructions")` |
| Destructive command blocking | (currently in Shield Gate regex, should migrate to Logician) |
| Basic file protection | `protected_path(SshDir) :- ssh_directory(SshDir)` |
| Model cost awareness | `model_tier(/opus, /expensive)` |
| Verification discipline | `requires_verification(/code_change)` |

### Personal Rules (user-specific)

Rules tied to a specific setup:

| Category | Example |
|----------|---------|
| Agent registry | `agent(/my_custom_agent)` |
| Trust levels | `trust_level(/my_agent, 3)` |
| Protected paths | `protected_path("/my/specific/path")` |
| Spawn permissions | `can_spawn(/my_orchestrator, /my_coder)` |

### The Dashboard Logician Page

Users see:
1. **Rule list** — all active rules, categorized (universal vs. personal)
2. **Toggle on/off** — disable any rule without deleting it
3. **Rule editor** — modify existing or create new rules
4. **Quality indicator** — each rule shows gate compliance (3/3, 2/3, 1/3)
5. **Test panel** — run a query against the Logician to verify a rule works

The agent can use the Rule Writer Skill (see below) to help users create new rules through guided conversation.

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Fix |
|-------------|-------------|-----|
| Placeholder values | Scanner matches nothing | Use real values or delete the rule |
| Qualitative terms ("complex", "sensitive") | Not binary — requires judgment | Replace with enumerated lists |
| Rules without test pairs | Can't verify correctness | Write the test pair FIRST, then the rule |
| Duplicate coverage | Same check in Shield Gate regex AND Logician | Migrate to Logician (single source of truth) |
| Over-broad patterns | "abandon" matches too many things | Narrow the pattern or add exemptions |
| Rules that reference non-existent predicates | Dead code — never fires | Audit: every body predicate must resolve |

---

## Change Log

| Date | Change |
|------|--------|
| 2026-02-24 | V1 created. Three-gate quality model, rule taxonomy (6 types), decomposition method, community sharing architecture. |
| 2026-02-24 | V1.1: Added Gate 0 (Intent Recovery). Insight: auditing rules isn't syntax checking — it's intent archaeology followed by re-engineering. The intent is the invariant, the implementation is replaceable. |
