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
"""Ask an AI the question of the form "table" for a list of places, by itself, and keep the answers: nobody has to paste anything.

Usage:
    python3 tools/collect_answers.py --check
    python3 tools/collect_answers.py --dry-run
    python3 tools/collect_answers.py [--engine anthropic] [--places FILE] [--out DIR] [--language he] [--pause 3] [--skip-existing]
                                     [--db SQLITE --report]

--check          only say whether the engine can be asked (a key, or Ollama running); nothing is asked.
--dry-run        print the questions that would be asked; nothing is asked.
--engine         an engine that answers by itself: anthropic (Claude with web search, the default), openai, ollama. The key is the one of the
                 window (the Key button) or the environment variable of the engine (ANTHROPIC_API_KEY, OPENAI_API_KEY); it is never printed.
--places         a text file, one place a line: `Place | year` (a line that begins with # is a remark). Without it, a list of 20 places that are
                 not alike (France, Italy, Hungary, Serbia, Romania, Israel, the United States ...).
--out            where the answers are kept (default ~/gramps-place-work/answers-table). The folder of the window, with the older answers, is not
                 touched.
--skip-existing  do not ask again for a place whose answer is already kept (a run that was stopped can go on).
--report         with --db: afterwards, run tools/replay_answers.py --ablate on the new answers (and on ~/gramps-place-work/answers-old if it
                 exists) and keep the reports next to the answers.

Every answer is kept as NAME_YEAR.txt with NAME_YEAR.meta.json (who answered, when), as the window does. An answer that is not a table (the
question given back, no answer, text only) is asked once more, and then kept in the folder `rejected` with the reason, not among the answers.
Nothing is written to any tree.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from placecompleter import answers, engines, ingest, prompts, settings, table                 # noqa: E402

WORK = os.path.expanduser("~/gramps-place-work")

# places that are not alike; the first ones have an older answer in the folder of the window, for the comparison
DEFAULT_PLACES = [("Blagnac", "2026"), ("Toulouse", "1999"), ("Paris", "2026"), ("Aussonne", "1997"), ("Ausson", "1980"), ("Parma", "1995"),
                  ("Sissa", "1990"), ("Bajmok", "1877"), ("Hadad", "1900"), ("Zombor", "1850"), ("\u00dajvid\u00e9k", "1900"), ("Deva", "1930"),
                  ("Hunedoara", "1945"), ("Kfar Hess", "1950"), ("Johnston", "1950"), ("Brooklyn", "1870"), ("New York", "1950"),
                  ("Z\u00fcrich", "1990"), ("Rotterdam", "2026"), ("Rishon LeZion", "2026")]


def read_places(path):
    """[(place, year)] from a text file: `Place | year`, a line that begins with # is a remark."""
    found = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            place, _bar, date = line.rpartition("|")
            if not place.strip() or not date.strip():
                raise ValueError("a line must be `Place | year`: %r" % line)
            found.append((place.strip(), date.strip()))
    return found


def usable(text, form="table"):
    """Is the answer one that can be read (and not the question given back)? For the form table: a table; for the older forms: the labelled lines."""
    if not text or prompts.looks_like_echo(text):
        return False
    if form != "table":
        return bool(ingest.parse_structured(text)["name"])
    if not table.is_table(text):
        return False
    converted, _notes = table.convert(text)
    return bool(ingest.parse_structured(converted)["name"])


def collect(places, cfg, folder, form="table", language="en", ask=engines.ask, pause=0.0, sleep=time.sleep, skip_existing=False, retries=1, say=print,
            clock=time.monotonic):
    """Ask for each place and keep the answer. Returns [(place, year, status, detail, stats)]: status is saved, kept (already there) or rejected;
    stats is {"seconds", "chars"} of the answer (the time of the questions that were needed, and the length of the answer), {} when nothing was asked."""
    results = []
    for number, (place, date) in enumerate(places, 1):
        path = os.path.join(folder, answers.safe_name(place, date) + ".txt")
        if skip_existing and os.path.exists(path):
            say("%2d/%d  %s %s: already kept" % (number, len(places), place, date))
            results.append((place, date, "kept", path, {}))
            continue
        prompt = prompts.build_prompt(place, date, form, language=language)
        detail, text, model = "", "", None
        started = clock()
        for attempt in range(1 + retries):
            try:
                got = ask(cfg, prompt)
            except engines.EngineError as exc:
                detail = str(exc).strip().splitlines()[0][:160] if str(exc).strip() else "the engine failed"
                continue
            text, model = got.get("text") or "", got.get("model")
            if usable(text, form):
                stats = {"seconds": round(clock() - started, 1), "chars": len(text)}
                meta = dict(engines.provenance(cfg, form, place, date, prompt, model=model), **stats)
                path = answers.save_answer(folder, place, date, text, meta)
                say("%2d/%d  %s %s: saved (%.0f s, %d characters)" % (number, len(places), place, date, stats["seconds"], stats["chars"]))
                results.append((place, date, "saved", path, stats))
                break
            detail = "the question was given back" if prompts.looks_like_echo(text) else "no table in the answer (it starts with: %s)" % \
                " ".join(text.split())[:80]
        else:
            if text:
                answers.save_answer(os.path.join(folder, "rejected"), place, date, text, engines.provenance(cfg, form, place, date, prompt, model=model))
            say("%2d/%d  %s %s: REJECTED, %s" % (number, len(places), place, date, detail))
            results.append((place, date, "rejected", detail, {"seconds": round(clock() - started, 1), "chars": len(text)}))
        if pause and number < len(places):
            sleep(pause)
    return results


