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
"""Give every Python file of the addon the license header of Gramps, and the banners that Gramps puts above its imports.

Usage:
    python3 tools/add_headers.py [--holder "Name <address>"] [--year 2026] [--check]

--holder  who holds the copyright (default: Avi Markovitz <avi.markovitz@gmail.com>).
--year    the year of the copyright line (default 2026).
--check   change nothing: say which files lack the header or a banner, and exit 1 if there are any.

The header is the one of the files of Gramps (GNU General Public License, version 2 or later): a comment before the docstring of the file. The
banners are the three-line comments above the imports, one for each kind of module, in the order in which the file imports them:

    Standard python modules, GTK/Gnome modules, Gramps modules, Place Completer modules

A banner is written where the kind of the imports changes. Nothing is moved: the order of the imports is the one that the file has (some files
put the folder of the addon in the path between two imports, and the order matters). The files of the tests get the header only.
Running it twice changes nothing.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DASHES = "# " + "-" * 73
MARK = "# This program is free software; you can redistribute it and/or modify"

TEMPLATE = """#
# Place Completer - a Gramps tool that completes the hierarchy of a place
# from the answer of an AI (type, levels with years, coordinates)
#
# Copyright (C) {year}       {holder}
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
"""

STANDARD, GTK, GRAMPS, LOCAL, OTHER = ("Standard python modules", "GTK/Gnome modules", "Gramps modules", "Place Completer modules", "Other modules")
FOLDERS_WITH_BANNERS = ("placecompleter", "tools")
FILES_WITH_BANNERS = ("placecompleter_tool.py", "placecompleter_gramplet.py", "placecompleter_quickview.py", "placecompleter_open.py")


def banner(name):
    return [DASHES, "#", "# %s" % name, "#", DASHES]


def kind_of(node):
    """The kind of module that an import statement brings."""
    if isinstance(node, ast.ImportFrom):
        if node.level:
            return LOCAL
        root = (node.module or "").split(".")[0]
    else:
        root = node.names[0].name.split(".")[0]
    if root in sys.stdlib_module_names:
        return STANDARD
    if root == "gi":
        return GTK
    if root == "gramps":
        return GRAMPS
    if root.startswith("placecompleter") or root == "tests":
        return LOCAL
    return OTHER


def wants_banners(path):
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    return rel.split("/")[0] in FOLDERS_WITH_BANNERS or rel in FILES_WITH_BANNERS


def has_header(text):
    """Is the license header in the first lines? (a line that IS the first line of the notice; the same words inside a string do not count)"""
    return any(line.rstrip() == MARK for line in text.splitlines()[:40])


def header_lines(holder, year):
    return TEMPLATE.format(holder=holder, year=year).splitlines()


def add_header(lines, holder, year):
    """The lines with the header after the first line when that is a #! line (and before everything else)."""
    at = 1 if lines and lines[0].startswith("#!") else 0
    return lines[:at] + header_lines(holder, year) + lines[at:]


def banner_positions(text):
    """[(index of the line where a banner is to be written, name)] for the imports at the top level of the file that have no banner above them."""
    tree = ast.parse(text)
    lines = text.splitlines()
    wanted, previous = [], None
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        kind = kind_of(node)
        if kind != previous:
            above = [l.strip() for l in lines[max(0, node.lineno - 1 - 5):node.lineno - 1]]
            if "# %s" % kind not in above:
                wanted.append((node.lineno - 1, kind))
            previous = kind
    return wanted


def add_banners(text):
    lines = text.splitlines()
    for index, kind in sorted(banner_positions(text), reverse=True):
        block = banner(kind)
        if index > 0 and lines[index - 1].strip():
            block = [""] + block
        lines[index:index] = block
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def python_files():
    found = []
    for folder in ("placecompleter", "tools", "tests", "."):
        base = os.path.join(ROOT, folder)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if name.endswith(".py") and os.path.isfile(path) and (folder != "." or name.startswith(("placecompleter_", "PlaceCompleter", "deploy_"))):
                found.append(path)
    return found


def process(path, holder, year, check=False):
    """The new text of a file, and what was missing in it."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    missing = []
    out = text
    if not has_header(out):
        out = "\n".join(add_header(out.splitlines(), holder, year)) + ("\n" if out.endswith("\n") or not out else "")
        missing.append("header")
    if wants_banners(path) and not path.endswith(".gpr.py"):
        with_banners = add_banners(out)
        if with_banners != out:
            missing.append("banners")
            out = with_banners
    return out, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--holder", default="Avi Markovitz <avi.markovitz@gmail.com>")
    parser.add_argument("--year", default="2026")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    lacking = []
    for path in python_files():
        out, missing = process(path, args.holder, args.year)
        if not missing:
            continue
        lacking.append((os.path.relpath(path, ROOT), missing))
        if not args.check:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
    for name, missing in lacking:
        print("%s %s: %s" % ("lacks" if args.check else "fixed", name, ", ".join(missing)))
    print("%d files %s" % (len(lacking), "lack something" if args.check else "changed"))
    return 1 if (args.check and lacking) else 0


if __name__ == "__main__":
    sys.exit(main())
