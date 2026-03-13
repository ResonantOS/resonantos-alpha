#!/bin/bash
# Test script for Watchtower features (#19, #20, #21)

set -e

DASHBOARD_DIR="$HOME/clawd/projects/resonantos-v3/dashboard"
cd "$DASHBOARD_DIR"

echo "🧪 Testing Watchtower Features..."
echo ""

# Test 1: Session Timer in base.html
echo "Test 1: Session Timer in header..."
if grep -q "session-timer" templates/base.html && \
   grep -q "sessionCountdown" templates/base.html && \
   grep -q "sessionMenu" templates/base.html; then
    echo "  ✅ Session timer HTML present"
else
    echo "  ❌ Session timer HTML missing"
    exit 1
fi

# Test 2: Session Timer CSS
echo "Test 2: Session Timer CSS..."
if grep -q ".session-timer" static/css/dashboard.css && \
   grep -q ".timer-text.critical" static/css/dashboard.css; then
    echo "  ✅ Session timer CSS present"
else
    echo "  ❌ Session timer CSS missing"
    exit 1
fi

# Test 3: Session Timer JS
echo "Test 3: Session Timer JavaScript..."
if grep -q "SESSION_RESET_HOURS" static/js/dashboard.js && \
   grep -q "updateSessionCountdown" static/js/dashboard.js && \
   grep -q "toggleSessionMenu" static/js/dashboard.js; then
    echo "  ✅ Session timer JS present"
else
    echo "  ❌ Session timer JS missing"
    exit 1
fi

# Test 4: Kanban Board HTML
echo "Test 4: Kanban Board in index.html..."
if grep -q "kanban-board" templates/index.html && \
   grep -q "tasks-todo" templates/index.html && \
   grep -q "tasks-inprogress" templates/index.html && \
   grep -q "tasks-done" templates/index.html; then
    echo "  ✅ Kanban HTML present"
else
    echo "  ❌ Kanban HTML missing"
    exit 1
fi

# Test 5: Kanban CSS
echo "Test 5: Kanban Board CSS..."
if grep -q ".kanban-board" static/css/dashboard.css && \
   grep -q ".kanban-column" static/css/dashboard.css && \
   grep -q ".kanban-task" static/css/dashboard.css; then
    echo "  ✅ Kanban CSS present"
else
    echo "  ❌ Kanban CSS missing"
    exit 1
fi

# Test 6: Kanban JS (drag-drop)
echo "Test 6: Kanban JavaScript..."
if grep -q "loadTasks" static/js/dashboard.js && \
   grep -q "renderKanban" static/js/dashboard.js && \
   grep -q "setupKanbanDragDrop" static/js/dashboard.js && \
   grep -q "updateTaskStatus" static/js/dashboard.js; then
    echo "  ✅ Kanban JS present"
else
    echo "  ❌ Kanban JS missing"
    exit 1
fi

# Test 7: Activity Feed HTML (terminal style)
echo "Test 7: Activity Feed HTML..."
if grep -q "activity-feed" templates/index.html && \
   grep -q "activityFeed" templates/index.html && \
   grep -q "activityFilter" templates/index.html && \
   grep -q "autoScrollToggle" templates/index.html; then
    echo "  ✅ Activity Feed HTML present"
else
    echo "  ❌ Activity Feed HTML missing"
    exit 1
fi

# Test 8: Activity Feed CSS (terminal style)
echo "Test 8: Activity Feed CSS (terminal style)..."
if grep -q ".activity-feed" static/css/dashboard.css && \
   grep -q ".activity-log-line" static/css/dashboard.css && \
   grep -q ".log-time" static/css/dashboard.css && \
   grep -q "background: #0d1117" static/css/dashboard.css; then
    echo "  ✅ Activity Feed CSS (terminal style) present"
else
    echo "  ❌ Activity Feed CSS missing"
    exit 1
fi

# Test 9: Activity Feed JS
echo "Test 9: Activity Feed JavaScript..."
if grep -q "loadActivityFeed" static/js/dashboard.js && \
   grep -q "renderActivityFeed" static/js/dashboard.js && \
   grep -q "filterActivityFeed" static/js/dashboard.js; then
    echo "  ✅ Activity Feed JS present"
else
    echo "  ❌ Activity Feed JS missing"
    exit 1
fi

# Test 10: ISSUES.md updated
echo "Test 10: ISSUES.md updated..."
if grep -q "\[x\] \*\*#19\*\*" ISSUES.md && \
   grep -q "\[x\] \*\*#20\*\*" ISSUES.md && \
   grep -q "\[x\] \*\*#21\*\*" ISSUES.md; then
    echo "  ✅ ISSUES.md marked complete"
else
    echo "  ❌ ISSUES.md not updated"
    exit 1
fi

# Test 11: Template syntax validation
echo "Test 11: Template syntax..."
if ./venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
env.get_template('base.html')
env.get_template('index.html')
print('  ✅ Templates valid')
" 2>/dev/null; then
    :
else
    echo "  ❌ Template syntax error"
    exit 1
fi

echo ""
echo "========================================"
echo "✅ All 11 tests passed!"
echo "========================================"
echo ""
echo "Features implemented:"
echo "  #19 - Session Timer (header countdown)"
echo "  #20 - Tasks Kanban Board (3 columns + drag-drop)"
echo "  #21 - Activity Feed (terminal/log style)"
