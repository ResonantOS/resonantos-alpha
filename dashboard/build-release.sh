#!/bin/bash
#
# ResonantOS Dashboard - Release Builder
# Creates a distributable package with compiled/obfuscated code
#
# Output: resonantos-dashboard-v{VERSION}.zip
#

set -e

VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build-release"
DIST_DIR="$SCRIPT_DIR/release"
PACKAGE_NAME="resonantos-dashboard-v${VERSION}"

cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ResonantOS Dashboard - Release Builder             ║"
echo "║                    Version: $VERSION                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf "$BUILD_DIR" "$DIST_DIR/$PACKAGE_NAME" "$DIST_DIR/$PACKAGE_NAME.zip"
mkdir -p "$BUILD_DIR" "$DIST_DIR/$PACKAGE_NAME"

# Check dependencies
echo ""
echo "🔍 Checking dependencies..."

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required"
    exit 1
fi
echo "   ✓ Node.js found"

if [ ! -d "node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install
fi
echo "   ✓ Node.js dependencies installed"

if [ ! -d "venv" ]; then
    echo "❌ Python venv not found. Run: python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi
echo "   ✓ Python venv found"

# Step 1: Compile Python backend
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📦 Step 1: Compiling Python Backend with PyInstaller..."
echo "═══════════════════════════════════════════════════════════════"

# Create a spec file for better control
cat > "$BUILD_DIR/dashboard.spec" << 'SPEC'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'flask',
        'flask_cors', 
        'sqlite3',
        'psutil',
        'requests',
        'json',
        'hashlib',
        'time',
        'subprocess',
        'pathlib'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
SPEC

./venv/bin/pyinstaller \
    --onefile \
    --name dashboard \
    --distpath "$DIST_DIR/$PACKAGE_NAME" \
    --workpath "$BUILD_DIR/pyinstaller" \
    --specpath "$BUILD_DIR" \
    --clean \
    --noconfirm \
    server.py 2>&1 | grep -E "(Building|Appending|Completed|Error)" || true

if [ ! -f "$DIST_DIR/$PACKAGE_NAME/dashboard" ]; then
    echo "❌ PyInstaller build failed"
    exit 1
fi

echo "   ✓ Binary compiled: dashboard"
ls -lh "$DIST_DIR/$PACKAGE_NAME/dashboard"

# Step 2: Obfuscate Frontend
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "🔒 Step 2: Obfuscating Frontend JavaScript..."
echo "═══════════════════════════════════════════════════════════════"

node scripts/build-dashboard.js

# Copy obfuscated files to release
cp -r dist-dashboard/static "$DIST_DIR/$PACKAGE_NAME/"
cp -r dist-dashboard/templates "$DIST_DIR/$PACKAGE_NAME/"

echo "   ✓ Frontend obfuscated and copied"

# Step 3: Create data directory and empty database
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📂 Step 3: Creating data directory..."
echo "═══════════════════════════════════════════════════════════════"

mkdir -p "$DIST_DIR/$PACKAGE_NAME/data"

# Create empty database with schema
cat > "$BUILD_DIR/init-db.sql" << 'SQL'
-- ResonantOS Dashboard Database Schema

CREATE TABLE IF NOT EXISTS chatbots (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    name TEXT NOT NULL,
    system_prompt TEXT,
    greeting TEXT DEFAULT 'Hi! How can I help you today?',
    suggested_prompts TEXT DEFAULT '[]',
    position TEXT DEFAULT 'bottom-right',
    theme TEXT DEFAULT 'dark',
    primary_color TEXT DEFAULT '#4ade80',
    bg_color TEXT DEFAULT '#1a1a1a',
    text_color TEXT DEFAULT '#e0e0e0',
    allowed_domains TEXT DEFAULT '',
    rate_per_minute INTEGER DEFAULT 10,
    rate_per_hour INTEGER DEFAULT 100,
    enable_analytics INTEGER DEFAULT 1,
    show_watermark INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    api_type TEXT DEFAULT 'internal',
    api_key_encrypted TEXT,
    model_id TEXT DEFAULT 'claude-sonnet',
    last_used_at INTEGER
);

CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chatbot_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    started_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    ended_at INTEGER,
    message_count INTEGER DEFAULT 0,
    satisfaction_rating INTEGER,
    FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
);

CREATE TABLE IF NOT EXISTS chatbot_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    FOREIGN KEY (conversation_id) REFERENCES chatbot_conversations(id)
);

CREATE TABLE IF NOT EXISTS licenses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chatbot_id TEXT,
    tier TEXT DEFAULT 'free',
    features TEXT DEFAULT '[]',
    stripe_subscription_id TEXT,
    stripe_customer_id TEXT,
    expires_at INTEGER,
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
);

