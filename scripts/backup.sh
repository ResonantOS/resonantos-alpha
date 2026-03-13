#!/bin/bash
# ResonantOS Backup Script
# Backs up critical data using Restic

set -e

# Configuration
RESTIC_REPO="/Users/augmentor/backups/restic"
RESTIC_PASSWORD_FILE="/Users/augmentor/.guardian/restic_password.txt"
LOG_FILE="/Users/augmentor/.clawdbot/logs/backup.log"

# Export password
export RESTIC_PASSWORD=$(cat "$RESTIC_PASSWORD_FILE")

# Timestamp
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting backup" >> "$LOG_FILE"

# Directories to back up
BACKUP_DIRS=(
    "/Users/augmentor/clawd"                    # All agent workspaces and projects
    "/Users/augmentor/.clawdbot"                # Clawdbot config and sessions
    "/Users/augmentor/.guardian"                # Guardian state and credentials
    "/Users/augmentor/clawd/memory"             # Memory databases (RAW, graph)
)

# Run backup
restic backup \
    --repo "$RESTIC_REPO" \
    --exclude "*.log" \
    --exclude "node_modules" \
    --exclude "__pycache__" \
    --exclude ".git/objects" \
    --exclude "*.pyc" \
    "${BACKUP_DIRS[@]}" \
    >> "$LOG_FILE" 2>&1

# Prune old backups (keep 7 daily, 4 weekly, 3 monthly)
restic forget \
    --repo "$RESTIC_REPO" \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 3 \
    --prune \
    >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup complete" >> "$LOG_FILE"
