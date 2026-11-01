#!/usr/bin/env python3
#
# Place Completer - a Gramps tool that completes the hierarchy of a place
# from the answer of an AI (type, levels with years, coordinates)
#
# Copyright (C) 2026       Avi Markovitz <avi.markovitz@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""Check that the Gramps versions made by tools/setup_gramps_versions.sh can be imported, and name the Python package that is missing if one cannot.

Usage:
    python3 tools/check_gramps_import.py DIR

Gramps is installed there with --no-deps, so a library that Gramps needs when it is imported (orjson, for example) may be missing: then every test that touches Gramps fails
with an error that is far from the cause. This prints one line per version (`ok`, or the name of the missing package and the command that installs it) and exits 1 if one is not ok.
It runs each version in a process of its own, with an empty home folder for Gramps, so nothing of the user's is read or written."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os
import subprocess
import sys
import tempfile

VERSIONS = ("site608", "site61b2", "sitemaster")
PROBE = ("import sys\n"
         "try:\n"
         "    import gramps.gen.lib, gramps.gen.db.utils, gramps.gen.display.place\n"
         "except ModuleNotFoundError as e:\n"
         "    print(\"MISSING \" + str(e.name))\n"
         "    sys.exit(2)\n"
         "except Exception as e:\n"
         "    print(\"FAILED \" + type(e).__name__ + \": \" + str(e))\n"
         "    sys.exit(3)\n"
         "print(\"OK\")\n")


def check_one(folder):
    """Return (True, '') when the version imports, else (False, the reason in a line)."""
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, PYTHONPATH=folder, GRAMPSHOME=home, GRAMPS_RESOURCES=os.path.join(folder, "share"), LANGUAGE="en")
        done = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, timeout=120)
    lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    if done.returncode == 0 and last == "OK":
        return True, ""
    if last.startswith("MISSING "):
        name = last.split(" ", 1)[1]
        return False, "missing Python package '%s' (install it: pip install --break-system-packages %s)" % (name, name)
    return False, last or (done.stderr.strip().splitlines() or ["no output"])[-1]


def main(argv):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1].strip())
        return 2
    bad = 0
    for version in VERSIONS:
        folder = os.path.join(argv[1], version)
        if not os.path.isdir(folder):
            print("%s: the folder is missing (run tools/setup_gramps_versions.sh)" % version)
            bad += 1
            continue
        good, why = check_one(folder)
        print("%s: %s" % (version, "ok" if good else why))
        bad += 0 if good else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
