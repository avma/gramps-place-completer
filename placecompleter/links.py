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
"""Which web links of an answer may become links of a place (rules LK1-LK5 of docs/ANALYZER_RULES.md).

A link of a place is a statement about the place itself, so only a few kinds of address qualify:
Wikipedia and Wikidata, and the official site of the place or of the authority over it. Tourism, hiking,
booking, advertising and shop pages never become a link of a place (they may still be cited as a source).
Whether a site is official cannot be proved from its address, so there are three levels: an address of
a known official shape is offered chosen, any other address is offered unchosen, a blocked one is not offered.
The number of links is limited so that the database is not filled with what nobody needs.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

MAX_WIKIDATA = 1
MAX_OFFICIAL = 2          # Wikipedia: one per language that the user chose; the total is Wikidata + the languages + these
FALLBACK_LANGUAGE = "en"

WIKIPEDIA, WIKIDATA, OFFICIAL, LIKELY_OFFICIAL, OTHER, BLOCKED = "wikipedia", "wikidata", "official", "likely-official", "other", "blocked"

BLOCKED_DOMAINS = {
    "tripadvisor", "booking", "expedia", "airbnb", "hotels", "trivago", "agoda", "kayak", "viator", "getyourguide", "komoot", "alltrails",
    "wikiloc", "outdooractive", "strava", "facebook", "instagram", "pinterest", "tiktok", "twitter", "x", "youtube", "amazon", "ebay",
    "groupon", "skyscanner", "lonelyplanet", "roughguides", "fodors", "yelp", "foursquare", "mapcarta", "waze", "maps",
}
BLOCKED_WORDS = {"tour", "tours", "trail", "trails", "hike", "hiking", "hotel", "hotels", "booking", "shop", "tickets", "ticket", "deals", "promo",
                 "cheap", "holiday", "holidays", "vacation", "vacations", "resort", "camping", "excursions", "itinerary", "itineraries"}
OFFICIAL_LABELS = {"gov", "gouv", "gob", "govt", "go", "gv", "admin", "gc", "europa"}
OFFICIAL_PREFIXES = ("comune", "comuni", "provincia", "regione", "municipio", "gemeinde", "stadt", "kommune", "kommun", "obec", "mesto", "varos",
                     "onkormanyzat", "primaria", "municipiul", "opstina", "mairie", "ayuntamiento", "city", "town", "county", "council", "archivio",
                     "archiv", "archives", "arhiv")
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "oldid"}


def normalize(url):
    """The form in which two addresses of the same page are equal (scheme, www, mobile, fragment, tracking, trailing slash)."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    host = re.sub(r"^www\.", "", host)
    host = re.sub(r"^([a-z-]+)\.m\.(wikipedia|wikidata)\.org$", r"\1.\2.org", host)
    host = re.sub(r"^m\.(wikipedia|wikidata)\.org$", r"\1.org", host)
    host = re.sub(r"^m\.", "", host)
    if host == "wikidata.org" or host == "m.wikidata.org":
        host = "wikidata.org"
    path = parts.path.rstrip("/") or ""
    if host == "wikidata.org":
        path = re.sub(r"^/entity/", "/wiki/", path)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING])
    return host + path + (("?" + query) if query else "")


def _labels(host):
    return host.split(".")


def classify(url):
    """(kind, reason) of one address."""
    text = url.strip()
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return BLOCKED, "not a web address"
    host = re.sub(r"^www\.", "", host)
    labels = _labels(host)
    if re.search(r"(^|\.)wikipedia\.org$", host):
        return WIKIPEDIA, "Wikipedia"
    if re.search(r"(^|\.)wikidata\.org$", host):
        return WIKIDATA, "Wikidata"
    # the registered name: the label before the public suffix (co.uk, gov.it ... have two labels)
    name_labels = labels[:-1] if len(labels) > 1 else labels
    if any(label in BLOCKED_DOMAINS for label in name_labels):
        return BLOCKED, "a commercial, tourism or social site"
    words = set(re.split(r"[^a-z]+", (host + " " + parts.path).lower()))
    hit = words & BLOCKED_WORDS
    if hit:
        return BLOCKED, "the address speaks of %s" % ", ".join(sorted(hit))
    if any(label in OFFICIAL_LABELS for label in labels[1:]) or labels[-1] in ("gov", "mil", "edu") or any(labels[0] == w or labels[0].startswith(w + "-") for w in OFFICIAL_PREFIXES):
        return LIKELY_OFFICIAL, "the address has the shape of an official site"
    return OTHER, "an address of unknown kind: choose it only if the site is official"


def _wikipedia_language(url):
    match = re.match(r"^https?://([a-z-]+)\.(?:m\.)?wikipedia\.org", url.strip(), re.I)
    return match.group(1).lower() if match else ""


