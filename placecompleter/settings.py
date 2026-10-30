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
"""The settings of the user that are not secret, in one small file that the window writes (nobody has to edit it by hand).

Now: the languages of the Wikipedia links of a place, in the order of preference ("he, en", "zh", "fr, es").
Default: the language of Gramps (the environment of the session), then English.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import json
import os
import re

FILE = os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "settings.json")
CODE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,8})?$")


def path():
    return os.environ.get("PLACECOMPLETER_SETTINGS") or FILE


def load():
    try:
        with open(path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data):
    target = path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def interface_language():
    """The language code of the session (LANGUAGE, LC_ALL, LANG), or '' when it is not a language (C, POSIX)."""
    for name in ("LANGUAGE", "LC_ALL", "LANG"):
        first = re.split(r"[:]", os.environ.get(name, ""))[0]
        code = re.split(r"[_.@]", first)[0].lower()
        if CODE.match(code):
            return code
    return ""


def parse_languages(text):
    """'he, en;fr' -> (['he', 'en', 'fr'], ['bad words']): codes in the order written, without repeats."""
    good, bad = [], []
    items = re.split(r"[,;\s]+", text.strip().lower()) if isinstance(text, str) else [str(x).strip().lower() for x in text]
    for item in items:
        if not item:
            continue
        if CODE.match(item):
            if item not in good:
                good.append(item)
        else:
            bad.append(item)
    return good, bad


def wikipedia_languages():
    """The languages of Wikipedia that the user wants, in the order of preference."""
    chosen = load().get("wikipedia_languages")
    if isinstance(chosen, list):
        good, _bad = parse_languages(chosen)
        if good:
            return good
    ui = interface_language()
    return [ui, "en"] if ui and ui != "en" else ["en"]


def set_wikipedia_languages(text):
    """Keep the languages typed by the user. Returns (languages, words that are not language codes); nothing is kept when none is valid."""
    good, bad = parse_languages(text)
    if good:
        data = load()
        data["wikipedia_languages"] = good
        save(data)
    return good, bad


def reset_wikipedia_languages():
    data = load()
    data.pop("wikipedia_languages", None)
    save(data)
