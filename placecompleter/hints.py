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
"""The hints that appear when the pointer rests on a field or a button of the window: short, in English, with examples where they help.
They are here and not in the window so that the texts can be read and checked without a window."""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .i18n import _ as tr

PLACE = tr("Place name to query (e.g., Parma, Sissa, Johnston).\nUse Region hint to distinguish homonymous places.")
DATE = tr("Target year for historical names and administrative structure (e.g., 1850).\nPartial or full dates are "
          "supported (e.g., 1990-05 or 1990-05-17).")
LANGUAGES = tr("Preferred Wikipedia link languages (comma-separated list, in priority order).\nAdds matching articles plus "
               "Wikidata link. Defaults to English if preferred languages are unavailable.\nExamples:\n  he, en\n  fr, es")
HINT = tr("Optional disambiguation term (county, state, region, or country).\nExamples:\n  Parma -> Italy\n  Johnston -> "
          "Iowa\nProviding a country will prompt historical administrative levels for that specific year.")
FORM = tr("Query prompt format sent to AI engine:\nauto: Automatically cycles prompt formats until successful "
          "(recommended).\ntable: Concise prompt returning structured tabular data.\nclassic: Comprehensive prompt "
          "describing all fields in detail.\nshort: Compact prompt paragraph for engines with input limits.\ndated: "
          "Classic prompt with explicit instruction to match historical date context.\nlong: Extended prompt requesting "
          "comparative present-day versus historical analysis.")
ENGINE = tr("Selected AI service provider.\nWeb options (Google AI, ChatGPT, Gemini) open in browser for manual paste back.\n"
            "API key options (Claude, OpenAI) and local Ollama process queries automatically.\nCheckmarks indicate ready "
            "status; crosses detail missing setup.")
ASK = tr("Submit query to selected AI. Does not modify family tree data.")
WIKIDATA = tr("Query Wikidata for missing place coordinates after analysis.\nOnly place names are transmitted.")
ANSWER = tr("AI response panel. Automated responses populate here directly.\nFor browser queries, copy and paste the raw "
            "response text here.")
PASTE = tr("Paste clipboard text into the response box.")
ANALYSE = tr("Analyze response text and generate preview of tree modifications. No data is changed yet.")
LEVELS = tr("Identified administrative levels, ordered from local to regional.\nUncheck any uncertain level to exclude it "
            "from tree updates.")
NEEDS = tr("Analysis summary. Red warnings indicate items requiring review before applying changes.")
APPLY = tr("Apply selected changes to the family tree in a single operation (reversible via Edit > Undo).")

TOGGLE_ALL = tr("Toggle selection for all non-conflicting proposals.\nManual review required for: tree conflicts, unverified "
                "web links, and mutually exclusive changes.\nReview modifications to existing tree elements carefully before "
                "applying.")

ALL = {"toggle_all": TOGGLE_ALL, "place": PLACE, "date": DATE, "hint": HINT, "form": FORM, "engine": ENGINE, "ask": ASK, "wikidata": WIKIDATA, "answer": ANSWER,
       "paste": PASTE, "analyse": ANALYSE, "levels": LEVELS, "needs": NEEDS, "apply": APPLY}
