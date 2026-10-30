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
"""The question that is sent to Google (AI mode) or to a chatbot, and the link that opens it.

Google AI mode is opened by the URL parameter udm=50 (https://www.google.com/search?udm=50&q=...). A normal search
page ignores a long template, so the link must carry udm=50. The answer is read by ingest.py.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re
import urllib.parse

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import data as datalib

SETTLEMENT_WORDS = "metropolis | city | town | village | hamlet | neighborhood | locality"
NESTING_RULE = ("CONTAINERS lists only divisions that nest, each wholly inside the next, up to the sovereign state: leave out a structure that overlaps them "
                "without being inside one (an intercommunality, for example). ")
SETTLEMENT_GUIDE = ("SETTLEMENT_TYPE_ON_DATE is ONE of the words listed, chosen by the size and character of the settlement itself IN {date} (not today, and "
                    "not by its legal status: commune, municipality and the like are a different question and are not an answer here): metropolis over about "
                    "500,000 inhabitants; city about 30,000 to 500,000; town about 2,000 to 30,000; village about 100 to 2,000; hamlet under about 100; in "
                    "earlier centuries judge by the settlements of that country and period; neighborhood is a named part of a city or town; locality is a named "
                    "place that is not a settlement with residents (a station, an estate, a crossing). After a bar, write the local historical term. ")


LONG = """Administrative history lookup. Place: {place}. Date: {date}.
Answer ONLY with the block below, in plain text: no introduction, no summary, no questions, no markdown, no bullets. Write UNKNOWN for anything you cannot verify; do not guess. Periods: YYYY-YYYY or YYYY-present. Name, type and containers must be those valid on {date}, not today's.

PLACE_NAME_ON_DATE: <name in the language of the ruling state on that date>
LANGUAGE: <code, e.g. hu, de, ro, sr>
OTHER_NAMES: <code>: <name> (<from>-<to>), one per line: only other languages or other times, not the name above or a short form of it
SETTLEMENT_TYPE_ON_DATE: <the lowest level that is a place, not a building or a street, as exactly one of: metropolis | city | town | village | hamlet | neighborhood | locality> | <the local historical term>
COORDINATES: <latitude>, <longitude> (decimal degrees)
CONTAINERS: one line per level, smallest unit first, up to the sovereign state (the country, the last line), each as:
<level number: 1 for the smallest unit, then 2, 3 ...; not an official code> | <unit name as used then> | <unit type: the generic English type (state, county, province, region, district, municipality, canton ...) and the local term> | <from>-<to> | <sovereign state>
STATE_ON_DATE: <sovereign state or empire> | <from>-<to>
DIFFERS_FROM_TODAY: <yes or no; if yes, what differs (name, type, containers)>
NOTES: <one or two sentences on assumptions, ambiguity or uncertain dates, or NONE>
SOURCES: one per line, at most 5: <full URL> | <what it supports>
NOT_SURE: <uncertain items above>

{levels}Every container must be valid on {date}. [[GUIDE]]For a level between the municipality and the country (district, county, province, region, canton) write its official name including the word for its type when that word is part of the official name (Provincia di Parma, Kanton Zürich, Județul Hunedoara). Never add a type word to the name of a municipality, city, town, village or the country: Tel Aviv, not City of Tel Aviv; Israel, not State of Israel; Kfar Hess, not Village Kfar Hess. If the name is ambiguous, choose the best-known place of that name and say so in NOTES (name the others there); write AMBIGUOUS: followed by the candidates (name, country, coordinates) and stop only if no candidate is clearly the main one."""

LONG = LONG.replace("[[GUIDE]]", SETTLEMENT_GUIDE + NESTING_RULE)

LONG_CLASSIC = """Administrative history lookup. Place: {place}. Date: {date}.
Answer ONLY with the block below, in plain text: no introduction, no summary, no questions, no markdown, no bullet points. Write UNKNOWN for anything you cannot verify; do not guess. Years have four digits; periods are written YYYY-YYYY (or YYYY-present).

