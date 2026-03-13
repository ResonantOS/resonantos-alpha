#!/bin/bash
# Quick test for Dashboard Improvements

DASHBOARD_DIR="$HOME/clawd/projects/resonantos/dashboard"
CLAWD_DIR="$HOME/clawd"

echo "=== Dashboard Improvements Quick Test ==="
echo ""

# Test 1: Check templates exist
echo "✓ Checking templates..."
[ -f "$DASHBOARD_DIR/templates/todo.html" ] && echo "  ✓ todo.html exists" || echo "  ✗ todo.html missing"
[ -f "$DASHBOARD_DIR/templates/ideas.html" ] && echo "  ✓ ideas.html exists" || echo "  ✗ ideas.html missing"
[ -f "$DASHBOARD_DIR/templates/intelligence.html" ] && echo "  ✓ intelligence.html exists" || echo "  ✗ intelligence.html missing"
echo ""

# Test 2: Check source files exist
echo "✓ Checking source files..."
[ -f "$CLAWD_DIR/TODO.md" ] && echo "  ✓ TODO.md exists" || echo "  ✗ TODO.md missing"
[ -f "$CLAWD_DIR/IDEAS.md" ] && echo "  ✓ IDEAS.md exists" || echo "  ✗ IDEAS.md missing"
find "$CLAWD_DIR/memory" -name "*community-intelligence*.md" -type f 2>/dev/null | head -1 >/dev/null && echo "  ✓ Intelligence files exist" || echo "  ✗ Intelligence files missing"
echo ""

# Test 3: Check Python syntax
echo "✓ Checking Python syntax..."
python3 -m py_compile "$DASHBOARD_DIR/server.py" 2>&1 && echo "  ✓ server.py syntax is valid" || echo "  ✗ server.py has syntax errors"
echo ""

# Test 4: Check for new routes in base.html
echo "✓ Checking navigation links..."
grep -q '/todo' "$DASHBOARD_DIR/templates/base.html" && echo "  ✓ /todo link added" || echo "  ✗ /todo link missing"
grep -q '/ideas' "$DASHBOARD_DIR/templates/base.html" && echo "  ✓ /ideas link added" || echo "  ✗ /ideas link missing"
grep -q '/intelligence' "$DASHBOARD_DIR/templates/base.html" && echo "  ✓ /intelligence link added" || echo "  ✗ /intelligence link missing"
echo ""

# Test 5: Check for new routes in server.py
echo "✓ Checking server routes..."
grep -q '@app.route.*todo' "$DASHBOARD_DIR/server.py" && echo "  ✓ /todo route defined" || echo "  ✗ /todo route missing"
grep -q '@app.route.*ideas' "$DASHBOARD_DIR/server.py" && echo "  ✓ /ideas route defined" || echo "  ✗ /ideas route missing"
grep -q '@app.route.*intelligence' "$DASHBOARD_DIR/server.py" && echo "  ✓ /intelligence route defined" || echo "  ✗ /intelligence route missing"
echo ""

# Test 6: Check for API endpoints
echo "✓ Checking API endpoints..."
grep -q '@app.route.*api/todo' "$DASHBOARD_DIR/server.py" && echo "  ✓ /api/todo endpoint" || echo "  ✗ /api/todo endpoint missing"
grep -q '@app.route.*api/ideas' "$DASHBOARD_DIR/server.py" && echo "  ✓ /api/ideas endpoint" || echo "  ✗ /api/ideas endpoint missing"
grep -q '@app.route.*api/intelligence' "$DASHBOARD_DIR/server.py" && echo "  ✓ /api/intelligence endpoint" || echo "  ✗ /api/intelligence endpoint missing"
echo ""

# Test 7: Count task parsing logic
echo "✓ Checking parsing functions..."
grep -q 'def parse_todo_md' "$DASHBOARD_DIR/server.py" && echo "  ✓ parse_todo_md function exists" || echo "  ✗ parse_todo_md function missing"
grep -q 'def parse_ideas_md' "$DASHBOARD_DIR/server.py" && echo "  ✓ parse_ideas_md function exists" || echo "  ✗ parse_ideas_md function missing"
grep -q 'def parse_intelligence_md' "$DASHBOARD_DIR/server.py" && echo "  ✓ parse_intelligence_md function exists" || echo "  ✗ parse_intelligence_md function missing"
echo ""

echo "=== Quick Test Complete ==="
