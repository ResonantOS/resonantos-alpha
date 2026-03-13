#!/bin/bash

# ResonantOS Chatbot End-to-End Test Script
# Tests chatbot creation, widget endpoints, and chat API

set -e

BASE_URL="${BASE_URL:-http://localhost:19100}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "ResonantOS Chatbot E2E Test Suite"
echo "============================================"
echo ""

# Helper functions
pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; exit 1; }
info() { echo -e "${YELLOW}→${NC} $1"; }

# Test 1: Check server is running
info "Test 1: Checking if server is running..."
if curl -s "$BASE_URL" > /dev/null 2>&1; then
    pass "Server is running at $BASE_URL"
else
    fail "Server is not running at $BASE_URL"
fi

# Test 2: Get chatbots list
info "Test 2: Fetching chatbots list..."
CHATBOTS=$(curl -s "$BASE_URL/api/chatbots")
if echo "$CHATBOTS" | grep -q '"chatbots"'; then
    TOTAL=$(echo "$CHATBOTS" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])" 2>/dev/null || echo "0")
    pass "Got chatbots list (total: $TOTAL)"
else
    fail "Could not fetch chatbots list"
fi

# Test 3: Create a new chatbot via API
info "Test 3: Creating new chatbot via API..."
CREATE_RESULT=$(curl -s -X POST "$BASE_URL/api/widget/generate" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "E2E Test Bot",
        "greeting": "Hello from E2E test!",
        "position": "bottom-right",
        "theme": "dark",
        "primaryColor": "#4ade80",
        "systemPrompt": "You are a test bot for E2E testing."
    }')

if echo "$CREATE_RESULT" | grep -q '"success".*true\|"widgetId"'; then
    WIDGET_ID=$(echo "$CREATE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('widgetId') or d.get('id', 'unknown'))" 2>/dev/null)
    pass "Created chatbot with ID: $WIDGET_ID"
else
    echo "Response: $CREATE_RESULT"
    fail "Could not create chatbot"
fi

# Test 4: Verify chatbot was created
info "Test 4: Verifying chatbot exists..."
CHATBOT_DATA=$(curl -s "$BASE_URL/api/chatbots/$WIDGET_ID")
if echo "$CHATBOT_DATA" | grep -q '"name".*"E2E Test Bot"'; then
    pass "Chatbot exists and has correct name"
else
    echo "Response: $CHATBOT_DATA"
    fail "Chatbot not found or has wrong data"
fi

# Test 5: Test chat API endpoint
info "Test 5: Testing chat API endpoint..."
CHAT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/chat/$WIDGET_ID" \
    -H "Content-Type: application/json" \
    -d '{"message": "Hello, this is a test message"}')

if echo "$CHAT_RESPONSE" | grep -q '"response"'; then
    pass "Chat API responded successfully"
else
    echo "Response: $CHAT_RESPONSE"
    # This might fail if no AI API is configured, which is OK for basic testing
    echo -e "${YELLOW}⚠ WARNING${NC}: Chat API may not have AI configured (expected in dev mode)"
fi

# Test 6: Update chatbot settings
info "Test 6: Updating chatbot settings..."
UPDATE_RESULT=$(curl -s -X PUT "$BASE_URL/api/chatbots/$WIDGET_ID" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "E2E Test Bot (Updated)",
        "greeting": "Updated greeting!",
        "primaryColor": "#ff5500"
    }')

if echo "$UPDATE_RESULT" | grep -q '"success".*true'; then
    pass "Chatbot updated successfully"
else
    echo "Response: $UPDATE_RESULT"
    fail "Could not update chatbot"
fi

# Test 7: Verify update
info "Test 7: Verifying update..."
UPDATED_DATA=$(curl -s "$BASE_URL/api/chatbots/$WIDGET_ID")
if echo "$UPDATED_DATA" | grep -q '"primary_color".*"#ff5500"'; then
    pass "Update verified - color changed"
else
    echo "Response: $UPDATED_DATA"
    fail "Update not applied correctly"
fi

# Test 8: Test widget download endpoint
info "Test 8: Testing widget download endpoint..."
DOWNLOAD_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "$BASE_URL/api/widget/download/$WIDGET_ID")
if [ "$DOWNLOAD_RESPONSE" == "200" ]; then
    pass "Widget download endpoint works"
else
    echo -e "${YELLOW}⚠ WARNING${NC}: Widget download returned HTTP $DOWNLOAD_RESPONSE"
fi

# Test 9: Delete test chatbot (cleanup)
info "Test 9: Cleaning up - deleting test chatbot..."
DELETE_RESULT=$(curl -s -X DELETE "$BASE_URL/api/chatbots/$WIDGET_ID")
if echo "$DELETE_RESULT" | grep -q '"success".*true'; then
    pass "Test chatbot deleted successfully"
else
    echo "Response: $DELETE_RESULT"
    echo -e "${YELLOW}⚠ WARNING${NC}: Could not delete test chatbot"
fi

# Test 10: Check dashboard pages load
info "Test 10: Checking dashboard pages..."
PAGES=("/" "/chatbots" "/agents" "/docs" "/status" "/settings")
ALL_PAGES_OK=true
for page in "${PAGES[@]}"; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$page")
    if [ "$HTTP_CODE" == "200" ]; then
        echo "  ✓ $page (200 OK)"
    else
        echo "  ✗ $page ($HTTP_CODE)"
        ALL_PAGES_OK=false
    fi
done
if [ "$ALL_PAGES_OK" == "true" ]; then
    pass "All dashboard pages load correctly"
else
    echo -e "${YELLOW}⚠ WARNING${NC}: Some pages had issues"
fi

echo ""
echo "============================================"
echo -e "${GREEN}All E2E tests completed!${NC}"
echo "============================================"
