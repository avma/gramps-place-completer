#!/bin/sh
# Usage: sh tools/check_all.sh [DIR] [module ...]   (default DIR: ~/gramps-test, made by tools/setup_gramps_versions.sh)
# Runs tools/check.sh against Gramps 6.0.8, 6.1 beta 2 and master, one after the other, and prints one line per version.
cd "$(dirname "$0")/.." || exit 1
DIR="${1:-$HOME/gramps-test}"
[ $# -gt 0 ] && shift
bad=0
for v in site608 site61b2 sitemaster; do
  if [ ! -d "$DIR/$v" ]; then echo "$v: missing (run tools/setup_gramps_versions.sh)"; bad=1; continue; fi
  echo "=== $v"
  PYTHONPATH="$DIR/$v" GRAMPS_RESOURCES="$DIR/$v/share" sh tools/check.sh "$@" || bad=1
done
[ "$bad" -eq 0 ] && echo "ALL VERSIONS OK" || echo "SOME VERSION NOT OK"
exit $bad
