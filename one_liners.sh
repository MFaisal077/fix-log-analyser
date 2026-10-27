#!/usr/bin/env bash
# Quick checks on a FIX log from the command line: the first things to run
# when a firm calls with a problem, before opening any script.
#
# Usage: bash one_liners.sh data/sample_fix.log

LOG=${1:-data/sample_fix.log}

echo "== Messages by type (35=) =="
# grep -o prints only the matching part; sort + uniq -c counts each value
grep -o '|35=[^|]*' "$LOG" | sort | uniq -c | sort -rn

echo
echo "== Number of rejected orders (150=8) =="
grep -c '|150=8|' "$LOG"

echo
echo "== Reject reasons (58=) =="
grep '|150=8|' "$LOG" | grep -o '|58=[^|]*' | sort | uniq -c

echo
echo "== Rejects per firm (56= on messages sent to the firm) =="
grep '|150=8|' "$LOG" | grep -o '|56=[^|]*' | sort | uniq -c

echo
echo "== Everything about one order =="
grep 'FIRM3-0002' "$LOG"

echo
echo "== Total shares filled (sum of 32= on fill reports) =="
# -F'|' splits each line on "|"; the loop finds the 32= field and adds it up
grep -E '\|150=(1|2)\|' "$LOG" \
  | awk -F'|' '{ for (i = 1; i <= NF; i++) if ($i ~ /^32=/) { split($i, kv, "="); total += kv[2] } }
               END { print total }'

echo
echo "== Last 5 lines (in a live log, tail -f keeps watching for new ones) =="
tail -n 5 "$LOG"
