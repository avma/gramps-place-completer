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
"""Make the PO files of the texts of the addon for editing in Poedit, and check them when they come back.

Usage:
    python3 tools/po_exchange.py make [--out DIR]
    python3 tools/po_exchange.py check FILE [FILE ...]

make    writes two files into DIR (default ~/gramps-place-work/po-exchange):
          placecompleter-he.po       each English text and its Hebrew: edit the Hebrew in the translation box;
          placecompleter-en-edit.po  each English text and, in the translation box, the same English: change it there where the English is to be corrected.
        Each text has the places where it is used, and what each %s or %d stands for when the code says it.
check   looks at a file that came back from Poedit and says what is wrong: a %s or %d that was lost or added, a line break that was lost, a space that was
        added or removed at the beginning or the end (some texts are pieces of a sentence that the program joins), a text that is still empty or still English
        (the Hebrew file), and which English texts were changed (the English file). Exit code 1 when something is wrong.

Why two files: a PO file has one box for each text. The English is the source; to correct it in Poedit it is put in the box of a second file, and the program
carries the correction to the code, and the Hebrew of that text with it.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = re.compile(r"%\([a-z_]+\)[sdf]|%[.0-9]*[sdfr]")
HEADER = ("Project-Id-Version: Place Completer\n" "Language: %s\n" "MIME-Version: 1.0\n" "Content-Type: text/plain; charset=UTF-8\n"
          "Content-Transfer-Encoding: 8bit\n" "Plural-Forms: nplurals=2; plural=(n != 1);\n")
NOTES = {
    "he": ["Place Completer: the English texts of the interface and their Hebrew.",
           "Edit the Hebrew in the translation box. Keep the %s, %d and %(name)s as they are: they are replaced by names and numbers.",
           "A text that begins or ends with a space, or with ; or , is a piece of a sentence that the program joins: keep that space or sign at the same end.",
           "The official Hebrew words of Gramps (Place, Repository, Citation, Confidence, Undo ...) are in docs/GLOSSARY_HE.md."],
    "en": ["Place Completer: the English texts of the interface, for correction.",
           "The translation box holds the same English. Change it there where the English is to be corrected; leave the others as they are.",
           "Keep the %s, %d and %(name)s (they are replaced by names and numbers), and a space or a sign at the beginning or the end (some texts are pieces of a sentence)."],
}


# ------------------------------------------------------------------------------------------------------------------------------ reading and writing PO


def _unquote(text):
    body = text.strip()
    if not (body.startswith('"') and body.endswith('"')):
        raise ValueError("not a quoted string: %r" % text)
    out, i, body = [], 0, body[1:-1]
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(escapes.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def _quote(text):
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def read_po(path):
    """(header text, [entries]) of a PO file; an entry is {msgid, msgstr, flags, refs, comments, fuzzy}. Plural entries and obsolete entries (#~) are skipped."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    entries, current, field, skip = [], {"flags": set(), "refs": [], "comments": []}, None, False

    def flush():
        nonlocal current, field, skip
        if "msgid" in current and not skip:
            current.setdefault("msgstr", "")
            current["fuzzy"] = "fuzzy" in current["flags"]
            entries.append(current)
        current, field, skip = {"flags": set(), "refs": [], "comments": []}, None, False
    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("#~"):
            skip = True
        elif line.startswith("#,"):
            if "msgid" in current:
                flush()
            current["flags"].update(f.strip() for f in line[2:].split(","))
        elif line.startswith("#:"):
            if "msgid" in current:
                flush()
            current["refs"] += line[2:].split()
        elif line.startswith("#"):
            if "msgid" in current:
                flush()
            current["comments"].append(line[1:].lstrip(". ").strip() if line.startswith("#.") else line[1:].strip())
        elif line.startswith("msgid_plural") or line.startswith("msgstr["):
            skip = True
        elif line.startswith("msgctxt"):
            field = "msgctxt"
            current["msgctxt"] = _unquote(line[len("msgctxt"):])
        elif line.startswith("msgid"):
            field = "msgid"
            current["msgid"] = _unquote(line[len("msgid"):])
        elif line.startswith("msgstr"):
            field = "msgstr"
            current["msgstr"] = _unquote(line[len("msgstr"):])
        elif line.startswith('"') and field:
            current[field] = current.get(field, "") + _unquote(line)
    flush()
    header = ""
    if entries and entries[0]["msgid"] == "":
        header = entries[0]["msgstr"]
        entries = entries[1:]
    return header, entries


def write_po(path, language, entries):
    """entries: [{msgid, msgstr, refs, hints}]."""
    out = ["# " + n for n in NOTES[language]] + ["", 'msgid ""', "msgstr " + _quote(""), ]
    for part in (HEADER % language).splitlines(keepends=True):
        out.append(_quote(part))
    for e in entries:
        out.append("")
        for hint in e.get("hints", []):
            out.append("#. " + hint)
        if e.get("refs"):
            out.append("#: " + " ".join(e["refs"]))
        if PLACEHOLDER.search(e["msgid"]):
            out.append("#, python-format")
        out.append("msgid " + _quote(e["msgid"]))
        out.append("msgstr " + _quote(e["msgstr"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


# ------------------------------------------------------------------------------------------------------------------------------ what each %s stands for


def hints_from_code():
    """{text: ["1: expression of the first %s", ...]} for the texts whose arguments are written at the place where they are used."""
    found = {}
    folders = [os.path.join(ROOT, "placecompleter")]
    files = [os.path.join(f, n) for f in folders for n in sorted(os.listdir(f)) if n.endswith(".py")]
    files += [os.path.join(ROOT, n) for n in sorted(os.listdir(ROOT)) if n.startswith("placecompleter_") and n.endswith(".py")]
    for path in files:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for node in ast.walk(ast.parse(source)):
            message, args = None, None
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name) \
                    and node.left.func.id in ("tr", "_") and node.left.args and isinstance(node.left.args[0], ast.Constant) and isinstance(node.left.args[0].value, str):
                message = node.left.args[0].value
                args = node.right.elts if isinstance(node.right, ast.Tuple) else ([] if isinstance(node.right, ast.Dict) else [node.right])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_need", "_note") and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                message, args = node.args[1].value, node.args[2:]
            if message is None or message in found:
                continue
            specs = PLACEHOLDER.findall(message)
            if specs and len(specs) == len(args) and not any(s.startswith("%(") for s in specs):
                found[message] = ["%d: %s" % (i, re.sub(r"\s+", " ", (ast.get_source_segment(source, a) or "")).strip()[:70]) for i, a in enumerate(args, 1)]
    return found


# ------------------------------------------------------------------------------------------------------------------------------ the two commands


def catalog():
    """[(msgid, refs)] of the texts of the program (po/template.pot), in order."""
    _header, entries = read_po(os.path.join(ROOT, "po", "template.pot"))
    return [(e["msgid"], e["refs"]) for e in entries]


def hebrew():
    path = os.path.join(ROOT, "po", "he-local.po")
    return {e["msgid"]: e["msgstr"] for e in read_po(path)[1]}


def make(out):
    os.makedirs(out, exist_ok=True)
    texts, he, hints = catalog(), hebrew(), hints_from_code()
    rows_he, rows_en = [], []
    for msgid, refs in texts:
        legend = (["what each placeholder stands for, in order: " + "; ".join(hints[msgid])] if msgid in hints else [])
        rows_he.append({"msgid": msgid, "msgstr": he.get(msgid, ""), "refs": refs, "hints": legend})
        rows_en.append({"msgid": msgid, "msgstr": msgid, "refs": refs, "hints": legend})
    write_po(os.path.join(out, "placecompleter-he.po"), "he", rows_he)
    write_po(os.path.join(out, "placecompleter-en-edit.po"), "en", rows_en)
    return len(texts), sum(1 for r in rows_he if r["msgstr"]), sum(1 for r in rows_he if r["hints"])


def _edges(text):
    return (text[:1].isspace() or text[:1] in ";,.", text[-1:].isspace(), text[:2] if text[:2] in ("; ", ", ", ". ") else "")


def problems_of(msgid, msgstr):
    """What is wrong with a text and its version (a list of words; empty when it is fine)."""
    found = []
    if sorted(PLACEHOLDER.findall(msgid)) != sorted(PLACEHOLDER.findall(msgstr)):
        found.append("the %%s / %%d / %%(name)s are not the same: %s -> %s" % (PLACEHOLDER.findall(msgid), PLACEHOLDER.findall(msgstr)))
    if msgid.count("\n") != msgstr.count("\n"):
        found.append("the number of line breaks is not the same: %d -> %d" % (msgid.count("\n"), msgstr.count("\n")))
    # (a prefix that joins the next word with a hyphen takes the place of the space: "from " is "m-" in Hebrew, "m-1846")
    start_ok = msgid[:1].isspace() == msgstr[:1].isspace()
    end_ok = msgid[-1:].isspace() == msgstr[-1:].isspace() or (msgid[-1:].isspace() and msgstr[-1:] in ("-", "\u05be"))
    if not (start_ok and end_ok):
        found.append("a space at the beginning or at the end was added or removed (it is a piece of a sentence)")
    if msgid[:2] in ("; ", ", ", ". ") and msgstr[:2] != msgid[:2]:
        found.append("the text must begin with %r" % msgid[:2])
    return found


def check(path):
    """(language, a list of lines of the report, number of problems)."""
    header, entries = read_po(path)
    language = (re.search(r"Language:\s*(\w+)", header) or [None, ""])[1]
    known = dict(catalog())
    report, bad = [], 0
    seen = {e["msgid"] for e in entries}
    for msgid in sorted(set(known) - seen):
        report.append("MISSING from the file: %r" % msgid[:70])
        bad += 1
    for msgid in sorted(seen - set(known)):
        report.append("NOT a text of the program (the source was changed in the file; correct it in the English file): %r" % msgid[:70])
        bad += 1
    empty, same, changed = 0, 0, []
    for e in entries:
        if e["msgid"] not in known:
            continue
        msgid, msgstr = e["msgid"], e["msgstr"]
        if e["fuzzy"]:
            report.append("FUZZY (Poedit marks it as not sure): %r" % msgid[:60])
            bad += 1
        if not msgstr:
            empty += 1
            continue
        for p in problems_of(msgid, msgstr):
            report.append("%r: %s" % (msgid[:60], p))
            bad += 1
        if language == "he" and msgstr == msgid and len(msgid) > 4:
            same += 1
        if language == "en" and msgstr != msgid:
            changed.append((msgid, msgstr))
    if language == "he":
        if empty:
            report.append("%d texts have no Hebrew yet" % empty)
            bad += 1
        if same:
            report.append("%d texts are still the English (check that this is meant)" % same)
    elif language == "en":
        report.append("%d English texts were changed:" % len(changed))
        for old, new in changed[:40]:
            report.append("    - %s\n    + %s" % (old.replace("\n", "\\n")[:150], new.replace("\n", "\\n")[:150]))
        if len(changed) > 40:
            report.append("    ... and %d more" % (len(changed) - 40))
    return language, report, bad


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("make")
    m.add_argument("--out", default=os.path.join(os.path.expanduser("~"), "gramps-place-work", "po-exchange"))
    c = sub.add_parser("check")
    c.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "make":
        total, with_hebrew, with_hints = make(args.out)
        print("%d texts; %d with Hebrew; %d with the meaning of the %%s written; files in %s" % (total, with_hebrew, with_hints, args.out))
        return 0
    worst = 0
    for path in args.files:
        language, report, bad = check(path)
        print("== %s (%s): %s" % (os.path.basename(path), language or "no language in the header", "%d problems" % bad if bad else "nothing wrong"))
        for line in report:
            print("   " + line)
        worst = max(worst, 1 if bad else 0)
    return worst


if __name__ == "__main__":
    sys.exit(main())
