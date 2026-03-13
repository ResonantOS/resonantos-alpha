# Dashboard Navigation Testing Guide

Quick validation checklist for the navigation reorganization changes.

---

## Prerequisites

```bash
cd /Users/augmentor/clawd/projects/resonantos/dashboard
python3 server.py
```

Dashboard should be running on http://localhost:5000

---

## Test 1: Overview Page Section Order

**Navigate to:** http://localhost:5000/

**Verify order from top to bottom:**
1. ✅ Metrics Cards Row (System, Agents, Chatbots, Uptime)
2. ✅ **Agent Activity (Last 24 Hours)** chart
3. ✅ **Agent Memory Status** table (should be AFTER activity chart)
4. ✅ Tasks Kanban Board
5. ✅ Live Activity Feed

**Pass criteria:** Memory Status appears AFTER Activity Chart (not before)

---

## Test 2: Agents Page Default Tab

**Navigate to:** http://localhost:5000/agents

**Verify:**
- ✅ Page loads successfully
- ✅ Three tabs visible: **Tasks** | Skills | Available Agents
- ✅ **Tasks tab is active** (highlighted/selected)
- ✅ Kanban board is visible with To Do / Done columns
- ✅ Task counts appear in column headers

**Pass criteria:** Tasks tab opens by default, kanban board visible

---

## Test 3: Skills Tab Functionality

**Starting from Agents page:**

**Steps:**
1. Click **Skills** tab
2. Observe page content

**Verify:**
- ✅ Skills tab becomes active (highlighted)
- ✅ Tasks panel hides
- ✅ Skills marketplace displays
- ✅ Search bar and filters visible
- ✅ Skill cards render correctly

**Pass criteria:** Skills functionality unchanged from before

---

## Test 4: Available Agents Tab Functionality

**Starting from Agents page:**

**Steps:**
1. Click **Available Agents** tab
2. Observe page content

**Verify:**
- ✅ Available Agents tab becomes active
- ✅ Skills panel hides
- ✅ Agent stats bar visible (Total, Active, Available, Unconfigured)
- ✅ Agent cards grid displays
- ✅ Agent details load correctly

**Pass criteria:** Available Agents functionality unchanged from before

---

## Test 5: Tab Switching

**Starting from Agents page:**

**Steps:**
1. Click Skills → verify Skills panel shows
2. Click Tasks → verify Tasks panel shows
3. Click Available Agents → verify Agents panel shows
4. Click Tasks → verify back to Tasks panel

**Verify:**
- ✅ Each tab switch updates active state
- ✅ Only one panel visible at a time
- ✅ No console errors during switching
- ✅ Data loads correctly for each tab

**Pass criteria:** Smooth tab switching, no visual glitches

---

## Test 6: Tasks Data Loading

**Navigate to:** http://localhost:5000/agents (Tasks tab)

**Verify:**
- ✅ Tasks kanban board visible
- ✅ Network request to `/api/tasks` succeeds
- ✅ Task counts update in column headers
- ✅ Task cards render in correct columns
- ✅ Empty state shows "No tasks" if no tasks exist

**Check browser console:**
```javascript
// Should see successful fetch
GET /api/tasks → 200 OK
```

**Pass criteria:** Tasks load from API without errors

---

## Test 7: Browser Console Errors

**Open DevTools (F12) → Console tab**

**Navigate through:**
1. Overview page
2. Agents page (Tasks tab)
3. Agents page (Skills tab)
4. Agents page (Available Agents tab)

**Verify:**
- ✅ No JavaScript errors
- ✅ No 404 errors for missing resources
- ✅ API calls succeed (200 status codes)

**Pass criteria:** Clean console, no errors

---

## Test 8: Responsive Behavior

**Test on different viewport sizes:**

1. Desktop (1920x1080)
2. Tablet (768x1024)
3. Mobile (375x667)

**Verify:**
- ✅ Tabs remain visible and clickable
- ✅ Kanban columns stack on mobile
- ✅ No horizontal scrolling
- ✅ Touch targets adequate size

**Pass criteria:** Responsive layout works correctly

---

## Test 9: Navigation Flow

**Simulate typical user workflow:**

1. Start at Overview → check system health
2. Click Agents in sidebar → lands on Tasks tab ✓
3. View pending tasks
4. Click Skills → explore available skills
5. Click Available Agents → check agent status
6. Return to Tasks → verify state preserved

**Verify:**
- ✅ Navigation intuitive and fast
- ✅ No unexpected page reloads
- ✅ Data doesn't re-fetch unnecessarily

**Pass criteria:** Smooth user experience

---

## Test 10: Backward Compatibility

**Check existing functionality still works:**

- ✅ Overview page metrics update
- ✅ Activity chart renders
- ✅ Memory status table loads
- ✅ Live activity feed streams
- ✅ Agent modal opens on click (Available Agents tab)
- ✅ Skill activation works (Skills tab)

**Pass criteria:** No regressions in existing features

---

## Quick Smoke Test

**5-minute validation:**

```bash
# 1. Start server
cd /Users/augmentor/clawd/projects/resonantos/dashboard
python3 server.py

# 2. Open browser → http://localhost:5000

# 3. Check Overview
✓ Activity chart above Memory Status

# 4. Click Agents
✓ Opens to Tasks tab
✓ Kanban board visible

# 5. Click Skills
✓ Skills marketplace loads

# 6. Click Available Agents
✓ Agent cards load

# Done! ✅
```

---

## Common Issues & Fixes

### Issue: Tasks tab doesn't load
**Check:**
- Server running?
- `/api/tasks` endpoint accessible?
- Browser console for errors

### Issue: Tabs don't switch
**Check:**
- JavaScript loaded correctly?
- Console errors?
- `switchAgentTab()` function defined?

### Issue: Kanban board empty
**Check:**
- `/api/tasks` returning data?
- Network tab shows successful request?
- Data format matches expected structure?

### Issue: Styling broken
**Check:**
- `dashboard.css` loaded?
- Kanban styles present in CSS?
- Browser cache cleared?

---

## Success Criteria Summary

**All tests pass if:**
1. ✅ Overview page sections in correct order
2. ✅ Agents page opens to Tasks by default
3. ✅ All three tabs functional (Tasks, Skills, Available Agents)
4. ✅ No JavaScript console errors
5. ✅ No breaking changes to existing features
6. ✅ Responsive design works
7. ✅ Navigation flow intuitive

---

## Reporting Issues

If tests fail, capture:
- Browser and version
- Console errors (screenshot)
- Network tab (failed requests)
- Steps to reproduce
- Expected vs actual behavior

---

**Estimated testing time:** 10-15 minutes for full validation  
**Minimum testing time:** 5 minutes for smoke test
