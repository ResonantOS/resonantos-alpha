#!/bin/bash
# Dashboard watchdog — restarts server_v2.py if it's not responding
DASHBOARD_DIR="/Users/augmentor/resonantos-augmentor/dashboard"
LOG="/tmp/dashboard.log"
PIDFILE="/tmp/dashboard.pid"

# Check if dashboard responds
if curl -s -o /dev/null -w "" --max-time 5 http://127.0.0.1:19100/ 2>/dev/null; then
    exit 0
fi

# Not responding — kill any zombie process
pkill -9 -f "python3.*server_v2.py" 2>/dev/null
sleep 2

# Start fresh
cd "$DASHBOARD_DIR"
nohup python3 server_v2.py >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "$(date -Iseconds) Dashboard restarted (pid $!)" >> "$LOG"
