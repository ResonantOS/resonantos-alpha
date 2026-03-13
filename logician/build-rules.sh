#!/bin/bash
# Concatenates all .mg rule files into combined_rules.mg for Mangle
# Usage: ./build-rules.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PRODUCTION_FILE="$ROOT_DIR/poc/production_rules.mg"
OUTPUT_FILE="$ROOT_DIR/poc/combined_rules.mg"

TMP_PREDICATES="$(mktemp)"

awk '
  /^[[:space:]]*#/ { next }
  /^[[:space:]]*$/ { next }
  {
    if ($0 ~ /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\(/) {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      sub(/[[:space:]]*\(.*/, "", line)
      print line
    }
  }
' "$PRODUCTION_FILE" | sort -u > "$TMP_PREDICATES"

{
  echo "# Combined Rules - Auto-generated"
  echo
  cat "$PRODUCTION_FILE"

  for rule_file in "$ROOT_DIR"/rules/*.mg; do
    if [ "$(basename "$rule_file")" = "production_rules.mg" ]; then
      continue
    fi

    echo
    echo "# ---- rules/$(basename "$rule_file") ----"

    awk -v predicates_file="$TMP_PREDICATES" '
      BEGIN {
        while ((getline line < predicates_file) > 0) {
          production_predicate[line] = 1
        }
        close(predicates_file)
        skip_statement = 0
      }

      {
        if (skip_statement) {
          if ($0 ~ /\.[[:space:]]*$/) {
            skip_statement = 0
          }
          next
        }

        if ($0 ~ /^[[:space:]]*#/ || $0 ~ /^[[:space:]]*$/) {
          print $0
          next
        }

        if ($0 ~ /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\(/) {
          predicate_line = $0
          sub(/^[[:space:]]*/, "", predicate_line)
          sub(/[[:space:]]*\(.*/, "", predicate_line)
          predicate_name = predicate_line
          if (predicate_name in production_predicate) {
            if ($0 !~ /\.[[:space:]]*$/) {
              skip_statement = 1
            }
            next
          }
        }

        print $0
      }
    ' "$rule_file"
  done
} > "$OUTPUT_FILE"

rm -f "$TMP_PREDICATES"

echo "Generated $OUTPUT_FILE"