def sitelink_urls(entity, languages):
    """The Wikipedia addresses that a Wikidata entity itself lists, for the languages asked (in that order).

    Wikidata names the article of every language of a place (entity["sitelinks"]["hewiki"]["title"]), so an article in the language
    of the user is found when the answer of the AI gave none, and no address is ever guessed.
    """
    found = []
    sitelinks = (entity or {}).get("sitelinks") or {}
    for lang in languages:
        item = sitelinks.get(lang.replace("-", "_") + "wiki")
        title = (item or {}).get("title")
        if title:
            found.append("https://%s.wikipedia.org/wiki/%s" % (lang.lower(), quote(title.replace(" ", "_"), safe="_(),'!*~:@")))
    return found


def select_links(urls, existing=(), languages=(FALLBACK_LANGUAGE,), max_total=None):
    """Choose the links to offer for one place.

    urls: the addresses of the answer (strings, in the order of the answer; the Wikipedia addresses of sitelink_urls may follow);
    existing: the addresses the place already has; languages: the languages of Wikipedia that the user wants, in the order of preference
    (the setting of the user). One article per language; English only when none of the languages has an article (the fallback).
    Returns (offered, rejected): offered is a list of {"path", "kind", "chosen", "reason"}, rejected a list of {"path", "reason"} for what
    was left out (blocked, a duplicate, a kind that is full, a language that was not asked, over the total).
    The total (when max_total is None) is one Wikidata, one Wikipedia per language, and MAX_OFFICIAL other; the links that exist count.
    """
    wanted = [l.lower() for l in languages if l] or [FALLBACK_LANGUAGE]
    wanted = [l for i, l in enumerate(wanted) if l not in wanted[:i]]
    if max_total is None:
        max_total = MAX_WIKIDATA + len(wanted) + MAX_OFFICIAL
    have = {normalize(u) for u in existing}
    used = {}                                                     # slot -> how many: WIKIDATA, OFFICIAL, ("wikipedia", language)
    for u in existing:
        kind = classify(u)[0]
        slot = (WIKIPEDIA, _wikipedia_language(u)) if kind == WIKIPEDIA else kind if kind == WIKIDATA else OFFICIAL
        used[slot] = used.get(slot, 0) + 1
    rejected, candidates, seen = [], [], set()
    for url in urls:
        url = url.strip()
        key = normalize(url)
        kind, reason = classify(url)
        if kind == BLOCKED:
            rejected.append({"path": url, "reason": reason})
        elif key in have or key in seen:
            rejected.append({"path": url, "reason": "the place already has this link" if key in have else "the same address twice"})
        else:
            seen.add(key)
            candidates.append({"path": url, "kind": kind, "reason": reason, "chosen": kind in (WIKIPEDIA, WIKIDATA, LIKELY_OFFICIAL)})
    # the fallback: English is wanted too, when no article exists (or is offered) in any language that the user chose
    in_wanted = any(slot[0] == WIKIPEDIA and slot[1] in wanted for slot in used if isinstance(slot, tuple)) or \
        any(c["kind"] == WIKIPEDIA and _wikipedia_language(c["path"]) in wanted for c in candidates)
    if not in_wanted and FALLBACK_LANGUAGE not in wanted:
        wanted = wanted + [FALLBACK_LANGUAGE]
    order = {WIKIDATA: 0, WIKIPEDIA: 1, LIKELY_OFFICIAL: 2, OFFICIAL: 2, OTHER: 3}

    def rank(item):
        """Most important first: when the total is full the least important is the one that is left out."""
        lang = _wikipedia_language(item["path"]) if item["kind"] == WIKIPEDIA else ""
        return (order[item["kind"]], wanted.index(lang) if lang in wanted else len(wanted))
    candidates.sort(key=rank)                 # stable: inside a rank, the order of the answer
    offered = []
    total = sum(used.values())
    for item in candidates:
        if item["kind"] == WIKIPEDIA:
            lang = _wikipedia_language(item["path"])
            slot, limit = (WIKIPEDIA, lang), 1
            if lang not in wanted:
                rejected.append({"path": item["path"], "reason": "its language (%s) is not among the languages that were asked" % (lang or "?")})
                continue
        elif item["kind"] == WIKIDATA:
            slot, limit = WIKIDATA, MAX_WIKIDATA
        else:
            slot, limit = OFFICIAL, MAX_OFFICIAL
        if used.get(slot, 0) >= limit:
            rejected.append({"path": item["path"], "reason": "the place has enough links of this kind"})
        elif total >= max_total:
            rejected.append({"path": item["path"], "reason": "the place has the most links that are added (%d)" % max_total})
        else:
            used[slot] = used.get(slot, 0) + 1
            total += 1
            offered.append(item)
    return offered, rejected
