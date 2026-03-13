# Logician Dashboard Sync Specification
**Date:** 2026-02-05  
**Requirement:** Software-based sync (not AI-managed)

---

## Problem

Currently:
- Dashboard displays Logician rules (reads `production_rules.mg`)
- No way to toggle rules on/off from dashboard
- Changes to Logician rules require manual file editing
- No automatic sync between dashboard ↔ Logician

---

## Required Solution

**Software integration** that provides:

### 1. Read Rules (Dashboard ← Logician)
- Dashboard pulls current rules from Logician on load
- Shows: rule name, description, status (active/inactive)
- Auto-refreshes (no manual reload needed)

### 2. Create Rule (Dashboard → Logician)
- UI to add new rule (form with: name, type, condition, action)
- Validates rule syntax
- Writes to `production_rules.mg`
- Restarts Logician service to reload
- New rule appears in dashboard immediately

### 3. Toggle Rule (Dashboard ↔ Logician)
- Toggle switch on each rule
- On → Off: Comments out rule in production_rules.mg (disable without deleting)
- Off → On: Uncomments rule (re-enable)
- Changes persist (survive Logician restarts)
- Reflects in dashboard instantly

### 4. Delete Rule (Dashboard → Logician)
- Remove rule button (with confirmation)
- Deletes from production_rules.mg
- Restarts Logician
- Disappears from dashboard

---

## Technical Implementation

### API Endpoints (add to dashboard server.py)

```python
# Read all rules
GET /api/logician/rules
→ Returns: [{name, type, active, description}, ...]

# Toggle rule on/off
POST /api/logician/rules/{rule_id}/toggle
→ Param: {active: true|false}
→ Action: Comment/uncomment in production_rules.mg
→ Restart: Logician service

# Create new rule
POST /api/logician/rules
→ Param: {name, type, condition, action}
→ Action: Append to production_rules.mg
→ Restart: Logician service

# Delete rule
DELETE /api/logician/rules/{rule_id}
→ Action: Remove from production_rules.mg
→ Restart: Logician service
```

### File Operations

**production_rules.mg location:**  
`/Users/augmentor/clawd/projects/logician/poc/production_rules.mg`

**Toggle implementation (comment/uncomment):**
```
# Active rule:
can_spawn(/strategist, /coder).

# Disabled rule (toggle OFF):
# [DISABLED] can_spawn(/strategist, /coder).
```

**Logician restart:**
```bash
# After any change to production_rules.mg
pkill -HUP logician  # Or: brew services restart logician
```

---

## UI Changes (Dashboard)

### Logician Rules Page

**Current:**
- Read-only list of rules

**New:**
- ✅ Toggle switch per rule (active/inactive)
- ➕ "Add Rule" button → opens form
- 🗑️ Delete button per rule (with confirmation)
- 🔄 Auto-refresh (shows changes immediately)

**Add Rule Form:**
- Rule Name (text input)
- Rule Type (dropdown: fact, permission, constraint, etc.)
- Condition (textarea, Mangle syntax)
- Action (textarea, if applicable)
- Validate button (checks syntax before saving)
- Save → writes to file + restarts Logician

---

## Constraints

**Software-driven (not AI):**
- No AI agent edits production_rules.mg manually
- All changes via API endpoints
- Dashboard UI is the control interface
- Logician auto-reloads on file change

**Safety:**
- Backup production_rules.mg before changes (`.backup` file)
- Validate syntax before writing (fail if invalid)
- Rollback on error (restore .backup)
- Log all changes (who changed what, when)

---

## Success Criteria

✅ Dashboard shows all Logician rules on load  
✅ Toggle switch disables/enables rule instantly  
✅ New rule created in dashboard appears in Logician immediately  
✅ Deleted rule removed from Logician and dashboard  
✅ No manual file editing required  
✅ Changes survive Logician restarts  
✅ All operations logged  

---

**Status:** Specification complete, awaiting implementation  
**Estimated effort:** 2-3 hours (API + UI + testing)  
**Priority:** High (enables autonomous rule management)

