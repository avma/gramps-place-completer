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
"""A table answer read into the labelled lines of the core (rules TB1-TB6 of docs/ANALYZER_RULES.md).

The question of the form "table" asks for two short parts: two lines about the place (Name, Language, From, Source; Alternatives) and one table
`Category | Value/Name | Year Range | Level Type | Explanation | Source` with the rows Place Type, Level 1 ... Level N, Sovereign state, Latitude, Longitude.
convert() turns such an answer, copied as it is (tab separated, or with bars as in Markdown), into the text that ingest.parse_structured reads, so
that everything after it (the place that exists, the proposals, the writing, Undo) is the same for every form of the question.
What the answer does not give is left out and said: a site that is not an address of a page, a name that is "from" a year, other places of the name.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re
import unicodedata

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import rules

URL = re.compile(r"https?://[^\s)\]>|\"']+")
PRESENT = ("present", "now", "today", "\u05d4\u05d5\u05d5\u05d4")


def _fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def _clean(cell):
    """A cell without Markdown: **bold**, `code`, [text](address)."""
    cell = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", lambda m: m.group(2) if URL.search(m.group(2)) and not m.group(1).strip() else m.group(1) or m.group(2), cell or "")
    return re.sub(r"[*`]", "", cell).strip()


def _cells(line):
    """The cells of a row of a table (tab separated, or bars as in Markdown), or None when the line is not a row."""
    if "\t" in line:
        return [c.strip() for c in line.rstrip("\n").split("\t")]
    if line.count("|") >= 2:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    return None


def _years(text):
    """'1800-present', '1801 \u2013 2015', '-1800 present' (a row written backwards by a right-to-left page), '2015-\u05d4\u05d5\u05d5\u05d4' -> '1800-present'; '' -> 'UNKNOWN'."""
    text = _clean(text).replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "UNKNOWN"
    m = re.search(r"(\d{3,4})\s*-\s*(\d{3,4}|%s)" % "|".join(PRESENT), text, re.I)
    if m:
        return "%s-%s" % (m.group(1), "present" if m.group(2).lower() in PRESENT else m.group(2))
    m = re.fullmatch(r"-\s*(\d{3,4})\s+(%s)" % "|".join(PRESENT), text, re.I)          # a page that wrote 1800-present backwards
    if m:
        return "%s-present" % m.group(1)
    m = re.search(r"(\d{3,4})\s+(%s)" % "|".join(PRESENT), text, re.I)
    if m:
        return "%s-present" % m.group(1)
    return text


def _number(cell):
    text = re.sub(r"[^\d.,\-]", "", _clean(cell)).replace(",", ".")
    try:
        float(text)
    except ValueError:
        return None
    return text


def _generic(level_type):
    """The type of a level as the core reads it: 'other (canton)' -> 'canton', 'department' -> 'department', '' -> 'unit'."""
    text = _clean(level_type)
    m = re.match(r"other\s*\((.+)\)\s*$", text, re.I)
    if m:
        return m.group(1).strip().lower()
    if not text or _fold(text) in ("unknown", "other"):
        return "unit"
    return text.lower()


def _columns(header):
    """{'value': i, 'years': i, 'type': i, 'explanation': i, 'source': i} from the header row (the usual order when a column is not named)."""
    found = {"value": 1, "years": 2, "type": 3, "explanation": 4, "source": 5}
    for i, name in enumerate(header):
        low = _fold(name)
        for key, start in (("value", "value"), ("years", "year"), ("type", "level type"), ("explanation", "explanation"), ("source", "source")):
            if low.startswith(start):
                found[key] = i
    return found


def _note(notes, message, *args):
    """A thing that the answer gave and that is not written: the English text (it is in the catalog: the extractor reads the first text of _note) and its arguments."""
    if rules.message_on(message):
        notes.append((message, args))


def _part_one(lines):
    """({name, language, from, source}, alternatives text) from the lines before the table."""
    info, alternatives = {}, ""
    for line in lines:
        text = _clean(line)
        low = _fold(text)
        if low.startswith("alternatives"):
            alternatives = text.split(":", 1)[1].strip() if ":" in text else ""
        elif low.startswith("name"):
            for part in text.split("|"):
                if ":" in part:
                    label, value = part.split(":", 1)
                    info[_fold(label)] = value.strip()
    return info, alternatives


def is_table(text):
    """Does the text have the header row of a table answer?"""
    return _header_index((text or "").splitlines()) is not None


def _header_index(lines):
    for n, line in enumerate(lines):
        cells = _cells(line)
        if cells and len(cells) >= 3 and _fold(_clean(cells[0])) == "category" and any(_fold(c).startswith("value") for c in cells[1:]):
            return n
    return None


def convert(text, place=""):
    """(text, notes): the labelled lines of the core for a table answer, or the text itself (and no notes) when it is not one.

    notes is a list of (message, arguments): what the answer gave that is not written (the screen shows them with the other needs).
    """
    lines = (text or "").splitlines()
    start = _header_index(lines)
    if start is None:
        return text, []
    columns = _columns(_cells(lines[start]))
    rows = []
    for line in lines[start + 1:]:
        if not line.strip():
            if rows:
                break
            continue
        cells = _cells(line)
        if cells is None:
            break
        if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
            continue                                                           # the line under the header of a Markdown table
        cells += [""] * (max(columns.values()) + 1 - len(cells))
        rows.append({"category": _fold(_clean(cells[0])), "value": _clean(cells[columns["value"]]), "years": cells[columns["years"]],
                     "type": cells[columns["type"]], "source": cells[columns["source"]]})
    info, alternatives = _part_one(lines[:start])
    kind = next((r for r in rows if r["category"] == "place type"), None)
    levels = [(int(m.group(1)), r) for r in rows for m in [re.fullmatch(r"level\s*(\d+)", r["category"])] if m]
    levels.sort(key=lambda item: item[0])
    state = next((r for r in rows if r["category"] in ("sovereign state", "sovereign")), None)
    lat = next((_number(r["value"]) for r in rows if r["category"] == "latitude"), None)
    lon = next((_number(r["value"]) for r in rows if r["category"] == "longitude"), None)
    if not (kind or levels or state or lat or lon):
        return text, []                                                        # a table with no data: the question given back
    notes, sources = [], {}

    def cite(cell, field):
        found = URL.search(_clean(cell) + " " + cell)
        if found:
            sources.setdefault(found.group(0).rstrip(".,;"), []).append(field)
        elif _clean(cell):
            site = _clean(cell)
            if (site, ) not in [n[1] for n in notes]:
                _note(notes, "response references domain (%s) rather than direct page URL; citation omitted", site)

    name = _clean(info.get("name", "")) or place.strip()
    out = ["PLACE_NAME_ON_DATE: %s" % name]
    if info.get("language"):
        out.append("LANGUAGE: %s" % _clean(info["language"]))
    cite(info.get("source", ""), "PLACE_NAME_ON_DATE")
    if kind and kind["value"]:
        out.append("SETTLEMENT_TYPE_ON_DATE: %s" % kind["value"])
        cite(kind["source"], "SETTLEMENT_TYPE_ON_DATE")
    if lat and lon:
        out.append("COORDINATES: %s, %s" % (lat, lon))
        for r in rows:
            if r["category"] in ("latitude", "longitude"):
                cite(r["source"], "COORDINATES")
    sovereign = state["value"] if state else ""
    lines_out, number = [], 0
    for _n, r in levels:
        number += 1
        lines_out.append("%d | %s | %s | %s | %s" % (number, r["value"], _generic(r["type"]), _years(r["years"]), sovereign))
        if not _clean(r["type"]):
            _note(notes, "administrative level %d (%s) lacks type classification in response", number, r["value"])
        cite(r["source"], "CONTAINERS")
    if state and sovereign:
        number += 1
        lines_out.append("%d | %s | sovereign state | %s | %s" % (number, sovereign, _years(state["years"]), sovereign))
        cite(state["source"], "CONTAINERS")
    if lines_out:
        out.append("CONTAINERS:")
        out += lines_out
    if state and sovereign:
        out.append("STATE_ON_DATE: %s | %s" % (sovereign, _years(state["years"])))
    out.append("NOTES: NONE")
    for url, fields in sources.items():
        out.append("SOURCES: %s | %s" % (url, ", ".join(sorted(set(fields)))))
    out.append("NOT_SURE: NONE")
    from_year = _clean(info.get("from", ""))
    if from_year and _fold(from_year) not in ("unknown", "none", ""):
        _note(notes, "response specifies name «%s» is active from %s; omitted from tree updates for manual review", name, from_year)
    if alternatives and _fold(alternatives).strip(". ") not in ("none", "unknown", ""):
        _note(notes, "response lists alternative locations matching name: %s. Use Region hint to refine search target", alternatives)
    return "\n".join(out) + "\n", notes
