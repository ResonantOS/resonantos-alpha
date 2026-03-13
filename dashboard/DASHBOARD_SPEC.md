# ResonantOS Dashboard - Design Specification
<!-- Created: 2026-02-06 | Source: Manolo feedback -->

## Product Vision

**What:** Dashboard for ResonantOS - the AI orchestration system
**Audience:** Power users managing AI agent fleets, projects, and communities
**Distribution:** Public release (downloadable, self-hosted)

---

## Current State Assessment

| Area | Status | Notes |
|------|--------|-------|
| Overall | ❌ Messy | Not well-structured, unprofessional graphics |
| UX | ❌ Poor | Not interactive enough, high friction |
| UI | ❌ Poor | Inconsistent, not polished |
| Project Manager | ✅ Good | Clean, interactive, well-structured - **USE AS MODEL** |
| Chatbot Manager | ⚠️ Concept OK | Right idea (single page + sub-tabs), needs UX/UI polish |
| Tabs/Navigation | ❌ Poor | Not logically organized from human perspective |
| Redundancy | ⚠️ Present | Some pages should merge (e.g., todo → integrate elsewhere) |

---

## Design Principles

### 1. Reference Model
**Project Manager page = gold standard.** Apply its patterns everywhere:
- Clean layout
- Interactive elements
- Well-structured information hierarchy
- Makes logical sense

### 2. Information Architecture
- **Main page:** Overview + System Monitor + Health Status
- **Chatbot Manager:** Single page with sub-tabs (keep this pattern)
- **Consolidate redundant pages:** Todo list integrates into relevant sections
- **Logical organization:** Human mental model, not technical structure

### 3. Visual Design

| Element | Requirement |
|---------|-------------|
| Theme | Dark (default) + Light |
| Theming system | Easy to change color scheme |
| User customization | Settings page: colors, logo, branding |
| Icons | Polished SVG icons (no emoji, no rough icons) |
| Density | Tighter/denser spacing |
| Professionalism | Polished, not prototype-looking |

### 4. Navigation
**Principle:** Least friction wins
- Reduce clicks to reach any function
- Logical tab grouping
- Sub-tabs where appropriate (like Chatbot Manager)

---

## Feature Requirements

### Core Features
1. **System Overview** - Health, status, key metrics at a glance
2. **Agent Management** - Monitor/control AI agents
3. **Project Manager** - Multi-project tracking (existing, good)
4. **Chatbot Manager** - Single-page with sub-tabs (existing concept, needs polish)
5. **Settings** - Theme, colors, logo, customization

### Integrations
- **GitHub** - Pull data from repos (issues, PRs, commits)
- Future: More integrations as needed

### User Customization (Settings)
- [ ] Dark/Light theme toggle
- [ ] Custom color scheme
- [ ] Upload logo
- [ ] Brand name/title customization

---

## Technical Requirements

### Theming
```
- CSS variables for all colors
- Theme switcher in settings
- Persist preference (localStorage)
- Custom theme editor (advanced)
```

### Icons
- Use polished SVG icon library (Lucide, Heroicons, or similar)
- Consistent sizing and styling
- No inline emoji as icons

### Layout
- Denser spacing (reduce padding/margins)
- Responsive but optimize for desktop
- Consistent component sizing

---

## Pages to Keep vs Consolidate

### Keep (with improvements)
- Overview/Main (system health + monitoring)
- Project Manager (model page - minor tweaks only)
- Chatbot Manager (restructure UX, keep single-page concept)
- Settings (new/expanded)

### Consolidate/Remove
- Todo List → Integrate into Project Manager or Overview
- Any placeholder pages → Remove or integrate
- Redundant monitoring views → Merge

---

## Priority Order

1. **UX Architecture** - Reorganize navigation, consolidate pages
2. **UI Polish** - SVG icons, tighter spacing, professional look
3. **Theming System** - Dark/light + customization
4. **Monitoring Improvements** - Better health/status visualization
5. **GitHub Integration** - Pull external data

---

## Success Criteria

- [ ] Looks professional (not prototype)
- [ ] Navigation is logical (human mental model)
- [ ] Friction is minimal (fewest clicks)
- [ ] Project Manager quality everywhere
- [ ] Theme customization works
- [ ] Ready for public release