PLACE_NAME_ON_DATE: <name in the official language of the ruling state on that date>
LANGUAGE: <language code of that name, e.g. hu, de, ro, sr>
OTHER_NAMES: <language code>: <name> (<from>-<to>), one per line: only names in other languages or used at other times, not the name above or a short form of it
SETTLEMENT_TYPE_ON_DATE: <the lowest level that is a place, not a building or a street, as exactly one of: metropolis | city | town | village | hamlet | neighborhood | locality> | <the local historical term>
COORDINATES: <latitude>, <longitude> (decimal degrees)
CONTAINERS: one line per administrative level, from the smallest unit that contains the place up to the sovereign state (the country, the last line), each line as:
<level number: 1 for the smallest unit, then 2, 3 ...; not an official code> | <unit name as used then> | <unit type: the generic English type (state, county, province, region, district, municipality, canton ...) and the local term> | <valid from>-<valid to> | <sovereign state it belonged to>
STATE_ON_DATE: <name of the sovereign state or empire> | <from>-<to>
NOTES: <one or two sentences on assumptions, ambiguity or uncertain dates, or NONE>
SOURCES: one line each, at most 5: <URL> | <what it supports>
NOT_SURE: <the items above that are uncertain>

{levels}Every container must be valid on {date}. [[GUIDE]]For a level between the municipality and the country (district, county, province, region, canton) write its official name including the word for its type when that word is part of the official name (Provincia di Parma, Kanton Zürich, Județul Hunedoara). Never add a type word to the name of a municipality, city, town, village or the country: Tel Aviv, not City of Tel Aviv; Israel, not State of Israel; Kfar Hess, not Village Kfar Hess. If the place name is ambiguous, choose the best-known place of that name and say so in NOTES (name the others there); write AMBIGUOUS: followed by the candidates (name, country, coordinates) and stop only if no candidate is clearly the main one."""

LONG_CLASSIC = LONG_CLASSIC.replace("[[GUIDE]]", SETTLEMENT_GUIDE + NESTING_RULE)

LONG_DATED = LONG_CLASSIC.replace(
    "Years have four digits; periods are written YYYY-YYYY (or YYYY-present).",
    "Years have four digits; periods are written YYYY-YYYY (or YYYY-present). Name, type and containers must be those valid on {date}, not today's.")

SHORT = ("{place} in {date}. Reply with exactly these labelled lines and nothing else, UNKNOWN if not sure. "
         "PLACE_NAME_ON_DATE: official name then. LANGUAGE: code. SETTLEMENT_TYPE_ON_DATE: exactly one of metropolis | city | town | village | hamlet | neighborhood | locality (its size class then, not its legal status: over 500,000 / 30,000-500,000 / 2,000-30,000 / 100-2,000 / under 100 inhabitants; neighborhood = a part of a city, locality = not a settlement), then | local term. "
         "COORDINATES: decimal. CONTAINERS: one line per level, smallest to largest, as level number (1, 2, 3 ...) | unit | generic English type then local term | years | sovereign state, the last line being the country; only divisions that nest (no intercommunalities). "
         "STATE_ON_DATE: sovereign state | years. NOTES: assumptions or ambiguity (choose the best-known place of that name and say so), or NONE. "
         "SOURCES: URL | what it supports. NOT_SURE: items. Names: a level between the municipality and the country (district, county, province, region, canton) with the "
         "word for its type when it is part of the official name (Provincia di Parma, Kanton Zürich); no type word on a municipality, city, town, village or country "
         "(Tel Aviv, Israel, Kfar Hess). {levels}")


TABLE = """What was the type of the settlement {place} in {date}, and which administrative levels did it belong to in that year (from the lowest level to the highest, up to the sovereign state; only levels that nest inside each other, no overlapping structures such as intercommunalities)? What are its coordinates, in decimal degrees?
If several places have this name, choose the most likely one and list the others in the Alternatives line.

Reply in two parts only, in plain text, with no introduction and everything in English except the Explanation column.