def summary(results):
    """The count of what was saved, kept and rejected, and the time and the length of an answer on average."""
    saved = [r for r in results if r[2] == "saved"]
    kept = [r for r in results if r[2] == "kept"]
    rejected = [r for r in results if r[2] == "rejected"]
    lines = ["", "saved: %d   already kept: %d   rejected: %d" % (len(saved), len(kept), len(rejected))]
    if saved:
        lines.append("an answer took %.0f seconds and %d characters on average (the form %s)" % (
            sum(r[4]["seconds"] for r in saved) / len(saved), sum(r[4]["chars"] for r in saved) / len(saved), "of the question that was asked"))
    lines += ["  rejected: %s %s: %s" % (r[0], r[1], r[3]) for r in rejected]
    return "\n".join(lines)


def report(folder, db):
    """The reports of tools/replay_answers.py, in the folder `reports` inside the folder of the answers (so that they are never read as answers): for each
    folder (the new answers, and the old ones if ~/gramps-place-work/answers-old exists) the report of what fired (replay-LABEL.txt and the table
    replay-LABEL.tsv) and the report of the rules switched off one at a time (ablate-LABEL.txt). Returns the files that were written."""
    tool = os.path.join(ROOT, "tools", "replay_answers.py")
    written = []
    reports = os.path.join(folder, "reports")
    os.makedirs(reports, exist_ok=True)
    for label, answers_dir in (("table", folder), ("old", os.path.join(WORK, "answers-old"))):
        if not os.path.isdir(answers_dir):
            continue
        for kind, extra in (("replay", []), ("ablate", ["--ablate"])):
            target = os.path.join(reports, "%s-%s.txt" % (kind, label))
            with open(target, "w", encoding="utf-8") as fh:
                subprocess.run([sys.executable, tool, "--db", db, "--answers", answers_dir, "--out", os.path.join(reports, "replay-%s.tsv" % label)] + extra,
                               stdout=fh, check=False)
            written.append(target)
    return written


def main(argv=None, ask=engines.ask):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", default="anthropic")
    parser.add_argument("--places", default="")
    parser.add_argument("--out", default=os.path.join(WORK, "answers-table"))
    parser.add_argument("--language", default="")
    parser.add_argument("--form", default="table", choices=sorted(prompts.FORMS))
    parser.add_argument("--pause", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default="")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = engines.pick(args.engine)
    except engines.EngineError as exc:
        print(exc)
        return 2
    if cfg.get("kind") != "api":
        print("%s does not answer by itself: choose an engine with a key (anthropic, openai) or ollama." % args.engine)
        return 2
    language = args.language or settings.interface_language() or "en"
    places = read_places(args.places) if args.places else list(DEFAULT_PLACES)
    if args.dry_run:                                                    # no key is needed to see the questions
        for place, date in places:
            print("--- %s %s\n%s\n" % (place, date, prompts.build_prompt(place, date, args.form, language=language)))
        print("%d questions would be asked of %s." % (len(places), cfg.get("label")))
        return 0
    ready, problems, fix = engines.readiness(cfg)
    if args.check or not ready:
        print("%s (%s): %s" % (cfg.get("label"), cfg.get("model") or "model chosen by itself", "ready" if ready else "NOT ready: " + "; ".join(problems)))
        if not ready:
            print("To fix: %s" % fix)
        return 0 if ready else 2
    print("Asking %s for %d places (about %d seconds of pauses); answers go to %s" % (cfg.get("label"), len(places), int(args.pause * len(places)), args.out))
    results = collect(places, cfg, args.out, args.form, language, ask=ask, pause=args.pause, skip_existing=args.skip_existing, retries=args.retries)
    print(summary(results))
    if args.report:
        if not args.db:
            print("--report needs --db (the snapshot).")
        else:
            for path in report(args.out, args.db):
                print("report: %s" % path)
    return 0 if all(r[2] != "rejected" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
