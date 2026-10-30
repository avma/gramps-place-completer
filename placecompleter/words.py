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
"""Words and text helpers of the analysis: the folding of names, the lists of generic words, the tests of an unknown value.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import functools
import re

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import packs


UNKNOWN_WORDS = {"", "unknown", "none", "n/a", "na", "?", "-", "unspecified", "not known"}


UNIT_WORDS = r"(?:Township|County|District|Parish|Precinct|Ward|Borough|Province|Region|Prefecture|Municipality|Kreis|Bezirk)"


CONNECTORS = {"of", "and", "the", "di", "del", "della", "dei", "degli", "de", "du", "des", "von", "van", "der", "den"}      # words between a type and a name


GENERIC = CONNECTORS | {"district", "county", "voivodeship", "crownland", "kronland", "komitat", "bezirk", "kreis",
           "kingdom", "empire", "province", "region", "municipality", "varmegye", "jaras", "kerulet", "megye", "township",
           # the same words in the languages of the region: "Județul Hunedoara" is the county Hunedoara
           "judetul", "judet", "comitatul", "comitat", "powiat", "okres", "oblast", "raion", "rayon", "gubernia", "guberniya", "zupanija",
           "zupa", "okruh", "kraj", "obec", "gmina", "wojewodztwo", "vojvodina", "pokrajina", "provincia", "comuna", "orasul", "municipiul",
           "state", "bundesstaat", "kanton", "canton", "gemeente", "comune", "commune", "provincie",
           # more of them: "Regione Emilia-Romagna" is the region Emilia-Romagna, "Land Salzburg" the state Salzburg, "Département du Nord" the department Nord
           "regione", "regio", "regiao", "regiunea", "contea", "prefettura", "prefecture", "dipartimento", "departement", "department", "departamento",
           "arrondissement", "comte", "condado", "comarca", "comunidad", "concelho", "distrito", "municipio", "estado", "land", "bundesland", "freistaat",
           "landkreis", "regierungsbezirk", "gemeinde", "provinz", "okrug", "krai", "governorate", "gouvernorat"}


_KIND_OF_PLACE = {"city", "town", "village", "hamlet", "borough", "municipality", "stadt", "ville", "stad", "gemeinde", "miasto", "mesto", "varos", "oras", "grad"}


def fold(text):
    t = packs.fold(text)
    return t.replace("tsch", "cs")


def is_unknown(text):
    return fold(text or "").strip(" .") in UNKNOWN_WORDS


@functools.lru_cache(maxsize=262144)
def _tokens_tuple(name):
    return tuple(t for t in re.split(r"[^a-z0-9]+", fold(name)) if t and t not in GENERIC)


def _tokens(name):
    return list(_tokens_tuple(name))


def _says_something(text):
    """Is there something in the text that the answer wrote for a field (not NONE, UNKNOWN, N/A or nothing)?"""
    return bool(text) and text.strip().strip(".").strip().upper() not in ("", "NONE", "UNKNOWN", "N/A", "NO", "NIL")


def _short_form(a, b):
    """Is one of the two names the other without a word that only says what kind of place it is (New York, New York City; Zürich, Stadt Zürich)?
    Then they are one name, not two: both are valid. A word that is part of a name (Johnston, Johnston Station) makes another name."""
    words = [set(re.split(r"[^a-z0-9]+", fold(x))) - {""} for x in (a, b)]
    if not (words[0] and words[1]):
        return False
    shorter, longer = sorted(words, key=len)
    return shorter <= longer and (longer - shorter) <= (GENERIC | _KIND_OF_PLACE)


def _unit_words(name):
    """The words in a name that say what kind of unit it is (county, judetul, kreis ...), folded."""
    return {t for t in re.split(r"[^a-z0-9]+", fold(name or "")) if t in GENERIC and t not in CONNECTORS}
