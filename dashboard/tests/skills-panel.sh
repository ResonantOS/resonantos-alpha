#!/bin/bash
# Skills Panel Test Script
# Tests the Skills Panel tab functionality

# Don't exit on first error - we want to run all tests
# set -e

BASE_URL="${BASE_URL:-http://localhost:5000}"
PASSED=0
FAILED=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "==========================================="
echo "  Skills Panel Test Suite"
echo "==========================================="
echo "Base URL: $BASE_URL"
echo ""

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    FAILED=$((FAILED + 1))
}

warn() {
    echo -e "${YELLOW}! WARN${NC}: $1"
}

# Test 1: Skills page loads
echo "Test 1: Skills page loads"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/skills")
if [ "$RESPONSE" == "200" ]; then
    pass "Skills page returns 200"
else
    fail "Skills page returned $RESPONSE (expected 200)"
fi

# Test 2: Skills API returns data
echo ""
echo "Test 2: Skills API returns data"
SKILLS_DATA=$(curl -s "$BASE_URL/api/skills")

if echo "$SKILLS_DATA" | grep -q '"skills"'; then
    pass "Skills API returns skills array"
else
    fail "Skills API missing skills array"
fi

# Test 3: Mock data has expected skills count
echo ""
echo "Test 3: Mock data has expected skills count"
SKILLS_COUNT=$(echo "$SKILLS_DATA" | grep -o '"id"' | wc -l | tr -d ' ')

if [ "$SKILLS_COUNT" -ge 6 ]; then
    pass "Skills API returns $SKILLS_COUNT skills (expected 6+)"
else
    fail "Skills API returned only $SKILLS_COUNT skills (expected 6+)"
fi

# Test 4: Skills have required fields
echo ""
echo "Test 4: Skills have required fields"
MISSING_FIELDS=0

for field in "id" "name" "icon" "description" "categories" "cost" "status" "rating"; do
    if ! echo "$SKILLS_DATA" | grep -q "\"$field\""; then
        warn "Missing field: $field"
        MISSING_FIELDS=$((MISSING_FIELDS + 1))
    fi
done

if [ "$MISSING_FIELDS" -eq 0 ]; then
    pass "All required fields present in skills data"
else
    fail "Missing $MISSING_FIELDS required fields"
fi

# Test 5: Skills page contains filter bar
echo ""
echo "Test 5: Skills page contains filter elements"
PAGE_HTML=$(curl -s "$BASE_URL/skills")

if echo "$PAGE_HTML" | grep -q "skills-filter-bar"; then
    pass "Skills page has filter bar"
else
    fail "Skills page missing filter bar"
fi

# Test 6: Skills page has category tags
echo ""
echo "Test 6: Skills page has category tags"
CATEGORIES=("essential" "arena" "productivity" "security" "creative" "integrations")
MISSING_CATS=0

for cat in "${CATEGORIES[@]}"; do
    if ! echo "$PAGE_HTML" | grep -qi "$cat"; then
        warn "Missing category: $cat"
        MISSING_CATS=$((MISSING_CATS + 1))
    fi
done

if [ "$MISSING_CATS" -eq 0 ]; then
    pass "All category tags present"
else
    fail "Missing $MISSING_CATS category tags"
fi

# Test 7: Skills page has modal
echo ""
echo "Test 7: Skills page has detail modal"
if echo "$PAGE_HTML" | grep -q "skillModal"; then
    pass "Skills page has detail modal"
else
    fail "Skills page missing detail modal"
fi

# Test 8: Skills grid container exists
echo ""
echo "Test 8: Skills grid container exists"
if echo "$PAGE_HTML" | grep -q 'id="skillsGrid"'; then
    pass "Skills grid container present"
else
    fail "Skills grid container missing"
fi

# Test 9: Sort dropdown exists
echo ""
echo "Test 9: Sort dropdown exists"
if echo "$PAGE_HTML" | grep -q "sortSelect"; then
    pass "Sort dropdown present"
else
    fail "Sort dropdown missing"
fi

# Test 10: Free and Premium skills in mock data
echo ""
echo "Test 10: Free and Premium skills exist"
FREE_COUNT=$(echo "$SKILLS_DATA" | grep -c '"cost":"free"' || echo 0)
PREMIUM_COUNT=$(echo "$SKILLS_DATA" | grep -c '"cost":"premium"' || echo 0)

if [ "$FREE_COUNT" -gt 0 ] && [ "$PREMIUM_COUNT" -gt 0 ]; then
    pass "Both free ($FREE_COUNT) and premium ($PREMIUM_COUNT) skills exist"
else
    fail "Missing skill types (free: $FREE_COUNT, premium: $PREMIUM_COUNT)"
fi

# Test 11: Coming Soon skills exist
echo ""
echo "Test 11: Coming Soon skills exist"
COMING_SOON_COUNT=$(echo "$SKILLS_DATA" | grep -c '"status":"coming-soon"' || echo 0)

if [ "$COMING_SOON_COUNT" -gt 0 ]; then
    pass "Coming Soon skills exist ($COMING_SOON_COUNT)"
else
    fail "No Coming Soon skills found"
fi

# Test 12: Navigation includes Skills tab
echo ""
echo "Test 12: Navigation includes Skills tab"
if echo "$PAGE_HTML" | grep -q 'href="/skills"'; then
    pass "Skills nav link exists"
else
    fail "Skills nav link missing"
fi

# Summary
echo ""
echo "==========================================="
echo "  Test Results"
echo "==========================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
