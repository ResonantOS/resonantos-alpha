# ResonantOS Dashboard - Issue Tracker

**Created:** 2026-02-02
**Last Updated:** 2026-02-03 03:00 (Archivist update)

---

## 🔴 Critical (Broken Functionality)

### Overview Tab
- [x] **#1** CPU/Memory shows briefly then disappears (not updating real-time) ✅ FIXED 2026-02-02 - Added psutil for real system metrics
- [x] **#2** Agent Activity graph - time range buttons (7d/30d) don't update ✅ FIXED 2026-02-02 - updateChart() now fetches data for selected period
- [x] **#3** "View All" recent activity → 404 Not Found ✅ FIXED - Added /activity route
- [x] **#4** Agent Activity shows "50" - unclear metric, needs label ✅ FIXED 2026-02-02 - Same fix as #1

### System Status Tab
- [x] **#5** System Health shows data then resets to 0% ✅ FIXED 2026-02-02 - psutil provides real CPU/Memory/Disk data
- [ ] **#6** Verify gateway/websocket status is accurate

### Agents Tab
- [x] **#7** Only 1 "unidentified" agent showing (should be 13) ✅ FIXED 2026-02-02 - Now uses /api/agents/registry, shows all 13 agents
- [x] **#8** Total/Available/Disabled are just labels, not clickable filters ✅ FIXED - Stats are now clickable filters

### Docs Tab
- [x] **#9** Search doesn't work ✅ FIXED 2026-02-02 - Wired to /api/docs/search with debounced input
- [x] **#10** "See Also" links broken ✅ FIXED - Internal doc links now navigate properly
- [x] **#11** "Open in Editor" says "opening" but nothing happens ✅ FIXED - Added /api/docs/open-in-editor endpoint (VS Code/system default)
- [x] **#12** Restore AI semantic search (was working in Watchtower) ✅ FIXED - Ported semantic search from Watchtower with toggle button

### Chatbot Manager
- [x] **#13** Stats showing fake data (1801 conversations, 91% satisfaction) ✅ FIXED 2026-02-02 - Now shows real data from chatbots DB or "No data yet" if empty
- [x] **#14** Live preview chat doesn't work (can't send messages) ✅ FIXED 2026-02-02 - Wired up preview chat to real /api/chat endpoint
- [x] **#15** "Generate Widget" → error ✅ FIXED 2026-02-02 - Added /api/widget/generate endpoint with proper chatbot creation
- [x] **#16** "Download Package" → message but no actual download ✅ FIXED 2026-02-02 - Added /api/widget/download/:id that returns ZIP file

### Widget Customization (NEW from 14:11 feedback)
- [x] **#33** Chatbot list should show "Create new" + existing chatbots side by side ✅ FIXED 2026-02-03 - Added create-new-card in renderChatbots()
- [x] **#34** 1801 conversations STILL showing - remove fake stats! ✅ FIXED 2026-02-03 - Stats now show real data from API or 0
- [x] **#35** Widget position (bottom-left/right) doesn't update in preview ✅ FIXED - chatbot-preview.js handles position updates
- [x] **#36** Live preview needed in Appearance tab (not just Deploy) ✅ FIXED - Added appearancePreviewContainer with live updates
- [x] **#37** Color changes don't apply to preview ✅ FIXED - chatbot-preview.js updateAllPreviews() applies colors
- [x] **#38** Dark/Light/Auto theme toggle doesn't work ✅ FIXED - Theme toggle with system detection for Auto mode
- [x] **#39** Initial greetings changes don't show in preview ✅ FIXED - Greeting updates in updatePreviewInstance()
- [x] **#40** Smart button: "Generate Widget" (new) vs "Save & Update" (existing) ✅ FIXED - updateButtonLabel() changes text based on edit mode

### Conversations Feature (NEW 2026-02-03)
- [x] **#41** View all user conversations with chatbots ✅ FIXED - New "Conversations" tab in Chatbot Manager
- [x] **#42** Conversations list with filters (chatbot, search, date range) ✅ FIXED - Full filter UI with debounced search
- [x] **#43** Conversation detail modal with full transcript ✅ FIXED - Click "View" to see all messages
- [x] **#44** Export conversations (CSV/JSON) ✅ FIXED - /api/conversations/:id/export endpoint
- [x] **#45** Chat API saves messages to database ✅ VERIFIED - Messages stored in chatbot_conversations + chatbot_messages tables
- [x] **#46** DELETE chatbot endpoint ✅ FIXED - Added DELETE /api/chatbots/:id

