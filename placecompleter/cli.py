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
"""Command line: report, agent-request and agent-validate.

    python3 -m placecompleter.cli report [SQLITE_DB] [--top N] [--csv FILE] [--pack FILE]
    python3 -m placecompleter.cli agent-request [SQLITE_DB] [--out FILE] [--max-tasks N] [--attempt K]
    python3 -m placecompleter.cli agent-validate RESPONSE.json --request REQUEST.json [--db DB] [--out PACK]
    python3 -m placecompleter.cli wikidata-pack [SQLITE_DB] [--online] [--max-places N] [--seed FILE]
    python3 -m placecompleter.cli complete-place NAME --date YYYY [--region R] [--pick Q] [--lang xx] [--online]
    python3 -m placecompleter.cli plan [SQLITE_DB] [--wikidata] [--pack FILE] [--out PLAN]
    python3 -m placecompleter.cli apply --plan PLAN --tree-dir COPY_DIR [--select 1,2 | --basis tree,evidence] [--yes]

The database is opened read-only and never written. Nothing is applied to a
tree here: every command only shows what would change.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import csv
import glob
import json
import os
import sys

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import agent, clipboard, complete, engines as enginelib, gaps, ingest as ingestlib, packs, plan as planlib, prompts, wikidata
from .answers import same_answer_elsewhere          # noqa: F401  (the tests and the commands use this name)
from .dates import describe
from .model import Tree

PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs")
# Where things go and what is read, from the environment (PLACECOMPLETER_...) with a default that belongs to nobody in particular.
WORK = enginelib.work_dir()                                                                          # the answers, the plans, the reports
SNAP = os.path.expanduser(os.environ.get("PLACECOMPLETER_TREE", ""))                                  # the sqlite.db to read: no default, say which
CACHE = os.path.expanduser(os.environ.get("PLACECOMPLETER_CACHE", "~/.cache/placecompleter_wikidata.json"))      # what Wikidata answered
LIVE_DIRS = [os.path.realpath(os.path.expanduser(d)) for d in os.environ.get("PLACECOMPLETER_LIVE_DIRS", "~/Dropbox").split(os.pathsep) if d]


def _gramps_resources():
    """Where Gramps keeps its own data when the environment does not say: the folder that holds the installed package `gramps` (None if it is not found)."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("gramps")
        return os.path.dirname(os.path.dirname(spec.origin)) if spec and spec.origin else None
    except (ImportError, ValueError, AttributeError):
        return None


def _years(span):
    return "%s-%s" % span if span else "?"


def _print_summary(title, counts):
    print(title)
    for key in ("events", "dated", "undated", "complete", "truncated, dated",
                "truncated, undated", "with a ? name", "cycle or missing parent"):
        print("  %-26s %d" % (key, counts.get(key, 0)))


def _lab(tree, handle):
    return tree.label(handle) if handle in tree.places else str(handle).replace("new:", "NEW ")


def _print_proposal(tree, p, say=print):
    flag = "  CONFLICT: replaces a different date" if p.get("conflict") else ""
    flag += "  [ASSUMPTION: same name for the whole lifetime]" if p.get("basis") == "assumption" else ""
    if p["kind"] == "add-place":
        say("  NEW PLACE %r (type %s)%s   (part of %s; %s)" % (
            p["names"][0]["value"], p["type_value"], " at %s,%s" % (p["lat"], p["lon"]) if p.get("lat") else "",
            p.get("bundle") or "no bundle", p["origin"]))
    elif p["kind"] == "add-url":
        say("  ADD LINK %s to %s%s   (%s; %s)" % (p["path"], tree.label(p["place"])[:30], "  [CHECK: is the site official?]" if p.get("optional") else "",
                                              p.get("note") or p.get("url_kind") or "", p["origin"]))
    elif p["kind"] in ("add-name", "set-name-date"):
        say("  %s %r (%s) of %s: %s  =>  %s   (%d events fixed%s; %s)%s" % (
            "ADD NAME" if p["kind"] == "add-name" else "SET NAME DATE", p["value"], p["lang"] or "-",
            tree.label(p["place"])[:30], describe(p["old"]), describe(p["new"]), p["events"],
            ", %d worse" % p["worse"] if p.get("worse") else "", p["origin"], flag))
    else:
        say("  %s -> %s: %s  =>  %s   (%d events fixed%s; %s)%s" % (
            _lab(tree, p["child"])[:30], _lab(tree, p["parent"])[:30], describe(p["old"]),
            describe(p["new"]), p["events"], ", %d worse" % p["worse"] if p.get("worse") else "", p["origin"], flag))
    for ev in p.get("evidence") or []:
        say("      evidence: %s | %s" % (ev.get("url", ""), ev.get("claim") or ev.get("quote", "")))