CREATE TABLE IF NOT EXISTS knowledge_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chatbot_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT,
    file_size INTEGER,
    uploaded_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_chatbot ON chatbot_conversations(chatbot_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON chatbot_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id);
SQL

sqlite3 "$DIST_DIR/$PACKAGE_NAME/data/chatbots.db" < "$BUILD_DIR/init-db.sql"
echo "   ✓ Database initialized: data/chatbots.db"

# Step 4: Create start scripts
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📜 Step 4: Creating start scripts..."
echo "═══════════════════════════════════════════════════════════════"

# Unix start script
cat > "$DIST_DIR/$PACKAGE_NAME/start.sh" << 'SCRIPT'
#!/bin/bash
#
# ResonantOS Dashboard Launcher
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
PORT="${PORT:-19100}"
HOST="${HOST:-127.0.0.1}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              ResonantOS Dashboard                            ║"
echo "║              Starting on http://$HOST:$PORT                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Set environment
export RESONANTOS_STATIC="$SCRIPT_DIR/static"
export RESONANTOS_TEMPLATES="$SCRIPT_DIR/templates"
export RESONANTOS_DATA="$SCRIPT_DIR/data"

# Start dashboard
./dashboard --port "$PORT" --host "$HOST" --dist

SCRIPT
chmod +x "$DIST_DIR/$PACKAGE_NAME/start.sh"
echo "   ✓ Created start.sh"

# Windows start script
cat > "$DIST_DIR/$PACKAGE_NAME/start.bat" << 'SCRIPT'
@echo off
REM ResonantOS Dashboard Launcher for Windows

set PORT=19100
set HOST=127.0.0.1

echo.
echo ══════════════════════════════════════════════════════════════
echo              ResonantOS Dashboard
echo              Starting on http://%HOST%:%PORT%
echo ══════════════════════════════════════════════════════════════
echo.

set RESONANTOS_STATIC=%~dp0static
set RESONANTOS_TEMPLATES=%~dp0templates
set RESONANTOS_DATA=%~dp0data

dashboard.exe --port %PORT% --host %HOST% --dist

pause
SCRIPT
echo "   ✓ Created start.bat"

# Step 5: Create README
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📖 Step 5: Creating documentation..."
echo "═══════════════════════════════════════════════════════════════"

cat > "$DIST_DIR/$PACKAGE_NAME/README.md" << 'README'
# ResonantOS Dashboard

A self-hosted AI chatbot management platform.

## Quick Start

### Linux/macOS:
```bash
./start.sh
```

### Windows:
```
start.bat
```

Then open http://localhost:19100 in your browser.

## Configuration

Edit `start.sh` or set environment variables:
- `PORT` - Server port (default: 19100)
- `HOST` - Bind address (default: 127.0.0.1, use 0.0.0.0 for network access)

## Data

All your data is stored in `data/chatbots.db`. Back this up regularly.

## Support

Visit https://resonantos.com for documentation and support.

## License

This software is proprietary. See LICENSE for terms.
README

echo "   ✓ Created README.md"

# Create LICENSE
cat > "$DIST_DIR/$PACKAGE_NAME/LICENSE" << 'LICENSE'
ResonantOS Dashboard - Proprietary License

Copyright (c) 2024-2026 ResonantOS. All rights reserved.

This software is proprietary and confidential. Unauthorized copying,
modification, distribution, or use of this software, in whole or in part,
is strictly prohibited.

The software is provided "as is", without warranty of any kind.

For licensing inquiries: hello@resonantos.com
LICENSE

echo "   ✓ Created LICENSE"

# Step 6: Create ZIP package
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📦 Step 6: Creating distribution package..."
echo "═══════════════════════════════════════════════════════════════"

cd "$DIST_DIR"
zip -r "$PACKAGE_NAME.zip" "$PACKAGE_NAME" -x "*.DS_Store" -x "*__pycache__*"

echo "   ✓ Created $PACKAGE_NAME.zip"

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    BUILD COMPLETE!                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📦 Package: $DIST_DIR/$PACKAGE_NAME.zip"
echo ""
echo "Contents:"
ls -lh "$DIST_DIR/$PACKAGE_NAME/"
echo ""
echo "Package size: $(du -h "$DIST_DIR/$PACKAGE_NAME.zip" | cut -f1)"
echo ""
echo "🚀 To test locally:"
echo "   cd $DIST_DIR/$PACKAGE_NAME && ./start.sh"
echo ""
echo "📤 To distribute:"
echo "   Share $DIST_DIR/$PACKAGE_NAME.zip with users"
