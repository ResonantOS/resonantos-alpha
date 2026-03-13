#!/bin/bash
# Test script for crypto payment integration
# Verifies all components are properly implemented

cd "$(dirname "$0")/.."

PASS=0
FAIL=0

pass() {
    echo "✅ $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "❌ $1"
    FAIL=$((FAIL + 1))
}

echo "========================================"
echo "Crypto Payment Integration Tests"
echo "========================================"
echo ""

# Test 1: Check crypto-payment.js exists
echo "Test 1: crypto-payment.js exists..."
if [ -f "static/js/crypto-payment.js" ]; then
    pass "crypto-payment.js exists"
else
    fail "crypto-payment.js not found"
fi

# Test 2: Check crypto-payment.js has required functions
echo "Test 2: crypto-payment.js has required functions..."
if grep -q "function initCryptoPayment" static/js/crypto-payment.js && \
   grep -q "function showPaymentChoice" static/js/crypto-payment.js && \
   grep -q "function verifyTransaction" static/js/crypto-payment.js; then
    pass "All required functions present"
else
    fail "Missing required functions in crypto-payment.js"
fi

# Test 3: Check server.py has crypto endpoints
echo "Test 3: server.py has crypto endpoints..."
if grep -q "@app.route('/api/crypto/checkout'" server.py && \
   grep -q "@app.route('/api/crypto/verify'" server.py && \
   grep -q "@app.route('/api/crypto/status'" server.py; then
    pass "All crypto endpoints present in server.py"
else
    fail "Missing crypto endpoints in server.py"
fi

# Test 4: Check settings.html has subscription section
echo "Test 4: settings.html has subscription section..."
if grep -q "subscriptionSection" templates/settings.html && \
   grep -q "addons-grid" templates/settings.html && \
   grep -q "CryptoPayment.showChoice" templates/settings.html; then
    pass "Subscription section present in settings.html"
else
    fail "Missing subscription section in settings.html"
fi

# Test 5: Check settings.html includes crypto-payment.js
echo "Test 5: settings.html includes crypto-payment.js..."
if grep -q "crypto-payment.js" templates/settings.html; then
    pass "crypto-payment.js included in settings.html"
else
    fail "crypto-payment.js not included in settings.html"
fi

# Test 6: Check CSS has crypto payment styles
echo "Test 6: dashboard.css has crypto payment styles..."
if grep -q "addons-grid" static/css/dashboard.css && \
   grep -q "payment-amount" static/css/dashboard.css && \
   grep -q "payment-method-btn" static/css/dashboard.css; then
    pass "Crypto payment CSS styles present"
else
    fail "Missing crypto payment CSS styles"
fi

# Test 7: Check server.py has pricing configuration
echo "Test 7: server.py has pricing configuration..."
if grep -q "CRYPTO_CONFIG" server.py && \
   grep -q "'watermark'" server.py && \
   grep -q "'extra_bots_3'" server.py && \
   grep -q "'extra_bots_10'" server.py; then
    pass "Pricing configuration present"
else
    fail "Missing pricing configuration"
fi

# Test 8: Check server.py has CoinGecko integration
echo "Test 8: server.py has CoinGecko price integration..."
if grep -q "coingecko.com" server.py && \
   grep -q "get_sol_price" server.py; then
    pass "CoinGecko price integration present"
else
    fail "Missing CoinGecko integration"
fi

# Test 9: Check server.py has database table creation
echo "Test 9: server.py has crypto_payments table..."
if grep -q "crypto_payments" server.py && \
   grep -q "CREATE TABLE IF NOT EXISTS" server.py; then
    pass "Database table creation present"
else
    fail "Missing database table creation"
fi

# Test 10: Python syntax check
echo "Test 10: Python syntax check..."
if python3 -m py_compile server.py 2>/dev/null; then
    pass "server.py has valid Python syntax"
else
    fail "server.py has syntax errors"
fi

# Test 11: JavaScript syntax check (basic)
echo "Test 11: JavaScript syntax check..."
if node -c static/js/crypto-payment.js 2>/dev/null; then
    pass "crypto-payment.js has valid JavaScript syntax"
else
    fail "crypto-payment.js has syntax errors"
fi

# Test 12: Check add-ons API endpoint
echo "Test 12: server.py has /api/addons endpoint..."
if grep -q "@app.route('/api/addons')" server.py; then
    pass "/api/addons endpoint present"
else
    fail "Missing /api/addons endpoint"
fi

echo ""
echo "========================================"
echo "Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi

exit 0