def _all_proposals(tree, rows, pack_files, about, say):
    props = gaps.propose_end_clips(tree, rows, about)
    say("\nPROPOSALS FROM THE TREE'S OWN DATA (shorten a link to a top-level place that ended): %d" % len(props))
    for p in props:
        say("  %s -> %s: %s  =>  %s   (%d events, years %s)" % (
            tree.label(p["child"])[:30], tree.label(p["parent"])[:30], describe(p["old"]),
            describe(p["new"]), p["events"], _years(p["years"])))
        say("      why: %s" % p["evidence"])
    for path in pack_files:
        pack = packs.load_pack(path)
        found, notes = packs.propose_from_pack(tree, pack, about)
        say("\nPROPOSALS FROM PACK %s: %d" % (pack["pack"]["id"], len(found)))
        for p in found:
            _print_proposal(tree, p, say)
        for note in notes:
            say("  note: %s" % note)
        props = props + found
    return props


def _simulate(tree, rows, props, about, top):
    after = gaps.analyse(gaps.apply(tree, props), about)
    _print_summary("\nSIMULATION AFTER THE PROPOSALS", gaps.summarize(after))
    print("\nWHAT CHANGES")
    for key, n in sorted(gaps.compare(rows, after).items()):
        print("  %-38s %d" % (key, n))
    print("\nSTILL OPEN AFTER THE SIMULATION (needs outside sources):")
    print("  link gaps (dated events): %d event(s) at %d place(s)" % (
        sum(g["events"] for g in gaps.link_gaps(after)), len(gaps.link_gaps(after))))
    print("  name gaps: %d event(s) at %d place(s)" % (
        sum(1 for r in after if r["unnamed"]), len({h for r in after for h in r["unnamed"]})))
    return after


def _pack_files(args):
    if getattr(args, "no_packs", False):
        return []
    return getattr(args, "pack", None) or sorted(glob.glob(os.path.join(PACKS_DIR, "*.json")))


def report(args):
    tree = Tree.from_sqlite(args.db)
    rows = gaps.analyse(tree, args.about_range)
    print("places: %d | events with a place: %d" % (len(tree.places), len(rows)))
    _print_summary("\nBASELINE", gaps.summarize(rows))
    print("\nLINK GAPS: no link covers the date (needs an outside source)")
    print("  %-44s %6s  %s" % ("place [id]", "events", "years"))
    for g in gaps.link_gaps(rows)[:args.top]:
        print("  %-44s %6d  %s" % (tree.label(g["place"])[:44], g["events"], _years(g["years"])))
    print("\nNAME GAPS: a place shows as '?' (no name covers the date)")
    print("  %-36s %-20s %6s  %-10s %s" % ("place [id]", "cause", "events", "years", "likely fix"))
    for g in gaps.name_gaps(tree, rows, args.about_range)[:args.top]:
        print("  %-36s %-20s %6d  %-10s %s" % (tree.label(g["place"])[:36], g["cause"], g["events"],
                                               _years(g["years"]), g["likely_fix"]))
    props = _all_proposals(tree, rows, _pack_files(args), args.about_range, print)
    after = _simulate(tree, rows, props, args.about_range, args.top)
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["event_id", "type", "year", "undated", "place", "before", "after", "end_before", "end_after"])
            for b, a in zip(rows, after):
                et = b["event"]["type"]
                w.writerow([b["event"]["id"], et.get("string") or et.get("value"), b["year"] or "",
                            int(b["undated"]), tree.label(b["chain"]["handles"][0]),
                            ", ".join(b["chain"]["names"]), ", ".join(a["chain"]["names"]),
                            b["chain"]["end"], a["chain"]["end"]])
        print("\nwrote %s" % args.csv)
    return 0


