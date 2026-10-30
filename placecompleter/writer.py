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
"""Write selected proposals into an open Gramps database.

Everything happens in ONE transaction, so Gramps' Undo reverts all of it in one step.
Before a proposal is written, the current state is compared with what the analysis
saw (same parent at that position, same old date, same name); a proposal whose
target changed in the meantime is skipped, never forced.
The Gramps library is imported only here, so the engine stays usable without it.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import rules
from .dates import is_empty
from .i18n import _ as tr


def date_from_dict(d):
    from gramps.gen.lib import Date
    date = Date()
    if is_empty(d):
        return date
    date.set(quality=d.get("quality", 0), modifier=d["modifier"], calendar=d.get("calendar", 0),
             value=tuple(d["dateval"]), text=d.get("text") or "")
    return date


def same_date(date, d):
    if is_empty(d):
        return date.is_empty()
    return (date.modifier == d["modifier"] and tuple(date.dateval) == tuple(d["dateval"])
            and date.quality == d.get("quality", 0))


def _check_link(db, p):
    place = db.get_place_from_handle(p["child"])
    if place is None:
        return None, tr("target place entity no longer exists in tree")
    refs = place.get_placeref_list()
    if p["kind"] == "add-link":
        if not db.has_place_handle(p["parent"]):
            return None, tr("parent place entity no longer exists in tree")
        for r in refs:
            if r.ref == p["parent"] and same_date(r.get_date_object(), p["new"]):
                return None, tr("hierarchy link already exists")
        return place, ""
    if p["index"] >= len(refs) or refs[p["index"]].ref != p["parent"]:
        return None, tr("parent hierarchy link position has shifted")
    if p["kind"] == "move-link" and (p["position"] >= p["index"] or refs[p["position"]].ref != p.get("above")):
        return None, tr("hierarchy link sequence has been modified")
    if not same_date(refs[p["index"]].get_date_object(), p["old"]):
        return None, tr("link date range was modified after analysis phase")
    return place, ""


def _get_place(db, handle):
    """The place, or None when it is gone (Gramps 6 raises an error for a handle that is not there; older versions gave None)."""
    return db.get_place_from_handle(handle) if db.has_place_handle(handle) else None


def _check_name(db, p):
    place = _get_place(db, p["place"])
    if place is None:
        return None, tr("target place entity no longer exists in tree")
    names = [place.get_name()] + list(place.get_alternative_names())
    if p["kind"] == "add-name":
        for n in names:
            if (n.get_value() == p["value"] and (n.get_language() or "") == p["lang"]
                    and same_date(n.get_date_object(), p["new"])):
                return None, tr("place name already exists")
        return place, ""
    if p["index"] >= len(names) or names[p["index"]].get_value() != p["value"]:
        return None, tr("place name position has shifted")
    if not same_date(names[p["index"]].get_date_object(), p["old"]):
        return None, tr("place name date range was modified after analysis phase")
    return place, ""


def _check_url(db, p):
    """A web link is added only when the place does not have the same page (in any form) now."""
    from .links import normalize
    place = _get_place(db, p["place"])
    if place is None:
        return None, tr("target place entity no longer exists in tree")
    if any(normalize(u.get_path()) == normalize(p["path"]) for u in place.get_url_list()):
        return None, tr("hierarchy link already exists")
    return place, ""


FILL_KINDS = ("set-coordinates", "set-name-language", "set-type", "rename-place", "change-type")


def _check_fill(db, p):
    """The field must still be empty: what somebody wrote in the meantime is never overwritten."""
    from gramps.gen.lib import PlaceType
    place = _get_place(db, p["place"])
    if place is None:
        return None, tr("target place entity no longer exists in tree")
    if p["kind"] == "set-coordinates":
        if (place.get_latitude() or "").strip() or (place.get_longitude() or "").strip():
            return None, tr("place already contains spatial coordinates")
    elif p["kind"] == "rename-place":
        if place.get_name().get_value() != p["value"]:
            return None, tr("place name was modified after analysis phase")
    elif p["kind"] == "change-type":                                  # the type must still be the one that the analysis saw
        now = place.get_type()
        if now.value != p["old_type_value"] or (p["old_type_value"] == 0 and now.string != p.get("old_type_string", "")):
            return None, tr("place type was modified after analysis phase")
    elif p["kind"] == "set-name-language":
        names = [place.get_name()] + list(place.get_alternative_names())
        if p["index"] >= len(names) or names[p["index"]].get_value() != p["value"]:
            return None, tr("place name position has shifted")
        if names[p["index"]].get_language():
            return None, tr("place name already has a language tag assigned")
    else:
        now = place.get_type()
        # (for an unknown type Gramps' .string is the word "Unknown": only the value counts; a type of the user's own with no text is no type, as in the Type column)
        if not (now.value == PlaceType.UNKNOWN or (now.value == PlaceType.CUSTOM and not (now.string or "").strip())):
            return None, tr("place entity already has an administrative type assigned")
    return place, ""


def _existing_with_url(db, path):
    from .links import normalize
    wanted = normalize(path)
    for handle in db.get_place_handles():
        place = db.get_place_from_handle(handle)
        if any(normalize(u.get_path()) == wanted for u in place.get_url_list()):
            return handle
    return None


def apply_proposals(db, proposals, dry_run=True, message="PlaceCompleter", provenance=None):
    """Apply the proposals; return a list of {"id", "status", "reason"} (and "cited": the sources cited, when provenance is given).

    provenance (citations.provenance_record): when given, each place that is touched also gets a citation to the sources of its proposals,
    in the same transaction.

    New places are created first (a place whose Wikidata link is already in the tree is reused);
    links that point at a new place are written with its real handle.
    """
    from gramps.gen.db import DbTxn
    from gramps.gen.lib import Place, PlaceName, PlaceRef, Url, UrlType
    results, work, created = [], [], {}
    for p in [q for q in proposals if q["kind"] == "add-place"]:
        urls = [u["path"] for u in p.get("urls", [])]
        existing = _existing_with_url(db, urls[0]) if urls else None
        if existing:
            created[p["handle"]] = existing
            results.append({"id": p["id"], "status": "skipped", "reason": tr("a place with this web link already exists")})
        else:
            work.append((p, None))
            results.append({"id": p["id"], "status": "dry-run" if dry_run else "applied", "reason": ""})
    new_handles = {p["handle"] for p, _ in work}
    for p in [q for q in proposals if q["kind"] != "add-place"]:
        if str(p.get("parent", "")).startswith("new:") and p["parent"] not in new_handles and p["parent"] not in created:
            results.append({"id": p["id"], "status": "skipped", "reason": tr("required new place entity is excluded from current selection")})
            continue
        probe = dict(p)
        for k in ("child", "parent"):
            if str(probe.get(k, "")).startswith("new:"):
                probe[k] = created.get(probe[k], "NEW")
        if str(p.get("place", "")).startswith("new:"):                         # a name (or another field) of a place that is made now
            if p["place"] in new_handles:
                work.append((p, None))                                         # nothing to check: the place is made in the same transaction
                results.append({"id": p["id"], "status": "dry-run" if dry_run else "applied", "reason": ""})
                continue
            if p["place"] not in created:
                results.append({"id": p["id"], "status": "skipped", "reason": tr("required new place entity is excluded from current selection")})
                continue
            probe["place"] = created[p["place"]]                               # the place was found in the tree by its link: check it as it is
        if str(p.get("child", "")).startswith("new:") and p["child"] in new_handles:
            work.append((p, None))
            results.append({"id": p["id"], "status": "dry-run" if dry_run else "applied", "reason": ""})
            continue
        if str(p.get("parent", "")).startswith("new:") and p["parent"] in new_handles and p["kind"] == "add-link":
            place = db.get_place_from_handle(p["child"]) if p.get("child") and not str(p["child"]).startswith("new:") else None
            ok = place is not None
            results.append({"id": p["id"], "status": ("dry-run" if dry_run else "applied") if ok else "skipped",
                            "reason": "" if ok else tr("target place entity no longer exists in tree")})
            if ok:
                work.append((p, None))
            continue
        place, reason = (_check_fill if p["kind"] in FILL_KINDS else _check_name if p["kind"] in ("add-name", "set-name-date") else _check_url if p["kind"] == "add-url" else _check_link)(db, probe)
        if place is None:
            results.append({"id": p["id"], "status": "skipped", "reason": reason})
        else:
            work.append((p, place))
            results.append({"id": p["id"], "status": "dry-run" if dry_run else "applied", "reason": ""})
    if dry_run or not work:
        return results
    with DbTxn("%s: %d change(s)" % (message, len(work)), db) as trans:
        for p, _ in [w for w in work if w[0]["kind"] == "add-place"]:
            place = Place()
            first = p["names"][0]
            name = PlaceName()
            name.set_value(first["value"])
            name.set_language(first["lang"])
            name.set_date_object(date_from_dict(first["date"]))
            place.set_name(name)
            for extra in p["names"][1:]:
                alt = PlaceName()
                alt.set_value(extra["value"])
                alt.set_language(extra["lang"])
                alt.set_date_object(date_from_dict(extra["date"]))
                place.add_alternative_name(alt)
            if p.get("type_string"):
                place.set_type((0, p["type_string"]))
            else:
                place.set_type(p["type_value"] if p["type_value"] is not None else -1)
            place.set_latitude(p.get("lat", ""))
            place.set_longitude(p.get("lon", ""))
            for u in p.get("urls", []):
                url = Url()
                url.set_path(u["path"])
                url.set_type(UrlType(UrlType.CUSTOM))
                url.get_type().set_from_xml_str(u.get("type", "Web Home"))
                place.add_url(url)
            created[p["handle"]] = db.add_place(place, trans)
        others = [w for w in work if w[0]["kind"] != "add-place"]
        # The links of a place are changed by their position in the list: first the edits that keep the positions, then the removals (from the end), and last
        # the insertions (their position is moved by the removals before it), so that no step moves the position that another one was made for.
        others.sort(key=lambda w: (0 if w[0]["kind"] not in ("add-link", "remove-link", "move-link") else 1 if w[0]["kind"] == "remove-link" else 2,
                                   -(w[0].get("index") or 0) if w[0]["kind"] == "remove-link" else 0))
        removed = {}
        for p, _stale in others:
            child = created.get(p.get("child"), p.get("child"))
            parent = created.get(p.get("parent"), p.get("parent"))
            place = db.get_place_from_handle(child if "child" in p else created.get(p["place"], p["place"]))
            new = date_from_dict(p["new"])
            if p["kind"] in ("end-link", "set-link"):
                place.get_placeref_list()[p["index"]].set_date_object(new)
            elif p["kind"] == "remove-link":                                  # only the link goes: both places stay
                refs = list(place.get_placeref_list())
                refs.pop(p["index"])
                place.set_placeref_list(refs)
                removed.setdefault(child, []).append(p["index"])
            elif p["kind"] == "move-link":                                    # before the link that Gramps would find first; nothing is removed
                refs = list(place.get_placeref_list())
                refs.insert(min(p["position"], len(refs) - 1), refs.pop(p["index"]))
                place.set_placeref_list(refs)
            elif p["kind"] == "add-link":
                ref = PlaceRef()
                ref.ref = parent
                ref.set_date_object(new)
                if p.get("position") is None:
                    place.add_placeref(ref)
                else:                                                     # before the direct link: Gramps uses the first one that fits the date
                    refs = list(place.get_placeref_list())
                    where = p["position"] - sum(1 for i in removed.get(child, []) if i < p["position"])
                    refs.insert(min(where, len(refs)), ref)
                    place.set_placeref_list(refs)
            elif p["kind"] == "add-url":
                url = Url()
                url.set_path(p["path"])
                url.set_type(UrlType(UrlType.CUSTOM))
                url.get_type().set_from_xml_str("Web Home")
                place.add_url(url)
            elif p["kind"] == "set-coordinates":
                place.set_latitude(p["lat"])
                place.set_longitude(p["lon"])
            elif p["kind"] == "rename-place":
                name = place.get_name()
                if p.get("keep_old") and not any(a.get_value() == p["value"] for a in place.get_alternative_names()):
                    old_name = PlaceName()                             # the old name stays, as an alternative name, with its language and period
                    old_name.set_value(name.get_value())
                    old_name.set_language(name.get_language())
                    old_name.set_date_object(name.get_date_object())
                    place.add_alternative_name(old_name)
                name.set_value(p["new_value"])
            elif p["kind"] == "set-name-language":
                ([place.get_name()] + list(place.get_alternative_names()))[p["index"]].set_language(p["lang"])
            elif p["kind"] in ("set-type", "change-type"):
                place.set_type((0, p["type_string"]) if p.get("type_string") else p["type_value"])
            elif p["kind"] == "add-name":
                alt = PlaceName()
                alt.set_value(p["value"])
                alt.set_language(p["lang"])
                alt.set_date_object(new)
                place.add_alternative_name(alt)
            else:
                names = [place.get_name()] + list(place.get_alternative_names())
                names[p["index"]].set_date_object(new)
            db.commit_place(place, trans)
        if provenance is not None:
            _cite_places(db, trans, work, created, results, provenance)
    return results


def _names_of(db, handle):
    place = _get_place(db, handle)
    if place is None:
        return []
    return [place.get_name().get_value()] + [n.get_value() for n in place.get_alternative_names()]


def _route_sources(db, by_place, main, chain=()):
    """{place: {url: info}} with every source of the AI on the place(s) that it is about, and on the main place when it is about none of them.
    A source that is about a place of the chain that this run does not change is not cited. What Wikidata says (a statement about one place)
    stays where it was said."""
    from . import citations
    names = {key: _names_of(db, key) for key in by_place}
    main_names = _names_of(db, main)
    untouched = {h: _names_of(db, h) for h in chain if h not in by_place and db.has_place_handle(h)}
    routed = {}
    for key, sources in by_place.items():
        for url, info in sources.items():
            if info["wikidata"]:
                targets = [key]
            elif citations.about(url, main_names):                            # about the place of the question: there, even when nothing else was written to it
                targets = [main]
            else:
                # the primary name of a place decides before its other names (a province often carries the name of its city as an alternative name)
                targets = [k for k in names if citations.about(url, names[k][:1])] or [k for k in names if citations.about(url, names[k])]
                if not targets and any(citations.about(url, n) for n in untouched.values()):
                    continue                                                  # about a place that is not written now
                targets = targets or [main]
            for target in targets:
                citations.merge(routed.setdefault(target, {}), {url: info})
    return routed


def _cite_places(db, trans, work, created, results, provenance):
    """A citation for every source of what was written, on the place it was written to (a link is written to its child)."""
    from . import citations
    by_place, ids, cache = {}, {}, {}
    for p, _stale in work:
        key = created.get(p["handle"]) if p["kind"] == "add-place" else created.get(p.get("child"), p.get("child")) if "child" in p else created.get(p["place"], p["place"])
        evidence = citations.collect(p)
        if key and evidence:
            citations.merge(by_place.setdefault(key, {}), evidence)
            ids.setdefault(key, []).append(p["id"])
    main = created.get(provenance.get("main"), provenance.get("main")) if provenance.get("main") else None
    if main and rules.on("CT5") and db.has_place_handle(main):                                # each source goes to the place that it is about (see citations.py)
        by_place = _route_sources(db, by_place, main, [created.get(h, h) for h in provenance.get("chain", ())])
    for key, sources in by_place.items():
        left_out = []
        titles = citations.attach(db, trans, key, sources, provenance, cache, left_out=left_out)
        for r in results:
            if r["id"] in ids.get(key, ()):
                r.setdefault("cited", [])
                r["cited"] += [t for t in titles if t not in r["cited"]]
                if left_out:
                    r.setdefault("not_cited", [])
                    r["not_cited"] += [t for t in left_out if t not in r["not_cited"]]
