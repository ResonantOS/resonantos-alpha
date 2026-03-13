# Dashboard Reorganization
**Date:** 2026-02-05  
**Requested by:** Manolo

---

## Changes to Existing Dashboard

### Overview Page
**Current order:**
1. System
2. Agents
3. Chatbot
4. Updates
5. Agent Memory Status

**New order:**
1. System
2. Agents
3. Chatbot
4. Updates
5. Agent Activity *(assume this exists)*
6. **Agent Memory Status** ← moved here (was at end)

**Change:** Move "Agent Memory Status" section to appear **after** "Agent Activity"

---

### Agents Tab
**Current structure:**
- Agent overview shows Tasks
- Skills section
- Available Agents section

**New structure (top menu tabs within Agents):**
1. **Tasks** ← moved from overview, now first tab
2. Skills
3. Available Agents

**Navigation flow:**
```
Left Menu → Agents
   ↓
Opens to: Tasks (first thing visible)
   ↓
Tabs: [Tasks] [Skills] [Available Agents]
```

---

## Implementation Notes

**Files to modify:**
- `/Users/augmentor/clawd/projects/resonantos/dashboard/templates/index.html` (Overview page)
- `/Users/augmentor/clawd/projects/resonantos/dashboard/templates/agents.html` (or equivalent)
- `/Users/augmentor/clawd/projects/resonantos/dashboard/server.py` (routing if needed)

**Goal:** Cleaner information hierarchy — Tasks are primary when viewing Agents section.

---

**Status:** Documented, awaiting implementation
