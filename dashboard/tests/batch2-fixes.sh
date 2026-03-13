#!/bin/bash
# Test script for Batch 2 dashboard fixes
set -e

DASHBOARD_DIR="$HOME/clawd/projects/resonantos-v3/dashboard"
PORT=19100

echo "=== Batch 2 Dashboard Fixes Test ==="
echo ""

# Check Python syntax
echo "1. Checking Python syntax..."
python3 -m py_compile "$DASHBOARD_DIR/server.py"
echo "   ✅ Python syntax OK"

# Check that all templates exist
echo ""
echo "2. Checking templates..."
templates=("base.html" "index.html" "agents.html" "docs.html" "settings.html" "projects.html")
for t in "${templates[@]}"; do
    if [[ -f "$DASHBOARD_DIR/templates/$t" ]]; then
        echo "   ✅ $t exists"
    else
        echo "   ❌ $t MISSING"
        exit 1
    fi
done

# Check for specific fixes in code
echo ""
echo "3. Checking specific fixes..."

# #3 - Activity route
if grep -q "def activity_page" "$DASHBOARD_DIR/server.py"; then
    echo "   ✅ #3 Activity route exists"
else
    echo "   ❌ #3 Activity route missing"
    exit 1
fi

# #8 - Clickable filters
if grep -q "stat-item clickable" "$DASHBOARD_DIR/templates/agents.html"; then
    echo "   ✅ #8 Clickable agent filters exist"
else
    echo "   ❌ #8 Clickable agent filters missing"
    exit 1
fi

# #10 - See Also links (navigateToDoc function)
if grep -q "navigateToDoc" "$DASHBOARD_DIR/templates/docs.html"; then
    echo "   ✅ #10 See Also link navigation exists"
else
    echo "   ❌ #10 See Also link navigation missing"
    exit 1
fi

# #11 - Open in editor endpoint
if grep -q "api_docs_open_in_editor" "$DASHBOARD_DIR/server.py"; then
    echo "   ✅ #11 Open in editor endpoint exists"
else
    echo "   ❌ #11 Open in editor endpoint missing"
    exit 1
fi

# #12 - Semantic search
if grep -q "api_docs_search_semantic" "$DASHBOARD_DIR/server.py"; then
    echo "   ✅ #12 Semantic search endpoint exists"
else
    echo "   ❌ #12 Semantic search endpoint missing"
    exit 1
fi

# #17 - Reset settings confirmation
if grep -q "resetConfirmModal" "$DASHBOARD_DIR/templates/settings.html"; then
    echo "   ✅ #17 Reset settings confirmation exists"
else
    echo "   ❌ #17 Reset settings confirmation missing"
    exit 1
fi

# #23 - 12h and 90d time options
if grep -q "12h" "$DASHBOARD_DIR/templates/index.html" && grep -q "90d" "$DASHBOARD_DIR/templates/index.html"; then
    echo "   ✅ #23 12h and 90d time options exist"
else
    echo "   ❌ #23 12h and 90d time options missing"
    exit 1
fi

# #24 - Powered by link
if grep -q "resonantos.com" "$DASHBOARD_DIR/templates/base.html"; then
    echo "   ✅ #24 Powered by ResonantOS link exists"
else
    echo "   ❌ #24 Powered by ResonantOS link missing"
    exit 1
fi

# #26 - Projects tab
if [[ -f "$DASHBOARD_DIR/templates/projects.html" ]] && grep -q "def projects_page" "$DASHBOARD_DIR/server.py" && grep -q "api_projects" "$DASHBOARD_DIR/server.py"; then
    echo "   ✅ #26 Projects tab exists (template, route, API)"
else
    echo "   ❌ #26 Projects tab incomplete"
    exit 1
fi

# Check CSS additions
echo ""
echo "4. Checking CSS additions..."
css_checks=("projects-grid" "stat-item.clickable" "semantic-toggle" "confirm-input" "powered-by")
for check in "${css_checks[@]}"; do
    if grep -q "$check" "$DASHBOARD_DIR/static/css/dashboard.css"; then
        echo "   ✅ CSS: $check"
    else
        echo "   ❌ CSS missing: $check"
        exit 1
    fi
done

echo ""
echo "=== All Batch 2 Tests Passed ✅ ==="
