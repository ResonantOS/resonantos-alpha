<p align="center">
  <img src="assets/banner.png" alt="ResonantOS Banner" width="100%">
</p>

<p align="center">
  <strong>The Experience Layer for AI Sovereignty</strong><br>
  <em>Built on <a href="https://github.com/openclaw/openclaw">OpenClaw</a> — Powered by Augmentatism</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.5.0-7c3aed?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/platform-macOS_%7C_Linux_%7C_Windows-333?style=for-the-badge" alt="Platform">
  <img src="https://img.shields.io/badge/license-RC--SL_v1.0-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/OpenClaw-compatible-blue?style=for-the-badge" alt="OpenClaw">
</p>

---

## 🚀 Install

**Prerequisites:** Node.js 18+ · Python 3 · Git

```bash
git clone https://github.com/ResonantOS/resonantos-alpha.git ~/resonantos-alpha
node ~/resonantos-alpha/install.js
```

---

## What is ResonantOS?

ResonantOS is an **experience layer** that runs on top of [OpenClaw](https://github.com/openclaw/openclaw). Think of it like macOS to Unix — OpenClaw is the kernel, ResonantOS adds the intelligence.

It gives your AI collaborator:

| Component | What It Does |
|-----------|-------------|
| 📚 **Knowledge Base** | Per-agent RAG — vector search with SQLite + Ollama embeddings |
| 🎯 **R-Awareness** | Contextual knowledge injection — the right docs at the right time |
| 📊 **Dashboard** | Mission Control at `localhost:19100` |
| 💰 **Symbiotic Wallet** | Three-wallet Solana architecture (Human + AI + Symbiotic PDA) |
| 🏛️ **DAO** | Resonant Chamber — on-chain governance and community treasury |
| 🪙 **Token Economy** | $RCT (soulbound governance) + $RES (transferable currency) + REX sub-tokens |
| 🛒 **Protocol Store** | Buy, sell, and trade AI protocol NFTs on-chain |
| 🛡️ **Shield** | 12 blocking enforcement layers · file protection (2000+ files) · injection detection |
| ⚖️ **Logician** | Policy engine · 250 facts · 16 rule files · Mangle/Datalog runtime |
| 📋 **Policy System** | 18 policy rules + 6 protocol flows · enforcement badges · dashboard visualization |
| 🔄 **Guardian** | Self-healing & incident recovery *(in development)* |

---

## 📝 Memory System

**Knowledge Base (RAG)** is the primary memory layer:
- Per-agent SQLite databases with vector embeddings
- Local Ollama embedding model (nomic-embed-text)
- Configurable SSoT access per agent (L0/L1/L2)
- Common KB for shared knowledge across agents

*R-Memory (compression pipeline) is temporarily disabled while being redesigned for compatibility with OpenClaw's native LCM compaction system.*

---

## ✨ Philosophy

### Augmentatism
> *"As artificial intelligence generates infinite content, the most human thing we can do is make meaning together."*

A social contract between human and AI. The human is sovereign — the AI amplifies, never replaces. We build **with** AI, not **under** it. [Read more →](https://augmentatism.com)

---

<details>
<summary><strong>What the installer does</strong></summary>

1. Checks dependencies (Node 18+, Python 3, Git, OpenClaw)
2. Installs extensions into OpenClaw (R-Awareness, Gateway Lifecycle, Shield Gate, Coherence Gate, Usage Tracker)
3. Creates workspace templates (AGENTS.md, SOUL.md, USER.md, MEMORY.md, etc.)
4. Sets up the SSoT document structure (L0–L4)
5. Configures keyword triggers for contextual injection
6. Installs the Setup Agent for guided onboarding
7. Installs Shield daemon and Logician rule engine
8. Installs Dashboard dependencies

</details>

**After install:**

```bash
openclaw gateway start                                    # 1. Start OpenClaw
cd ~/resonantos-alpha/dashboard && python3 server_v2.py   # 2. Launch Dashboard
open http://localhost:19100                                # 3. Open Mission Control
```

---

## 🚀 Getting Started

### Fresh Installation

The installer creates workspace templates (`AGENTS.md`, `SOUL.md`, `USER.md`, `MEMORY.md`, `TOOLS.md`) that teach your AI how to operate. To get the most out of the system:

1. **Gather your documents** — business plan, project briefs, values statement, anything that defines your work. Put them in a single folder (e.g., `~/Desktop/my-docs/`).
2. **Tell your AI:** *"Read everything in ~/Desktop/my-docs/ and use it to fill in my SOUL.md, USER.md, and MEMORY.md."*
3. Your AI will extract your values, communication style, project context, and preferences into the right files.

### Existing Installation

If you already have OpenClaw running with your own workspace files:

1. Tell your AI where your existing documents live.
2. Ask it to review them and populate the ResonantOS workspace templates with relevant context.
3. Your existing files won't be overwritten — the installer only creates templates for files that don't exist yet.

### The Memory System

Your AI maintains two layers of memory:

| Layer | File | Purpose |
|-------|------|---------|
| **Daily logs** | `memory/YYYY-MM-DD.md` | Raw session notes: decisions, lessons, mistakes, open items |
| **Long-term** | `MEMORY.md` | Curated insights distilled from daily logs |

Daily logs follow a structured format that captures not just *what* happened, but *what was learned* — including mistakes and whether they can be prevented by rules. OpenClaw's built-in `memory_search` automatically indexes all memory files, making them searchable via RAG across sessions.

### Self-Improvement Loop

ResonantOS includes a self-improvement protocol where your AI learns from its own mistakes:

1. **First occurrence** of a mistake is tracked in the daily log
2. **Second occurrence** (pattern detected) triggers evaluation: can this be prevented mechanically?
3. **If enforceable**, a Logician rule is created — starting in advisory mode, then graduating to enforcement
4. **If not enforceable**, it becomes a permanent lesson in `MEMORY.md`

This means your AI gets better over time without you having to micromanage it. Mistakes become rules. Rules become guarantees.

---

## 💬 Join the Community

Building a second brain is better together. Join us on Discord — share your setup, get help, and help shape what ResonantOS becomes:

**[→ Join the Discord](https://discord.gg/MRESQnf4R4)**

---

## 🔄 Updating

Already installed? Get the latest:

```bash
cd ~/resonantos-alpha
git pull origin main
```

If the dashboard is running, restart it after pulling to pick up changes.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│              ResonantOS Layer                │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │ R-Memory │ │R-Awareness│ │  Dashboard  │  │
│  │ compress │ │ SSoT inject│ │ Mission Ctrl│  │
│  └──────────┘ └───────────┘ └────────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │  Shield  │ │ Logician  │ │  Guardian   │  │
│  │ security │ │governance │ │self-healing │  │
│  └──────────┘ └───────────┘ └────────────┘  │
├─────────────────────────────────────────────┤
│           OpenClaw Kernel                    │
│  Gateway · Sessions · Tools · Memory · Cron  │
├─────────────────────────────────────────────┤
│           Infrastructure                     │
│  macOS/Linux · Telegram/Discord · Anthropic  │
└─────────────────────────────────────────────┘
```

---

## 🧠 Memory Architecture

Your AI maintains persistent memory across sessions through multiple layers:

| Layer | Purpose |
|-------|---------|
| **Knowledge Base (RAG)** | Per-agent SQLite + vector embeddings for semantic search across all documents |
| **Daily Logs** | `memory/YYYY-MM-DD.md` — raw session notes, decisions, lessons, mistakes |
| **Long-term Memory** | `MEMORY.md` — curated insights distilled from daily logs |
| **Shared Memory Logs** | `memory/shared-log/` — structured collaboration logs with DNA sequencing for fine-tuning |
| **OpenClaw LCM** | Native Lossless Context Management handles conversation compaction |

*R-Memory (custom compression pipeline) is temporarily disabled while being redesigned to integrate with OpenClaw's native LCM system.*

---

## 🎯 R-Awareness — Contextual Intelligence

Your AI loads the right knowledge at the right time, based on what you're talking about.

| Feature | Detail |
|---------|--------|
| **Cold Start** | ~120 tokens (identity only) — not 1600+ |
| **Keyword Triggers** | Mention "philosophy" → loads philosophy docs automatically |
| **TTL Management** | Docs stay for 15 turns, then unload |
| **Manual Control** | `/R load`, `/R remove`, `/R list`, `/R pause` |
| **Token Budget** | Max 15K tokens, 10 docs per turn |

---

## 📚 SSoT — Single Source of Truth

Knowledge is organized in layers, from permanent truths to working notes:

| Layer | Purpose | Examples |
|-------|---------|---------|
| **L0** | Foundation | Philosophy, manifesto, constitution |
| **L1** | Architecture | System specs, component design |
| **L2** | Active Projects | Current work, milestones |
| **L3** | Drafts | Ideas, proposals in progress |
| **L4** | Notes | Session logs, raw captures |

Higher layers are stable; lower layers change frequently. Your AI knows the difference.

---

## 📊 Dashboard

The Dashboard runs at `localhost:19100` — everything stays on your machine.

| Page | What You'll Find |
|------|-----------------|
| **Overview** | System health, agent status, activity feed |
| **Shield** | Security status, file protection groups (locked/unlocked), daemon health |
| **Policy Graph** | 18 policy rules + 6 protocol flows with enforcement badges (🟢 blocking / 🟠 partial / 🔴 not enforced) |
| **R-Memory** | SSoT document manager, keyword config, file locking |
| **Wallet** | Solana DevNet integration (DAO, tokens, onboarding) |
| **Agents** | Agent management and skills |
| **Projects** | Project tracking, TODO, Ideas |
| **Protocol Store** | Browse and manage AI protocol NFTs |

---

## 🔧 Configuration

### `dashboard/config.json`
Solana RPC endpoints, token mints, safety caps. Copy from `config.example.json` and fill in your values.

### `r-awareness/keywords.json`
Maps keywords to SSoT documents. When you say a keyword, the matching doc loads into your AI's context.

### `r-memory/config.json`
Compression triggers, block size, eviction thresholds. Defaults work well — tune if needed.

---

## 🛡️ Security

- **Shield Daemon** — Always-on security service (port 9999) with health monitoring
- **12 Blocking Layers** — Direct Coding Gate, Delegation Gate, Injection Detection, State Claim Gate, Config Change Gate, and more
- **File Protection** — 2000+ files tracked across 7 groups, OS-level immutable flags (`chflags uchg`)
- **Logician Policy Engine** — 250 facts, 16 rule files, Mangle/Datalog runtime for governance decisions
- **YARA Rules** — Nightly updated malware/threat signatures
- **Sanitization Auditor** — `tools/sanitize-audit.py` scans for leaked secrets before any public release
- **Local-First** — No cloud dependencies. Your data stays on your machine.

---

## 👥 Built By

**[Manolo Remiddi](https://manolo.world)** — Composer, photographer, sound engineer, AI strategist.

**Augmentor** — AI collaborator running on OpenClaw. Force multiplier, second brain.

Together, building proof that human-AI symbiosis works.

---

## 📖 Learn More

- [ResonantOS](http://resonantos.com) — Official website
- [Augmentatism Manifesto](http://augmentatism.com) — The philosophy
- [OpenClaw](https://github.com/openclaw/openclaw) — The kernel
- [GitHub Organization](https://github.com/ResonantOS) — Development home
- [Discord](https://discord.gg/MRESQnf4R4) — Join the community

---

## 📜 License

**[Resonant Core — Symbiotic License v1.0 (RC-SL v1.0)](LICENSE)**

Not MIT. Not GPL. A symbiotic license: free to share and adapt, with a 1% tithe for commercial use that funds both the community DAO and core development. [Read the full license →](LICENSE)

---

<p align="center">
  <em>"As artificial intelligence generates infinite content,<br>the most human thing we can do is make meaning together."</em>
</p>
