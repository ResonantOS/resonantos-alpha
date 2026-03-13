#!/bin/bash
# Test script for widget preview fixes (#35-#40)
# Run from dashboard directory

cd "$(dirname "$0")/.."

echo "=== Widget Preview Test Suite ==="
echo ""

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo "✅ $name"
        PASS=$((PASS + 1))
    else
        echo "❌ $name"
        FAIL=$((FAIL + 1))
    fi
}

# Test 1: chatbot-preview.js exists
echo "--- File Structure ---"
check "#36 chatbot-preview.js exists" "test -f static/js/chatbot-preview.js"

# Test 2: Preview module has required functions
echo ""
echo "--- Preview Module Functions ---"
check "ChatbotPreview.init function" "grep -q 'function init' static/js/chatbot-preview.js"
check "ChatbotPreview.updateAllPreviews" "grep -q 'updateAllPreviews' static/js/chatbot-preview.js"
check "ChatbotPreview.setEditMode function" "grep -q 'function setEditMode' static/js/chatbot-preview.js"
check "ChatbotPreview.setCreateMode function" "grep -q 'function setCreateMode' static/js/chatbot-preview.js"
check "ChatbotPreview.toggleChat function" "grep -q 'function togglePreviewChat' static/js/chatbot-preview.js"

# Test 3: Position handling (#35)
echo ""
echo "--- #35 Position Handling ---"
check "Position state tracking" "grep -q \"position:.*'bottom-right'\" static/js/chatbot-preview.js"
check "Position event listeners" "grep -q 'input\[name=\"position\"\]' static/js/chatbot-preview.js"
check "Position CSS classes in template" "grep -q 'position-bottom-right' templates/chatbots.html"
check "Position CSS styles" "grep -q 'position-bottom-left' static/css/dashboard.css"
check "Position-bottom-right CSS" "grep -q '.preview-widget.position-bottom-right' static/css/dashboard.css"
check "Position-bottom-left CSS" "grep -q '.preview-widget.position-bottom-left' static/css/dashboard.css"

# Test 4: Live preview in Appearance tab (#36)
echo ""
echo "--- #36 Live Preview in Appearance Tab ---"
check "Appearance tab has preview container" "grep -q 'appearancePreviewContainer' templates/chatbots.html"
check "Appearance layout CSS" "grep -q '.appearance-layout' static/css/dashboard.css"
check "Deploy tab has preview container" "grep -q 'deployPreviewContainer' templates/chatbots.html"

# Test 5: Color changes (#37)
echo ""
echo "--- #37 Color Changes ---"
check "Primary color listener" "grep -q \"getElementById('primaryColor')\" static/js/chatbot-preview.js"
check "Background color listener" "grep -q \"getElementById('bgColor')\" static/js/chatbot-preview.js"
check "Text color listener" "grep -q \"getElementById('textColor')\" static/js/chatbot-preview.js"
check "Color applied to button" "grep -q 'button.style.backgroundColor' static/js/chatbot-preview.js"
check "Color CSS variables" "grep -q '\-\-chat-primary' static/css/dashboard.css"

# Test 6: Theme handling (#38)
echo ""
echo "--- #38 Theme Handling ---"
check "Theme state tracking" "grep -q \"theme:.*'dark'\" static/js/chatbot-preview.js"
check "Theme event listeners" "grep -q 'input\[name=\"theme\"\]' static/js/chatbot-preview.js"
check "Auto theme detection" "grep -q 'prefers-color-scheme' static/js/chatbot-preview.js"
check "Theme-dark CSS" "grep -q '.preview-widget.theme-dark' static/css/dashboard.css"
check "Theme-light CSS" "grep -q '.preview-widget.theme-light' static/css/dashboard.css"

# Test 7: Greeting updates (#39)
echo ""
echo "--- #39 Greeting Updates ---"
check "Greeting state tracking" "grep -q 'greeting:' static/js/chatbot-preview.js"
check "Greeting event listener" "grep -q \"getElementById('greeting')\" static/js/chatbot-preview.js"
check "Greeting element update" "grep -q 'preview-greeting' templates/chatbots.html"

# Test 8: Smart button labeling (#40)
echo ""
echo "--- #40 Smart Button Labeling ---"
check "Generate button has ID" "grep -q 'generateWidgetBtn' templates/chatbots.html"
check "Button label logic" "grep -q 'Save & Update' static/js/chatbot-preview.js"
check "isEditing state" "grep -q 'isEditing' static/js/chatbot-preview.js"
check "setEditMode updates button" "grep -q 'updateButtonLabel' static/js/chatbot-preview.js"

# Test 9: Script included in template
echo ""
echo "--- Integration ---"
check "chatbot-preview.js included in template" "grep -q 'chatbot-preview.js' templates/chatbots.html"
check "ChatbotPreview.init called" "grep -q 'ChatbotPreview.init()' templates/chatbots.html"

# Test 10: Server endpoint
echo ""
echo "--- Server Endpoints ---"
check "PUT endpoint returns id" "grep -q \"'id': chatbot_id\" server.py"

echo ""
echo "=== Results ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "✅ All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi
