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
"""List the texts of the addon that a user reads (the first argument of _(...), tr(...) and _need(out, ...), and a few fixed names), as
po/template.pot. Run it after adding a text:   python3 tools/extract_strings.py   then add the translation to po/he-local.po"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["PlaceCompleter.gpr.py", "placecompleter_tool.py", "placecompleter_gramplet.py", "placecompleter_quickview.py"] + \
    sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "placecompleter", "*.py")))
# words shown from data, not written as a text in the code
EXTRA = ["CONFLICTS WITH SAVED RESPONSE: text is IDENTICAL to response saved for %s. AI returned static text across "
         "different dates; name and type accuracy cannot be verified", "assumption", "evidence", "CONFLICT"]


def extract(files=None):
    """{msgid: ['file:line', ...]} in the order found."""
    found = {}
    for rel in files or FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            args = node.args
            if name in ("_", "tr") and args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                found.setdefault(args[0].value, []).append("%s:%d" % (rel, node.lineno))
            elif name in ("_need", "_note") and len(args) >= 2 and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
                found.setdefault(args[1].value, []).append("%s:%d" % (rel, node.lineno))
    for word in EXTRA:
        found.setdefault(word, ["(shown from data)"])
    found.pop("", None)
    return found


def quote(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def write_pot(found, path):
    out = ['# Place Completer: the texts to translate. Made by tools/extract_strings.py; do not edit.', 'msgid ""', 'msgstr ""',
           '"Content-Type: text/plain; charset=UTF-8\\n"', ""]
    for msgid, where in found.items():
        out += ["#: " + " ".join(where[:3]), "msgid " + quote(msgid), 'msgstr ""', ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


if __name__ == "__main__":
    found = extract()
    write_pot(found, os.path.join(ROOT, "po", "template.pot"))
    print("%d texts in po/template.pot" % len(found))
