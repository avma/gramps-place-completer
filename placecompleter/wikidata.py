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
"""Wikidata as a source of dated place links, names and lifetimes.

The client keeps every answer in a JSON cache and, only when asked, queries the
public API politely (a pause between calls, back-off on 429). Without network it
serves whatever the cache holds, which is how the tests run.

What is taken from Wikidata, and how it is trusted:
  - P131 (located in) with a start and/or end time, rank "deprecated" ignored:
    a dated parent link between two places that BOTH resolve to a place of the tree.
  - P1448 (official name) with a period: a dated name.
  - P571 / P576 (inception / dissolution): the lifetime of an entity, used to
    extend the period of a name the tree already has (the same name is assumed).
A tree place is tied to an entity only when the match is unambiguous: equal name
(any language) and, when the tree has coordinates, within 50 km. Ambiguity is
reported, never guessed.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import datetime
import email.utils
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import HOMEPAGE, __version__, packs

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "PlaceCompleter/%s (Gramps addon; %s)" % (__version__, HOMEPAGE)
LANGUAGES = ("en", "hu", "sr", "de", "ro", "uk", "sk", "cs", "pl", "hr", "sl", "he", "ru")
# Gramps place types that are addresses, not places with a history: STREET, BUILDING, NUMBER.
# The type is only a HINT: it is typed by hand and can be wrong (a county chosen as "Building").
ADDRESS_TYPES = (7, 19, 20)
STREET_WORDS = {"utca", "ut", "u", "ter", "korut", "sor", "koz", "strada", "str", "calea", "bulevardul", "bd", "piata",
                "aleea", "gasse", "strasse", "platz", "ulica", "ul", "street", "road", "avenue", "square", "boulevard"}
PLACE_TYPE_NAMES = {1: "Country", 2: "State", 3: "County", 4: "City", 8: "Province", 9: "Region", 12: "District",
                    14: "Municipality", 15: "Town", 16: "Village", 17: "Hamlet", 7: "Street", 19: "Building", 20: "Number"}
TYPE_WORDS = (("sovereign state", 1), ("country", 1), ("county", 3), ("district", 12), ("municipality", 14),
              ("city", 4), ("town", 15), ("village", 16), ("hamlet", 17), ("province", 8), ("region", 9), ("state", 2))


def looks_like_address(name):
    """A street address by its name: a house number, with or without a street word."""
    tokens = [packs.fold(t).strip(".,") for t in re.split(r"\s+", name or "") if t]
    has_digit = any(re.search(r"\d", t) for t in tokens)
    has_street_word = any(t in STREET_WORDS for t in tokens)
    ends_with_number = bool(tokens) and bool(re.fullmatch(r"\d+[a-z]?(/\d+)?", tokens[-1])) and len(tokens) > 1
    return (has_digit and has_street_word) or ends_with_number


def is_address(tree, handle):
    """Skip a Wikidata lookup only when the place BEHAVES like an address.

    It must be a leaf (no place has it as a parent) and either have an address-like name
    or be typed as an address with a digit in its name. The type alone never decides.
    """
    if any(r.get("ref") == handle for p in tree.places.values() for r in p["refs"]):
        return False
    names = [n.get("value") or "" for n in tree.all_names(handle)]
    typed = tree.places[handle]["type"].get("value") in ADDRESS_TYPES
    return any(looks_like_address(n) for n in names) or (typed and any(re.search(r"\d", n) for n in names))


def type_from_classes(labels_en):
    for label in labels_en:
        low = (label or "").lower()
        for word, value in TYPE_WORDS:
            if word in low:
                return value
    return None


class Client:
    def __init__(self, cache_path=None, fetch=None, pause=3.0, languages=LANGUAGES):
        self.cache_path, self.fetch, self.pause, self.languages = cache_path, fetch, pause, languages
        self.answers, self.entity_cache, self.entity_langs, self.network_calls = {}, {}, {}, 0
        if cache_path and os.path.exists(cache_path):
            self.load(cache_path)

    @staticmethod
    def _langs_of(url):
        m = re.search(r"[?&]languages=([^&]+)", url)
        return set(urllib.parse.unquote(m.group(1)).split("|")) if m else set()

    def _remember(self, url, answer):
        if isinstance(answer, dict) and "entities" in answer:
            for qid, ent in answer["entities"].items():
                self.entity_cache[qid] = ent
                self.entity_langs[qid] = self.entity_langs.get(qid, set()) | self._langs_of(url)

    def load(self, path):
        with open(path, encoding="utf-8") as fh:
            for url, answer in json.load(fh).items():
                self.answers[url] = answer
                self._remember(url, answer)

    def save(self):
        if self.cache_path:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(self.answers, fh, ensure_ascii=False, separators=(",", ":"))

    def _get(self, url):
        if url in self.answers:
            return self.answers[url]
        if self.fetch is None:
            return None
        if self.network_calls:
            time.sleep(self.pause)
        answer = self.fetch(url)
        self.network_calls += 1
        if answer is not None:
            self.answers[url] = answer
        return answer

    def search(self, text, language="en", limit=5):
        url = "%s?action=wbsearchentities&search=%s&language=%s&limit=%d&format=json" % (
            API, urllib.parse.quote(text), language, limit)
        return (self._get(url) or {}).get("search", [])

    def sitelinks(self, qid, languages):
        """{'sitelinks': {'hewiki': {'title': ...}}} for the Wikipedia languages asked (one small request; {} when Wikidata has none)."""
        sites = "%7C".join(sorted("%swiki" % l.replace("-", "_") for l in languages))
        url = "%s?action=wbgetentities&ids=%s&props=sitelinks&sitefilter=%s&format=json" % (API, qid, sites)
        answer = self._get(url) or {}
        return (answer.get("entities") or {}).get(qid) or {}

    def entities(self, ids):
        wanted = set(self.languages)
        missing = [i for i in ids if i not in self.entity_cache or not wanted <= self.entity_langs.get(i, wanted)]
        for start in range(0, len(missing), 40):
            batch = missing[start:start + 40]
            url = "%s?action=wbgetentities&ids=%s&props=labels%%7Cclaims&languages=%s&format=json" % (
                API, "%7C".join(batch), "%7C".join(self.languages))
            answer = self._get(url)
            if answer:
                self._remember(url, answer)
        return {i: self.entity_cache[i] for i in ids if i in self.entity_cache}


FETCH_TIMEOUT = 30                                   # seconds for one question to Wikidata
MAX_RETRY_WAIT = 60                                   # seconds: the longest that a server may ask the program to wait


def retry_after(header, default):
    """The seconds to wait that a Retry-After header asks for: a number of seconds or a date (both are allowed), `default` when it says nothing that can be read,
    and never more than MAX_RETRY_WAIT (nor less than 0)."""
    wait = default
    if header:
        try:
            wait = float(header)
        except ValueError:
            try:
                when = email.utils.parsedate_to_datetime(header)
                wait = (when - datetime.datetime.now(when.tzinfo)).total_seconds()
            except (TypeError, ValueError, IndexError):
                wait = default
    return max(0.0, min(float(wait), MAX_RETRY_WAIT))


def urllib_fetch(url, retries=3):
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:                     # nosec B310 (an https address of Wikidata, built here)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 429:
                time.sleep(retry_after(err.headers.get("Retry-After"), 10 * (attempt + 1)))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(2 * (attempt + 1))
    return None


# ----- reading the entity JSON -------------------------------------------------

def iso_time(snak_value):
    """'+1804-00-00T00:00:00Z' -> '1804'; '+1944-07-31T...' -> '1944-07-31'; None if too coarse."""
    if not isinstance(snak_value, dict) or "time" not in snak_value:
        return None
    if snak_value.get("precision", 9) < 9:
        return None
    m = re.match(r"^\+?(\d{1,4})-(\d{2})-(\d{2})T", snak_value["time"])
    if not m or int(m.group(1)) < 1:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return str(year) if not month else ("%d-%02d" % (year, month) if not day else "%d-%02d-%02d" % (year, month, day))


def claims(entity, prop):
    """Usable claims of a property: deprecated ones are dropped."""
    out = []
    for c in (entity.get("claims") or {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        snak = (c.get("mainsnak") or {})
        value = (snak.get("datavalue") or {}).get("value") if snak.get("snaktype", "value") == "value" else None
        quals = c.get("qualifiers") or {}

        def when(p):
            for q in quals.get(p, []):
                t = iso_time((q.get("datavalue") or {}).get("value"))
                if t:
                    return t
            return None
        out.append({"rank": c.get("rank", "normal"), "value": value, "start": when("P580"), "end": when("P582")})
    return out


def entity_id(value):
    return value.get("id") if isinstance(value, dict) else None


def labels(entity):
    return {lang: v.get("value") for lang, v in (entity.get("labels") or {}).items() if v.get("value")}


def official_names(entity):
    out = []
    for c in claims(entity, "P1448"):
        v = c["value"]
        if isinstance(v, dict) and v.get("text"):
            out.append({"name": v["text"], "language": v.get("language") or "", "start": c["start"], "end": c["end"]})
    return out


def lifetime(entity):
    start = next((iso_time(c["value"]) for c in claims(entity, "P571") if iso_time(c["value"])), None)
    end = next((iso_time(c["value"]) for c in claims(entity, "P576") if iso_time(c["value"])), None)
    return start, end


def coordinates(entity):
    for c in claims(entity, "P625"):
        v = c["value"]
        if isinstance(v, dict) and "latitude" in v:
            return v["latitude"], v["longitude"]
    return None


def place_like(entity):
    c = entity.get("claims") or {}
    return "P131" in c or "P625" in c or ("P17" in c and "P571" in c)


def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


# ----- tying tree places to entities --------------------------------------------

def tree_coordinates(place):
    try:
        lat, lon = float(place.get("lat")), float(place.get("lon"))
        return (lat, lon) if (lat or lon) else None
    except (TypeError, ValueError):
        return None


def resolve(tree, handle, client):
    """Return {"qid", "label"} for the entity of a tree place, or {"ambiguous": [...]} / {"none": True}."""
    place = tree.places[handle]
    names = []
    for n in tree.all_names(handle):
        if n.get("value") and n["value"] not in [x[0] for x in names]:
            names.append((n["value"], n.get("lang") or ""))
    wanted = {packs.fold(n) for n, _l in names}
    qids = []
    for value, lang in names[:4]:
        for language in dict.fromkeys([lang if lang in client.languages else "en", "en"]):
            for hit in client.search(value, language):
                if hit.get("id") not in qids:
                    qids.append(hit["id"])
    ents = client.entities(qids)
    here = tree_coordinates(place)
    scored = []
    for qid in qids:
        e = ents.get(qid)
        if not e or not place_like(e):
            continue
        known = {packs.fold(v) for v in labels(e).values()} | {packs.fold(o["name"]) for o in official_names(e)}
        if not (wanted & known):
            continue
        score = 3
        there = coordinates(e)
        if here and there:
            d = km(here, there)
            if d > 50:
                continue
            score += 5 if d <= 15 else 2
        scored.append((score, qid, e))
    if not scored:
        return {"none": True}
    scored.sort(key=lambda s: -s[0])
    best = [s for s in scored if s[0] == scored[0][0]]
    if len(best) > 1:
        return {"ambiguous": [(s[1], labels(s[2]).get("en") or s[1]) for s in best]}
    return {"qid": scored[0][1], "label": labels(scored[0][2]).get("en") or scored[0][1], "score": scored[0][0]}


def _evidence(qid, claim):
    return [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/%s" % qid, "claim": claim,
             "retrieved": time.strftime("%Y-%m-%d")}]


def build_pack(tree, handles, client, max_places=25):
    """A regional pack (origin wikidata) for the given tree places, and a list of notes."""
    notes, resolved = [], {}
    for handle in list(handles):
        if len(resolved) + len([n for n in notes if "not looked up" not in n]) >= max_places:
            break
        typed_address = tree.places[handle]["type"].get("value") in ADDRESS_TYPES
        if is_address(tree, handle):
            notes.append("%s: an address, not looked up in Wikidata" % tree.label(handle))
            continue
        if typed_address:
            notes.append("TYPE CHECK %s: typed as %s, but it has places under it or no address-like name; "
                         "it was looked up as a place" % (tree.label(handle),
                                                          PLACE_TYPE_NAMES.get(tree.places[handle]["type"].get("value"))))
        r = resolve(tree, handle, client)
        label = tree.label(handle)
        if "qid" in r:
            resolved[handle] = r
        elif "ambiguous" in r:
            notes.append("%s: ambiguous in Wikidata (%s), not used" % (label, ", ".join("%s %s" % c for c in r["ambiguous"])))
        else:
            notes.append("%s: no matching entity in Wikidata" % label)
    by_qid = {r["qid"]: h for h, r in resolved.items()}
    ents = client.entities(list(by_qid))
    class_ids = sorted({entity_id(c["value"]) for e in ents.values() for c in claims(e, "P31") if entity_id(c["value"])})
    class_ents = client.entities(class_ids)
    for qid, handle in by_qid.items():
        classes = [labels(class_ents[i]).get("en") for i in (entity_id(c["value"]) for c in claims(ents.get(qid, {}), "P31"))
                   if i in class_ents]
        suggested = type_from_classes(classes)
        have = tree.places[handle]["type"].get("value")
        if suggested and have in ADDRESS_TYPES + (-1,) and suggested != have:
            notes.append("TYPE CHECK %s: the tree says %s, Wikidata says %s (%s)" % (
                tree.label(handle), PLACE_TYPE_NAMES.get(have, "Unknown"), PLACE_TYPE_NAMES.get(suggested),
                ", ".join(c for c in classes if c)[:60]))
    places, edges = {}, []

    def key_of(handle):
        k = "p-" + tree.places[handle]["id"]
        if k not in places:
            places[k] = {"key": k, "gramps_id": tree.places[handle]["id"], "names": [tree.name_of(handle)],
                         "origin": "wikidata"}
        return k

    for handle, r in resolved.items():
        e = ents.get(r["qid"])
        if not e:
            continue
        for c in claims(e, "P131"):
            target = by_qid.get(entity_id(c["value"]))
            if target is None or not (c["start"] or c["end"]):
                continue
            (born, died), (pborn, pdied) = lifetime(e), lifetime(ents.get(entity_id(c["value"]), {}))
            start = c["start"] or born or pborn
            end = c["end"] or died or pdied
            if not start or not end:
                notes.append("%s -> %s: dated on one side only, not used" % (tree.label(handle), tree.label(target)))
                continue
            edges.append({"child": key_of(handle), "parent": key_of(target), "valid_from": start, "valid_to": end,
                          "origin": "wikidata", "evidence": _evidence(r["qid"], "P131 %s, start %s, end %s, rank %s" % (
                              entity_id(c["value"]), c["start"], c["end"], c["rank"]))})
        for o in official_names(e):
            if o["start"]:
                key_of(handle)
                places[key_of(handle)]["names"].append({
                    "name": o["name"], "language": o["language"], "valid_from": o["start"], "valid_to": o["end"],
                    "origin": "wikidata", "evidence": _evidence(r["qid"], "P1448 %r (%s), start %s, end %s" % (
                        o["name"], o["language"], o["start"], o["end"]))})
        born, died = lifetime(e)
        if died:
            key_of(handle)
            places[key_of(handle)]["lifetime"] = {
                "valid_from": born, "valid_to": died, "origin": "wikidata",
                "evidence": _evidence(r["qid"], "P571 %s, P576 %s: the entity ceased to exist" % (born, died))}
        if born:
            current = tree.places[handle]["name"]
            if current.get("value"):
                key_of(handle)
                places[key_of(handle)]["names"].append({
                    "name": current["value"], "language": current.get("lang") or "", "valid_from": born, "valid_to": died,
                    "origin": "wikidata", "basis": "lifetime", "evidence": _evidence(r["qid"], "P571 %s, P576 %s: the entity existed then; "
                                                                "the same name is assumed" % (born, died))})
    # parents that are not in the tree yet: offer to create them (at most 6 per run)
    wanted = {}
    for handle, r in resolved.items():
        e = ents.get(r["qid"])
        for c in claims(e or {}, "P131"):
            target = entity_id(c["value"])
            if target and target not in by_qid and (c["start"] or c["end"]):
                wanted.setdefault(target, []).append((handle, r["qid"], c))
    new_ents = client.entities(sorted(wanted)) if wanted else {}
    made = 0
    for target, uses in sorted(wanted.items()):
        t = new_ents.get(target)
        if not t or not place_like(t):
            continue
        tb, td = lifetime(t)
        usable = []
        for handle, child_qid, c in uses:
            born, died = lifetime(ents.get(child_qid, {}))
            start, end = c["start"] or born or tb, c["end"] or died or td
            if start and end:
                usable.append((handle, child_qid, c, start, end))
        names_by_lang = labels(t)
        primary = names_by_lang.get("en") or next(iter(names_by_lang.values()), None)
        if not usable or not primary:
            continue
        if made >= 6:
            notes.append("more parents could be created; run again after applying these")
            break
        period = {"valid_from": tb, "valid_to": td} if tb else {}
        names = [dict(period, name=primary, language="en")]
        for lang, value in names_by_lang.items():
            if value != primary:
                names.append(dict(period, name=value, language=lang))
        class_labels = [labels(c).get("en") for c in client.entities(
            [entity_id(x["value"]) for x in claims(t, "P31") if entity_id(x["value"])]).values()]
        guessed = type_from_classes(class_labels)
        coords = coordinates(t)
        key = "wd-%s" % target
        places[key] = {"key": key, "create": True, "names": names, "origin": "wikidata", "wikidata_qid": target,
                       "type_value": guessed if guessed is not None else -1,
                       "evidence": _evidence(target, "item %s: %s (%s)" % (target, primary, ", ".join(x for x in class_labels if x)[:60]))}
        if coords:
            places[key]["coordinates"] = {"lat": coords[0], "lon": coords[1]}
        made += 1
        for handle, child_qid, c, start, end in usable:
            edges.append({"child": key_of(handle), "parent": key, "valid_from": start, "valid_to": end, "origin": "wikidata",
                          "evidence": _evidence(child_qid, "P131 %s, start %s, end %s, rank %s" % (
                              target, c["start"], c["end"], c["rank"]))})
    pack = {"schema": packs.SCHEMA, "pack": {"id": "wikidata-%s" % time.strftime("%Y%m%d"), "version": 1,
                                             "origin": "wikidata", "created": time.strftime("%Y-%m-%d")},
            "places": list(places.values()), "edges": edges}
    packs.validate(pack)
    return pack, notes