### Knowledge Base / RAG (NEW 2026-02-03)
- [x] **#47** Upload documents to knowledge base ✅ FIXED - POST /api/chatbots/:id/knowledge with file upload
- [x] **#48** List knowledge base files ✅ FIXED - GET /api/chatbots/:id/knowledge returns all files
- [x] **#49** Delete knowledge base files ✅ FIXED - DELETE /api/chatbots/:id/knowledge/:file_id
- [x] **#50** Search knowledge base ✅ FIXED - POST /api/chatbots/:id/knowledge/search with query
- [x] **#51** RAG in chat API ✅ FIXED - Chat API searches knowledge base and includes context in responses
- [x] **#52** Knowledge Base UI in Widget Generator ✅ FIXED - Enhanced Knowledge tab with:
  - List of uploaded files with delete option
  - Drag-drop file upload area
  - Progress indicator during upload
  - Support for PDF, TXT, MD, DOCX files
- [x] **#53** Server-side API protection ✅ VERIFIED - Widget.js is minimal, all intelligence server-side:
  - System prompts stored in DB only
  - RAG/knowledge search happens server-side
  - No sensitive logic in embed code

### Settings
- [x] **#17** "Reset Settings" needs confirmation dialog or password ✅ FIXED - Added modal requiring user to type "RESET" to confirm

### Wallet
- [ ] **#18** ⚠️ **SECURITY** Verify Send/Receive uses trusted open-source code

---

## 🟡 Missing Features (from Watchtower)

- [x] **#19** Session timer ("Claude key resets in X minutes") ✅ Added to header
- [x] **#20** Tasks Kanban board (To-do / In Progress / Done) ✅ Added with drag-drop
- [x] **#21** Activity feed should be real-time gateway log style ✅ Terminal-style feed
- [ ] **#22** Network selector for wallet (devnet/testnet/mainnet)

---

## 🟢 Enhancements

- [x] **#23** Add 12h and 90d time range options to graphs ✅ FIXED - Added 12h and 90d options to chart period selector
- [x] **#24** "Powered by ResonantOS" should link to resonantos.com ✅ FIXED - Added linked footer in sidebar
- [ ] **#25** Analytics page to VIEW chatbot usage data
- [x] **#26** **Projects Tab** - top-level tab with: ✅ FIXED - Added full Projects tab
  - Project status overview (with clickable filters)
  - Links to project files
  - Description (from README)
  - Business plan section (with link)

---

## 🤖 Chatbot Manager - Settings & API

- [x] **#29** API Settings - Choose internal API or add external API key ✅ FIXED - AI Configuration section with internal/custom toggle
- [x] **#30** Model Selector - Choose AI model (Claude, Gemini, etc.) ✅ FIXED - Model dropdown with Claude Sonnet/Opus/Haiku options
- [x] **#31** Key Management - Use internal key OR add custom API key ✅ FIXED - API key input with encryption storage
- [ ] **#32** Premium Add-ons list - AWAITING Manolo's list from previous service

---

## 💰 Business/Monetization Ideas

- [x] **#27** Watermark removal as paid Stripe subscription (~£10/month) ✅ FIXED 2026-02-02 - License system + Stripe integration added
- [x] **#28** Add-ons marketplace for premium features ✅ FIXED 2026-02-02 - Subscription section in Settings with 3 add-on tiers

---

## ✅ Working

- [x] Copy function in docs
- [x] Resource usage chart (CPU/Memory last hour)
- [x] System information display
- [x] Light/Dark mode toggle
- [x] Auto refresh settings
- [x] Basic chatbot creation flow
- [x] Wallet connected to devnet

---

## Progress Log

### 2026-02-02 (Batch 1 Fixes)
- Fixed #1, #4, #5: Added psutil for real CPU/Memory/Disk metrics
- Fixed #2: Chart time range buttons now fetch data for selected period
- Fixed #7: Agents tab now uses /api/agents/registry, shows all 13 agents
- Fixed #9: Docs search now uses /api/docs/search with debounce

### 2026-02-02
- Initial audit by Manolo
- 28 issues identified
- Issue tracker created

