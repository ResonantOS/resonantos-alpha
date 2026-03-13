#!/bin/bash
# Test script for Chatbot Manager and License Server
# Run from: ~/clawd/projects/resonantos-v3/dashboard/

# Don't exit on error - we track test results ourselves

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
BASE_URL="http://127.0.0.1:19100"
PASS=0
FAIL=0

cd "$DASHBOARD_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================"
echo "ResonantOS Dashboard - Chatbot & License Tests"
echo "============================================"
echo ""

# Check if server is running
echo -n "Checking server status... "
if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}Server is running${NC}"
else
    echo -e "${YELLOW}Server not running. Starting...${NC}"
    ./venv/bin/python server.py --port 19100 &
    SERVER_PID=$!
    sleep 3
    
    if ! curl -s "$BASE_URL/health" > /dev/null 2>&1; then
        echo -e "${RED}Failed to start server${NC}"
        exit 1
    fi
fi

# Function to run a test
run_test() {
    local name="$1"
    local expected="$2"
    local result="$3"
    
    if [[ "$result" == *"$expected"* ]]; then
        echo -e "  ${GREEN}✓${NC} $name"
        ((PASS++))
    else
        echo -e "  ${RED}✗${NC} $name"
        echo "    Expected: $expected"
        echo "    Got: $result"
        ((FAIL++))
    fi
}

echo ""
echo "--- Test 1: API Endpoints Exist ---"

# Test /api/chatbots endpoint
result=$(curl -s "$BASE_URL/api/chatbots")
run_test "GET /api/chatbots returns JSON" "total" "$result"

# Test /api/license/features endpoint
result=$(curl -s "$BASE_URL/api/license/features")
run_test "GET /api/license/features returns features" "remove_watermark" "$result"

# Test /api/stripe/config endpoint
result=$(curl -s "$BASE_URL/api/stripe/config")
run_test "GET /api/stripe/config returns config" "publishableKey" "$result"

echo ""
echo "--- Test 2: Chatbot CRUD Operations ---"

# Create a chatbot
result=$(curl -s -X POST "$BASE_URL/api/widget/generate" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Test Bot",
        "greeting": "Hello from test!",
        "systemPrompt": "You are a test bot",
        "primaryColor": "#ff5500",
        "showWatermark": true
    }')
run_test "POST /api/widget/generate creates chatbot" "success" "$result"

# Extract widget ID
WIDGET_ID=$(echo "$result" | grep -o '"widgetId":"[^"]*' | cut -d'"' -f4)
if [ -n "$WIDGET_ID" ]; then
    echo "    Created widget ID: $WIDGET_ID"
    
    # Get chatbot
    result=$(curl -s "$BASE_URL/api/chatbots/$WIDGET_ID")
    run_test "GET /api/chatbots/:id returns chatbot" "Test Bot" "$result"
    
    # Update chatbot
    result=$(curl -s -X PUT "$BASE_URL/api/chatbots/$WIDGET_ID" \
        -H "Content-Type: application/json" \
        -d '{"name": "Updated Test Bot"}')
    run_test "PUT /api/chatbots/:id updates chatbot" "success" "$result"
    
    # Verify update
    result=$(curl -s "$BASE_URL/api/chatbots/$WIDGET_ID")
    run_test "Chatbot name was updated" "Updated Test Bot" "$result"
fi

echo ""
echo "--- Test 3: Chat API ---"

if [ -n "$WIDGET_ID" ]; then
    result=$(curl -s -X POST "$BASE_URL/api/chat/$WIDGET_ID" \
        -H "Content-Type: application/json" \
        -d '{"message": "Hello, testing!"}')
    run_test "POST /api/chat/:id returns response" "response" "$result"
fi

echo ""
echo "--- Test 4: Widget Generation ---"

if [ -n "$WIDGET_ID" ]; then
    # Test widget embed code generation
    result=$(curl -s "$BASE_URL/api/chatbots")
    run_test "Chatbot appears in list after creation" "Updated Test Bot" "$result"
    
    # Test widget download endpoint exists
    result=$(curl -s -w "%{http_code}" -o /dev/null "$BASE_URL/api/widget/download/$WIDGET_ID")
    run_test "GET /api/widget/download/:id returns 200" "200" "$result"
fi

echo ""
echo "--- Test 5: License System ---"

# Check license for user without one
result=$(curl -s -X POST "$BASE_URL/api/license/check" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test_user", "feature": "remove_watermark"}')
run_test "License check returns valid=false for free user" "\"valid\":false" "$result"

# Grant a test license
result=$(curl -s -X POST "$BASE_URL/api/license/grant" \
    -H "Content-Type: application/json" \
    -d '{
        "user_id": "test_user",
        "tier": "pro",
        "features": ["remove_watermark", "profile_pic"],
        "expires_days": 30
    }')
run_test "POST /api/license/grant creates license" "success" "$result"

# Check license again
result=$(curl -s -X POST "$BASE_URL/api/license/check" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test_user", "feature": "remove_watermark"}')
run_test "License check returns valid=true after grant" "\"valid\":true" "$result"

echo ""
echo "--- Test 6: Stripe Integration (Endpoints Only) ---"

# Test Stripe checkout endpoint (will fail without real keys, but should return proper error)
result=$(curl -s -X POST "$BASE_URL/api/stripe/checkout" \
    -H "Content-Type: application/json" \
    -d '{"feature": "remove_watermark", "user_id": "test"}')
# Should return error about Stripe not configured or create session
if [[ "$result" == *"error"* ]] || [[ "$result" == *"sessionId"* ]]; then
    run_test "POST /api/stripe/checkout responds correctly" "Stripe" "$result"
else
    run_test "POST /api/stripe/checkout responds correctly" "error or sessionId" "$result"
fi

echo ""
echo "--- Test 7: Settings API ---"

# Get settings
result=$(curl -s "$BASE_URL/api/settings")
run_test "GET /api/settings returns settings" "theme" "$result"

# Save settings
result=$(curl -s -X POST "$BASE_URL/api/settings" \
    -H "Content-Type: application/json" \
    -d '{"theme": "dark", "autoRefresh": true}')
run_test "POST /api/settings saves settings" "success" "$result"

echo ""
echo "--- Test 8: Database Schema ---"

# Check that chatbots database exists and has correct tables
if [ -f "chatbots.db" ]; then
    tables=$(sqlite3 chatbots.db ".tables" 2>/dev/null)
    run_test "chatbots table exists" "chatbots" "$tables"
    run_test "licenses table exists" "licenses" "$tables"
    run_test "chatbot_conversations table exists" "chatbot_conversations" "$tables"
    run_test "chatbot_messages table exists" "chatbot_messages" "$tables"
else
    echo -e "  ${YELLOW}!${NC} chatbots.db not found (created on first request)"
fi

echo ""
echo "============================================"
echo "Test Summary"
echo "============================================"
echo -e "Passed: ${GREEN}$PASS${NC}"
echo -e "Failed: ${RED}$FAIL${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
