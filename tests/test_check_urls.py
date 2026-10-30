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
"""tools/check_urls.py: the web addresses of the saved answers, found and checked politely."""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

spec = importlib.util.spec_from_file_location("check_urls", os.path.join(ROOT, "tools", "check_urls.py"))
check_urls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_urls)


class Handler(BaseHTTPRequestHandler):
    busy = {"n": 0}
    seen_agents = []

    def log_message(self, *args):
        pass

    def reply(self, code, headers=None, body=b""):
        self.send_response(code)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def handle_any(self):
        Handler.seen_agents.append(self.headers.get("User-Agent"))
        path = self.path
        if path == "/ok":
            self.reply(200)
        elif path == "/missing":
            self.reply(404)
        elif path == "/blocked":
            self.reply(403)
        elif path == "/moved":
            self.reply(301, {"Location": "/ok"})
        elif path == "/nohead":
            self.reply(405 if self.command == "HEAD" else 200)
        elif path == "/busy":
            Handler.busy["n"] += 1
            self.reply(429 if Handler.busy["n"] < 3 else 200, {"Retry-After": "7"})
        elif path == "/always-busy":
            self.reply(429)
        else:
            self.reply(404)

    do_HEAD = do_GET = handle_any


class Server:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class FindTests(unittest.TestCase):
    def test_the_addresses_of_a_text_without_the_punctuation_of_the_sentence(self):
        text = ("See https://example.org/a, and https://example.org/b. (https://example.org/c) <https://example.org/d> "
                "[x](https://example.org/e) https://example.org/f; \"https://example.org/g\"")
        self.assertEqual(check_urls.extract_urls(text), ["https://example.org/a", "https://example.org/b", "https://example.org/c", "https://example.org/d",
                                                         "https://example.org/e", "https://example.org/f", "https://example.org/g"])

    def test_a_bracket_that_is_part_of_the_address_is_kept(self):
        text = "[Wikipedia](https://en.wikipedia.org/wiki/Hunedoara_County_(historic)). and https://en.wikipedia.org/wiki/Kingdom_of_Hungary_(1867\u20131918)."
        self.assertEqual(check_urls.extract_urls(text), ["https://en.wikipedia.org/wiki/Hunedoara_County_(historic)",
                                                         "https://en.wikipedia.org/wiki/Kingdom_of_Hungary_(1867\u20131918)"])

    def test_the_same_address_written_in_two_ways_is_one(self):
        self.assertEqual(check_urls.canonical("https://en.wikipedia.org/wiki/B\u00e1cs-Bodrog_County"),
                         check_urls.canonical("https://en.wikipedia.org/wiki/B%C3%A1cs-Bodrog_County"))

    def test_the_addresses_of_a_folder_with_the_answers_that_have_them(self):
        work = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(work, "rejected"))
            for name, text in (("A_1900.txt", "x https://example.org/one https://example.org/two"), ("B_1900.txt", "https://example.org/one"),
                               ("rejected/C_1900.txt", "https://example.org/rejected")):
                with open(os.path.join(work, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
            found = check_urls.collect_urls(work)
            self.assertEqual(dict(found), {"https://example.org/one": ["A_1900.txt", "B_1900.txt"], "https://example.org/two": ["A_1900.txt"]})
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_kind_of_each_code(self):
        self.assertEqual([check_urls.kind(c) for c in (200, 301, 404, 410, 401, 403, 429, 503, 500, 0)],
                         ["ok", "ok", "missing", "missing", "blocked", "blocked", "slow", "slow", "error", "error"])


class CheckTests(unittest.TestCase):
    def test_a_page_that_is_there_a_page_that_is_not_and_a_site_that_refuses_programs(self):
        with Server() as s:
            self.assertEqual(check_urls.check(s.base + "/ok", sleep=lambda x: None), (200, "ok"))
            self.assertEqual(check_urls.check(s.base + "/moved", sleep=lambda x: None), (200, "ok"))          # a redirect is followed
            self.assertEqual(check_urls.check(s.base + "/missing", sleep=lambda x: None), (404, "missing"))
            self.assertEqual(check_urls.check(s.base + "/blocked", sleep=lambda x: None), (403, "blocked"))

    def test_a_site_that_does_not_allow_head_is_asked_with_get(self):
        with Server() as s:
            self.assertEqual(check_urls.check(s.base + "/nohead", sleep=lambda x: None), (200, "ok"))

    def test_a_site_that_says_to_slow_down_is_waited_for_as_long_as_it_asks(self):
        Handler.busy["n"] = 0
        waits = []
        with Server() as s:
            self.assertEqual(check_urls.check(s.base + "/busy", retries=3, sleep=waits.append), (200, "ok"))
        self.assertEqual(waits, [7, 7])                                                                       # the Retry-After of the site, twice

    def test_a_site_that_never_stops_saying_slow_down_is_slow_and_not_missing(self):
        waits = []
        with Server() as s:
            self.assertEqual(check_urls.check(s.base + "/always-busy", retries=2, sleep=waits.append), (429, "slow"))
        self.assertEqual(waits, [5, 10])                                                                      # 5, 10 ... when the site does not say

    def test_no_answer_at_all_is_an_error(self):
        def refuse(url, method, timeout):
            raise urllib.error.URLError("no such host")
        self.assertEqual(check_urls.check("http://no.such.host.invalid/", opener=refuse, sleep=lambda x: None), (0, "error"))

    def test_the_program_says_who_it_is(self):
        Handler.seen_agents.clear()
        with Server() as s:
            check_urls.check(s.base + "/ok", sleep=lambda x: None)
        self.assertTrue(all(a.startswith("PlaceCompleter-urlcheck/") for a in Handler.seen_agents))

    def test_there_is_a_pause_between_two_requests_to_the_same_site(self):
        pauses = []
        with Server() as s:
            check_urls.check_all([s.base + "/ok", s.base + "/missing", s.base + "/blocked"], pause=1.5, sleep=pauses.append)
        self.assertEqual(len(pauses), 2)
        self.assertTrue(all(0 < p <= 1.5 for p in pauses))


class MainTests(unittest.TestCase):
    def test_the_report_names_the_addresses_that_are_not_there_and_the_answers_that_have_them(self):
        work = tempfile.mkdtemp()
        try:
            with Server() as s:
                with open(os.path.join(work, "Place_1900.txt"), "w", encoding="utf-8") as fh:
                    fh.write("%s/ok %s/missing %s/blocked" % (s.base, s.base, s.base))
                buffer, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(errors):
                    code = check_urls.main(["--answers", work, "--pause", "0"], sleep=lambda x: None)
            out = buffer.getvalue()
            self.assertEqual(code, 1)                                                                           # one page is missing
            self.assertIn("addresses checked: 3", out)
            self.assertIn("missing", out)
            self.assertIn("/missing", out)
            self.assertIn("Place_1900.txt", out)
            self.assertIn("not decided", out)                                                                   # the blocked one
            with open(os.path.join(work, "urls.tsv"), encoding="utf-8") as fh:
                self.assertEqual(len(fh.read().splitlines()), 4)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_a_folder_without_addresses_is_said(self):
        work = tempfile.mkdtemp()
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                self.assertEqual(check_urls.main(["--answers", work]), 2)
            self.assertIn("no web addresses", buffer.getvalue())
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
