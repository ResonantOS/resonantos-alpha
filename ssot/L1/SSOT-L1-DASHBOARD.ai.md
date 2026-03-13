# Dashboard — Compressed

| Field | Value |
|-------|-------|
| Stack | Python Flask, Jinja2, vanilla JS, SQLite |
| Port | 19100 (localhost only) |
| Server | Single `server_v2.py` |

## Pages

| Route | Purpose |
|-------|---------|
| `/` | System health, agent status, uptime |
| `/agents` | Agent management, R-Memory model selector |
| `/chatbots` | Chatbot builder, widget embeds |
| `/r-memory` | SSoT doc manager, keywords, file locking |
| `/wallet` | Symbiotic Wallet, leaderboard, NFTs, protocol store |
| `/projects` | Project tracking |
| `/docs` | Documentation browser |
| `/settings` | System configuration |

## SSoT Manager (R-Memory Page)
- Document tree (L0–L4), markdown editor with live preview
- Keywords per doc (R-Awareness triggers)
- Dual token display (raw `.md` vs compressed `.ai.md`)
- File locking: macOS `chflags uchg` / Linux `chattr +i`

## Layer Hierarchy

| Layer | Lock Default | Purpose |
|-------|-------------|---------|
| L0 | Locked | Foundation (vision, philosophy, business) |
| L1 | Locked | Architecture (specs, patterns) |
| L2 | Unlocked | Active projects |
| L3 | Unlocked | Drafts, proposals |
| L4 | Unlocked | Working notes, session logs |

## Design Principles
- Local-first (no cloud), single-file backend, dark theme, no build step
- Dependencies: flask, flask-cors, psutil
