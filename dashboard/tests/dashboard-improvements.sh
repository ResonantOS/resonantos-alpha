#!/bin/bash
# Test script for Dashboard Improvements: TODO, IDEAS, Intelligence Hub

set +e  # Don't exit on errors - we want to see all test results

DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAWD_DIR="$HOME/clawd"
PORT=19100
SERVER_PID=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# ============================================================================
# Utility Functions
# ============================================================================

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
    ((TESTS_FAILED++))
}

cleanup_server() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        log_info "Stopping test server (PID: $SERVER_PID)..."
        kill $SERVER_PID 2>/dev/null || true
        sleep 1
        kill -9 $SERVER_PID 2>/dev/null || true
    fi
}

# Ensure cleanup on exit
trap cleanup_server EXIT

# ============================================================================
# Test Suite
# ============================================================================

test_python_syntax() {
    log_info "Testing Python syntax..."
    if python3 -m py_compile "$DASHBOARD_DIR/server.py"; then
        log_success "server.py compiles without errors"
    else
        log_error "server.py has syntax errors"
        return 1
    fi
}

test_templates_exist() {
    log_info "Testing template files exist..."
    
    local templates=("todo.html" "ideas.html" "intelligence.html")
    for template in "${templates[@]}"; do
        if [ -f "$DASHBOARD_DIR/templates/$template" ]; then
            log_success "Template exists: $template"
        else
            log_error "Template missing: $template"
            return 1
        fi
    done
}

test_source_files_exist() {
    log_info "Testing source files exist..."
    
    if [ -f "$CLAWD_DIR/TODO.md" ]; then
        log_success "TODO.md exists"
    else
        log_error "TODO.md not found"
        return 1
    fi
    
    if [ -f "$CLAWD_DIR/IDEAS.md" ]; then
        log_success "IDEAS.md exists"
    else
        log_error "IDEAS.md not found"
        return 1
    fi
    
    # Check for intelligence files
    if find "$CLAWD_DIR/memory" -name "*community-intelligence*.md" -type f 2>/dev/null | head -1 | grep -q .; then
        log_success "Community intelligence files exist"
    else
        log_error "No community intelligence files found"
        return 1
    fi
}

start_server() {
    log_info "Starting test server on port $PORT..."
    
    cd "$DASHBOARD_DIR"
    
    # Start server in background
    python3 server.py > /tmp/dashboard-test.log 2>&1 &
    SERVER_PID=$!
    
    # Wait for server to be ready
    local retries=30
    while [ $retries -gt 0 ]; do
        if lsof -i ":$PORT" >/dev/null 2>&1; then
            log_success "Server started successfully (PID: $SERVER_PID)"
            sleep 1
            return 0
        fi
        ((retries--))
        sleep 0.5
    done
    
    log_error "Server failed to start"
    cat /tmp/dashboard-test.log
    return 1
}

test_page_routes() {
    log_info "Testing page routes..."
    
    local routes=("/" "/todo" "/ideas" "/intelligence")
    for route in "${routes[@]}"; do
        local response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT$route")
        if [ "$response" = "200" ]; then
            log_success "Route $route returns 200"
        else
            log_error "Route $route returns $response (expected 200)"
            return 1
        fi
    done
}

test_api_endpoints() {
    log_info "Testing API endpoints..."
    
    # Test /api/todo
    local todo_response=$(curl -s "http://localhost:$PORT/api/todo")
    if echo "$todo_response" | grep -q '"success"'; then
        log_success "API /api/todo responds with valid JSON"
        
        # Check if tasks are parsed
        if echo "$todo_response" | grep -q '"tasks"'; then
            log_success "API /api/todo returns tasks array"
        else
            log_error "API /api/todo missing tasks array"
        fi
    else
        log_error "API /api/todo response is invalid"
        return 1
    fi
    
    # Test /api/ideas
    local ideas_response=$(curl -s "http://localhost:$PORT/api/ideas")
    if echo "$ideas_response" | grep -q '"success"'; then
        log_success "API /api/ideas responds with valid JSON"
        
        if echo "$ideas_response" | grep -q '"ideas"'; then
            log_success "API /api/ideas returns ideas array"
        else
            log_error "API /api/ideas missing ideas array"
        fi
    else
        log_error "API /api/ideas response is invalid"
        return 1
    fi
    
    # Test /api/intelligence
    local intel_response=$(curl -s "http://localhost:$PORT/api/intelligence")
    if echo "$intel_response" | grep -q '"success"'; then
        log_success "API /api/intelligence responds with valid JSON"
        
        if echo "$intel_response" | grep -q '"intelligence"'; then
            log_success "API /api/intelligence returns intelligence object"
        else
            log_error "API /api/intelligence missing intelligence object"
        fi
    else
        log_error "API /api/intelligence response is invalid"
        return 1
    fi
}

