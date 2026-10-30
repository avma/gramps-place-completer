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
"""The model of the window: what is asked, what is shown, what is chosen, what is written.

No GTK here: the window (placecompleter_tool.py) only draws this and passes clicks to it, so everything the window does is
tested without a screen. A session is one question about one place on one date:

    begin()        -> an action for the window: open a link, copy the question, or call an API
    receive(text)  -> "ready" (the control screen), "ambiguous" (choose a place), "retry" (the next form of the question), "failed"
    rows / toggle  -> the proposals, with a check box each; a new place and its links are one choice
    preview()      -> what Gramps would display for an event on that date, for the proposals checked now
    apply(db)      -> one transaction, one Undo
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import answers, citations, table as tablelib, confidence, engines as enginelib, hierarchy, ingest as ingestlib, keystore, links as linklib, names as namelib, rules, plan as planlib, prompts, settings, writer
from .complete import parse_date
from .dates import describe, is_empty
from .i18n import _ as tr
from .kinds import TYPE_NAMES, type_name

PLACE_TYPES = TYPE_NAMES                                              # (the English words, kept under the old name)
WARNING_STARTS = rules.warning_starts() + ("CONFLICT",)             # (CONFLICT also begins the note of a saved answer that disagrees)
MAX_QUESTIONS = 5


def _which_name(p, with_language=True):
    """Which of the names of the place a row is about: a place can have the same spelling in several languages, and a row that does not say which
    one looks like the same row again and again. 'primary name, no language' / 'alternative name no. 3, language: de'."""
    index = p.get("index")
    role = tr("primary name") if not index else tr("alternative name #%d") % index
    if not with_language:
        return role
    return "%s, %s" % (role, tr("language: %s") % p["lang"] if p.get("lang") else tr("unspecified language"))


def describe_proposal(tree, p, new_names):
    """One line in plain words for a proposal of a plan."""
    def where(handle):
        if str(handle).startswith("new:"):
            return "«%s» (new)" % new_names.get(handle, "?")
        return "«%s»" % tree.label(handle) if handle in tree.places else "«?»"

    def period(d):
        return "" if not d else describe(d)
    kind = p["kind"]
    if kind == "add-place":
        first = p["names"][0]
        ptype = p.get("type_string") or (type_name(p["type_value"]) if p.get("type_value") in PLACE_TYPES else tr("type pending selection"))
        extra = tr(", coordinates %s, %s%s") % (p["lat"], p["lon"], " from " + p["source_note"] if p.get("source_note") else "") if p.get("lat") else ""
        return tr("Create place «%s» (%s%s); primary name: %s") % (first["value"], ptype, extra, period(first.get("date")))
    if kind == "add-url":
        return tr("Attach web link %s to %s (%s)") % (p["path"], where(p["place"]), p.get("note") or "")
    if kind == "add-name":
        return tr("Add place name «%s» (%s) to %s: %s") % (p["value"], p.get("lang") or "-", where(p["place"]), period(p.get("new")))
    if kind == "set-name-date" and is_empty(p.get("old")):
        return tr("Assign date period to name «%s» (%s) of %s: %s") % (
            p["value"], _which_name(p), where(p["place"]), period(p.get("new")))
    if kind == "set-name-date":
        return tr("Update date period for name «%s» (%s) of %s: %s -> %s") % (p["value"], _which_name(p), where(p["place"]),
                                                                              period(p.get("old")), period(p.get("new")))
    if kind == "set-coordinates":
        return tr("Set missing coordinates for %s: %s, %s (%s)") % (
            where(p["place"]), p["lat"], p["lon"], "from " + p["source_note"] if p.get("source_note")
            else tr("from AI response: verify accuracy (coordinates may deviate slightly)"))
    if kind == "rename-place":
        return tr("Rename %s to «%s» (previous name retained as alternative name)") % (
            where(p["place"]), p["new_value"])
    if kind == "set-name-language":
        return tr("Set language tag for name «%s» (%s) of %s to %s") % (p["value"], _which_name(p, with_language=False),
                                                                                       where(p["place"]), p["lang"])
    if kind == "change-type":
        return tr("Change administrative place type of %s from %s to %s") % (
            where(p["place"]), type_name(p["old_type_value"]) if p.get("old_type_value") in PLACE_TYPES else "?", p.get("type_string") or (type_name(p["type_value"]) if p.get("type_value") in PLACE_TYPES else "?"))
    if kind == "set-type":
        return tr("Set administrative place type of %s to %s") % (where(p["place"]), type_name(p["type_value"]) if p.get("type_value") in PLACE_TYPES else "?")
    if kind == "add-link":
        return tr("Enclose %s inside %s: %s%s") % (where(p["child"]), where(p["parent"]), period(p.get("new")),
                                           tr(" (an intermediate level inserted before the direct link to %s, which applies to the other years)") % where(p["above"])
                                           if p.get("refines") and p.get("above") else "")
    if kind == "remove-link":
        return tr("Disconnect %s from %s (removes hierarchy link; retains place entities)") % (where(p["child"]), where(p["parent"]))
    if kind == "move-link":
        return tr("Prioritize link of %s inside %s over link inside %s") % (
            where(p["child"]), where(p["parent"]), where(p["above"]))
    if kind == "set-link":
        return tr("Update hierarchy link date range for %s inside %s: %s -> %s%s") % (where(p["child"]), where(p["parent"]), period(p.get("old")), period(p.get("new")),
                                                                   tr(" (to use the intermediate level)") if p.get("refines") else "")
    return kind


class Session:
    def __init__(self, tree, work_dir, engines_path=None, pack_files=(), about_range=50):
        self.tree = tree
        self.work_dir = work_dir
        self.engines_path = engines_path
        self.aliases = ingestlib.alias_map(list(pack_files)) if pack_files else {}
        self.about_range = about_range
        self.reset()

    def reset(self):
        self.place = self.date = self.hint = ""
        self.cfg = None
        self.state, self.message = "idle", ""
        self.text = self.rec = self.result = self.plan = self.meta = None
        self.choices = {}                                      # the user's choice for a unit that could be several places: {slot: handle | new | skip}
        self.selected, self.candidates, self.levels = set(), [], []
        self.applied = None
        self.saved_path = None
        self._forms, self._form_index, self._asked, self._place_text, self._last = [], 0, 0, "", {}
        self._extra_needs = []

    # ------------------------------------------------------------ settings the window shows
    def engine_choices(self):
        """[(id, label, kind, key status)] for the engine list."""
        found = enginelib.load_engines(self.engines_path)
        return [(k, found[k].get("label", k), found[k]["kind"], enginelib.key_status(found[k])) for k in sorted(found)]

    def engine_options(self):
        """Engines for the list of the window: [{id, label, kind, status, ready, fix, lacks}], those that can work first."""
        found = enginelib.load_engines(self.engines_path)
        order = ["google", "manual", "chatgpt", "gemini", "anthropic", "openai", "ollama"]
        out = []
        for key in sorted(found, key=lambda k: (order.index(k) if k in order else len(order), k)):
            cfg = {**found[key], "id": key}
            ready, problems, fix = enginelib.readiness(cfg)
            out.append({"id": key, "label": cfg.get("label", key), "kind": cfg["kind"], "status": enginelib.key_status(cfg),
                        "ready": ready, "fix": fix, "lacks": [x for x in problems if x != "no key"]})
        return sorted(out, key=lambda o: not o["ready"])

    # ------------------------------------------------------------ asking
    def begin(self, place, date, hint="", engine="google", form="auto"):
        self.reset()
        place, date = place.strip(), date.strip()
        if not place:
            return self._fail(tr("Please enter a place name."))
        try:
            parse_date(date)
        except ValueError:
            return self._fail(tr("Date format must be YYYY, YYYY-MM, or YYYY-MM-DD."))
        try:
            self.cfg = enginelib.pick(engine, self.engines_path)
        except enginelib.EngineError as exc:
            return self._fail(str(exc))
        ready, problems, fix = enginelib.readiness(self.cfg)
        if not ready:
            result = self._fail(tr("%s is not ready for queries (%s): %s.") % (self.cfg.get("label", engine), ", ".join(problems), fix))
            if problems == ["no key"]:                          # the key is the only thing missing: the window can ask for it
                result["needs_key"] = self.cfg["id"]               # the window opens the key dialog instead of only complaining
            local = enginelib._local_address(self.cfg)
            if self.cfg["id"] == "ollama" and local and not enginelib._listening(*local):
                result["needs_setup"] = "ollama"                   # the window offers to install it, start it, download a model
            return result
        self.place, self.date, self.hint = place, date, hint.strip()
        self._place_text = place + (", " + self.hint if self.hint else "")
        self._country = hierarchy.find_country(self.hint) or hierarchy.find_country(self._place_text)     # typed by the user: Italy, Italia ...
        self._forms = list(prompts.AUTO_ORDER) if form == "auto" else [form]
        return self._ask()

    def _ask(self):
        if self._asked >= MAX_QUESTIONS:
            return self._fail(tr("Max query attempts reached without valid response. Add a Region hint or switch AI engine."))
        form = self._forms[self._form_index]
        prompt = prompts.build_prompt(self._place_text, self.date, form, hierarchy.prompt_line(self._country, hierarchy.year_of(self.date)),
                                      language=settings.interface_language() or "en")
        self._asked += 1
        self.state = "asked"
        self._last = {"prompt": prompt, "form": form, "url": None}
        label = self.cfg.get("label", self.cfg["id"])
        if self.cfg["kind"] == "browser":
            self._last["url"] = enginelib.browser_url(self.cfg, prompt)
            if self.cfg.get("copy"):                           # a page that cannot be given the question: it is copied for the user to paste
                self.message = tr("Query for «%s» on %s copied and %s launched. Paste query (Ctrl+V) and submit; once completed, copy full "
                                  "response back here and click Analyze.") % (self._place_text, self.date, label)
                return {"action": "open-url", "url": self._last["url"], "prompt": prompt, "form": form, "copy": True}
            self.message = tr("Query sent to %s for «%s» on %s (format: %s). Copy full AI response text and click Analyze.") % (
                label, self._place_text, self.date, form)
            return {"action": "open-url", "url": self._last["url"], "prompt": prompt, "form": form}
        if self.cfg["kind"] == "manual":
            self.message = tr("Query for «%s» on %s copied. Paste into AI interface, then copy response back here and click Analyze.") % (
                self._place_text, self.date)
            return {"action": "copy-prompt", "prompt": prompt, "form": form}
        self.message = tr("Querying %s (%s) regarding «%s» for date %s…") % (label, enginelib.known_model(self.cfg) or tr("model selected automatically"),
                                                                    self._place_text, self.date)
        return {"action": "call-api", "prompt": prompt, "form": form}

    def run_api(self, http=None, http_get=None):
        """Ask the API engine (blocking: the window runs this in a thread) and read the answer."""
        try:
            got = enginelib.ask(self.cfg, self._last["prompt"], http=http or enginelib.post_json, http_get=http_get)
        except enginelib.EngineError as exc:
            result = self._fail(tr("AI engine error: %s") % exc)
            if "HTTP 401" in str(exc):
                result["needs_key"] = self.cfg["id"]               # the service refused the key: offer to enter it again
            if isinstance(exc, enginelib.NeedsSetup):
                result["needs_setup"] = self.cfg["id"]             # Ollama with no model: offer to download one
            return result
        return self.receive(got["text"], model=got["model"])

    # ------------------------------------------------------------ the key of an engine
    def _engine(self, engine_id):
        return enginelib.pick(engine_id, self.engines_path)

    def key_info(self, engine_id):
        """What the key window shows: whether a key is saved, where from, how to recognise it, and where a new one would be kept."""
        cfg, store = self._engine(engine_id), keystore.get_store()
        rep = enginelib.key_report(cfg)
        return {"needed": rep["needed"], "set": bool(rep.get("set")), "where": rep.get("where"), "problems": rep.get("problems", []),
                "hint": enginelib.key_hint(cfg) if rep.get("set") else "", "store": store.name, "secure": store.secure,
                "label": cfg.get("label", engine_id), "model": enginelib.known_model(cfg), "host": enginelib.service_host(cfg)}

    def save_key(self, engine_id, key):
        """Keep a key typed in the window (keystore.StoreError is raised if it cannot be kept)."""
        key = (key or "").strip().strip("\"'").strip()
        if not key:
            raise ValueError(tr("Please enter an API key first."))
        wrong = enginelib.key_mismatch(self._engine(engine_id), key)
        if wrong:
            raise ValueError(wrong)                                       # a key of another service is not kept for this one
        keystore.get_store().set(enginelib.key_account(self._engine(engine_id)), key)
        return self.key_info(engine_id)

    def settle_model(self, engine_id, http_get=None):
        """Find the model of an engine that needs none written by hand, right after its key is saved: {'ok', 'model', 'how', 'message'}.
        The service is asked what it has (nothing is spent); what is chosen is kept and used from then on."""
        cfg = self._engine(engine_id)
        if cfg.get("kind") != "api":
            return {"ok": True, "model": "", "how": "", "message": ""}
        try:
            model, how = enginelib.settle_model(cfg, http_get=http_get)
        except enginelib.EngineError as exc:
            return {"ok": False, "model": "", "how": "", "message": str(exc)}
        return {"ok": True, "model": model, "how": how, "message": ""}

    def remove_key(self, engine_id):
        keystore.get_store().delete(enginelib.key_account(self._engine(engine_id)))
        return self.key_info(engine_id)

    def test_key(self, engine_id, key=None, http_get=None):
        """Ask the service if it accepts the key typed (or the one saved), spending nothing: {'ok', 'message'}."""
        return enginelib.check_key(self._engine(engine_id), key=key or None, http_get=http_get or enginelib.get_json)

    # ------------------------------------------------------------ reading the answer
    def receive(self, text, model=None):
        text = (text or "").strip()
        if not text:
            return self._fail(tr("No response text found. Please paste AI response text first."))
        self.meta = enginelib.provenance(self.cfg, self._last.get("form"), self._place_text, self.date, self._last.get("prompt", ""),
                                         model=model, url=self._last.get("url"))
        text, table_notes = tablelib.convert(text, self.place)                   # a table answer is read into the labelled lines: everything after is the same for every form
        rec = ingestlib.parse_structured(text)
        echo = prompts.looks_like_echo(text)
        if echo or (not rec["name"] and not rec["ambiguous"]):
            reason = (tr("AI returned unfulfilled prompt. Try adding a province in Region hint or switch AI engine.") if echo
                      else tr("Google returned no search results for this query") if prompts.looks_like_no_answer(text)
                      else tr("Text does not conform to expected response template (starts with: %s)") % text[:100].replace("\n", " "))
            if self._form_index + 1 < len(self._forms):
                self._form_index += 1
                nxt = self._ask()
                self.message = tr("%s. Fallback prompt format generated (%s).") % (reason, self._forms[self._form_index])
                return {"action": "retry", "reason": reason, "next": nxt}
            return self._fail(tr("%s; all prompt fallback formats exhausted.") % reason)
        if rec["candidates"]:
            self.candidates = ingestlib.candidate_hints(self.tree, rec["candidates"])
            self.state = "ambiguous"
            self.message = tr("Name matches multiple places; select target entity.")
            return {"action": "ambiguous", "candidates": self.candidates,
                    "best": max(range(len(self.candidates)), key=lambda i: self.candidates[i]["score"])}
        self.text, self.rec = text, rec
        elsewhere = answers.same_answer_elsewhere(self.work_dir_answers, self.place, self.date, text)
        self.saved_path = answers.save_answer(self.work_dir_answers, self.place, self.date, text, self.meta)
        self._extra_needs = [(message % args, tr(message) % args) for message, args in table_notes]
        if elsewhere:
            same = ("CONFLICTS WITH SAVED RESPONSE: text is IDENTICAL to response saved for %s. AI returned static text across "
                    "different dates; name and type accuracy cannot be verified")
            self._extra_needs.append((same % ", ".join(elsewhere), tr(same) % ", ".join(elsewhere)))     # (English, shown): the importance is read from the English
        self._extra_needs += [("CONFLICTS WITH SAVED RESPONSE: " + m, tr("CONFLICTS WITH SAVED RESPONSE: ") + m) for m in
                              ingestlib.compare_with_saved(rec, self.work_dir_answers, self.date, skip_path=self.saved_path)]
        self.levels = [{"index": i, "text": "%s | %s | %s-%s" % (c["name"], c["type"], c["from"] or "?", c["to"] or "present"), "used": True}
                       for i, c in enumerate(rec["containers"], 1)]
        return self._analyse()

    @property
    def work_dir_answers(self):
        return os.path.join(self.work_dir, "answers")

    def choose_candidate(self, index):
        """Ambiguous name: the window sends a second question with the place described exactly."""
        if self.state != "ambiguous":
            return self._fail(tr("No selectable options available."))
        self._place_text = ingestlib.refined_place(self.place, self.candidates[index]["candidate"])
        self._form_index = 0
        return self._ask()

    def ambiguous_units(self):
        """[{slot, name, type, candidates: [{handle, label, score}]}]: the units of the answer that could be several places of the tree.
        Nothing is created for them until the user has chosen."""
        return list(self.result.get("ambiguous", [])) if self.result else []

    def choose_unit(self, slot, choice):
        """choice: the handle of a place of the tree, "new" (make a new place) or "skip" (leave the level out). Analyses again."""
        self.choices[slot] = choice
        return self._analyse()

    def set_level_used(self, index, used):
        """Leave out (or bring back) one administrative level of the answer, e.g. the doubtful middle one."""
        for level in self.levels:
            if level["index"] == index:
                level["used"] = bool(used)
        return self._analyse()

    def _analyse(self):
        skip = {lv["index"] for lv in self.levels if not lv["used"]}
        self.result = ingestlib.ingest(self.tree, self.rec, self.date, self.about_range, skip, self.aliases, self.choices,
                                      country=getattr(self, "_country", None),
                                      languages=settings.wikipedia_languages())
        self.plan = planlib.make_plan(self.tree, self.result["proposals"], "window %s %s" % (self._place_text, self.date))
        self.selected = set()                                  # nothing is chosen for you: every proposal is an assumption
        self.state = "ready"
        self.message = tr("Review proposals, select acceptable modifications, and click Apply.")
        return {"action": "ready"}

    def _fail(self, message):
        self.state, self.message = "error", message
        return {"action": "error", "message": message}

    # ------------------------------------------------------------ what the window shows
    def needs(self):
        """[(text, level)] with level 'warning' or 'info'."""
        out = []

        def level(text):
            return "warning" if text.startswith(WARNING_STARTS) or "CONFLICT" in text[:20] else "info"
        english = self.result["needs"] if self.result else []
        shown = (self.result.get("needs_local") if self.result else None) or english
        if len(shown) != len(english):                                    # (they are made together: this is only a guard)
            shown = english
        for text, local in zip(english, shown):                           # the importance is read from the English, the text shown is the user's
            out.append((local, level(text)))
        for item in self._extra_needs:
            text, local = item if isinstance(item, tuple) else (item, item)
            out.append((local, level(text)))
        if self.plan and any(citations.collect(p) for p in self.plan["proposals"]):
            out.append((tr("Modified places will receive source citations linked to web repositories, including confidence ratings and "
                           "retrieval metadata."), "info"))
        return out

    def rows(self):
        if not self.plan:
            return []
        names = {p["handle"]: p["names"][0]["value"] for p in self.plan["proposals"] if p["kind"] == "add-place"}
        return [{"id": p["id"], "selected": p["id"] in self.selected, "kind": p["kind"], "basis": p["basis"],
                 "conflict": bool(p.get("conflict")), "refines": bool(p.get("refines")), "bundle": p.get("bundle"),
                 "text": describe_proposal(self.tree, p, names)} for p in self.plan["proposals"]]

    def changes(self):
        """The proposals grouped as the CHOICES they are. Steps that cannot work alone (a new place and its links; a new level put in
        between and the cut of the old direct link) are one change with one check box; a proposal that stands alone is a change by itself.
        [{id, selected, title, why, flag, basis, confidence, confidence_level, confidence_why, steps: [{id, text}]}]"""
        if not self.plan:
            return []
        names = {p["handle"]: p["names"][0]["value"] for p in self.plan["proposals"] if p["kind"] == "add-place"}
        groups, order = {}, []
        for p in self.plan["proposals"]:
            key = p["bundle"] if p.get("bundle") else self._same_name_key(p) or ("alone", p["id"])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(p)
        out = []
        unsure = self.rec["not_sure"] if self.rec else ()
        doubtful = bool(self._doubts_about_the_answer())
        for number, key in enumerate(order, 1):
            steps = groups[key]
            repeated = len(steps) > 1 and key[0] == "same-name"
            level, level_why = confidence.of_steps(steps, unsure, doubtful)
            out.append({"id": number, "selected": all(p["id"] in self.selected for p in steps), "basis": steps[0]["basis"],
                        "confidence": confidence.label(level), "confidence_level": level, "confidence_why": level_why,
                        "title": self._change_title(steps, names), "why": "" if repeated else self._why_together(steps) + self._why_needs(steps),
                        "existing": any(p.get("existing") for p in steps),
                        "flag": self._flag(steps), "show_steps": not repeated,
                        "steps": [{"id": p["id"], "text": describe_proposal(self.tree, p, names)} for p in steps]})
        return out

    @staticmethod
    def _same_name_key(p):
        """The same name of a place, written the same, that gets the same period: it is ONE choice however many times the place has it
        (a name that is in the place twice is two names to Gramps, but one thing to decide)."""
        if p["kind"] != "set-name-date" or not is_empty(p.get("old")):
            return None
        return ("same-name", p["place"], (p.get("value") or "").casefold(), (p.get("lang") or ""), describe(p.get("new")))

    @staticmethod
    def _flag(steps):
        if any(p.get("conflict") for p in steps):
            return "CONFLICT"
        if any(p.get("optional") for p in steps):
            return tr("verify official status of web source")
        if any(p["kind"] == "remove-link" for p in steps):
            return tr("disconnects place link")
        if any(p["kind"] == "set-link" for p in steps):
            return tr("modifies hierarchy link")
        if any(p.get("refines") for p in steps):
            return tr("inserts intermediate level")
        if any(p["kind"] == "rename-place" for p in steps):
            return tr("renames place")
        if any(p["kind"] == "change-type" for p in steps):
            return tr("modifies place type")
        if any(p.get("existing") for p in steps):
            return tr("modifies existing tree data")
        return tr("populates unassigned field") if all(p["kind"] in planlib.FILL_KINDS or (p["kind"] == "set-name-date" and is_empty(p.get("old")))
                                             for p in steps) else ""

    def _change_title(self, steps, names):
        def where(handle):
            return "«%s» (new)" % names.get(handle, "?") if str(handle).startswith("new:") else "«%s»" % self.tree.label(handle)
        inserted = next((p for p in steps if p["kind"] == "add-link" and p.get("refines") and p.get("above")), None)
        if inserted:
            return tr("Insert %s between %s and %s") % (where(inserted["parent"]), where(inserted["child"]), where(inserted["above"]))
        old_link = next((p for p in steps if p["kind"] == "set-link"), None)
        new_link = next((p for p in steps if p["kind"] == "add-link" and old_link and p["child"] == old_link["child"] and p["parent"] != old_link["parent"]), None)
        if old_link and new_link:                                    # a place that is put under another: a move
            return tr("Move %s from %s to %s") % (where(old_link["child"]), where(old_link["parent"]), where(new_link["parent"]))
        made = [p for p in steps if p["kind"] == "add-place"]
        if made:
            more = len(steps) - len(made)
            return tr("Create place «%s»%s") % (made[0]["names"][0]["value"], tr(" and place it in the hierarchy") if more else "")
        if len(steps) > 1 and all(p["kind"] == "set-name-date" for p in steps):
            return tr("%s [name occurs %d times in this place; period assigned to all occurrences]") % (describe_proposal(self.tree, steps[0], names), len(steps))
        return describe_proposal(self.tree, steps[0], names)

    @staticmethod
    def _why_together(steps):
        if len(steps) < 2:
            return ""
        reasons = []
        if any(p.get("refines") for p in steps):
            reasons.append(tr("new link placed before the existing link, because Gramps uses the first link that fits the date; the existing link is retained for the remaining years"))
        if any(p["kind"] == "set-link" for p in steps) and any(p["kind"] == "add-link" for p in steps):
            reasons.append(tr("link to previous place retained strictly for years preceding new link start date"))
        if any(p["kind"] == "add-place" for p in steps):
            reasons.append(tr("target place entity must exist prior to hierarchy linking"))
        return tr("These modification steps are interdependent: ") + "; ".join(reasons) + "." if reasons else tr("These modification steps are interdependent.")

    @staticmethod
    def _why_needs(steps):
        if not any(p.get("requires_key") for p in steps):
            return ""
        return " " + tr("Requires the new link: selecting this option automatically checks the dependent link.")

    def _enforce(self, selecting):
        """A step that needs another one (a disconnect needs the new link that replaces it): chosen, it brings the other; the other unchosen, it goes."""
        by_key = {p["key"]: p["id"] for p in self.plan["proposals"] if p.get("key")}
        for p in self.plan["proposals"]:
            needed = by_key.get(p.get("requires_key"))
            if needed is None or p["id"] not in self.selected:
                continue
            if selecting:
                self.selected.add(needed)
            elif needed not in self.selected:
                self.selected.discard(p["id"])

    def toggle(self, proposal_id):
        """Check or uncheck a proposal; a new place with its links goes together."""
        row = next((p for p in self.plan["proposals"] if p["id"] == proposal_id), None)
        if row is None:
            return
        group = {p["id"] for p in self.plan["proposals"] if row.get("bundle") and p.get("bundle") == row["bundle"]} or {proposal_id}
        if proposal_id in self.selected:
            self.selected -= group
            self._enforce(False)
        else:
            self.selected |= group
            self._enforce(True)
            self._drop_rivals(group)

    def toggle_change(self, change_id):
        """Check or uncheck a whole change (all its steps)."""
        change = next((c for c in self.changes() if c["id"] == change_id), None)
        if change:
            ids = {st["id"] for st in change["steps"]}
            if ids <= self.selected:
                self.selected -= ids
                self._enforce(False)
            else:
                self.selected |= ids
                self._enforce(True)
                self._drop_rivals(ids)

    def select_all(self, include_conflicts=False):
        """What the window selects by itself: additions and the filling of empty fields. A change to data that exists is chosen one by one."""
        self.selected = {p["id"] for p in self.plan["proposals"] if (include_conflicts or not p.get("conflict")) and not p.get("existing")
                         and not p.get("optional")}                       # (a site of unknown kind is chosen by the user, never by the window)

    def select_existing(self):
        """The user's own act: choose every change to data that exists (with the steps that these need).

        A change in CONFLICT (it replaces a different date) is not chosen here: it is checked one by one. Returns what happened, so that the window
        can say it: {"chosen": how many were chosen now, "already": how many were chosen before, "conflicts": how many were left out for a conflict}."""
        existing = [p for p in self.plan["proposals"] if p.get("existing")]
        sure = {p["id"] for p in existing if not p.get("conflict")}
        already = len(sure & self.selected)
        self.selected |= sure
        self._enforce(True)
        return {"chosen": len(sure) - already, "already": already, "conflicts": sum(1 for p in existing if p.get("conflict"))}

    def selectable_by_all(self):
        """(ids that "Select all" chooses, {id: why it is left for the user}).

        Left for the user: a change in CONFLICT with the tree, a web link of a site of unknown kind, and a proposal that has a rival (the other one
        decides the same thing differently: one or the other, never both). A step is as selectable as the step it needs, and a bundle is chosen whole."""
        proposals = self.plan["proposals"]
        rival = planlib.rivals(proposals)
        left = {}
        for p in proposals:
            if p.get("conflict"):
                left[p["id"]] = "conflict"
            elif p.get("optional"):
                left[p["id"]] = "optional"
            elif rival.get(p["id"]):
                left[p["id"]] = "exclusive"
        by_key = {p["key"]: p["id"] for p in proposals if p.get("key")}
        changed = True
        while changed:
            changed = False
            for p in proposals:
                if p["id"] in left:
                    continue
                if by_key.get(p.get("requires_key")) in left or (p.get("bundle") and any(q["id"] in left and q.get("bundle") == p["bundle"] for q in proposals)):
                    left[p["id"]] = "needs"
                    changed = True
        return {p["id"] for p in proposals if p["id"] not in left}, left

    def all_selected(self):
        """True when everything that "Select all" would choose is chosen (the button then clears)."""
        if not self.plan:
            return False
        chosen, _left = self.selectable_by_all()
        return bool(chosen) and chosen <= self.selected

    def toggle_all(self):
        """The user's own act, one button: choose everything that can be chosen, or, when all of it is chosen already, uncheck everything.

        Returns {"action": "selected" or "cleared", "chosen": how many were chosen now, "conflicts", "optional", "exclusive", "needs": how many were
        left for the user (see selectable_by_all)}."""
        chosen, left = self.selectable_by_all()
        counts = {key: sum(1 for w in left.values() if w == why) for key, why in (("conflicts", "conflict"), ("optional", "optional"), ("exclusive", "exclusive"), ("needs", "needs"))}
        if chosen and chosen <= self.selected:
            self.selected = set()
            return dict(counts, action="cleared", chosen=0)
        new = chosen - self.selected
        self.selected |= chosen
        self._enforce(True)
        return dict(counts, action="selected", chosen=len(new))

    def _drop_rivals(self, ids):
        """Chosen by hand: the proposals that decide the same thing differently are unchosen (one or the other, never both)."""
        rival = planlib.rivals(self.plan["proposals"])
        for i in ids:
            self.selected -= rival.get(i, set())
        self._enforce(False)

    def has_existing(self):
        return bool(self.plan) and any(p.get("existing") for p in self.plan["proposals"])

    def clear_selection(self):
        self.selected = set()

    def selected_proposals(self):
        return planlib.select(self.plan, ids=set(self.selected)) if self.plan else []

    def preview(self):
        """What Gramps would display for an event on that date at this place, for the proposals checked now: (text, how it ends)."""
        names, end = ingestlib.preview_for(self.tree, self.selected_proposals(), self.result["child"], self.date, self.about_range)
        return ", ".join(names), end

    # ------------------------------------------------------------ coordinates from Wikidata
    def coordinate_targets(self, limit=6):
        """What to ask Wikidata: [{key, name, region, near}] for the place and the places of its chain that lack coordinates, or
        whose coordinates come only from the answer. Cheap and local: the asking itself (geo.lookup_many) is slow, it is the network."""
        r = self.result
        if not r:
            return []
        props, tree = r["proposals"], self.tree
        names = {p["handle"]: p["names"][0]["value"] for p in props if p["kind"] == "add-place"}
        parent_of = {}
        for p in props:
            if p["kind"] == "add-link":
                parent_of.setdefault(p["child"], p["parent"])

        def label(key):
            if key in names:
                return names[key]
            held = tree.places.get(key)
            return namelib.plain_name(held["name"].get("value"), (held["type"] or {}).get("value"), (held["type"] or {}).get("string", "")) if held else ""

        def region(key):
            up = parent_of.get(key) or next((ref["ref"] for ref in (tree.places.get(key) or {}).get("refs", [])), None)
            return label(up) if up else None
        main = r["child"]
        ai = self.rec["coordinates"] if self.rec else None
        targets, seen = [], set()
        for number, p in enumerate(props):
            if p["kind"] == "set-coordinates":
                seen.add(p["place"])
                if not p.get("source_note"):                      # a note means Wikidata was asked about it already
                    targets.append({"key": "prop:%d" % number, "name": label(p["place"]), "region": region(p["place"]),
                                    "near": (float(p["lat"]), float(p["lon"])), "main": p["place"] == main})
            elif p["kind"] == "add-place":
                seen.add(p["handle"])
                if not p.get("source_note"):
                    near = (float(p["lat"]), float(p["lon"])) if p.get("lat") and p["handle"] == main else None
                    targets.append({"key": "prop:%d" % number, "name": p["names"][0]["value"], "region": region(p["handle"]), "near": near,
                                    "main": p["handle"] == main})
        for u in r.get("units", []) + [{"handle": main, "name": ""}]:
            held = tree.places.get(u.get("handle") or "")
            if held and (held["type"] or {}).get("value") == 1:
                continue                                          # the coordinates of a country mean nothing
            if held and u["handle"] not in seen and not (str(held["lat"]).strip() or str(held["lon"]).strip()):
                seen.add(u["handle"])
                targets.append({"key": "unit:%s" % u["handle"], "name": label(u["handle"]), "region": region(u["handle"]),
                                "near": tuple(ai) if (u["handle"] == main and ai) else None, "main": u["handle"] == main})
        return [t for t in targets if t["name"]][:limit]

    def apply_coordinates(self, findings):
        """Use what Wikidata answered (geo.lookup_many): its coordinates replace those of the answer, with the basis 'evidence' and the
        statement as source; a place that lacks them and has none from the answer gets a proposal of its own; what Wikidata could not
        settle keeps the answer's coordinates, and it is said. Proposals keep their numbers, so nothing checked is lost."""
        if not self.result:
            return 0
        props, used = self.result["proposals"], 0
        for key, f in findings.items():
            kind, _, ref = key.partition(":")
            if kind == "prop":
                p = props[int(ref)]
                name = p["names"][0]["value"] if p["kind"] == "add-place" else self.tree.name_of(p["place"])
            else:
                p, name = None, self.tree.name_of(ref)
            if not f.get("found"):
                self._extra_needs.append(tr("Wikidata: %s: %s%s") % (name, f.get("reason", tr("no results found")),
                                                                 tr("; coordinates from AI response retained for review") if p is not None else ""))
                continue
            used += 1
            self._links_from_wikidata(p, ref, f)
            evidence = [{"source": "wikidata", "url": f["url"], "claim": "P625 (coordinates) of %s" % f["label"]}]
            note = "Wikidata %s «%s»" % (f["qid"], f["label"])
            if p is not None:
                p["lat"], p["lon"], p["basis"], p["evidence"], p["source_note"] = f["lat"], f["lon"], "evidence", evidence, note
            else:
                props.append({"kind": "set-coordinates", "confidence": "evidence", "basis": "evidence", "conflict": False, "origin": "wikidata",
                              "evidence": evidence, "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {}, "index": None,
                              "place": ref, "lat": f["lat"], "lon": f["lon"], "source_note": note})
            self._extra_needs.append(tr("Wikidata: %s: coordinates %s, %s from %s%s") % (
                name, f["lat"], f["lon"], f["qid"], tr(" (%.1f km from the location returned in the answer)") % f["km"] if f.get("km") is not None else ""))
        self.plan = planlib.make_plan(self.tree, props, "window %s %s" % (self._place_text, self.date))
        self.message = tr("Wikidata queried: %d place(s) populated with coordinates.") % used
        return used

    def _links_from_wikidata(self, prop, ref, finding):
        """The Wikidata item of the main place and its Wikipedia articles in the languages of the user are links of that place (LK1-LK5):
        in the new place itself, or as proposals of their own for a place of the tree. Nothing is added for any other place of the chain."""
        main = self.result["child"]
        if finding.get("articles") is None or not rules.on("WL"):
            return
        place = prop["handle"] if prop is not None and prop["kind"] == "add-place" else prop["place"] if prop is not None else ref
        if place != main:
            return
        props = self.result["proposals"]
        if prop is not None and prop["kind"] == "add-place":
            have = [u["path"] for u in prop.get("urls", [])]
        else:
            have = list(self.tree.places[main]["urls"]) if main in self.tree.places else []
            have += [q["path"] for q in props if q["kind"] == "add-url" and q["place"] == main]
        offered, _left = linklib.select_links([finding["url"]] + list(finding["articles"]), have, settings.wikipedia_languages())
        evidence = [{"source": "wikidata", "url": finding["url"], "claim": "the Wikidata item and its articles for %s" % finding["label"]}]
        for item in offered:
            if prop is not None and prop["kind"] == "add-place":
                prop.setdefault("urls", []).append({"path": item["path"], "type": "Web Home"})
            else:
                props.append(ingestlib.url_proposal(main, item, evidence, origin="wikidata", basis="evidence"))

    # ------------------------------------------------------------ writing
    def _doubts_about_the_answer(self):
        """The notes of the analysis (in English) that say the answer as a whole cannot be trusted: it contradicts itself, or it is the same text
        that was saved for another date. They lower the confidence of the citations by one level."""
        texts = list(self.result["needs"]) if self.result else []
        texts += [item[0] if isinstance(item, tuple) else item for item in self._extra_needs]
        return [t for t in texts if t.startswith("CONFLICTS WITH SAVED RESPONSE")]

    def check(self, db):
        """A dry run: which of the chosen proposals would be skipped, and why."""
        return writer.apply_proposals(db, self.selected_proposals(), dry_run=True)

    def apply(self, db):
        """Write the chosen proposals in ONE transaction (one Undo). Returns the result of each."""
        proposals = self.selected_proposals()
        if not proposals:
            raise ValueError(tr("No items selected."))
        provenance = citations.provenance_record(self.meta, place=self._place_text, date=self.date, answer_file=getattr(self, "saved_path", "") or "",
                                                 not_sure=", ".join(sorted(self.rec["not_sure"])) if self.rec else "",
                                                 doubts=self._doubts_about_the_answer(), main=self.result["child"] if self.result else "",
                                                 chain=[u["handle"] for u in (self.result or {}).get("units", []) if u.get("handle")])
        results = writer.apply_proposals(db, proposals, dry_run=False, message="PlaceCompleter %s" % self._place_text, provenance=provenance)
        self.applied = results
        self.state = "applied"
        written = sum(r["status"] == "applied" for r in results)
        skipped = [r for r in results if r["status"] == "skipped"]
        cited = {t for r in results for t in r.get("cited", [])}
        left_out = {t for r in results for t in r.get("not_cited", [])}
        self.message = tr("%d change(s) applied in a single batch (reversible via Edit > Undo)%s%s%s.") % (
            written, tr("; %d skipped: %s") % (len(skipped), "; ".join(r["reason"] for r in skipped)) if skipped else "",
            tr("; %d source(s) cited on modified places") % len(cited) if cited else "",
            tr("; %d secondary source(s) omitted (max %d citations per place per run)") % (len(left_out), citations.MAX_CITATIONS) if left_out else "")
        return results

    def refresh(self, tree):
        """After a write the tree has changed: read it again (the window passes Tree.from_db(db))."""
        self.tree = tree
