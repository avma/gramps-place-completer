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
"""A SETTLEMENT's name should not repeat its type: "City of Johnston" (type City) is "Johnston".

Only settlements (city, town, village, hamlet, borough, municipality) lose the English prefix "<type word> of", and only when the place's own
type is that word (so "City of Johnston" of type City, but never "Bay of Pigs"). Administrative units keep their word: "Polk County",
"State of Iowa", "Kingdom of Hungary", "Bács-Bodrog vármegye", "Zombori járás" are the usual names of those places, consistent with each
other and with the Hungarian ones. The English suffix forms ("Polk County", "Webster Township") are never touched.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re

SETTLEMENT_WORDS = {"city", "town", "village", "hamlet", "borough", "municipality"}
VALUE_WORDS = {13: ("borough",), 14: ("municipality",), 4: ("city",), 15: ("town",), 16: ("village",), 17: ("hamlet",)}
KEEP = {"city of london", "city of westminster"}           # here "City of" is the name of a different place, not a type word
_PATTERN = re.compile(r"^(?P<word>[A-Za-z]+)\s+of\s+(?P<rest>\S.*)$", re.IGNORECASE)


def plain_name(name, type_value=None, type_text=""):
    """'City of Johnston' -> 'Johnston' when the type says City (a Gramps type value, or the words of a type text); else the name as it is."""
    text = (name or "").strip()
    m = _PATTERN.match(text)
    if not m or " ".join(text.casefold().split()) in KEEP:
        return text
    words = (set(VALUE_WORDS.get(type_value, ())) | set(re.findall(r"[a-z]+", (type_text or "").casefold()))) & SETTLEMENT_WORDS
    return " ".join(m.group("rest").split()) if m.group("word").casefold() in words else text


def settlement_like(type_value=None, type_text=""):
    """Is this a settlement (a city, a town, a village ...) by its Gramps type value or by the words of a type text ("city, municipal corporation")?"""
    words = set(re.findall(r"[a-z]+", (type_text or "").casefold()))
    return type_value in VALUE_WORDS or bool(words & (SETTLEMENT_WORDS | {"municipal", "corporation", "community"}))


# The language the names of a place are written in follows the state that ruled it (the convention of the tree: Hungary -> hu, Romania -> ro,
# Ukraine -> uk ...). Only states with one official language are here, by their whole folded name: "Austria-Hungary" is not one of them, and for a
# state that is not here the language of a name is left empty, as it always was.
STATE_LANGUAGES = {
    "romania": "ro", "kingdom of romania": "ro", "socialist republic of romania": "ro", "moldova": "ro",
    "hungary": "hu", "kingdom of hungary": "hu", "magyarorszag": "hu", "kingdom of hungary (1000-1946)": "hu",
    "austria": "de", "austrian empire": "de", "empire of austria": "de", "kaisertum osterreich": "de", "osterreich": "de",
    "germany": "de", "german empire": "de", "deutsches reich": "de", "prussia": "de", "kingdom of prussia": "de",
    "poland": "pl", "kingdom of poland": "pl", "ukraine": "uk", "czechoslovakia": "cs", "czech republic": "cs", "czechia": "cs",
    "slovakia": "sk", "serbia": "sr", "kingdom of serbia": "sr", "croatia": "hr", "slovenia": "sl",
    "russia": "ru", "russian empire": "ru", "france": "fr", "italy": "it", "kingdom of italy": "it", "italia": "it", "repubblica italiana": "it", "italian republic": "it", "regno d'italia": "it", "netherlands": "nl",
    "lithuania": "lt", "latvia": "lv", "estonia": "et", "bulgaria": "bg", "greece": "el", "turkey": "tr", "israel": "he",
    "denmark": "da", "sweden": "sv", "norway": "no", "finland": "fi", "spain": "es", "portugal": "pt",
    "united states": "en", "united states of america": "en", "usa": "en", "united kingdom": "en", "great britain": "en", "england": "en",
}


def state_language(state):
    """The language code of the names that a state's rule goes with ('' when the state is not known or has no single language)."""
    import unicodedata
    text = unicodedata.normalize("NFKD", state or "")
    key = " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())
    return STATE_LANGUAGES.get(key, "")