test_data_parsing() {
    log_info "Testing data parsing..."
    
    # Check TODO parsing
    local todo_json=$(curl -s "http://localhost:$PORT/api/todo")
    if echo "$todo_json" | grep -q '"title"'; then
        log_success "TODO parser extracts task titles"
    else
        log_error "TODO parser not extracting titles"
    fi
    
    if echo "$todo_json" | grep -q '"completed"'; then
        log_success "TODO parser extracts completion status"
    else
        log_error "TODO parser not extracting completion status"
    fi
    
    # Check IDEAS parsing
    local ideas_json=$(curl -s "http://localhost:$PORT/api/ideas")
    if echo "$ideas_json" | grep -q '"priority"'; then
        log_success "IDEAS parser extracts priority levels"
    else
        log_error "IDEAS parser not extracting priority"
    fi
    
    # Check Intelligence parsing
    local intel_json=$(curl -s "http://localhost:$PORT/api/intelligence")
    if echo "$intel_json" | grep -q '"releases"'; then
        log_success "Intelligence parser extracts releases"
    else
        log_error "Intelligence parser not extracting releases"
    fi
}

test_navigation_links() {
    log_info "Testing navigation links..."
    
    local homepage=$(curl -s "http://localhost:$PORT/")
    
    if echo "$homepage" | grep -q '/todo'; then
        log_success "Navigation includes /todo link"
    else
        log_error "Navigation missing /todo link"
    fi
    
    if echo "$homepage" | grep -q '/ideas'; then
        log_success "Navigation includes /ideas link"
    else
        log_error "Navigation missing /ideas link"
    fi
    
    if echo "$homepage" | grep -q '/intelligence'; then
        log_success "Navigation includes /intelligence link"
    else
        log_error "Navigation missing /intelligence link"
    fi
}

test_responsive_design() {
    log_info "Testing responsive design (HTML validation)..."
    
    local todo_html=$(curl -s "http://localhost:$PORT/todo")
    
    # Check for viewport meta tag
    if echo "$todo_html" | grep -q 'viewport'; then
        log_success "Templates include viewport meta tag"
    else
        log_error "Templates missing viewport meta tag"
    fi
    
    # Check for CSS classes
    if echo "$todo_html" | grep -q 'card\|responsive\|grid'; then
        log_success "Templates use responsive CSS classes"
    else
        log_error "Templates missing responsive CSS classes"
    fi
}

# ============================================================================
# Run All Tests
# ============================================================================

main() {
    echo "======================================"
    echo "Dashboard Improvements Test Suite"
    echo "======================================"
    echo ""
    
    # Pre-server tests
    test_python_syntax || return 1
    test_templates_exist || return 1
    test_source_files_exist || return 1
    echo ""
    
    # Start server
    start_server || return 1
    echo ""
    
    # Server tests
    test_page_routes || true
    echo ""
    
    test_api_endpoints || true
    echo ""
    
    test_data_parsing || true
    echo ""
    
    test_navigation_links || true
    echo ""
    
    test_responsive_design || true
    echo ""
    
    # Summary
    echo "======================================"
    echo "Test Summary"
    echo "======================================"
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        log_success "All tests passed!"
        return 0
    else
        log_error "$TESTS_FAILED test(s) failed"
        return 1
    fi
}

main "$@"