def agent_request(args):
    tree = Tree.from_sqlite(args.db)
    rows = gaps.analyse(tree, args.about_range)
    props = _all_proposals(tree, rows, _pack_files(args), args.about_range, lambda *_: None)
    after_tree = gaps.apply(tree, props)
    after = gaps.analyse(after_tree, args.about_range)
    if args.wikidata:
        found, _notes, _pack = _wikidata_step(tree, after_tree, after, args, print)
        after_tree = gaps.apply(tree, props + found)
        after = gaps.analyse(after_tree, args.about_range)
        print("Wikidata proposals taken into account: %d (the agent is asked only about what is left)" % len(found))
    request = agent.build_request(after_tree, after, attempt=args.attempt, max_tasks=args.max_tasks)
    out = args.out or os.path.join(WORK, "agent_request_%s.json" % request["request_id"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(request, fh, ensure_ascii=False, indent=1)
    print("request %s: %d task(s) for the %d event(s) that still have a gap" % (
        request["request_id"], len(request["tasks"]), sum(1 for r in after if r["unnamed"] or (r["chain"]["end"] == "truncated" and not r["undated"]))))
    for t in request["tasks"]:
        print("  %s  %-34s %s" % (t["task_id"], "%s [%s]" % (t["names"][0]["name"], t["gramps_id"]),
                                  "; ".join("%s %s" % (g["kind"], _years(tuple(g["years"]) if g["years"] else None)) for g in t["gaps"])))
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "prompt.md")
    with open(prompt_path, encoding="utf-8") as fh:
        prompt = fh.read()
    bundle = os.path.splitext(out)[0] + "_task.md"
    with open(bundle, "w", encoding="utf-8") as fh:
        fh.write(prompt + "\n\n## Request\n\n```json\n" + json.dumps(request, ensure_ascii=False, indent=1) + "\n```\n")
    if request.get("skipped_addresses"):
        print("%d address place(s) left out (street addresses need archives, not the web)" % request["skipped_addresses"])
    print("wrote %s\nwrote %s  <- open it, copy everything, paste it to the agent" % (out, bundle))
    return 0


def _wikidata_step(tree, after_tree, after, args, say):
    """Look the places that still have a gap up in Wikidata; return (proposals, notes, pack)."""
    handles = []
    for g in gaps.name_gaps(after_tree, after, args.about_range):
        if g["cause"] != "undated event":
            handles.append(g["place"])
    for g in gaps.link_gaps(after):
        handles.append(g["place"])
    handles = list(dict.fromkeys(handles))
    client = wikidata.Client(cache_path=args.cache, fetch=wikidata.urllib_fetch if args.online else None, pause=args.pause)
    for seed in args.seed:
        client.load(seed)
    say("places with a gap to look up: %d%s" % (len(handles), " (online, max %d)" % args.max_places if args.online else " (cache only)"))
    pack, notes = wikidata.build_pack(after_tree, handles, client, args.max_places)
    if args.online:
        client.save()
        say("network calls: %d, cache: %s" % (client.network_calls, args.cache))
    found, more = packs.propose_from_pack(after_tree, pack, args.about_range)
    return found, notes + more, pack


def wikidata_pack(args):
    tree = Tree.from_sqlite(args.db)
    rows = gaps.analyse(tree, args.about_range)
    base = _all_proposals(tree, rows, _pack_files(args), args.about_range, lambda *_: None)
    after_tree = gaps.apply(tree, base)
    after = gaps.analyse(after_tree, args.about_range)
    found, notes, pack = _wikidata_step(tree, after_tree, after, args, print)
    out = args.out or os.path.join(WORK, "wikidata_pack.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, ensure_ascii=False, indent=1)
    print("wrote %s (%d place(s), %d link(s))" % (out, len(pack["places"]), len(pack["edges"])))
    print("\nPROPOSALS FROM WIKIDATA: %d" % len(found))
    for p in found:
        _print_proposal(tree, p)
    for note in notes:
        print("  note: %s" % note)
    _simulate(tree, rows, base + found, args.about_range, args.top)
    return 0


def make_plan(args):
    tree = Tree.from_sqlite(args.db)
    rows = gaps.analyse(tree, args.about_range)
    quiet = lambda *_: None
    proposals = _all_proposals(tree, rows, _pack_files(args), args.about_range, quiet)
    if args.wikidata:
        after_tree = gaps.apply(tree, proposals)
        found, notes, _pack = _wikidata_step(tree, after_tree, gaps.analyse(after_tree, args.about_range), args, quiet)
        proposals = proposals + found
    plan = planlib.make_plan(tree, proposals, "db=%s" % args.db)
    out = args.out or os.path.join(WORK, "plan.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    planlib.save_plan(plan, out)
    print("%-3s %-10s %-14s %-44s %s" % ("#", "basis", "kind", "what", "change / effect"))
    for p in plan["proposals"]:
        what = p["label"] if p["kind"] not in ("add-name", "set-name-date") else "%s: %r (%s)" % (p["label"], p["value"], p["lang"] or "-")
        change = ("type %s" % p["type_value"]) if p["kind"] == "add-place" else ("link %s" % p["path"]) if p["kind"] == "add-url" else "%s => %s" % (describe(p["old"]), describe(p["new"]))
        print("%-3d %-10s %-14s %-44s %s  (%d fixed%s)%s%s" % (
            p["id"], p["basis"], p["kind"], what[:44], change, p["events"],
            ", %d worse" % p["worse"] if p["worse"] else "", "  CONFLICT" if p["conflict"] else "",
            "  [bundle %s]" % p["bundle"] if p.get("bundle") else ""))
    print("\nwrote %s (%d proposals). Apply to a COPY of the tree with: apply --plan %s --tree-dir DIR --basis tree,evidence"
          % (out, len(plan["proposals"]), out))
    return 0


def apply_plan(args):
    plan = planlib.load_plan(args.plan)
    ids = {int(x) for x in args.select.split(",") if x.strip()} if args.select else None
    bases = {x.strip() for x in args.basis.split(",") if x.strip()} if args.basis else None
    if ids is None and bases is None:
        print("STOP: choose what to apply with --select 1,2 and/or --basis tree,evidence,assumption")
        return 2
    folder = os.path.realpath(os.path.expanduser(args.tree_dir))
    for live in LIVE_DIRS:
        if folder == live or folder.startswith(live + os.sep):
            print("STOP: %s is inside %s (live data: PLACECOMPLETER_LIVE_DIRS says which folders). Work on a copy outside it." % (folder, live))
            return 2
    if not os.path.isfile(os.path.join(folder, "sqlite.db")):
        print("STOP: no sqlite.db in %s" % folder)
        return 2
    if os.path.exists(os.path.join(folder, "lock")):
        print("STOP: the tree is locked (open in Gramps?): %s" % os.path.join(folder, "lock"))
        return 2
    chosen = planlib.select(plan, ids, bases)
    if not chosen:
        print("Nothing selected.")
        return 0
    if _gramps_resources():
        os.environ.setdefault("GRAMPS_RESOURCES", _gramps_resources())
    from gramps.gen.db.utils import make_database
    from . import writer
    db = make_database("sqlite")
    db.load(folder, mode="w" if args.yes else "r")
    try:
        name = ""
        try:
            with open(os.path.join(folder, "name.txt"), encoding="utf-8") as fh:
                name = fh.read().strip()
        except OSError:
            pass
        print("tree: %s (%s), %d people" % (name or "(no name)", folder, db.get_number_of_people()))
        results = writer.apply_proposals(db, chosen, dry_run=not args.yes)
        by_id = {p["id"]: p for p in chosen}
        for r in results:
            print("  #%-3d %-8s %-14s %s%s" % (r["id"], r["status"], by_id[r["id"]]["kind"], by_id[r["id"]]["label"][:50],
                                              "  (%s)" % r["reason"] if r["reason"] else ""))
    finally:
        db.close()
    print("\n%s. Check it with: report %s" % ("WRITTEN in one transaction (Undo reverts it all)" if args.yes
                                               else "DRY RUN: nothing was written. Add --yes to write",
                                               os.path.join(folder, "sqlite.db")))
    return 0


def complete_place(args):
    tree = Tree.from_sqlite(args.db)
    client = wikidata.Client(cache_path=args.cache, fetch=wikidata.urllib_fetch if args.online else None, pause=args.pause)
    for seed in args.seed:
        client.load(seed)
    result = complete.complete_place(tree, args.name, args.date, client, region=args.region, pick=args.pick,
                                     language=args.lang, about=args.about_range)
    if args.online:
        client.save()
    print(complete.render(result))
    if result["proposals"]:
        out = args.out or os.path.join(WORK, "plan_complete.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        planlib.save_plan(planlib.make_plan(tree, result["proposals"], "complete-place %s %s" % (args.name, args.date)), out)
        print("\nwrote %s. Apply to a COPY with: apply --plan %s --tree-dir DIR --basis evidence,assumption" % (out, out))
    return 0


def ingest_text(args):
    tree = Tree.from_sqlite(args.db)
    with open(args.file, encoding="utf-8") as fh:
        rec = ingestlib.parse_structured(fh.read())
    skip = {int(x) for x in args.skip.split(",") if x.strip()}
    result = ingestlib.ingest(tree, rec, args.date, args.about_range, skip, ingestlib.alias_map(_pack_files(args)))
    compare_dir = getattr(args, "compare_dir", "") or os.path.join(WORK, "answers")
    if os.path.isdir(compare_dir):
        result["needs"] += ["CONFLICTS WITH SAVED RESPONSE: " + m for m in ingestlib.compare_with_saved(rec, compare_dir, args.date, skip_path=args.file)]
    print(complete.render(result))
    for number, unit in enumerate(rec["containers"], 1):
        print("  level %d: %s | %s | %s-%s" % (number, unit["name"], unit["type"], unit["from"] or "?", unit["to"] or "present"))
    if result["proposals"]:
        out = args.out or os.path.join(WORK, "plan_ingest.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        planlib.save_plan(planlib.make_plan(tree, result["proposals"], "ingest-text %s %s" % (args.file, args.date)), out)
        print("\nwrote %s. Everything here is an assumption until you confirm it; conflicts are never selected by --basis." % out)
    return 0


def _form(args):
    return "short" if getattr(args, "short", False) else (getattr(args, "form", None) or "classic")


def search_ai(args, opener=None):
    place = args.place + (", " + args.hint if getattr(args, "hint", "") else "")
    prompt = prompts.build_prompt(place, args.date, _form(args))
    try:
        cfg = enginelib.pick(getattr(args, "engine", "google") or "google", getattr(args, "engines_file", None))
    except enginelib.EngineError as exc:
        print(exc)
        return 2
    print("question (%d characters, form %s):\n%s\n" % (len(prompt), _form(args), prompt if args.show else prompt.splitlines()[0] + " ..."))
    if cfg["kind"] == "api":
        print("%s answers by itself: use ai-complete (this command only opens a question in a browser)." % cfg["label"])
        return 2
    if cfg["kind"] == "manual":
        print("copied to the clipboard." if clipboard.write_clipboard(prompt) else "no clipboard tool: copy the question above by hand.")
        return 0
    url = enginelib.browser_url(cfg, prompt)
    print("link (%d characters) opens %s:\n%s" % (len(url), cfg["label"], url if args.show else url[:110] + "..."))
    if not args.no_open:
        import webbrowser
        if not (opener or webbrowser.open)(url):
            print("the browser could not be started: open the link by hand")
    return 0


def keys_cmd(args, getpass_fn=None, http_get=None):
    """Keep, remove or test the key of an engine from the terminal (the window does the same with a small dialog)."""
    from . import keystore
    try:
        cfg = enginelib.pick(args.engine, getattr(args, "engines_file", None))
    except enginelib.EngineError as exc:
        print(exc)
        return 2
    if not enginelib.needs_key(cfg):
        print("%s does not require an API key." % cfg.get("label", args.engine))
        return 0
    store = keystore.get_store()
    if getattr(args, "set", False):
        import getpass
        key = (getpass_fn or getpass.getpass)("Key for %s (nothing is shown): " % cfg.get("label", args.engine)).strip()
        if not key:
            print("No key was typed: nothing changed.")
            return 2
        try:
            store.set(enginelib.key_account(cfg), key)
        except keystore.StoreError as exc:
            print("The key could not be kept: %s" % exc)
            return 2
        print("Key kept in %s%s." % (store.name, "" if store.secure else ": THIS IS NOT ENCRYPTED, so do not copy or sync that folder"))
    elif getattr(args, "remove", False):
        store.delete(enginelib.key_account(cfg))
        print("Key removed from %s." % store.name)
    elif getattr(args, "test", False):
        res = enginelib.check_key(cfg, http_get=http_get or enginelib.get_json)
        print(("OK: " if res["ok"] else "NOT OK: ") + res["message"])
        return 0 if res["ok"] else 2
    print("%s: %s | new keys are kept in: %s" % (cfg.get("label", args.engine), enginelib.key_status(cfg), store.name))
    return 0


def list_engines(args):
    try:
        found = enginelib.load_engines(getattr(args, "engines_file", None))
    except enginelib.EngineError as exc:
        print(exc)
        return 2
    print("Engines (add or change them in %s):" % enginelib.config_path())
    for name in sorted(found):
        cfg = found[name]
        extra = " | model %s" % cfg.get("model") if cfg.get("model") else ""
        print("  %-10s %-8s %s%s | %s" % (name, cfg["kind"], cfg.get("label", ""), extra, enginelib.key_status(cfg)))
    return 0


def ai_complete(args, opener=None, wait=None, read=None, choose=None, http=None):
    """Open an AI (Google AI mode by default) with the question, wait for the answer to be copied, show the control screen.

    - "No answer for this search" (Google sometimes says so) moves on to the next form of the question.
    - An ambiguous name is chosen HERE (Google loses the question when a candidate is clicked there) and a second
      question describes the place exactly.
    """
    import webbrowser
    place = args.place + (", " + args.hint if getattr(args, "hint", "") else "")
    try:
        cfg = enginelib.pick(getattr(args, "engine", "google") or "google", getattr(args, "engines_file", None))
    except enginelib.EngineError as exc:
        print(exc)
        return 2
    chosen_form = _form(args)
    forms = list(prompts.AUTO_ORDER) if chosen_form == "auto" else [chosen_form]
    tree = Tree.from_sqlite(args.db)
    text = rec = meta = None
    asked, form_index = 0, 0
    while True:
        if asked >= 5:
            print("Five questions were asked without a usable answer: stop here and try later, or add --hint \"Iowa\" "
                  "(the region), or use another --engine.")
            return 2
        form = forms[form_index]
        prompt = prompts.build_prompt(place, args.date, form)
        asked += 1
        model, url = None, None
        if cfg["kind"] == "api":
            print("Asking %s (%s) with the question (form %s) for %s on %s..." % (cfg["label"], cfg.get("model"), form, place, args.date))
            try:
                got = enginelib.ask(cfg, prompt, http=http or enginelib.post_json)
            except enginelib.EngineError as exc:
                print("AI engine error: %s" % exc)
                return 2
            text, model = got["text"], got["model"]
        else:
            if cfg["kind"] == "manual":
                copied = clipboard.write_clipboard(prompt)
                print("The question (form %s) %s." % (form, "is on the clipboard: paste it into the AI you use" if copied
                                                      else "could not be copied (no clipboard tool): copy it from below\n\n" + prompt + "\n"))
            else:
                url = enginelib.browser_url(cfg, prompt)
                ok = (opener or webbrowser.open)(url)
                print("%s was %s with the question (form %s) for %s on %s." % (
                    cfg["label"], "opened" if ok else "NOT opened (open this link by hand: %s)" % url, form, place, args.date))
            print("When the answer is complete: select all of it, copy it (Ctrl+C), then come back here.")
            (wait or (lambda: input("Press Enter when the answer is copied... ")))()
            text = (read or clipboard.read_clipboard)()
        meta = enginelib.provenance(cfg, form, place, args.date, prompt, model=model, url=url)
        if not text:
            print("The clipboard is empty, or no clipboard tool is installed (xclip, xsel or wl-paste). "
                  "Save the answer as a text file and use: ingest-text FILE --date %s" % args.date)
            return 2
        rec = ingestlib.parse_structured(text)
        if prompts.looks_like_echo(text) or (not rec["name"] and not rec["ambiguous"]):
            reason = "the AI gave the question back instead of an answer (it could not fill it in)" if prompts.looks_like_echo(text) else \
                "Google returned no search results for this query" if prompts.looks_like_no_answer(text) else \
                "the clipboard does not hold an answer in the template (it starts with: %s)" % text.strip()[:120].replace("\n", " ")
            if form_index + 1 < len(forms):
                form_index += 1
                print("\n%s. Trying the next form of the question (%s)...\n" % (reason[0].upper() + reason[1:], forms[form_index]))
                continue
            print("\n%s, and no other form is left. Try again in a few minutes, add --hint, or use --engine chatgpt." % (reason[0].upper() + reason[1:]))
            return 2
        if not rec["candidates"]:
            break
        hints = ingestlib.candidate_hints(tree, rec["candidates"])
        print("\nThe name is ambiguous. Which one do you mean?")
        for i, h in enumerate(hints, 1):
            c_ = h["candidate"]
            print("  %d. %s, %s%s   (%s, %s)%s" % (i, c_["name"], c_["country"], " (%s)" % c_["region"] if c_["region"] else "",
                                                 c_["coordinates"][0], c_["coordinates"][1], "\n       <- " + "; ".join(h["notes"]) if h["notes"] else ""))
        best = max(range(len(hints)), key=lambda i: hints[i]["score"])
        picked = (choose or (lambda n: input("Number (Enter = %d, 0 = stop): " % (best + 1)).strip() or str(best + 1)))(len(hints))
        if str(picked) in ("0", ""):
            return 0
        try:
            candidate = rec["candidates"][int(picked) - 1]
        except (ValueError, IndexError):
            print("Not a valid number.")
            return 2
        place = ingestlib.refined_place(args.place, candidate)
        print("\nAsking again about: %s\n" % place)
    folder = args.save_dir or os.path.join(WORK, "answers")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in "%s_%s" % (args.place, args.date))
    path = os.path.join(folder, safe + ".txt")
    elsewhere = same_answer_elsewhere(folder, args.place, args.date, text)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if meta:
        with open(path[:-4] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
    print("answer saved: %s%s\n" % (path, "  (asked: %s, model: %s)" % (meta["engine"], meta["model"]) if meta else ""))
    if elsewhere:
        print("WARNING: this answer is IDENTICAL to the one saved for %s. The AI gave the same text for different dates, so "
              "what it says about the name and the type on the date cannot be trusted: check them.\n" % ", ".join(elsewhere))
    skip = {int(x) for x in args.skip.split(",") if x.strip()}
    result = ingestlib.ingest(tree, rec, args.date, args.about_range, skip, ingestlib.alias_map(_pack_files(args)))
    result["needs"] += ["CONFLICTS WITH SAVED RESPONSE: " + m for m in ingestlib.compare_with_saved(rec, folder, args.date, skip_path=path)]
    print(complete.render(result))
    for number, unit in enumerate(rec["containers"], 1):
        print("  level %d: %s | %s | %s-%s" % (number, unit["name"], unit["type"], unit["from"] or "?", unit["to"] or "present"))
    if result["proposals"]:
        out = args.out or os.path.join(WORK, "plan_ingest.json")
        planlib.save_plan(planlib.make_plan(tree, result["proposals"], "ai-complete %s %s" % (place, args.date)), out)
        print("\nwrote %s. Everything here is an assumption until you confirm it; conflicts are never selected by --basis." % out)
    return 0


def agent_validate(args):
    tree = Tree.from_sqlite(args.db)
    with open(args.request, encoding="utf-8") as fh:
        request = json.load(fh)
    with open(args.response, encoding="utf-8") as fh:
        response = json.load(fh)
    result = agent.validate_response(response, request, tree)
    print("ACCEPTED (%d)" % len(result["accepted"]))
    for a in result["accepted"]:
        print("  + %s" % a)
    print("REJECTED (%d)" % len(result["rejected"]))
    for r in result["rejected"]:
        print("  - %s: %s" % (r["where"], "; ".join(r["reasons"])))
    for note in result["notes"]:
        print("note: %s" % note)
    if not result["pack"]:
        print("\nNothing to simulate.")
        return 1 if result["rejected"] else 0
    out = args.out or os.path.join(WORK, "agent_pack_%s.json" % request.get("request_id"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result["pack"], fh, ensure_ascii=False, indent=1)
    print("\nwrote the accepted items as a pack: %s" % out)
    rows = gaps.analyse(tree, args.about_range)
    base = _all_proposals(tree, rows, _pack_files(args), args.about_range, lambda *_: None)
    found, notes = packs.propose_from_pack(gaps.apply(tree, base), result["pack"], args.about_range)
    print("\nPROPOSALS FROM THE AGENT PACK: %d" % len(found))
    for p in found:
        _print_proposal(tree, p)
    for note in notes:
        print("  note: %s" % note)
    _simulate(tree, rows, base + found, args.about_range, args.top)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="placecompleter.cli")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--top", type=int, default=15)
    common.add_argument("--pack", action="append", default=[],
                        help="a regional pack (JSON); default: every file in the packs folder")
    common.add_argument("--no-packs", action="store_true", help="ignore the packs folder")
    common.add_argument("--about-range", type=int, default=50,
                        help="Gramps setting behavior.date-about-range (years)")
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report", parents=[common])
    r.add_argument("db", nargs="?", default=SNAP)
    r.add_argument("--csv", default="")
    q = sub.add_parser("agent-request", parents=[common])
    q.add_argument("db", nargs="?", default=SNAP)
    q.add_argument("--out", default="")
    q.add_argument("--attempt", type=int, default=1)
    q.add_argument("--max-tasks", type=int, default=12)
    q.add_argument("--wikidata", action="store_true", help="look the gaps up in Wikidata first (cache only unless --online)")
    q.add_argument("--cache", default=CACHE)
    q.add_argument("--seed", action="append", default=[])
    q.add_argument("--online", action="store_true")
    q.add_argument("--max-places", type=int, default=12)
    q.add_argument("--pause", type=float, default=3.0)
    v = sub.add_parser("agent-validate", parents=[common])
    v.add_argument("response")
    v.add_argument("--request", required=True)
    v.add_argument("--db", default=SNAP)
    v.add_argument("--out", default="")
    pl = sub.add_parser("plan", parents=[common])
    pl.add_argument("db", nargs="?", default=SNAP)
    pl.add_argument("--out", default="")
    pl.add_argument("--wikidata", action="store_true", help="include Wikidata proposals (cache only unless --online)")
    pl.add_argument("--cache", default=CACHE)
    pl.add_argument("--seed", action="append", default=[])
    pl.add_argument("--online", action="store_true")
    pl.add_argument("--max-places", type=int, default=12)
    pl.add_argument("--pause", type=float, default=3.0)
    ap_ = sub.add_parser("apply", parents=[common])
    ap_.add_argument("--plan", required=True)
    ap_.add_argument("--tree-dir", required=True, help="folder of a COPY of the tree (contains sqlite.db)")
    ap_.add_argument("--select", default="", help="proposal numbers, e.g. 1,2,5")
    ap_.add_argument("--basis", default="", help="tree, evidence and/or assumption")
    ap_.add_argument("--yes", action="store_true", help="really write (default is a dry run)")
    cp = sub.add_parser("complete-place", parents=[common])
    cp.add_argument("name")
    cp.add_argument("--date", required=True, help="the event date: YYYY, YYYY-MM or YYYY-MM-DD")
    cp.add_argument("--db", default=SNAP)
    cp.add_argument("--region", default=None, help="a word that helps tell places apart, e.g. Serbia")
    cp.add_argument("--pick", default=None, help="the Wikidata item to use, e.g. Q204475")
    cp.add_argument("--lang", default=None, help="force the language of the names (hu, ro, sr, ...)")
    cp.add_argument("--out", default="")
    cp.add_argument("--cache", default=CACHE)
    cp.add_argument("--seed", action="append", default=[])
    cp.add_argument("--online", action="store_true")
    cp.add_argument("--pause", type=float, default=3.0)
    it = sub.add_parser("ingest-text", parents=[common])
    it.add_argument("file", help="the answer, saved as a text file (the template of agent/search_prompt.md)")
    it.add_argument("--date", required=True)
    it.add_argument("--db", default=SNAP)
    it.add_argument("--skip", default="", help="container levels to leave out, e.g. 2")
    it.add_argument("--compare-dir", default="", help="folder of saved answers to compare with (default ~/gramps-place-work/answers)")
    it.add_argument("--out", default="")
    sa = sub.add_parser("search-ai", parents=[common])
    sa.add_argument("place")
    sa.add_argument("--date", required=True)
    sa.add_argument("--short", action="store_true", help="the short form of the question")
    sa.add_argument("--form", choices=sorted(prompts.FORMS), default="classic", help="classic (default), short, dated or long")
    sa.add_argument("--engine", default="google", help="an engine of the list (see the engines command)")
    sa.add_argument("--hint", default="", help="a word that tells places apart, added to the name (e.g. Iowa)")
    sa.add_argument("--show", action="store_true", help="print the whole question and link")
    sa.add_argument("--no-open", action="store_true", help="only print the link")
    sub.add_parser("engines", parents=[common])
    kc = sub.add_parser("keys", parents=[common])
    kc.add_argument("engine")
    kc.add_argument("--set", action="store_true", help="type the key (nothing is shown) and keep it")
    kc.add_argument("--remove", action="store_true", help="remove the kept key")
    kc.add_argument("--test", action="store_true", help="ask the service whether it accepts the key (spends nothing)")
    ac = sub.add_parser("ai-complete", parents=[common])
    ac.add_argument("place")
    ac.add_argument("--date", required=True)
    ac.add_argument("--db", default=SNAP)
    ac.add_argument("--hint", default="", help="a word that tells places apart, added to the name (e.g. Iowa)")
    ac.add_argument("--short", action="store_true")
    ac.add_argument("--form", choices=sorted(prompts.FORMS) + ["auto"], default="auto",
                    help="auto (default: classic, then short, dated, long: the next one when Google says there is no answer), or one form")
    ac.add_argument("--engine", default="google", help="google, chatgpt, gemini, manual, anthropic (Claude API), openai, ollama, or your own (engines command)")
    ac.add_argument("--skip", default="", help="container levels to leave out, e.g. 2")
    ac.add_argument("--out", default="")
    ac.add_argument("--save-dir", default="")
    w = sub.add_parser("wikidata-pack", parents=[common])
    w.add_argument("db", nargs="?", default=SNAP)
    w.add_argument("--out", default="")
    w.add_argument("--cache", default=CACHE)
    w.add_argument("--seed", action="append", default=[], help="load extra cached answers (JSON, same format as the cache)")
    w.add_argument("--online", action="store_true", help="query Wikidata for what the cache does not hold")
    w.add_argument("--max-places", type=int, default=12)
    w.add_argument("--pause", type=float, default=3.0)
    args = ap.parse_args(argv)
    if hasattr(args, "db") and not args.db:
        print("STOP: no tree given: pass the path of a sqlite.db (a copy, outside the live data) or set PLACECOMPLETER_TREE.")
        return 2
    return {"report": report, "agent-request": agent_request, "agent-validate": agent_validate,
            "wikidata-pack": wikidata_pack, "plan": make_plan, "apply": apply_plan,
            "complete-place": complete_place, "ingest-text": ingest_text, "search-ai": search_ai,
            "ai-complete": ai_complete, "engines": list_engines, "keys": keys_cmd}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
