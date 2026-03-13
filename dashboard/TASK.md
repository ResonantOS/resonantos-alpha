# TASK: Improve Knowledge Base Page

## Overview
Improve the Knowledge Base settings page with better UI/UX.

## Changes Needed

### 1. Replace Icon
Change from emoji 📚 to SVG icon (clock-like for knowledge/archives)

### 2. Reorganize Layout
- **Common Knowledge Base** at top — with per-agent toggles (enable/disable which agents can access it)
- **Divider line**
- **Agent-specific blocks** below in order: Main → Voice → Coder (dynamic list from config)

### 3. Each Block Has
- Upload button to add documents (file input)
- Expandable to show list of uploaded files
- **Click file to preview** in a scrollable popup modal

### 4. File Preview Modal
- Click any file to open modal
- Modal shows full file content in a scrollable div
- Modal has close button (X) and closes on overlay click
- Use existing dark theme styling

## Files
- `server_v2.py` — Add endpoint to read file content
- `templates/settings.html` — Update UI

## API Endpoint Additions

### GET /api/knowledge/file
```python
@app.route("/api/knowledge/file")
def api_knowledge_file():
    """Read content of a knowledge file."""
    path = request.args.get("path", "")
    # Validate path is inside ~/.openclaw/knowledge/
    # Return file content as JSON
```

### POST /api/knowledge/upload
```python
@app.route("/api/knowledge/upload", methods=["POST"])
def api_knowledge_upload():
    """Upload a file to a knowledge folder."""
    # Handle multipart form upload
    # Save to appropriate folder
```

## Acceptance Criteria
1. SVG icon instead of emoji
2. Common KB at top with per-agent toggles
3. Divider line separating common from agent-specific
4. Agent blocks in order: Main → Voice → Coder
5. Upload button on each block
6. Expandable file list
7. Click file opens scrollable preview modal
8. Matches dark theme
