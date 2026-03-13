#!/bin/bash
#
# ResonantOS Dashboard Build Script
# Builds protected production bundle
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔨 ResonantOS Dashboard Builder"
echo "================================"
echo ""

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required. Please install it first."
    exit 1
fi

# Check for dependencies
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Parse arguments
DEV_MODE=""
if [ "$1" = "--dev" ]; then
    DEV_MODE="--dev"
    echo "⚡ Building in DEVELOPMENT mode (no obfuscation)"
else
    echo "🔒 Building in PRODUCTION mode (full obfuscation)"
fi
echo ""

# Build dashboard
echo "📦 Building Dashboard..."
node scripts/build-dashboard.js $DEV_MODE

echo ""

# Build runtime widget (always - this is the SaaS widget served from CDN)
echo "📦 Building Runtime Widget..."
node scripts/build-runtime-widget.js

# Build per-chatbot widgets (optional - legacy mode)
if [ "$2" = "--widgets" ]; then
    echo "📦 Building Widget Templates..."
    node scripts/build-widget.js --chatbot-id demo --tier free
    node scripts/build-widget.js --chatbot-id demo-pro --tier pro
fi

echo ""
echo "🎉 Build complete!"
echo ""
echo "To run in production mode:"
echo "  ./venv/bin/python server.py --dist"
echo ""
echo "Or deploy dist-dashboard/ to your production server."