Part 1, two lines:
Name: <official name of the place in {date}> | Language: <ISO code of the language of that name: fr, en, he ...> | From: <YYYY in which the name began to be used, or UNKNOWN> | Source: <full URL>
Alternatives: <up to 3 other places: name | region | country>, or NONE

Part 2, one table with exactly these columns:
Category | Value/Name | Year Range | Level Type | Explanation | Source

The rows, in this order: Place Type, Level 1, Level 2, ..., Sovereign state, Latitude, Longitude.
- Place Type: Value/Name is ONE word only, by the size of the settlement itself in {date}: metropolis (over about 500,000 inhabitants) | city (30,000-500,000) | town (2,000-30,000) | village (100-2,000) | hamlet (under 100). Year Range and Level Type: empty.
- Level N and Sovereign state: Level 1 is the unit directly ABOVE the settlement: do not list the settlement itself, or a municipality with the same name as the settlement, as a level. Value/Name is the official local name in {date}. Year Range: YYYY-present or YYYY-YYYY (the period in which this level, with this name, included the place). Level Type: one word from country | state | region | province | department | county | district | municipality | other (for other write: other (local term)).
- Latitude and Longitude: Value/Name is a decimal number only; the other columns are empty.
- Explanation: one short sentence in the language with ISO code {language}. The legal status of the place (for example commune) belongs only here.
- Source: one full URL, written out as visible text (not a hidden link), for each row that has a source; otherwise empty.
{levels}"""

FORMS = {"table": TABLE, "classic": LONG_CLASSIC, "short": SHORT, "dated": LONG_DATED, "long": LONG}
AUTO_ORDER = ["table", "classic", "short", "dated", "long"]      # Google AI mode refused "long" twice and answered classic and short


def build_prompt(place, date, form="classic", levels="", language=""):
    """form: classic (the first template: answered every time), short (answered), dated (classic plus one sentence that the
    date matters), long (dated plus a DIFFERS_FROM_TODAY line: Google AI mode answered "no answer" both times it was sent)."""
    return FORMS[form].format(place=place.strip(), date=str(date).strip(), levels=levels or "", language=language or "en").rstrip()


def ai_mode_url(prompt):
    """The link that opens Google in AI mode with the question already asked."""
    return "https://www.google.com/search?" + urllib.parse.urlencode({"udm": "50", "q": prompt}, quote_via=urllib.parse.quote)


ENGINES = ("google", "chatgpt", "gemini")


def load_no_answer_phrases(directory=""):
    """The words by which a search service says it has no answer (data/no-answer-phrases.json), else the English ones."""
    data = datalib.load("no-answer-phrases.json", {}, directory)
    phrases = data.get("phrases") if isinstance(data, dict) else None
    found = tuple(str(p) for p in phrases if p) if isinstance(phrases, list) else ()
    return found or ("no answer for this search", "try asking something else")


NO_ANSWER = load_no_answer_phrases()


def engine_url(engine, prompt):
    """The link that opens an AI with the question: Google AI mode (udm=50), ChatGPT (?q=, web search on) or Gemini (?q=)."""
    q = urllib.parse.urlencode({"q": prompt}, quote_via=urllib.parse.quote)
    if engine == "chatgpt":
        return "https://chatgpt.com/?hints=search&" + q
    if engine == "gemini":
        return "https://gemini.google.com/app?" + q
    return ai_mode_url(prompt)


def looks_like_echo(text):
    """Is the 'answer' the question itself (the AI could not fill the template in and gave it back): its own instruction, or the template with its <fields> unfilled."""
    low = (text or "").lower()
    if any(m in low for m in ("answer only with the block below", "administrative history lookup. place:", "reply with exactly these labelled lines", "reply in two parts only")):
        return True                                                       # the instruction of a form, or the first line of one
    return len(re.findall(r"^\s*[A-Z_]{4,}:\s*<[^<>\n]+>", text or "", re.M)) >= 2


def looks_like_no_answer(text):
    low = (text or "").lower()
    return any(m in low for m in NO_ANSWER)