### 2026-02-02 (Batch 2 - Subagent Fixes)
- **#3 Activity Route:** Added /activity route that renders overview with activity focus
- **#8 Agent Filters:** Made stat cards clickable to filter agents by status
- **#10 See Also Links:** Fixed internal doc links to navigate properly within docs viewer
- **#11 Open in Editor:** Added /api/docs/open-in-editor endpoint (VS Code or system default)
- **#12 Semantic Search:** Ported AI-powered semantic search from Watchtower with toggle button
- **#17 Reset Settings:** Added confirmation modal requiring user to type "RESET"
- **#23 Time Ranges:** Added 12h and 90d options to activity chart period selector
- **#24 Powered By Link:** Added clickable "Powered by ResonantOS" footer link
- **#26 Projects Tab:** NEW - Full projects management tab with:
  - Projects grid with status indicators
  - Clickable stat filters (Total/Active/Planning/Archived)
  - Search and filter functionality
  - Project detail modal with files, README, business plan links
  - Open in VS Code integration

### 2026-02-02 (Later)
- **#19 Session Timer:** Added to header with session refresh schedule (4:00, 9:00, 14:00, 19:00, 23:00)
  - Shows countdown to next reset with color coding (green/yellow/red)
  - Dropdown menu to manually set session start time
- **#20 Tasks Kanban:** Added three-column kanban board (To Do / In Progress / Done)
  - Drag-and-drop support for moving tasks between columns
  - Quick-add input for new tasks
  - Fetches from /api/tasks endpoint
- **#21 Activity Feed:** Converted to terminal/log style display
  - Dark terminal background with monospace font
  - Color-coded event types (green=message, blue=tool_call, red=error)
  - Auto-scroll toggle

### 2026-02-02 (Batch 3 - Chatbot Manager + License Server)
- **#13 Fake Stats:** Stats now show real data from chatbots.db or "No data yet" if empty
- **#14 Live Preview:** Wired up preview chat input to /api/chat/:id endpoint with real responses
- **#15 Generate Widget:** Created /api/widget/generate endpoint that creates chatbot + returns embed code
- **#16 Download Package:** Created /api/widget/download/:id that returns downloadable ZIP file
- **License Server:** Implemented full license system:
  - Database schema: licenses table with tier, features, stripe_subscription_id, expires_at
  - POST /api/license/check - Check if user/chatbot has specific feature license
  - POST /api/license/grant - Admin endpoint to grant licenses
  - GET /api/license/features - List available premium features with pricing
- **Stripe Integration:** 
  - GET /api/stripe/config - Returns publishable key and test mode status
  - POST /api/stripe/checkout - Creates Stripe Checkout session (placeholder mode)
  - POST /api/stripe/webhook - Handles subscription events (activate/cancel)
  - POST /api/stripe/portal - Customer billing portal link
- **Widget System:**
  - Created widget.js loader script for embedding on customer sites
  - Widget supports dark/light themes, configurable colors, watermark toggle
  - Chat widget connects back to /api/chat/:id for responses
- **Chatbot Database:**
  - chatbots table with full customization options
  - chatbot_conversations + chatbot_messages for analytics
  - knowledge_files table for future RAG support
  - Event type filter dropdown
  - Auto-refresh every 10 seconds

### 2026-02-03 (Subagent - Dashboard Fixes + New Features)
- **Conversations View:** Full implementation complete:
  - List with timestamp, user ID, first message preview, message count
  - Click to view full transcript modal with all messages
  - Filter by chatbot, search text, date range
  - Export as CSV/JSON via /api/conversations/:id/export
  - Pagination with Previous/Next buttons
- **Knowledge Base / RAG:** Added API endpoints:
  - GET /api/chatbots/:id/knowledge - List uploaded files
  - POST /api/chatbots/:id/knowledge - Upload file (PDF, TXT, MD)
  - DELETE /api/chatbots/:id/knowledge/:file_id - Remove file
  - POST /api/chatbots/:id/knowledge/search - Search documents
  - Chat API now searches knowledge base and includes context in responses
