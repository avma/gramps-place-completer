#!/bin/sh
# Usage: sh tools/setup_gramps_versions.sh [DIR]     (default DIR: ~/gramps-test)
# Installs the three Gramps versions that the tests run against, each in its own folder (needs the network once):
#   DIR/site608  Gramps 6.0.8 (from PyPI)
#   DIR/site61b2 Gramps 6.1 beta 2 (git tag v6.1.0-beta2)
#   DIR/sitemaster Gramps master (git, shallow)
# The 6.1 sources are built by pip and need `msgfmt` (package gettext). Run it again to refresh: an existing folder is kept.
set -e
DIR="${1:-$HOME/gramps-test}"
mkdir -p "$DIR"
command -v msgfmt >/dev/null || { echo "msgfmt is missing: install the package gettext first"; exit 1; }
[ -d "$DIR/site608" ] || pip install --no-deps --break-system-packages --target "$DIR/site608" gramps==6.0.8
for pair in "site61b2 v6.1.0-beta2" "sitemaster master"; do
  set -- $pair
  [ -d "$DIR/$1" ] && continue
  rm -rf "$DIR/src-$1"
  if [ "$2" = master ]; then git clone -q --depth 1 https://github.com/gramps-project/gramps.git "$DIR/src-$1"
  else git clone -q --depth 1 --branch "$2" https://github.com/gramps-project/gramps.git "$DIR/src-$1"; fi
  pip install --no-deps --break-system-packages --target "$DIR/$1" "$DIR/src-$1"
done
echo "Ready in $DIR. Run: sh tools/check_all.sh $DIR"
