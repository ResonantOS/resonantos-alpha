#!/usr/bin/env python3
"""
ResonantOS Watchdog Service
Monitors OpenClaw gateway, dashboard, logician, and shield-gate services.
Auto-restarts services if down (up to 3 attempts).
Logs all actions to watchdog.log.
Runs every 2 minutes via launchd.
"""

import subprocess
import time
import os
from datetime import datetime

# Configuration
LOG_FILE = "/Users/augmentor/resonantos-augmentor/watchdog/watchdog.log"
MAX_RESTART_ATTEMPTS = 3
CHECK_INTERVAL = 120  # 2 minutes

# Services to monitor
SERVICES = {
    "gateway": {
        "port": 18789,
        "process_pattern": "openclaw",
        "start_cmd": "openclaw gateway start",
    },
    "dashboard": {
        "port": 19100,
        "process_pattern": "server_v2.py",
        "start_cmd": "cd /Users/augmentor/resonantos-augmentor/dashboard && FLASK_ENV=development python3 server_v2.py",
    },
    "logician": {
        "port": 8080,
        "process_pattern": "mangle-server|daemon.py",
        "start_cmd": "cd /Users/augmentor/resonantos-augmentor/shield && python3 daemon.py",
    },
    "shield": {
        "port": None,
        "process_pattern": None,
        "log_file": "/Users/augmentor/resonantos-augmentor/shield/logs/shield-gate.log",
        "start_cmd": None,  # Shield runs inside gateway
    }
}

def log(message):
    """Log message to log file with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
    print(log_entry.strip())

def check_port(port):
    """Check if a port is in use."""
    if port is None:
        return False
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0 and str(port) in result.stdout
    except Exception as e:
        log(f"Error checking port {port}: {e}")
        return False

def check_process(process_pattern):
    """Check if a process is running."""
    if process_pattern is None:
        return False
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_pattern],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        log(f"Error checking process {process_pattern}: {e}")
        return False

def check_log_file(log_file):
    """Check if a log file exists and was recently modified (within last 5 minutes)."""
    if log_file is None:
        return False
    try:
        if not os.path.exists(log_file):
            return False
        # Check if file was modified within last 5 minutes
        mtime = os.path.getmtime(log_file)
        age_seconds = time.time() - mtime
        return age_seconds < 300  # 5 minutes
    except Exception as e:
        log(f"Error checking log file {log_file}: {e}")
        return False

def check_service(service_name):
    """Check if a service is running (port, process, or log file)."""
    service = SERVICES[service_name]
    
    # Check port if defined
    if service.get("port") and check_port(service["port"]):
        return True
    
    # Check process pattern if defined
    if service.get("process_pattern") and check_process(service["process_pattern"]):
        return True
    
    # Check log file if defined (for shield)
    if service.get("log_file") and check_log_file(service["log_file"]):
        return True
    
    return False

def restart_service(service_name):
    """Attempt to restart a service."""
    service = SERVICES[service_name]
    start_cmd = service.get("start_cmd")
    
    # Shield cannot be restarted independently (runs inside gateway)
    if start_cmd is None:
        log(f"Service {service_name} cannot be auto-restarted (runs inside gateway)")
        return False
    
    for attempt in range(1, MAX_RESTART_ATTEMPTS + 1):
        log(f"Attempting to restart {service_name} (attempt {attempt}/{MAX_RESTART_ATTEMPTS})")
        
        try:
            # For dashboard, we need to run in background
            if service_name == "dashboard":
                subprocess.Popen(
                    start_cmd,
                    shell=True,
                    cwd="/Users/augmentor/resonantos-augmentor/dashboard",
                    stdout=open("/dev/null", "w"),
                    stderr=open("/dev/null", "w")
                )
            else:
                subprocess.run(
                    start_cmd,
                    shell=True,
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # Wait a bit for service to start
            time.sleep(5)
            
            # Check if service is now running
            if check_service(service_name):
                log(f"Successfully restarted {service_name}")
                return True
            else:
                log(f"Service {service_name} still not responding after restart attempt {attempt}")
                
        except Exception as e:
            log(f"Error restarting {service_name}: {e}")
        
        time.sleep(2)
    
    log(f"FAILED to restart {service_name} after {MAX_RESTART_ATTEMPTS} attempts")
    return False

def main():
    """Main watchdog loop."""
    log("=" * 50)
    log("Watchdog service started")
    log("=" * 50)
    
    while True:
        try:
            for service_name in SERVICES:
                if not check_service(service_name):
                    log(f"Service {service_name} is DOWN")
                    restart_service(service_name)
                else:
                    log(f"Service {service_name} is UP")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log("Watchdog service stopped by user")
            break
        except Exception as e:
            log(f"Error in watchdog loop: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