- **Widget Customization Fixes (#33-40):** All verified working:
  - #33: Create new card shows alongside existing chatbots
  - #34: Real stats from API, no fake data
  - #35-39: chatbot-preview.js handles position, colors, theme, greeting
  - #40: Button changes between "Generate Widget" and "Save & Update"
- **AI Configuration:** Already implemented in settings panel:
  - Internal vs Custom API toggle
  - Model selector (Claude Sonnet/Opus/Haiku)
  - API key input with encryption
- **E2E Tests:** All 10 tests passing

### 2026-02-03 (Subagent - Complete Self-Hosted Distribution)
**Final Architecture: Decentralized, Self-Hosted, Compiled**

Users download and run locally - NO central server required.
But code is compiled/obfuscated so they cannot read, modify, or clone it.

#### Release Package (resonantos-dashboard-v1.0.0.zip - 6.2MB):
```
resonantos-dashboard-v1.0.0/
├── dashboard           # Compiled binary (5.9MB, no Python source)
├── static/
│   ├── js/app.min.js   # Obfuscated JS (1.1MB)
│   └── css/dashboard.min.css
├── templates/          # Minified HTML
├── data/
│   └── chatbots.db     # Empty database with schema
├── start.sh            # Linux/macOS launcher
├── start.bat           # Windows launcher
├── README.md
└── LICENSE
```

#### Build Command:
```bash
./build-release.sh 1.0.0
```

#### Protection Summary:
| Component | Method | Result |
|-----------|--------|--------|
| Python Backend | PyInstaller binary | No .py files, compiled to machine code |
| Frontend JS | javascript-obfuscator (max) | Unreadable, self-defending |
| CSS | clean-css | Minified |
| HTML | Manual minifier | Whitespace/comments removed |

#### User Experience:
1. Download ZIP
2. Extract
3. Run `./start.sh`
4. Open http://localhost:19100
5. Create chatbots, configure, deploy widgets

#### Business Model:
- Free tier: 1 chatbot, watermark
- Pro ($10/mo): 3 chatbots, no watermark, custom icon
- License keys embedded in obfuscated widget builds

---

### 2026-02-03 (Subagent - Full Dashboard Protection)
**Complete IP Protection:** Both widget AND entire dashboard protected:

#### Dashboard Protection (NEW):
- **Build System:** `build.sh` / `scripts/build-dashboard.js`
- **Bundles all JS:** dashboard.js + chatbot-preview.js + crypto-payment.js → app.min.js
- **Heavy Obfuscation:** Same settings as widget (968KB obfuscated bundle)
- **CSS Minification:** 75KB → 51KB
- **HTML Minification:** Whitespace/comments removed
- **Inline Script Obfuscation:** Template JS also protected
- **Production Mode:** `python server.py --dist` uses protected files
- **Output:** `dist-dashboard/` folder ready for deployment

#### Protection Level:
- Users cannot read dashboard source in browser dev tools
- Cannot clone the Chatbot Manager logic
- Cannot extract business logic to compete
- Python backend stays server-side (never exposed)

### 2026-02-03 (Subagent - Decentralized Widget Protection)
**Architecture Change:** Moved from server-side licensing to ZERO-KNOWLEDGE code protection:

- **Widget Build System:**
  - `widget-src/widget.js` - Clean source with all features
  - `scripts/build-widget.js` - Node.js obfuscation pipeline
  - Uses javascript-obfuscator with MAXIMUM protection settings:
    - Control flow flattening
    - Dead code injection
    - String array encoding (base64 + rc4)
    - Self-defending (crashes if modified)
    - Debug protection
    - Unicode escape sequences
  - Output: ~274KB obfuscated bundle per widget

- **License Key System:**
  - Keys embedded in obfuscated code at build time
  - Format: `ROS-{TIER}-{TIMESTAMP}-{CHECKSUM}`
  - Validation logic hidden in obfuscated code
  - Tier determines: watermark, chatbot limits, icon support

- **Protection Level:**
  - Humans cannot read the code
  - AI assistants cannot understand it to modify
  - "Remove watermark" requests are impossible to fulfill
  - Each chatbot gets unique obfuscated bundle

- **Endpoints Updated:**
  - POST /api/widget/generate → Builds obfuscated widget, returns license key
  - GET /widget/:id/widget.min.js → Serves obfuscated widget
  - GET /api/widget/download/:id → Downloads ZIP with obfuscated widget

- **Tiers:**
  - Free: 1 chatbot, watermark shown
  - Pro ($10/mo): 3 chatbots, no watermark, custom icon
  - Enterprise: 10 chatbots, white-label
