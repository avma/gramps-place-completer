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
"""A small gettext compiler: .po text to .mo bytes, in plain Python (no msgfmt needed). Used by deploy_addon.py to make the addon's translation."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import array
import struct


def _unquote(text):
    body = text.strip()
    if not (body.startswith('"') and body.endswith('"')):
        raise ValueError("not a quoted string: %r" % text)
    out, i, body = [], 0, body[1:-1]
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(escapes.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def parse_po(text):
    """{msgid: msgstr} of the translated entries (an empty msgstr is a missing translation and is not in the result), plus the header
    under the key ''. Understands msgid/msgstr with continuation lines, comments, and #, fuzzy (a fuzzy entry is not used)."""
    entries, current, field, fuzzy = [], {}, None, False

    def flush():
        nonlocal current, field, fuzzy
        if "msgid" in current:
            entries.append((current["msgid"], current.get("msgstr", ""), fuzzy))
        current, field, fuzzy = {}, None, False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("#"):
            continue
        elif line.startswith("msgid "):
            if "msgstr" in current:
                flush()
            current["msgid"], field = _unquote(line[6:]), "msgid"
        elif line.startswith("msgstr "):
            current["msgstr"], field = _unquote(line[7:]), "msgstr"
        elif line.startswith('"') and field:
            current[field] += _unquote(line)
    flush()
    return {mid: mstr for mid, mstr, fz in entries if mstr and not fz}


def compile_mo(catalog):
    """The bytes of a .mo file for {msgid: msgstr}."""
    catalog = dict(catalog)
    catalog.setdefault("", "Content-Type: text/plain; charset=UTF-8\n")
    ids = sorted(catalog)
    ids_blob, strs_blob, id_index, str_index = b"", b"", [], []
    for mid in ids:
        a, b = mid.encode("utf-8"), catalog[mid].encode("utf-8")
        id_index.append((len(a), len(ids_blob)))
        ids_blob += a + b"\0"
        str_index.append((len(b), len(strs_blob)))
        strs_blob += b + b"\0"
    count = len(ids)
    keystart = 7 * 4 + 16 * count
    valuestart = keystart + len(ids_blob)
    koffsets, voffsets = [], []
    for length, offset in id_index:
        koffsets += [length, offset + keystart]
    for length, offset in str_index:
        voffsets += [length, offset + valuestart]
    header = struct.pack("Iiiiiii", 0x950412DE, 0, count, 7 * 4, 7 * 4 + count * 8, 0, 0)
    return header + array.array("i", koffsets + voffsets).tobytes() + ids_blob + strs_blob
