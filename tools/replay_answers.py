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
"""Replay the saved answers through the analysis and count what fires: which proposals, which messages (rules).

Usage:
    python3 tools/replay_answers.py [--answers DIR] [--db SQLITE] [--out FILE.tsv]

--answers  the folder of saved answers (default ~/gramps-place-work/answers). A file is NAME_DATE.txt (Johnston_1995.txt); a table answer
           as it was copied is read too.
--db       a Gramps SQLite file, opened read-only (the snapshot is the usual choice). Without it every place is new, so that only what the
           answer says itself is measured (types, levels, notes), and nothing about places that exist.
--out      the report as a table (default ~/gramps-place-work/replay_report.tsv).
--ablate   switch the rules (placecompleter/rules.py) off one at a time and say how many answers change: the proposals (what would be
           written) and the notes. A rule that changes nothing is a rule these answers never needed.
--without  switch the rules with these ids off (RULE,RULE ...) for the whole run.

The report also lists the messages of the program that did not fire in any answer: the rules that these answers never needed.

Nothing is written to any tree. The point is to see, over real answers, which rules of the analysis are ever used (docs/RULES_REVIEW.md).
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import ast
import collections
import contextlib
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from placecompleter import cli, ingest, rules, table                                           # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402

WORK = os.path.expanduser("~/gramps-place-work")
REPORT_PREFIXES = ("ablate-", "replay-", "urls")                          # files that the tools write: not answers


OWN_WORDS = ("sources listed by the answer", "the answer's own doubts", "the answer's own notes", "the answer itself is NOT SURE about",
             "the answer lists sites that may be official", "the answer added a remark to the name")


def shape(message):
    """A message without its names and numbers: the rule that wrote it."""
    text = re.sub(r"https?://\S+", "#", message)
    for prefix in OWN_WORDS:
        if text.startswith(prefix):
            text = prefix                                                                      # what follows is the answer's own words: the same rule every time
    text = re.sub(r"'[^']*'|\"[^\"]*\"|\u00ab[^\u00bb]*\u00bb|\[[^\]]*\]|\([^)]*\)|\d+", "#", text)
    return re.sub(r"\s+", " ", text).strip()[:110]


def declared_messages():
    """Every message that the analysis can put on the screen: the first text of _need(out, ...) and _note(notes, ...) in the program, by file."""
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "placecompleter", "*.py"))):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_need", "_note") and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                found.append((os.path.basename(path), node.args[1].value))
    return found


def unused(shapes):
    """The messages (rules) of the program that none of the answers made fire. Approximate: a message counts as seen when the fixed words of its
    first two parts (the text between the names and numbers) are all in a message that fired, letters only: the names, the numbers and the
    quotes are not the same in every answer, and a message that fired was cut after 110 characters."""
    def letters(text):
        return re.sub(r"[^a-z]", "", text.lower())
    seen = [letters(s) for s in shapes]
    out = []
    for file, template in declared_messages():
        fixed = [letters(part) for part in re.split(r"%[sdr]", re.sub(r"\([^)]*\)", "", template))]       # (what is in brackets is not in a shape)
        fixed = [f for f in fixed if len(f) >= 8][:2] or [letters(template)]
        if not any(all(f in s for f in fixed) for s in seen):
            out.append((file, template))
    return out


PROPOSAL_KEYS = ("kind", "place", "handle", "child", "parent", "index", "type_value", "type_string", "path", "value", "new_value", "lat", "lon", "optional")


def fingerprint(screen, notes=()):
    """(what would be proposed, the notes) of an analysis, in a form that two analyses can be compared by."""
    proposals = []
    for p in screen["proposals"]:
        item = {k: p.get(k) for k in PROPOSAL_KEYS}
        item["names"] = [n.get("value") for n in p.get("names", [])]
        proposals.append(json.dumps(item, sort_keys=True, default=str))
    return tuple(sorted(proposals)), tuple(screen["needs"]) + tuple(message % args for message, args in notes)


def analyse_all(tree, items, aliases=None, fired=None):
    """{label: fingerprint} for the answers that can be read. fired (a dict) gets, for each answer, the message rules that wrote a note."""
    done = {}
    for label, place, date, text in items:
        with rules.recording() as counter:
            converted, notes = table.convert(text, place)
            rec = ingest.parse_structured(converted)
            if not rec["name"] or not date:
                continue
            try:
                done[label] = fingerprint(ingest.ingest(tree, rec, date, aliases=aliases), notes)
            except Exception:
                continue
        if fired is not None:
            fired[label] = counter
    return done


def ablate(tree, items, aliases=None, ids=None, progress=None):
    """[{id, group, kind, title, proposals, notes, labels, answers}]: for each rule that can be measured by replay, the number of answers whose
    proposals and whose notes change when the rule is switched off (and which answers, for the proposals).

    A rule of a note (M..) changes no proposal by design, so it is not run again: the answers in which it wrote a note are counted from one run.
    The behavior rules are run again, once each (the analysis of a tree of some hundreds of places takes about a tenth of a second)."""
    say = progress or (lambda text: None)
    fired = {}
    say("the answers, all the rules on ...")
    base = analyse_all(tree, items, aliases, fired)
    rows = []
    behavior = [r for r in rules.all_rules() if r["switchable"] and r["measured"] == "replay" and r["kind"] == "behavior" and (not ids or r["id"] in ids)]
    for n, rule in enumerate(behavior, 1):
        say("rule %s switched off (%d of %d) ..." % (rule["id"], n, len(behavior)))
        with (rules.enabled(rule["id"]) if rule.get("default_off") else rules.disabled(rule["id"])):          # a rule that is off by default is tried ON
            other = analyse_all(tree, items, aliases)
        changed_proposals = sorted(label for label in base if other.get(label, ((), ()))[0] != base[label][0])
        changed_notes = [label for label in base if other.get(label, ((), ()))[1] != base[label][1]]
        title = rule["title"] + ("   [OFF by default: this is what changes when it is switched ON]" if rule.get("default_off") else "")
        rows.append({"id": rule["id"], "group": rule["group"], "kind": "behavior", "title": title, "proposals": len(changed_proposals),
                     "notes": len(changed_notes), "labels": changed_proposals, "answers": len(base)})
    for rule in rules.all_rules():
        if rule["kind"] == "message" and (not ids or rule["id"] in ids):
            wrote = [label for label in base if fired.get(label, {}).get(rule["id"])]
            rows.append({"id": rule["id"], "group": rule["group"], "kind": "message", "title": rule["title"], "proposals": 0,
                         "notes": len(wrote), "labels": [], "answers": len(base)})
    return rows


def ablation_report(rows):
    if not rows:
        return "no rule to measure"
    lines = ["rules switched off one at a time over %d answers (how many answers change):" % rows[0]["answers"], "",
             "  id    grp  proposals  notes  what the rule does"]
    for r in sorted(rows, key=lambda r: (r["proposals"] + r["notes"], r["id"])):
        lines.append("  %-5s %-3s  %9d  %5d  %s" % (r["id"], r["group"], r["proposals"], r["notes"], r["title"][:90]))
    nothing = [r["id"] for r in rows if not r["proposals"] and not r["notes"]]
    only_notes = [r["id"] for r in rows if not r["proposals"] and r["notes"]]
    lines += ["", "no effect on any answer: %s" % (", ".join(nothing) or "-"),
              "only notes change (what would be written is the same): %s" % (", ".join(only_notes) or "-"),
              "not measured here: WL (asks Wikidata), CT2, CT4, CT5 (are seen by writing to a database), and the rules that are not switchable yet"]
    for r in rows:
        if r["proposals"] and r["kind"] == "behavior":
            lines.append("  %s changes the proposals of: %s" % (r["id"], ", ".join(r["labels"][:6]) + (" ..." if len(r["labels"]) > 6 else "")))
    return "\n".join(lines)


def name_and_date(path):
    """('Johnston', '1950') from Johnston_1950.txt; a word after the date (Johnston_1950_v2.txt) is ignored; no date: (name, '')."""
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = stem.split("_")
    for n in range(len(parts) - 1, 0, -1):
        if re.fullmatch(r"\d{3,4}(-\d\d){0,2}", parts[n]):
            return " ".join(parts[:n]), parts[n]
    return stem.replace("_", " "), ""


def replay(tree, items, aliases=None):
    """items: [(label, place, date, text)]. Returns (rows, kinds, shapes, errors): a row per answer, the proposals by kind (and in how many
    answers), the messages by shape (and in how many answers), and the answers that could not be read."""
    rows, kinds, shapes, errors = [], collections.Counter(), collections.Counter(), []
    in_answers = collections.defaultdict(set)
    for label, place, date, text in items:
        converted, notes = table.convert(text, place)
        rec = ingest.parse_structured(converted)
        if not rec["name"] or not date:
            errors.append((label, "no place name" if not rec["name"] else "no date in the file name"))
            continue
        try:
            screen = ingest.ingest(tree, rec, date, aliases=aliases)
        except Exception as error:                                                             # a failure is a finding, not a stop
            errors.append((label, "%s: %s" % (type(error).__name__, error)))
            continue
        needs = list(screen["needs"]) + [message % args for message, args in notes]
        by_kind = collections.Counter(p["kind"] for p in screen["proposals"])
        for kind in by_kind:
            in_answers[("kind", kind)].add(label)
        for message in needs:
            in_answers[("need", shape(message))].add(label)
        kinds.update(by_kind)
        shapes.update(shape(m) for m in needs)
        rows.append({"file": label, "place": place, "date": date, "type": rec["type_value"], "levels": len(rec["containers"]),
                     "proposals": sum(by_kind.values()), "kinds": ", ".join("%s:%d" % kv for kv in sorted(by_kind.items())), "needs": len(needs)})
    counted = {key: len(files) for key, files in in_answers.items()}
    return rows, {k: (kinds[k], counted[("kind", k)]) for k in kinds}, {s: (shapes[s], counted[("need", s)]) for s in shapes}, errors


def report(rows, kinds, shapes, errors, out, never=None):
    lines = ["answers read: %d   not read: %d" % (len(rows), len(errors)), "", "proposals by kind (total, in how many answers):"]
    lines += ["  %-18s %4d  %3d" % (k, v[0], v[1]) for k, v in sorted(kinds.items(), key=lambda kv: -kv[1][1])]
    lines += ["", "messages by rule (total, in how many answers), the most used first:"]
    lines += ["  %3d %3d  %s" % (v[0], v[1], s) for s, v in sorted(shapes.items(), key=lambda kv: -kv[1][1])]
    if never is not None:
        lines += ["", "messages (rules) of the program that did NOT fire in any answer (%d; approximate):" % len(never)]
        lines += ["  %-12s %s" % (f, t[:100]) for f, t in never]
    if errors:
        lines += ["", "answers that were not read:"] + ["  %s: %s" % e for e in errors]
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("file\tplace\tdate\ttype\tlevels\tproposals\tkinds\tneeds\n")
            for r in rows:
                fh.write("\t".join(str(r[k]) for k in ("file", "place", "date", "type", "levels", "proposals", "kinds", "needs")) + "\n")
        lines += ["", "table: %s" % out]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", default=os.path.join(WORK, "answers"))
    parser.add_argument("--db", default="")
    parser.add_argument("--out", default=os.path.join(WORK, "replay_report.tsv"))
    parser.add_argument("--ablate", action="store_true")
    parser.add_argument("--without", default="")
    args = parser.parse_args(argv)
    paths = sorted(p for p in glob.glob(os.path.join(args.answers, "*.txt"))
                   if not p.endswith(".meta.txt") and not os.path.basename(p).startswith(REPORT_PREFIXES))       # a report is not an answer
    if not paths:
        print("no answers in %s" % args.answers)
        return 2
    items = []
    for path in paths:
        place, date = name_and_date(path)
        with open(path, encoding="utf-8") as fh:
            items.append((os.path.basename(path), place, date, fh.read()))
    tree = Tree.from_sqlite(args.db) if args.db else Tree({}, [])
    aliases = ingest.alias_map(cli._pack_files(argparse.Namespace()))
    if args.ablate:
        print(ablation_report(ablate(tree, items, aliases, progress=lambda text: print(text, file=sys.stderr, flush=True))))
        return 0
    off = [i.strip() for i in args.without.split(",") if i.strip()]
    with (rules.disabled(*off) if off else contextlib.nullcontext()):
        rows, kinds, shapes, errors = replay(tree, items, aliases)
    print(report(rows, kinds, shapes, errors, out=args.out, never=unused(shapes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
