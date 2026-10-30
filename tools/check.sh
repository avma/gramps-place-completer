#!/bin/sh
# Usage: sh tools/check.sh [module ...]   Run the tests: all of them, or only the modules given (names without .py), and print one line per module and the total.
cd "$(dirname "$0")/.." || exit 1
modules="$*"
[ -z "$modules" ] && modules=$(ls tests/test_*.py | sed 's#tests/##; s#\.py$##')
total=0; bad=0
for m in $modules; do
  out=$(python3 -m unittest "tests.$m" 2>&1)
  n=$(echo "$out" | grep -E '^Ran ' | awk '{print $2}')
  status=$(echo "$out" | grep -E '^(OK|FAILED)' | tail -1)
  total=$((total + ${n:-0}))
  case "$status" in OK*) ;; *) bad=$((bad + 1)); echo "NOT OK $m: $status"; echo "$out" | grep -E '^(FAIL|ERROR):' | head -5 ;; esac
done
echo "TOTAL tests: $total, modules not OK: $bad"
[ "$bad" -eq 0 ]
