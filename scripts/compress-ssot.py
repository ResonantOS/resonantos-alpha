#!/usr/bin/env python3
"""
SSoT Compression Agent
Converts .md SSoT documents to .ai.md (AI-optimized, lossless, ~80% token savings)
Uses Haiku 4.5 via OpenClaw gateway sub-agent (cheap, fast, stateless)

Usage:
    python3 compress-ssot.py <file.md>       # Compress single file
    python3 compress-ssot.py --all           # Compress all SSoT docs  
    python3 compress-ssot.py --sync          # Only compress if .md newer than .ai.md
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_DIR = SCRIPT_DIR.parent
SSOT_DIR = REPO_DIR / "ssot"
MODEL = "anthropic/claude-haiku-4-5"

COMPRESS_PROMPT = """You are a lossless document compressor. Convert the document below to AI-optimized format.

RULES:
1. LOSSLESS: Every fact, decision, parameter, name, date, and relationship MUST be preserved. Zero information loss.
2. FORMAT: Use tables, code blocks, key-value pairs, and terse labels. Never use prose or sentences where a table row works.
3. STRUCTURE: Keep the document hierarchy (headers). Remove all explanatory text, narrative, and filler.
4. HEADER: First line: # [TITLE] [AI-OPTIMIZED] then <!-- Tokens: ~NNN | Human version: FILENAME -->
5. NO OPINIONS: Do not add, interpret, or editorialize. Only compress what exists.
6. TARGET: ~80% token reduction from original.

Output ONLY the compressed document, nothing else.

---

DOCUMENT TO COMPRESS (filename: FILENAME):

"""

AUDIT_PROMPT = """Compare ORIGINAL and COMPRESSED versions below. Check for ANY information loss: missing facts, decisions, parameters, names, dates, relationships, or altered meaning.

If PERFECT (no loss): respond with exactly PASS
If ISSUES: respond with FAIL followed by the missing items, then provide the COMPLETE corrected compressed version starting with # header.

---

"""


def call_model(prompt: str) -> str:
    """Call model via openclaw agent CLI through the gateway."""
    # Write prompt to temp file to avoid shell escaping issues
    tmp = Path("/tmp/ssot-compress-prompt.txt")
    tmp.write_text(prompt)

    result = subprocess.run(
        ["openclaw", "agent", "-m", f"@{tmp}", "--thinking", "off", "--json"],
        capture_output=True, text=True, timeout=180,
    )

    tmp.unlink(missing_ok=True)

    if result.returncode != 0:
        # Try parsing output anyway
        pass

    # Parse JSON response
    output = result.stdout.strip()
    # Find JSON in output (may have warnings before it)
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                return data.get("response", data.get("message", data.get("text", "")))
            except json.JSONDecodeError:
                continue

    # Fallback: try the whole output as JSON
    try:
        data = json.loads(output)
        return data.get("response", data.get("message", data.get("text", "")))
    except (json.JSONDecodeError, ValueError):
        # Return raw stdout as last resort
        return output


def compress_file(src: Path, sync_mode: bool = False):
    if src.suffix != ".md" or src.name.endswith(".ai.md"):
        return

    dest = src.with_suffix("").with_suffix(".ai.md")

    if sync_mode and dest.exists() and dest.stat().st_mtime > src.stat().st_mtime:
        print(f"SKIP (up to date): {src.name}")
        return

    print(f"COMPRESSING: {src.name} ...")
    content = src.read_text()

    # Step 1: Compress
    prompt = COMPRESS_PROMPT.replace("FILENAME", src.name) + content
    compressed = call_model(prompt)

    if not compressed:
        print(f"ERROR: Compression failed for {src.name}")
        return

    # Step 2: Audit
    print(f"AUDITING: {src.name} ...")
    audit_input = f"{AUDIT_PROMPT}ORIGINAL:\n{content}\n\n---\n\nCOMPRESSED:\n{compressed}"
    audit_result = call_model(audit_input)

    if audit_result.strip().upper().startswith("PASS"):
        dest.write_text(compressed)
    else:
        print(f"AUDIT: corrections needed ...")
        lines = audit_result.split("\n")
        corrected_start = None
        for i, line in enumerate(lines):
            if line.startswith("# "):
                corrected_start = i
                break
        if corrected_start is not None:
            corrected = "\n".join(lines[corrected_start:])
            dest.write_text(corrected)
        else:
            dest.write_text(compressed)
            print(f"WARNING: Using original compression (no corrected version found)")

    # Stats
    orig_tokens = len(content) // 4
    comp_tokens = len(dest.read_text()) // 4
    savings = 100 - (comp_tokens * 100 // orig_tokens) if orig_tokens > 0 else 0
    print(f"DONE: {src.name} → {dest.name} | ~{orig_tokens}→~{comp_tokens} tokens (~{savings}% saved)\n")


def main():
    args = sys.argv[1:]
    sync_mode = False
    files = []

    while args:
        arg = args.pop(0)
        if arg == "--sync":
            sync_mode = True
        elif arg == "--all":
            files.extend(sorted(SSOT_DIR.rglob("*.md")))
        else:
            files.append(Path(arg))

    files = [f for f in files if not f.name.endswith(".ai.md")]

    if not files:
        print("Usage: compress-ssot.py [--sync] <file.md|--all>")
        sys.exit(1)

    print(f"=== SSoT Compression Agent (via OpenClaw Gateway) ===")
    print(f"Files: {len(files)}\n")

    for f in files:
        try:
            compress_file(f, sync_mode)
        except Exception as e:
            print(f"ERROR on {f.name}: {e}\n")

    print("=== Complete ===")


if __name__ == "__main__":
    main()
