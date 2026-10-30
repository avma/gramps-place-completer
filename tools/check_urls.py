#!/usr/bin/env python3
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
"""Check the web addresses in the saved answers: does the page exist? (It does not check that the page says what the AI says it does.)

Usage:
    python3 tools/check_urls.py [--answers DIR] [--pause 1.5] [--retries 3] [--timeout 15] [--out FILE.tsv]

--answers  the folder of saved answers (default ~/gramps-place-work/answers-table); every NAME.txt is read, the folder `rejected` is not.
--pause    seconds to wait between two requests to the same site (default 1.5): a site that is asked too fast says "429 Too Many Requests".
--retries  how many times to try again when a site says to slow down (429) or is busy (503); it waits as long as the site asks (at most 60 s).
--out      the result for every address as a table (default: next to the answers, urls.tsv).

The program says who it is (a User-Agent) and asks for the head of the page only (HEAD, then GET when the site does not allow HEAD).
The result of each address is one of:
    ok        the page answered (2xx, after redirects)
    missing   404 or 410: the page is not there: the address is wrong
    blocked   401 or 403: the site refuses programs; this says nothing about the address
    slow      429 or 503 even after the retries: the site was too busy; ask again later
    error     no answer at all (a name that does not exist, a time-out)
Nothing is written to any tree.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import argparse
import collections
import glob
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AGENT = "PlaceCompleter-urlcheck/1.0 (a Gramps addon; https://github.com/avma/gramps-place-completer)"
WORK = os.path.expanduser("~/gramps-place-work")
ADDRESS = re.compile(r"https?://[^\s<>\"'|\u00a0]+")


def extract_urls(text):
    """The web addresses in a text; the punctuation of a sentence and a bracket that is not part of the address are not."""
    found = []
    for url in ADDRESS.findall(text or ""):
        while url:
            if url[-1] in ".,;:!?\u2026":
                url = url[:-1]
            elif url[-1] == ")" and url.count("(") < url.count(")"):
                url = url[:-1]
            elif url[-1] == "]" and url.count("[") < url.count("]"):
                url = url[:-1]
            else:
                break
        if url:
            found.append(url)
    return found


def canonical(url):
    """One form for the same address (letters written plainly or as %C3%A1)."""
    return urllib.parse.quote(urllib.parse.unquote(url), safe=":/?#[]@!$&'()*+,;=%-._~")


def collect_urls(folder):
    """{address: [files that have it]} from the answers of the folder, in the order found."""
    found = collections.OrderedDict()
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        with open(path, encoding="utf-8") as fh:
            for url in extract_urls(fh.read()):
                found.setdefault(canonical(url), [])
                name = os.path.basename(path)
                if name not in found[canonical(url)]:
                    found[canonical(url)].append(name)
    return found


def kind(code):
    if 200 <= code < 400:
        return "ok"
    if code in (404, 410):
        return "missing"
    if code in (401, 403):
        return "blocked"
    if code in (429, 503):
        return "slow"
    return "error"


def _request(url, method, timeout):
    request = urllib.request.Request(url, method=method, headers={"User-Agent": AGENT, "Accept": "text/html,*/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return answer.status


def _once(url, timeout, opener):
    """(code, seconds the site asked to wait or None): HEAD, then GET when the site does not allow HEAD. code 0: no answer at all."""
    for method in ("HEAD", "GET"):
        try:
            return opener(url, method, timeout), None
        except urllib.error.HTTPError as error:
            wait = error.headers.get("Retry-After") if error.headers else None
            asked = min(60, int(wait)) if wait and str(wait).isdigit() else None
            if method == "HEAD" and error.code in (400, 403, 405, 501):
                continue                                                      # some sites do not answer HEAD: ask again with GET
            return error.code, asked
        except (urllib.error.URLError, OSError, ValueError):
            return 0, None
    return 0, None


def check(url, timeout=15, retries=3, sleep=time.sleep, opener=_request):
    """(code, kind) of an address; when the site says 429 or 503 it waits as long as the site asks (or 5, 10, 20 ... seconds) and asks again."""
    code = 0
    for attempt in range(retries + 1):
        code, asked = _once(url, timeout, opener)
        if code in (429, 503) and attempt < retries:
            sleep(asked if asked is not None else 5 * (2 ** attempt))
            continue
        break
    return code, kind(code)


def check_all(urls, pause=1.5, retries=3, timeout=15, sleep=time.sleep, opener=_request, say=lambda s: None):
    """[(url, code, kind)] for the addresses, with a pause between two requests to the same site."""
    results, last = [], {}
    for number, url in enumerate(urls, 1):
        host = urllib.parse.urlsplit(url).netloc
        if host in last:
            wait = pause - (time.monotonic() - last[host])
            if wait > 0:
                sleep(wait)
        code, result = check(url, timeout=timeout, retries=retries, sleep=sleep, opener=opener)
        last[host] = time.monotonic()
        results.append((url, code, result))
        say("%3d/%d  %s  %s" % (number, len(urls), code or "---", url))
    return results


def summary(results, sources=None):
    count = collections.Counter(r[2] for r in results)
    lines = ["", "addresses checked: %d" % len(results)] + ["  %-8s %3d" % (k, count[k]) for k in ("ok", "missing", "blocked", "slow", "error") if count[k]]
    problems = [r for r in results if r[2] in ("missing", "error")]
    if problems:
        lines += ["", "the page is not there (missing) or there was no answer (error):"]
        for url, code, result in problems:
            lines.append("  %-7s %s  %s" % (result, code or "---", url) + ("   <- " + ", ".join((sources or {}).get(url, [])[:3]) if sources else ""))
    other = [r for r in results if r[2] in ("blocked", "slow")]
    if other:
        lines += ["", "not decided (the site refuses programs, or was too busy): %d. Open a few by hand, or ask again later." % len(other)]
    return "\n".join(lines)


def main(argv=None, opener=_request, sleep=time.sleep):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", default=os.path.join(WORK, "answers-table"))
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    sources = collect_urls(args.answers)
    if not sources:
        print("no web addresses in %s" % args.answers)
        return 2
    print("%d different addresses; about %d seconds at one request every %.1f s" % (len(sources), int(len(sources) * args.pause), args.pause))
    results = check_all(list(sources), args.pause, args.retries, args.timeout, sleep=sleep, opener=opener, say=lambda s: print(s, file=sys.stderr, flush=True))
    out = args.out or os.path.join(args.answers, "urls.tsv")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("result\tcode\turl\tanswers\n")
        for url, code, result in results:
            fh.write("%s\t%s\t%s\t%s\n" % (result, code, url, ", ".join(sources[url])))
    print(summary(results, sources))
    print("\ntable: %s" % out)
    return 0 if not any(r[2] in ("missing", "error") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
