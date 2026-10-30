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
"""Reading the text of an answer: the labelled lines of the template made into one record (parse_structured).
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import rules
from .wikidata import km, tree_coordinates
from .kinds import OVERLAY_WORDS, SETTLEMENT_CLASSES, SETTLEMENT_TYPES, TREE_TYPES, _own_type
from .words import UNIT_WORDS, _says_something, fold, is_unknown


LABELS = ("PLACE_NAME_ON_DATE", "LANGUAGE", "OTHER_NAMES", "SETTLEMENT_TYPE_ON_DATE", "COORDINATES", "CONTAINERS",
          "STATE_ON_DATE", "DIFFERS_FROM_TODAY", "SOURCES", "NOT_SURE", "NOTES", "AMBIGUOUS")


def _period(text):
    """(from, to) as year strings; None for an unknown start and for "present" or an unknown end."""
    m = re.search(r"(\d{4}|unknown|\?)\s*[-–]\s*(\d{4}|present|today|now|unknown|\?)", text or "", flags=re.I)
    if not m:
        return None, None
    first = m.group(1) if m.group(1).isdigit() else None
    last = m.group(2) if m.group(2).isdigit() else None
    return first, last


def _candidate(line):
    """'[Johnston, United States (Iowa)](link), 41.67, -93.69' -> {'name', 'region', 'country', 'coordinates'}."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).strip().lstrip("-*0123456789.) ").strip()
    m = re.search(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$", text)
    if not m:
        return None
    head = text[:m.start()].rstrip(" ,;")
    parens = re.findall(r"\(([^)]*)\)", head)
    base = re.sub(r"\s*\([^)]*\)", "", head).strip(" ,")
    parts = [x.strip() for x in base.split(",") if x.strip()]
    return {"name": parts[0] if parts else base, "country": parts[-1] if len(parts) > 1 else "",
            "region": parens[-1].strip() if parens else "", "coordinates": (float(m.group(1)), float(m.group(2))), "text": text}


def candidate_hints(tree, candidates):
    """What the tree knows about each candidate: a place named like its region or country, and the nearest place by coordinates."""
    out = []
    for c in candidates:
        wanted = {fold(x) for x in (c["region"], c["country"]) if x}
        named = [tree.label(h) for h in tree.places if wanted & {fold(n.get("value")) for n in tree.all_names(h)}]
        nearest = None
        for h, place in tree.places.items():
            here = tree_coordinates(place)
            if here:
                d = km(here, c["coordinates"])
                if d <= 150 and (nearest is None or d < nearest[0]):
                    nearest = (d, tree.label(h))
        notes = []
        if named:
            notes.append("your tree has: " + ", ".join(named[:3]))
        if nearest:
            notes.append("nearest place of your tree with coordinates: %s (%.0f km)" % (nearest[1], nearest[0]))
        out.append({"candidate": c, "notes": notes, "score": len(named) * 2 + (1 if nearest else 0)})
    return out


def refined_place(base_name, candidate):
    """The place text for a second question that cannot be mistaken for another place."""
    where = ", ".join(x for x in (candidate["region"], candidate["country"]) if x)
    return "%s, %s (coordinates %s, %s)" % (base_name, where, candidate["coordinates"][0], candidate["coordinates"][1]) if where else \
        "%s (coordinates %s, %s)" % (base_name, candidate["coordinates"][0], candidate["coordinates"][1])


def _split_remark(text):
    """'Johnston (also called Johnston Station)' -> ('Johnston', 'also called Johnston Station')."""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", (text or "").strip())
    if m and m.group(1):
        return m.group(1).strip(), m.group(2).strip()
    return (text or "").strip(), ""


def _clean_type(text):
    t = (text or "").strip()
    m = re.fullmatch(r"(.+?)\s+and\s+\1", t, flags=re.I)
    return m.group(1) if m else t


def _restore_lines(text):
    """Put the line breaks back when copying flattened the answer into one line."""
    labels = "|".join(LABELS)
    text = re.sub(r"[ \t]+(?=(?:%s):)" % labels, "\n", text)
    text = re.sub(r"(?<=\S)[ \t]+(?=\d+\s*\|\s*[^|\n]+\|)", "\n", text)       # "1 | a | b | c | d 2 | e | ..."
    text = re.sub(r"(?<=\S)[ \t]+(?=https?://\S+\s*\|)", "\n", text)               # one source per line
    text = re.sub(r"(?<=\))[ \t]+(?=[a-z]{2,3}:\s)", "\n", text)                    # "hu: x (1462-present) sr: y (1918-present)"
    return text


def parse_structured(text):
    """Parse the labelled lines. Unknown labels are ignored; a missing field is simply absent."""
    fields, current = {}, None
    text = re.sub(r"\[([^\]]*)\]\((?:[^()\n]|\([^)\n]*\))*\)", r"\1", text)      # [Iowa](https://...) -> Iowa
    text = re.sub(r"<[^<>\n]*\s[^<>\n]*>", "UNKNOWN", text)                            # <name in the official language ...>: a field of the template left unfilled
    text = _restore_lines(text)
    for raw in text.splitlines():
        line = raw.strip().strip("`")
        if not line:
            continue
        m = re.match(r"^([A-Z_]+):\s*(.*)$", line)
        if m and m.group(1) in LABELS:
            current = m.group(1)
            fields[current] = [m.group(2)] if m.group(2) else []
        elif current:
            fields[current].append(line)
    rec = {"raw": text, "fields": sorted(fields)}
    first = lambda k: (fields.get(k) or [""])[0].strip()
    rec["name"], rec["name_remark"] = _split_remark(first("PLACE_NAME_ON_DATE"))
    rec["name"] = rec["name"] if _says_something(rec["name"]) else None                  # UNKNOWN, NONE, N/A: the answer has no name
    rec["notes"] = " ".join(x.strip() for x in fields.get("NOTES", []) if x.strip())
    rec["language"] = first("LANGUAGE").lower() or None
    rec["other_names"] = []
    for line in fields.get("OTHER_NAMES", []):
        m = re.match(r"^(\w{2,3})\s*:\s*(.+?)(?:\s*\((.*?)\))?\s*$", line)
        if m and not is_unknown(m.group(2)):
            start, end = _period(m.group(3) or "")
            rec["other_names"].append({"lang": m.group(1).lower(), "name": m.group(2), "from": start, "to": end})
    rec["type_text"] = " / ".join(dict.fromkeys(x.strip() for x in first("SETTLEMENT_TYPE_ON_DATE").split("|") if x.strip())) or None
    low = (rec["type_text"] or "").lower()
    rec["type_value"] = next((v for w, v in SETTLEMENT_TYPES if w in low), None)
    rec["type_string"] = ""
    rec["type_closed"] = False                                              # True when the answer is one bare word of the closed list (see below)
    head = re.fullmatch(r"\s*([a-z]+)\s*", fold(first("SETTLEMENT_TYPE_ON_DATE").split("|")[0]))
    word = head.group(1) if head else ""
    if rules.on("ST3") and word in SETTLEMENT_CLASSES:                      # the closed answer (one bare word): it decides, what follows it (the local term) cannot change it
        rec["type_value"] = SETTLEMENT_CLASSES[word]
        rec["type_closed"] = True
        whole = fold(rec["type_text"] or "")
        for rule in TREE_TYPES["rules"]:                                    # the conventions of the tree come first, as for the levels above (whole words, any language)
            if any(re.search(r"\b%s\b" % re.escape(w), whole) for w in rule["words"]):
                rec["type_value"], rec["type_string"] = rule["value"], rule["string"]
                break
    if rec["type_value"] is None and rec["type_text"]:
        own = _own_type(rec["type_text"].split(" / ")[0])
        if own:
            rec["type_string"] = own["string"]                                  # a custom type: the answer's word (the value stays unknown here)
    m = re.search(r"(-?\d{1,3}\.\d+)\s*[,|;/]\s*(-?\d{1,3}\.\d+)", first("COORDINATES"))
    rec["coordinates"] = (float(m.group(1)), float(m.group(2))) if m else None
    rec["containers"], rec["unit_notes"] = [], []
    for line in fields.get("CONTAINERS", []):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5 or (len(parts) >= 4 and re.fullmatch(r"\d+", parts[0])):
            parts = parts[1:]                       # the first column is a number: or a code, or UNKNOWN, whatever the model wrote
        if len(parts) < 3:
            continue
        name, remark = _split_remark(parts[0])
        utype, _type_remark = _split_remark(parts[1])
        if is_unknown(name):
            # the unit was written in the type column ("UNKNOWN | Webster Township (...) | ...")? read it from there
            m = re.match(r"^\s*([A-Z][\w'’.\- ]*?\s%s)\b\s*(?:\(([^()]*)\))?" % UNIT_WORDS, parts[1])
            if not m:
                rec["unit_notes"].append("a container line without a unit name was left out: %s" % line.strip()[:80])
                continue
            name, remark = m.group(1).strip(), (m.group(2) or "").strip()
            utype = re.search(UNIT_WORDS, m.group(1)).group(0).lower()
            rec["unit_notes"].append("the unit %r was written where the type belongs: read from there" % name)
        if remark:
            rec["unit_notes"].append("%s: the answer remarks: %s" % (name, remark))
        if rules.on("LV1") and any(w in fold(utype) for w in OVERLAY_WORDS):
            rec["unit_notes"].append("the level %r (%s) was left out: it is a structure that overlaps the levels of the chain and is not one of them" % (name, utype))
            continue
        start, end = _period(parts[2])
        rec["containers"].append({"name": name, "type": _clean_type(utype), "from": start, "to": end,
                                  "state": parts[3] if len(parts) > 3 else ""})
    state = first("STATE_ON_DATE").split("|")
    rec["state"] = None
    if state and state[0].strip():
        start, end = _period(state[1] if len(state) > 1 else "")
        rec["state"] = {"name": state[0].strip(), "from": start, "to": end}
    rec["differs_from_today"] = first("DIFFERS_FROM_TODAY") or None
    rec["sources"], rec["sources_without_link"] = [], []
    for line in fields.get("SOURCES", []):
        url, _, what = line.partition("|")
        if url.strip().startswith("http"):
            rec["sources"].append({"url": url.strip(), "supports": what.strip()})
        elif re.fullmatch(r"[\w.-]+\.[a-z]{2,}", url.strip()):
            rec["sources_without_link"].append(url.strip())
    # only the labels count: text the page adds after the answer ("let me know if...") is not part of it
    raw_doubts = " ".join(x.strip() for x in fields.get("NOT_SURE", []) if x.strip())
    rec["not_sure"] = {x.strip() for x in re.split(r"[,;\s]+", raw_doubts) if x.strip() in LABELS}
    words = [w for w in re.split(r"[,;\s]+", raw_doubts) if w]
    rec["not_sure_text"] = raw_doubts if (len(words) > 3 and not all(w in LABELS or is_unknown(w) for w in words)) else ""
    rec["ambiguous"] = fields.get("AMBIGUOUS", [])
    rec["candidates"] = [c for c in (_candidate(l) for l in rec["ambiguous"]) if c]
    return rec
