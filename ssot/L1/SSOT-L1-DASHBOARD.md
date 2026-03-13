# ResonantOS Dashboard -- Architecture

| Field | Value |
|-------|-------|
| ID | SSOT-L1-DASHBOARD-V1 |
| Created | 2026-02-11 |
| Updated | 2026-03-02 |
| Author | Augmentor |
| Level | L1 (Architecture) |
| Status | Active |
| Stale After | 90 days |

---

## 1. Overview

Local web dashboard for managing ResonantOS. Runs on `localhost:19100`. Not a cloud service -- everything stays on the user's machine.

## 2. Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python Flask (single `server_v2.py`) |
| Templates | Jinja2 with dark theme |
| Database | SQLite (`chatbots.db` for chatbot manager) |
| Frontend | Vanilla JS, no npm/node dependencies |
| CSS | Custom dark theme with CSS variables |
| Port | 19100 (default) |

## 3. Pages

| Page | Route | Purpose |
|------|-------|---------|
| Overview | `/` | System health, agent status, uptime, activity feed |
| Agents | `/agents` | Agent management, skills marketplace |
| Chatbots | `/chatbots` | Chatbot builder with visual customizer, widget embeds, knowledge base |
| R-Memory | `/r-memory` | SSoT document manager, keyword config, file locking |
| Projects | `/projects` | Project tracking |
| Docs | `/docs` | Documentation browser |
| TODO | `/todo` | Task management |
| Ideas | `/ideas` | Idea capture |
| Intelligence | `/intelligence` | Research and intelligence tools |
| Settings | `/settings` | System configuration, rules |

## 4. R-Memory Page (SSoT Manager)

### 4.1 Purpose
Visual interface for managing Single Source of Truth (SSoT) documents. These are markdown files organized in a hierarchy (L0-L4) that get injected into the AI agent's context by R-Awareness when relevant keywords are detected in conversation.

### 4.2 Features
- **Document tree**: Browse SSoTs by layer (L0-L4)
- **Markdown editor**: Split-pane with live preview, token counter
- **Keywords per document**: Configure trigger words for R-Awareness injection
- **Dual token display**: Shows both compressed (.ai.md) and raw (.md) token counts
- **File locking**: OS-level immutable flags prevent AI from editing critical docs

### 4.3 Layer Hierarchy

| Layer | Name | Purpose | Lock Default |
|-------|------|---------|-------------|
| L0 | Foundation | Vision, mission, philosophy, manifesto, business plan | Locked |
| L1 | Architecture | System architecture, technical specs, integration patterns | Locked |
| L2 | Active Projects | Current project status, milestones, decisions | Unlocked |
| L3 | Drafts | Plans, proposals, research in progress | Unlocked |
| L4 | Notes | Working notes, session logs, incidents | Unlocked |

### 4.4 File Locking System

**macOS**: Uses `chflags uchg` (user immutable flag). Lock is free, unlock requires sudo (master password). Strongest OS-level protection -- even root processes respect it by default.

**Linux**: Users should implement via `chattr +i` (requires root). Same concept, different command. The AI can help build this.

**Windows**: Users should implement via `attrib +R` (read-only) or NTFS ACLs. The AI can help build this.

The dashboard detects lock state from the filesystem and shows 🔒/🔓 per document and per layer.

### 4.5 Compression System

Each SSoT document can have a compressed `.ai.md` version alongside it:
- Raw `.md`: Human-readable, full document (what users edit)
- Compressed `.ai.md`: Lossless compressed version (tables over prose, terse, all data preserved)
- R-Awareness injects the `.ai.md` version to save 55-80% tokens
- Compression done by Haiku sub-agent (cheap model)

### 4.6 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/r-memory/documents` | List all SSoT docs with metadata |
| GET | `/api/r-memory/documents/<path>` | Get document content |
| PUT | `/api/r-memory/documents/<path>` | Save document content |
| POST | `/api/r-memory/documents` | Create new document |
| DELETE | `/api/r-memory/documents/<path>` | Delete (move to trash) |
| GET | `/api/r-memory/keywords` | Get keyword mappings |
| PUT | `/api/r-memory/keywords` | Save keyword mappings |
| GET | `/api/r-memory/stats` | Overview statistics |
| POST | `/api/r-memory/lock/<path>` | Lock a document |
| POST | `/api/r-memory/unlock/<path>` | Unlock (requires password) |
| POST | `/api/r-memory/lock-layer/<layer>` | Lock entire layer |
| POST | `/api/r-memory/unlock-layer/<layer>` | Unlock entire layer |

## 5. File Structure

```
dashboard/
├── server.py              # Flask backend (all routes + API)
├── templates/
│   ├── base.html          # Sidebar + layout shell
│   ├── index.html         # Overview page
│   ├── chatbots.html      # Chatbot manager
│   ├── r-memory.html      # SSoT manager
│   ├── agents.html        # Agent management
│   └── ...                # Other pages
├── static/
│   ├── css/dashboard.css  # Dark theme styles
│   └── js/dashboard.js    # Shared JS utilities
├── chatbots.db            # SQLite database
└── README.md
```

## 6. Design Principles

- **Local-first**: Everything runs on the user's machine, no cloud dependency
- **Single file backend**: One `server.py`, easy to understand and modify
- **Dark theme**: Consistent with terminal/dev aesthetic
- **AI-friendly**: The AI can read this doc and help users extend/customize the dashboard
- **No build step**: Pure Python + vanilla JS, no npm/webpack/bundler

## 7. Dependencies

- Python 3.x
- Flask
- flask-cors
- psutil
- markdown2 (optional, for server-side rendering)

## 8. Related Documents

- R-Memory plugin: `SSOT-L2-R-MEMORY.md`
- R-Awareness spec: `SSOT-L1-R-AWARENESS-OLD.md`
- R-Memory strategy: `R-MEMORY-V2-STRATEGY.md`
