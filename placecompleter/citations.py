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
"""Citations for the places that are written: where each piece of information came from, to look it up again when two sources disagree.

Every proposal carries its evidence (the pages the answer lists and what each is cited for; a Wikidata statement). When the proposals are
written, each place that was touched gets a Citation to a Source for each such page, in the same step (one Undo):
  Source    one per web page: its title, the address in publication information and as a source attribute "URL" (that is how it is found again);
            and a link to a Repository, the web site the page belongs to (Wikipedia, Wikidata, ...): the one the tree has, or a new one. A source
            that is found and has no repository gets one; a source that has one is left as it is.
  Citation  the page text says what it is cited for; the date is the day it was fetched; the confidence follows what the analysis knows (below);
            and a note of the type Place with how it was found (which AI, which question, the saved answer, what the answer was unsure of).
  Confidence  Wikidata statement: Normal. What an AI found: Normal when the answer cites the page for fields it does not doubt; Low when it says
            it is not sure about part of them, or does not say what the page supports; Very Low when it is not sure about all of them; and
            one level lower when the analysis found that the answer contradicts itself or disagrees with an answer saved for another date.
Nothing is cited twice: a place that already has a citation to that page with that text is left alone; a source that the tree has (the same
page in another form: http/https, www, mobile, a fragment) is used again and not made a second time.
A citation goes to the place that its source is ABOUT: a page whose title is the name of a place written in the same run (Wikipedia: Parma ->
Parma, Wikipedia (it): Provincia di Parma -> Provincia di Parma) is cited on that place only; a page that is about none of them is cited on the
main place, the one the question was about. A page about the main place is cited on it even when nothing else was written to it, and the
primary name of a place decides before its other names (a province often carries the name of its city as another name). A page that is about a place
of the chain that this run does not change is not cited at all. (Without the main place, as in a plan applied from the command line, every place that was touched
gets the sources of its own proposals, as before.)
At most MAX_CITATIONS citations are added to one place in one run, the strongest first: the higher confidence, then Wikidata, Wikipedia and
official sites before other sites, then the page cited for more fields. What is left out is reported. A tourism, commercial or social site is
still cited when the answer rests on it, but its confidence is never above Low.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import datetime
import re
import unicodedata
import urllib.parse

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import links as linklib, rules
from .i18n import _

URL_ATTRIBUTE = "URL"
MAX_CITATIONS = 3


def source_title(url, claim=""):
    """A readable title from an address: 'Wikipedia: Johnston, Iowa', 'Wikidata Q1', else 'host: last part of the path'."""
    parsed = urllib.parse.urlparse(url or "")
    host = parsed.netloc.lower().replace("www.", "")
    last = urllib.parse.unquote(parsed.path.rstrip("/").split("/")[-1]).replace("_", " ").strip()
    if host.endswith("wikipedia.org"):
        language = host.split(".")[0]
        return ("Wikipedia: %s" if language == "en" else "Wikipedia (" + language + "): %s") % (last or host)
    if host.endswith("wikidata.org"):
        return "Wikidata %s" % (last or "")
    return "%s: %s" % (host, last) if last else (host or url)


def collect(proposal):
    """{url: {'claims': [...], 'wikidata': bool}} from the evidence of one proposal."""
    out = {}
    for e in proposal.get("evidence") or []:
        url = (e.get("url") or "").strip()
        if not url:
            continue
        item = out.setdefault(url, {"claims": [], "wikidata": e.get("source") == "wikidata"})
        claim = e.get("claim")
        for part in ([claim] if isinstance(claim, str) else list(claim or [])):
            if part and part not in item["claims"]:
                item["claims"].append(part)
    return out


def merge(into, more):
    for url, info in more.items():
        item = into.setdefault(url, {"claims": [], "wikidata": info["wikidata"]})
        for claim in info["claims"]:
            if claim not in item["claims"]:
                item["claims"].append(claim)
    return into


def _claim_text(info):
    claims = ", ".join(info["claims"])
    if info["wikidata"]:
        return claims or _("Wikidata statement")
    return (_("Reported by AI search supporting: %s") % claims) if claims else _("Reported by an AI search")


def _note_text(info, prov, url=None):
    how = _("Found by %(engine)s (%(model)s) on %(day)s, responding to query regarding «%(place)s» on %(date)s (query "
            "format: %(form)s).") % {
        "engine": prov.get("engine_label") or prov.get("engine") or "?", "model": prov.get("model") or "?",
        "day": prov["today"].isoformat(), "place": prov.get("place") or "?", "date": prov.get("date") or "?", "form": prov.get("form") or "?"}
    if info["wikidata"]:
        how = _("Retrieved from Wikidata on %(day)s while completing «%(place)s».") % {"day": prov["today"].isoformat(), "place": prov.get("place") or "?"}
    lines = [how]
    if prov.get("answer_file"):
        lines.append(_("Saved response: %s") % prov["answer_file"])
    if prov.get("not_sure") and not info["wikidata"]:
        lines.append(_("The response indicates uncertainty regarding: %s") % prov["not_sure"])
    level, why = confidence_for(info, prov, url)
    lines.append(_("Confidence level %(level)s: %(why)s.") % {"level": _LEVEL_NAMES[level], "why": why})
    return "\n".join(lines)


VERY_LOW, LOW, NORMAL = 0, 1, 2                                                      # the levels of Gramps (Citation.CONF_...)
_LEVEL_NAMES = {VERY_LOW: _("Very Low"), LOW: _("Low"), NORMAL: _("Normal")}       # (the words Gramps uses for them)
_LABEL = re.compile(r"^[A-Z][A-Z_]{2,}$")


def _fields(claims):
    """The fields of the answer (PLACE_NAME_ON_DATE, CONTAINERS ...) that a page is cited for."""
    return {t for claim in claims or [] for t in re.split(r"[,;\s]+", claim or "") if _LABEL.match(t)}


def confidence_for(info, prov, url=None):
    """(level, why) of the citation of a page: what the analysis already knows about how sure the answer is (see the top of the file)."""
    if info["wikidata"]:
        return NORMAL, _("a Wikidata statement")
    fields = _fields(info["claims"])
    unsure = {t for t in re.split(r"[,;\s]+", prov.get("not_sure") or "") if t}
    if not fields:
        level, why = LOW, _("the response does not specify which fields this page supports")
    elif fields <= unsure:
        level, why = VERY_LOW, _("the response expresses uncertainty regarding all claims cited on this page: %s") % ", ".join(sorted(fields))
    elif fields & unsure:
        level, why = LOW, _("the response expresses uncertainty regarding part of this claim: %s") % ", ".join(sorted(fields & unsure))
    else:
        level, why = NORMAL, _("the response cites this page for %s without expressing uncertainty") % ", ".join(sorted(fields))
    if prov.get("doubts") and level > VERY_LOW:
        level -= 1
        why += "; " + _("downgraded one confidence level due to internal contradictions or discrepancies with saved responses")
    if rules.on("CT4") and url and level > LOW and linklib.classify(url)[0] == linklib.BLOCKED:
        level = LOW
        why += "; " + _("the web link is a commercial, tourism, or social site rather than an official record source")
    return level, why


KNOWN_SITES = (("wikipedia.org", "Wikipedia", "https://www.wikipedia.org"), ("wikidata.org", "Wikidata", "https://www.wikidata.org"),
               ("geonames.org", "GeoNames", "https://www.geonames.org"), ("familysearch.org", "FamilySearch", "https://www.familysearch.org"),
               ("archive.org", "Internet Archive", "https://archive.org"), ("jewishgen.org", "JewishGen", "https://www.jewishgen.org"),
               ("geni.com", "Geni", "https://www.geni.com"))


def _host(url):
    host = (urllib.parse.urlparse(url or "").netloc or "").lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def repository_identity(url):
    """(name, home address, host) of the web site a page belongs to: 'Wikipedia' for every language of it, 'Wikidata', else the host itself.
    ('', '', '') when the address has no host."""
    host = _host(url)
    if not host:
        return "", "", ""
    for domain, name, home in KNOWN_SITES:
        if host == domain or host.endswith("." + domain):
            return name, home, domain
    scheme = urllib.parse.urlparse(url).scheme or "https"
    return host, "%s://%s" % (scheme, host), host


def _find_repository(db, name, host):
    """The repository of the tree for this site: by its name (any case) or by the host of one of its addresses."""
    for handle in db.get_repository_handles():
        repo = db.get_repository_from_handle(handle)
        if repo.get_name().strip().casefold() == name.casefold():
            return handle
        for link in repo.get_url_list():
            site = _host(link.get_path())
            if site and (site == host or site.endswith("." + host)):
                return handle
    return None


def _repository_for(db, trans, url, cache):
    """The handle of the repository for the site of the page (created when the tree has none), or None when the address has no host."""
    from gramps.gen.lib import Repository, RepositoryType, Url, UrlType
    name, home, host = repository_identity(url)
    if not name:
        return None
    key = ("repository", name)
    if key in cache:
        return cache[key]
    handle = _find_repository(db, name, host)
    if handle is None:
        repo = Repository()
        repo.set_name(name)
        repo.set_type(RepositoryType.WEBSITE)
        address = Url()
        address.set_path(home)
        address.set_type(UrlType.WEB_HOME)
        repo.add_url(address)
        handle = db.add_repository(repo, trans)
    cache[key] = handle
    return handle


def _link_to_repository(db, trans, source, url, cache):
    """Give the source a link to the repository of its site, if it has none (a source that has one is never changed). True when it was linked."""
    from gramps.gen.lib import RepoRef, SourceMediaType
    if source.get_reporef_list():
        return False
    handle = _repository_for(db, trans, url, cache)
    if handle is None:
        return False
    link = RepoRef()
    link.set_reference_handle(handle)
    link.set_media_type(SourceMediaType.ELECTRONIC)
    source.add_repo_reference(link)
    return True


def _find_source(db, url, cache):
    if url in cache:
        return cache[url]
    wanted = linklib.normalize(url)
    for handle in db.get_source_handles():
        source = db.get_source_from_handle(handle)
        if source.get_publication_info() == url or any(a.get_value() == url and str(a.get_type()) == URL_ATTRIBUTE
                                                       for a in source.get_attribute_list()) \
                or linklib.normalize(source.get_publication_info() or "") == wanted \
                or any(str(a.get_type()) == URL_ATTRIBUTE and linklib.normalize(a.get_value() or "") == wanted for a in source.get_attribute_list()):
            cache[url] = handle
            return handle
    return None


def _already_cited(db, place, source_handle, page):
    return any(c.get_reference_handle() == source_handle and c.get_page() == page
               for c in (db.get_citation_from_handle(h) for h in place.get_citation_list()))


def strength(url, info, prov, position):
    """The key that orders the sources of a place, strongest first (see the top of the file)."""
    level = confidence_for(info, prov, url)[0]
    kind = {linklib.WIKIDATA: 0, linklib.WIKIPEDIA: 1, linklib.OFFICIAL: 2, linklib.LIKELY_OFFICIAL: 2, linklib.OTHER: 3, linklib.BLOCKED: 4}[linklib.classify(url)[0]]
    return (-level, 0 if info["wikidata"] else kind, -len(_fields(info["claims"])), position)


def attach(db, trans, place_handle, sources, prov, cache, limit=MAX_CITATIONS, left_out=None):
    """Give the place a citation to each of the sources (see the top of the file), the strongest first, at most `limit` new ones.

    Returns the titles of those that were added; the titles of the sources that the limit left out are appended to `left_out` (a list)."""
    from gramps.gen.lib import Citation, Date, Note, NoteType, Source, SrcAttribute
    if not rules.on("CT2"):
        limit = 10 ** 9
    added = []
    ordered = sorted(((position, url, info) for position, (url, info) in enumerate(sources.items())),
                     key=lambda item: strength(item[1], item[2], prov, item[0]))
    for _position, url, info in ordered:
        place = db.get_place_from_handle(place_handle)
        source_handle = _find_source(db, url, cache)
        if len(added) >= limit:                                                    # the place has all that one run adds
            if source_handle is None or not _already_cited(db, place, source_handle, _claim_text(info)):
                if left_out is not None:
                    left_out.append(source_title(url))
            continue
        if source_handle is None:
            source = Source()
            source.set_title(source_title(url))
            source.set_publication_info(url)
            attribute = SrcAttribute()
            attribute.set_type(URL_ATTRIBUTE)
            attribute.set_value(url)
            source.add_attribute(attribute)
            _link_to_repository(db, trans, source, url, cache)                    # every source is linked to the repository of its site
            source_handle = cache[url] = db.add_source(source, trans)
        else:
            source = db.get_source_from_handle(source_handle)
            if _link_to_repository(db, trans, source, url, cache):                # a source found with no repository gets one
                db.commit_source(source, trans)
        page = _claim_text(info)
        if _already_cited(db, place, source_handle, page):
            continue
        today = prov["today"]
        date = Date()
        date.set_yr_mon_day(today.year, today.month, today.day)
        citation = Citation()
        citation.set_reference_handle(source_handle)
        citation.set_page(page)
        citation.set_date_object(date)
        citation.set_confidence_level({VERY_LOW: Citation.CONF_VERY_LOW, LOW: Citation.CONF_LOW, NORMAL: Citation.CONF_NORMAL}[confidence_for(info, prov, url)[0]])
        note = Note()
        note.set(_note_text(info, prov, url))
        note.set_type(NoteType.PLACE)
        citation.add_note(db.add_note(note, trans))
        place.add_citation(db.add_citation(citation, trans))
        db.commit_place(place, trans)
        added.append(source_title(url))
    return added


def _fold(text):
    """Letters and digits only, lower case, without accents: how two names are compared."""
    text = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"[\W_]+", " ", "".join(c for c in text if not unicodedata.combining(c)).casefold()).strip()


def about(url, names):
    """True when the page is ABOUT a place with one of these names: the title of a Wikipedia article (before a comma: 'Johnston, Iowa' is Johnston), or a
    whole part of the address of another site ('.../comune/parma/'), is the name of the place. A Wikidata page is never decided by its name."""
    parsed = urllib.parse.urlparse(url or "")
    host = parsed.netloc.lower()
    if host.endswith("wikidata.org"):
        return False
    path = urllib.parse.unquote(parsed.path)
    parts = [path.rstrip("/").split("/")[-1]] if host.endswith("wikipedia.org") else [p for p in path.split("/") if p]
    wanted = {_fold(n) for n in names if _fold(n)}
    for part in parts:
        title = part.replace("_", " ")
        if _fold(title) in wanted or _fold(title.split(",")[0]) in wanted:
            return True
    return False


def provenance_record(meta=None, place="", date="", answer_file="", not_sure="", today=None, doubts=(), main="", chain=()):
    """What the notes say about how the information was found. meta: engines.provenance() of the answer."""
    meta = meta or {}
    return {"engine": meta.get("engine"), "engine_label": meta.get("engine_label"), "model": meta.get("model"), "form": meta.get("form"),
            "place": place or meta.get("place"), "date": date or meta.get("date"), "answer_file": answer_file, "not_sure": not_sure,
            "doubts": list(doubts), "today": today or datetime.date.today(), "main": main, "chain": list(chain)}
