# Logician Dashboard UI Spec

## Overview

Add a new "Rules" section to the ResonantOS Dashboard that displays active Logician rules and allows toggling them on/off.

## Requirements

### 1. Rules Page (`/rules`)

Display all Logician rules organized by file:
- `security_rules.mg` — Security & Shield
- `agent_rules.mg` — Agent Permissions
- `preparation_rules.mg` — Preparation Protocol
- `crypto_rules.mg` — Crypto Wallet Protection
- `research_rules.mg` — Research Tool Access

### 2. Rule Display

For each rule file, show:
- File name and description
- Number of rules/facts
- Toggle switch (enabled/disabled)
- Expand to see individual rules

### 3. Toggle Functionality

- Toggle entire rule files on/off
- Some rules are **locked** (cannot be disabled):
  - All `crypto_rules.mg` (absolute prohibitions)
  - Core `security_rules.mg` (injection blocking)
- Disabled rules are skipped during Logician queries

### 4. API Endpoints

```
GET  /api/logician/rules          — List all rule files + status
GET  /api/logician/rules/<file>   — Get rules from specific file
POST /api/logician/rules/<file>/toggle — Enable/disable rule file
GET  /api/logician/status         — Logician daemon health
```

### 5. UI Components

```
┌─────────────────────────────────────────────────────────┐
│ Rules                                            [🔄]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 🔒 crypto_rules.mg                         [LOCKED]     │
│    Crypto wallet protection - 45 rules                  │
│    ▶ Expand                                             │
│                                                         │
│ 🛡️ security_rules.mg                       [✓ ON]      │
│    Shield protocol, injection blocking - 62 rules       │
│    ▶ Expand                                             │
│                                                         │
│ 👥 agent_rules.mg                          [✓ ON]      │
│    Agent permissions and spawning - 38 rules            │
│    ▶ Expand                                             │
│                                                         │
│ 📋 preparation_rules.mg                    [○ OFF]     │
│    Preparation protocol - 41 rules                      │
│    ▶ Expand                                             │
│                                                         │
│ 🔬 research_rules.mg                       [✓ ON]      │
│    Research tool access - 52 rules                      │
│    ▶ Expand                                             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6. Expanded Rule View

When expanded, show rules in readable format:
```
┌─────────────────────────────────────────────────────────┐
│ 🔬 research_rules.mg                       [✓ ON]      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Tool Access:                                            │
│ • Researcher → Brave, Perplexity, Perplexity Pro       │
│ • Strategist → Brave only                              │
│ • Coder → Brave only                                   │
│ • Designer → Brave only                                │
│                                                         │
│ Rate Limits (per hour):                                 │
│ • Strategist: 50 Brave calls                           │
│ • Researcher: 100 Brave, 30 Perplexity, 10 Pro         │
│                                                         │
│ [View Raw Rules]                                        │
└─────────────────────────────────────────────────────────┘
```

### 7. State Persistence

- Store enabled/disabled state in `logician/config/enabled_rules.json`
- Logician daemon reads this on startup and query
- Changes take effect immediately (no restart needed)

### 8. Locked Rules

Rules that cannot be disabled (hardcoded):
```python
LOCKED_RULES = [
    "crypto_rules.mg",  # All absolute prohibitions
]

LOCKED_SECTIONS = {
    "security_rules.mg": [
        "forbidden_output",
        "block_input",
        "injection_pattern"
    ]
}
```

## Implementation Notes

1. Parse `.mg` files to extract rules and metadata
2. Create simple Prolog/Mangle parser or use regex for display
3. Logician daemon needs endpoint to report which rules are loaded
4. Consider WebSocket for live rule status updates

## Files to Modify/Create

- `dashboard/templates/rules.html` — New page
- `dashboard/static/js/rules.js` — Toggle logic
- `dashboard/api/logician.py` — API endpoints
- `logician/config/enabled_rules.json` — State file
- `logician/daemon.py` — Add rule filtering

## Priority

HIGH — Core feature for system transparency and control
