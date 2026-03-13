#!/bin/bash
# YARA Rules Nightly Updater
# Pulls community YARA rules and merges with custom rules
# Runs via cron — zero API cost

set -euo pipefail

SHIELD_DIR="$(cd "$(dirname "$0")" && pwd)"
RULES_DIR="$SHIELD_DIR/rules"
COMMUNITY_DIR="$RULES_DIR/community"
LOG_FILE="$SHIELD_DIR/yara-update.log"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"
}

log "=== YARA Rules Update Started ==="

# Create community rules directory
mkdir -p "$COMMUNITY_DIR"

# 1. Pull YARA-Rules community repository (curated collection)
YARA_RULES_REPO="https://github.com/Yara-Rules/rules/archive/refs/heads/master.tar.gz"
TEMP_DIR=$(mktemp -d)

log "Downloading community YARA rules..."
if curl -sL "$YARA_RULES_REPO" -o "$TEMP_DIR/yara-rules.tar.gz" 2>>"$LOG_FILE"; then
    tar -xzf "$TEMP_DIR/yara-rules.tar.gz" -C "$TEMP_DIR" 2>>"$LOG_FILE"
    
    # Copy relevant rule categories
    CATEGORIES=("malware" "email" "exploit_kits" "crypto" "webshells")
    COPIED=0
    for cat in "${CATEGORIES[@]}"; do
        SRC="$TEMP_DIR/rules-master/$cat"
        if [ -d "$SRC" ]; then
            cp -r "$SRC" "$COMMUNITY_DIR/" 2>>"$LOG_FILE"
            COUNT=$(find "$SRC" -name "*.yar" -o -name "*.yara" | wc -l | tr -d ' ')
            COPIED=$((COPIED + COUNT))
        fi
    done
    log "Copied $COPIED community rule files"
else
    log "ERROR: Failed to download community rules"
fi

# 2. Pull abuse.ch YARA rules (threat intelligence)
ABUSE_CH_URL="https://yaraify-api.abuse.ch/download/yaraify-rules.zip"
if curl -sL "$ABUSE_CH_URL" -o "$TEMP_DIR/abuse-ch.zip" 2>>"$LOG_FILE"; then
    mkdir -p "$COMMUNITY_DIR/abuse-ch"
    unzip -qo "$TEMP_DIR/abuse-ch.zip" -d "$COMMUNITY_DIR/abuse-ch/" 2>>"$LOG_FILE" || true
    log "Updated abuse.ch rules"
else
    log "WARNING: Failed to download abuse.ch rules (non-critical)"
fi

# Cleanup
rm -rf "$TEMP_DIR"

# Count total rules
TOTAL=$(find "$RULES_DIR" -name "*.yar" -o -name "*.yara" | wc -l | tr -d ' ')
log "Total YARA rule files: $TOTAL"
log "=== YARA Rules Update Complete ==="
