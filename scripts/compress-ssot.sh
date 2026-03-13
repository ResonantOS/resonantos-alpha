#!/bin/bash
# SSoT Compression Agent
# Converts .md SSoT documents to .ai.md (AI-optimized, lossless, ~80% token savings)
# Uses Haiku 4.5 via Anthropic API (cheap, fast, stateless)
#
# Usage:
#   ./compress-ssot.sh <file.md>           # Compress single file
#   ./compress-ssot.sh --all               # Compress all SSoT docs
#   ./compress-ssot.sh --sync              # Only compress if .md is newer than .ai.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SSOT_DIR="$REPO_DIR/ssot"
MODEL="claude-haiku-4-5"

# Get API key from OpenClaw auth profiles
API_KEY=$(python3 -c "
import json
with open('$HOME/.openclaw/agents/main/agent/auth-profiles.json') as f:
    data = json.load(f)
profiles = data.get('profiles', data)
for k, v in profiles.items():
    if isinstance(v, dict) and v.get('provider') == 'anthropic' and v.get('token'):
        print(v['token'])
        break
" 2>/dev/null)

if [[ -z "${API_KEY:-}" ]]; then
    echo "ERROR: No Anthropic API key found in auth-profiles.json"
    exit 1
fi

call_haiku() {
    local prompt="$1"
    local content="$2"
    
    local response
    response=$(curl -s https://api.anthropic.com/v1/messages \
        -H "Content-Type: application/json" \
        -H "x-api-key: $API_KEY" \
        -H "anthropic-version: 2023-06-01" \
        -d "$(python3 -c "
import json, sys
print(json.dumps({
    'model': '$MODEL',
    'max_tokens': 4096,
    'messages': [{'role': 'user', 'content': sys.stdin.read()}]
}))
" <<< "$prompt

---

$content")")
    
    echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'content' in data:
    print(data['content'][0]['text'])
elif 'error' in data:
    print('ERROR: ' + data['error'].get('message', str(data['error'])), file=sys.stderr)
    sys.exit(1)
"
}

compress_file() {
    local src="$1"
    local basename="${src%.md}"
    local dest="${basename}.ai.md"
    local filename=$(basename "$src")
    
    # Skip .ai.md files
    if [[ "$src" == *.ai.md ]]; then
        return 0
    fi
    
    # Sync mode: skip if .ai.md is newer
    if [[ "${SYNC_MODE:-false}" == "true" ]] && [[ -f "$dest" ]] && [[ "$dest" -nt "$src" ]]; then
        echo "SKIP (up to date): $filename"
        return 0
    fi
    
    echo "COMPRESSING: $filename ..."
    
    local content
    content=$(cat "$src")
    
    # Step 1: Compress
    local compress_prompt="You are a lossless document compressor. Convert this document to AI-optimized format.

RULES:
1. LOSSLESS: Every fact, decision, parameter, name, date, and relationship MUST be preserved. Zero information loss.
2. FORMAT: Use tables, code blocks, key-value pairs, and terse labels. Never use prose or sentences where a table row works.
3. STRUCTURE: Keep the document hierarchy (headers). Remove all explanatory text, narrative, and filler.
4. HEADER: First line: # [TITLE] [AI-OPTIMIZED] then <!-- Tokens: ~NNN | Human version: $filename -->
5. NO OPINIONS: Do not add, interpret, or editorialize. Only compress what exists.
6. TARGET: ~80% token reduction from original.

Output ONLY the compressed document, nothing else."

    local compressed
    compressed=$(call_haiku "$compress_prompt" "$content")
    
    if [[ -z "$compressed" ]]; then
        echo "ERROR: Compression failed for $filename"
        return 1
    fi
    
    # Step 2: Audit
    echo "AUDITING: $filename ..."
    local audit_prompt="Compare ORIGINAL and COMPRESSED versions. Check for ANY information loss: missing facts, decisions, parameters, names, dates, relationships, or altered meaning.

If PERFECT (no loss): respond with exactly PASS
If ISSUES: respond with FAIL followed by the missing items, then provide the COMPLETE corrected compressed version."

    local audit_input="ORIGINAL:
$content

---

COMPRESSED:
$compressed"
    
    local audit_result
    audit_result=$(call_haiku "$audit_prompt" "$audit_input")
    
    if echo "$audit_result" | head -1 | grep -qi "^PASS"; then
        echo "$compressed" > "$dest"
    else
        echo "AUDIT: corrections needed, extracting..."
        # Try to extract corrected version from audit response
        local corrected
        corrected=$(echo "$audit_result" | sed -n '/^# /,$p')
        if [[ -n "$corrected" ]]; then
            echo "$corrected" > "$dest"
        else
            echo "$compressed" > "$dest"
            echo "WARNING: Using original compression (couldn't extract corrected version)"
        fi
    fi
    
    # Stats
    local orig_chars=$(wc -c < "$src" | tr -d ' ')
    local comp_chars=$(wc -c < "$dest" | tr -d ' ')
    local orig_tokens=$(( orig_chars / 4 ))
    local comp_tokens=$(( comp_chars / 4 ))
    local savings=0
    if [[ $orig_tokens -gt 0 ]]; then
        savings=$(( 100 - (comp_tokens * 100 / orig_tokens) ))
    fi
    
    echo "DONE: $filename → $(basename "$dest") | ~${orig_tokens}→~${comp_tokens} tokens (~${savings}% saved)"
    echo ""
}

# Parse args
SYNC_MODE="false"
FILES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sync) SYNC_MODE="true"; shift ;;
        --all) 
            while IFS= read -r f; do
                FILES+=("$f")
            done < <(find "$SSOT_DIR" -name "*.md" ! -name "*.ai.md" -type f | sort)
            shift ;;
        *) FILES+=("$1"); shift ;;
    esac
done

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "Usage: compress-ssot.sh [--sync] <file.md|--all>"
    exit 1
fi

echo "=== SSoT Compression Agent (Haiku 4.5) ==="
echo "Files: ${#FILES[@]}"
echo ""

for f in "${FILES[@]}"; do
    compress_file "$f"
done

echo "=== Complete ==="
