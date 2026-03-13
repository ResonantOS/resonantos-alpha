#!/usr/bin/env python3
"""
Shield Daemon - 24/7 Security Monitoring Service

Provides:
- HTTP health check endpoint on localhost:9999
- Alert directory monitoring
- Graceful shutdown handling
- Comprehensive logging
"""

import os
import sys
import json
import time
import signal
import logging
import threading
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
HEALTH_PORT = 9999
HEALTH_HOST = "127.0.0.1"
ALERTS_DIR = Path.home() / "clawd" / "security" / "alerts"
LOGS_DIR = Path.home() / "clawd" / "security" / "logs"
LOG_FILE = LOGS_DIR / "shield_daemon.log"
PID_FILE = Path.home() / "clawd" / "security" / "shield" / "shield.pid"

# Ensure directories exist
ALERTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("shield")


class ShieldState:
    """Global state for the Shield daemon."""
    def __init__(self):
        self.start_time = datetime.now()
        self.alerts_processed = 0
        self.last_alert_time = None
        self.running = True
        self.health_server = None
        self.observer = None


state = ShieldState()


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoint."""
    
    def log_message(self, format, *args):
        # Suppress default HTTP logging, use our logger
        logger.debug(f"Health check: {args[0]}")
    
    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            uptime = (datetime.now() - state.start_time).total_seconds()
            response = {
                "status": "healthy",
                "service": "shield-daemon",
                "uptime_seconds": int(uptime),
                "alerts_processed": state.alerts_processed,
                "last_alert": state.last_alert_time.isoformat() if state.last_alert_time else None,
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response, indent=2).encode())
        
        elif self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Count alert files
            alert_files = list(ALERTS_DIR.glob("*.json"))
            response = {
                "pending_alerts": len(alert_files),
                "alerts_dir": str(ALERTS_DIR),
                "log_file": str(LOG_FILE)
            }
            self.wfile.write(json.dumps(response, indent=2).encode())
        
        else:
            self.send_response(404)
            self.end_headers()


class AlertHandler(FileSystemEventHandler):
    """Watches for new alert files in the alerts directory."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith(".json"):
            self.process_alert(event.src_path)
    
    def process_alert(self, filepath):
        """Process a new alert file."""
        try:
            with open(filepath, "r") as f:
                alert = json.load(f)
            
            state.alerts_processed += 1
            state.last_alert_time = datetime.now()
            
            severity = alert.get("severity", "UNKNOWN")
            alert_type = alert.get("type", "UNKNOWN")
            
            logger.warning(f"🚨 ALERT [{severity}] {alert_type}: {alert.get('message', 'No message')}")
            
            # Archive processed alert
            archive_dir = ALERTS_DIR / "processed"
            archive_dir.mkdir(exist_ok=True)
            
            archive_path = archive_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{Path(filepath).name}"
            Path(filepath).rename(archive_path)
            
            logger.info(f"Alert archived to {archive_path}")
            
        except Exception as e:
            logger.error(f"Error processing alert {filepath}: {e}")


def run_health_server():
    """Run the health check HTTP server."""
    try:
        server = HTTPServer((HEALTH_HOST, HEALTH_PORT), HealthHandler)
        state.health_server = server
        logger.info(f"Health endpoint listening on http://{HEALTH_HOST}:{HEALTH_PORT}/health")
        
        while state.running:
            server.handle_request()
            
    except Exception as e:
        logger.error(f"Health server error: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, shutting down gracefully...")
    state.running = False
    
    if state.health_server:
        state.health_server.shutdown()
    
    if state.observer:
        state.observer.stop()
        state.observer.join(timeout=5)
    
    # Remove PID file
    if PID_FILE.exists():
        PID_FILE.unlink()
    
    logger.info("Shield daemon stopped.")
    sys.exit(0)


def write_pid():
    """Write PID file for process tracking."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def main():
    """Main entry point for Shield daemon."""
    logger.info("=" * 50)
    logger.info("🛡️  Shield Daemon Starting")
    logger.info("=" * 50)
    
    # Write PID file
    write_pid()
    logger.info(f"PID: {os.getpid()}")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start alert directory watcher
    event_handler = AlertHandler()
    observer = Observer()
    observer.schedule(event_handler, str(ALERTS_DIR), recursive=False)
    observer.start()
    state.observer = observer
    logger.info(f"Monitoring alerts directory: {ALERTS_DIR}")
    
    # Process any existing alerts on startup
    existing_alerts = list(ALERTS_DIR.glob("*.json"))
    if existing_alerts:
        logger.info(f"Processing {len(existing_alerts)} existing alerts...")
        for alert_file in existing_alerts:
            event_handler.process_alert(str(alert_file))
    
    # Start health server in main thread
    logger.info("Shield daemon is now running.")
    run_health_server()


if __name__ == "__main__":
    main()
