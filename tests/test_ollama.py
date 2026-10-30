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
"""placecompleter/ollama.py: what Ollama lacks, and the steps the program takes for the user. Nothing here needs Ollama or a network."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from placecompleter import engines, ollama                                                  # noqa: E402


def listening(answer):
    return lambda host, port, timeout=0.5: answer


def models(*ids):
    return lambda url, headers, timeout=20: {"data": [{"id": i, "created": 1} for i in ids]}


class FakeStream:
    """What urlopen gives for a streamed answer: lines of JSON as bytes."""
    def __init__(self, *items, then=None):
        self.lines = [(json.dumps(i) if isinstance(i, dict) else i).encode() + b"\n" for i in items]
        self.then, self.closed = then, False

    def __iter__(self):
        yield from self.lines
        if self.then:
            raise self.then

    def close(self):
        self.closed = True


class BinaryAndStateTests(unittest.TestCase):
    def test_the_program_is_found_on_the_path_or_in_the_places_the_installer_uses(self):
        self.assertEqual(ollama.binary(which=lambda n: "/somewhere/ollama", exists=lambda p: False), "/somewhere/ollama")
        self.assertEqual(ollama.binary(which=lambda n: None, exists=lambda p: p == "/usr/local/bin/ollama"), "/usr/local/bin/ollama")
        self.assertEqual(ollama.binary(which=lambda n: None, exists=lambda p: False), "")

    def state(self, listen, installed, *ids):
        return ollama.state(listening=listening(listen), which=lambda n: "/usr/bin/ollama" if installed else None, exists=lambda p: False,
                            http_get=models(*ids))

    def test_the_four_states(self):
        self.assertEqual(self.state(False, False), "missing")
        self.assertEqual(self.state(False, True), "stopped")
        self.assertEqual(self.state(True, True), "no-model")
        self.assertEqual(self.state(True, True, "llama3.2:latest"), "ready")

    def test_a_model_for_embeddings_cannot_answer_so_it_is_not_a_model(self):
        self.assertEqual(self.state(True, True, "nomic-embed-text:latest"), "no-model")
        self.assertEqual(ollama.installed_models(models("nomic-embed-text", "qwen2.5:7b")), ["qwen2.5:7b"])

    def test_a_server_that_answers_badly_is_a_server_without_a_model(self):
        def bad(url, headers, timeout=20):
            raise engines.EngineError("the service answered HTTP 500")
        self.assertEqual(ollama.state(listening=listening(True), which=lambda n: None, exists=lambda p: False, http_get=bad), "no-model")
        self.assertEqual(ollama.installed_models(lambda url, headers, timeout=20: "not a listing"), [])

    def test_the_official_command_is_the_one_ollama_documents(self):
        self.assertEqual(ollama.INSTALL_COMMAND, "curl -fsSL https://ollama.com/install.sh | sh")


class StartServerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = os.path.join(tmp.name, "logs", "ollama-serve.log")

    def run_it(self, popen, probes, **extra):
        clock = {"t": 0.0}
        answers = list(probes)

        def listen(host, port, timeout=0.5):
            return answers.pop(0) if len(answers) > 1 else answers[0]

        def sleep(seconds):
            clock["t"] += seconds
        return ollama.start_server(popen=popen, listening=listen, sleep=sleep, now=lambda: clock["t"], log_path=self.log,
                                   which=lambda n: "/usr/bin/ollama", exists=lambda p: False, **extra)

    def test_it_is_started_detached_in_the_background_and_waited_for(self):
        calls = []
        ok, message = self.run_it(lambda argv, **kw: calls.append((argv, kw)), [False, False, True])
        self.assertEqual((ok, message), (True, ""))
        argv, kw = calls[0]
        self.assertEqual(argv, ["/usr/bin/ollama", "serve"])
        self.assertTrue(kw["start_new_session"])                                  # it does not die with the window
        self.assertEqual(kw["stdin"], __import__("subprocess").DEVNULL)
        self.assertTrue(os.path.exists(self.log))                                  # what it says goes to a file

    def test_when_it_never_answers_the_log_is_named(self):
        ok, message = self.run_it(lambda argv, **kw: None, [False], wait=3)
        self.assertFalse(ok)
        self.assertIn(self.log, message)

    def test_when_it_cannot_be_started_the_reason_is_said(self):
        def boom(argv, **kw):
            raise OSError("Permission denied")
        ok, message = self.run_it(boom, [False])
        self.assertEqual((ok, "Permission denied" in message), (False, True))

    def test_nothing_is_started_when_it_is_not_installed(self):
        called = []
        ok, message = ollama.start_server(popen=lambda *a, **k: called.append(1), listening=listening(False), which=lambda n: None,
                                          exists=lambda p: False, log_path=self.log)
        self.assertEqual((ok, called), (False, []))
        self.assertIn("not installed", message)


class PullTests(unittest.TestCase):
    def run_it(self, stream, cancelled=lambda: False, error=None):
        seen, requests = [], []

        def opener(request, timeout=60):
            requests.append((request.full_url, request.data, request.headers, timeout))
            if error:
                raise error
            return stream
        result = ollama.pull("llama3.2", lambda *a: seen.append(a), opener=opener, cancelled=cancelled)
        return result, seen, requests

    def test_a_download_reports_its_progress_and_ends_with_success(self):
        stream = FakeStream({"status": "pulling manifest"}, {"status": "downloading", "total": 2000000000, "completed": 500000000},
                            {"status": "downloading", "total": 2000000000, "completed": 2000000000}, {"status": "success"})
        result, seen, requests = self.run_it(stream)
        self.assertEqual(result, (True, ""))
        self.assertEqual(seen[1], ("downloading", 500000000, 2000000000))
        self.assertEqual(seen[-1], ("success", 0, 0))
        url, data, headers, _timeout = requests[0]
        self.assertEqual(url, "http://localhost:11434/api/pull")
        self.assertEqual(json.loads(data), {"model": "llama3.2", "name": "llama3.2", "stream": True})
        self.assertTrue(stream.closed)

    def test_an_error_of_the_server_ends_it_with_its_words(self):
        result, _seen, _r = self.run_it(FakeStream({"status": "pulling manifest"}, {"error": "pull model manifest: file does not exist"}))
        self.assertEqual(result, (False, "pull model manifest: file does not exist"))

    def test_a_stream_that_stops_before_success_is_not_a_download(self):
        result, _seen, _r = self.run_it(FakeStream({"status": "downloading", "total": 10, "completed": 5}))
        self.assertEqual((result[0], "terminated prematurely" in result[1]), (False, True))

    def test_the_user_can_cancel(self):
        stream = FakeStream({"status": "downloading", "total": 10, "completed": 5}, {"status": "success"})
        result, seen, _r = self.run_it(stream, cancelled=lambda: True)
        self.assertEqual((result, seen), ((False, "download cancelled"), []))
        self.assertTrue(stream.closed)

    def test_a_broken_connection_in_the_middle_is_said(self):
        result, _seen, _r = self.run_it(FakeStream({"status": "downloading", "total": 10, "completed": 5}, then=OSError("connection reset")))
        self.assertEqual((result[0], "connection reset" in result[1]), (False, True))

    def test_the_server_not_running_is_explained(self):
        refused = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        result, _seen, _r = self.run_it(None, error=refused)
        self.assertFalse(result[0])
        self.assertIn("cannot connect to http://localhost:11434/api/pull:", result[1])
        self.assertIn("Ollama)", result[1])

    def test_a_bad_model_name_is_answered_by_the_server_and_said(self):
        err = urllib.error.HTTPError("http://localhost:11434/api/pull", 400, "Bad Request", {}, io.BytesIO(b'{"error": "invalid model name"}'))
        result, _seen, _r = self.run_it(None, error=err)
        self.assertEqual(result, (False, "service returned HTTP error 400: invalid model name"))

    def test_lines_that_are_not_json_are_skipped(self):
        result, seen, _r = self.run_it(FakeStream("not json", {"status": "success"}))
        self.assertEqual((result, len(seen)), ((True, ""), 1))


class TerminalTests(unittest.TestCase):
    def which(self, *present):
        return lambda name: "/usr/bin/" + name if name in present else None

    def test_each_terminal_gets_its_own_way_to_run_a_command(self):
        script = "echo hi"
        gnome = ollama.terminal_argv(script, self.which("gnome-terminal", "xterm"))
        self.assertEqual(gnome[:4], ["/usr/bin/gnome-terminal", "--", "bash", "-c"])
        self.assertTrue(gnome[4].startswith("echo hi; "))
        self.assertEqual(ollama.terminal_argv(script, self.which("mate-terminal"))[:3], ["/usr/bin/mate-terminal", "-x", "bash"])
        xfce = ollama.terminal_argv(script, self.which("xfce4-terminal"))
        self.assertEqual((xfce[0], xfce[1]), ("/usr/bin/xfce4-terminal", "-e"))
        self.assertTrue(xfce[2].startswith("bash -c "))
        for name in ("konsole", "x-terminal-emulator", "xterm"):
            self.assertEqual(ollama.terminal_argv(script, self.which(name))[:4], ["/usr/bin/" + name, "-e", "bash", "-c"])

    def test_the_window_waits_for_a_key_so_that_the_output_can_be_read(self):
        self.assertIn("read -r", ollama.terminal_argv("x", self.which("xterm"))[-1])

    def test_no_terminal_gives_none(self):
        self.assertIsNone(ollama.terminal_argv("x", self.which()))

    def test_the_installer_is_run_in_a_terminal_that_asks_for_the_password_itself(self):
        calls = []
        ok, message = ollama.open_installer_terminal(popen=lambda argv, **kw: calls.append((argv, kw)), which=self.which("gnome-terminal"))
        self.assertEqual((ok, message), (True, ""))
        argv, kw = calls[0]
        self.assertIn(ollama.INSTALL_COMMAND, argv[-1])
        self.assertTrue(kw["start_new_session"])

    def test_when_there_is_no_terminal_the_user_is_told_to_copy_the_command(self):
        ok, message = ollama.open_installer_terminal(popen=lambda *a, **k: None, which=self.which())
        self.assertEqual((ok, "Copy command" in message), (False, True))

    def test_when_the_terminal_cannot_be_opened_the_reason_is_said(self):
        def boom(argv, **kw):
            raise OSError("no display")
        ok, message = ollama.open_installer_terminal(popen=boom, which=self.which("xterm"))
        self.assertEqual((ok, "no display" in message), (False, True))


class FormattingTests(unittest.TestCase):
    def test_percent(self):
        self.assertEqual((ollama.percent(5, 10), ollama.percent(0, 0), ollama.percent(20, 10), ollama.percent(-1, 10)), (50, None, 100, 0))

    def test_sizes(self):
        self.assertEqual((ollama.human_size(2000000000), ollama.human_size(340000000), ollama.human_size(1234567890)), ("2.0 GB", "340 MB", "1.2 GB"))

    def test_the_suggested_models_start_with_the_default(self):
        self.assertEqual(ollama.SUGGESTED[0][0], ollama.DEFAULT_MODEL)
        self.assertTrue(all(note for _name, note in ollama.SUGGESTED))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class LogFileTests(unittest.TestCase):
    def test_the_log_file_of_the_server_is_closed_here_after_it_is_started(self):
        import tempfile
        seen = []
        with tempfile.TemporaryDirectory() as folder:
            def popen(command, **kwargs):
                seen.append(kwargs["stdout"])
            ollama.start_server(popen=popen, listening=lambda host, port: True, sleep=lambda s: None, which=lambda n: "/usr/bin/ollama",
                                log_path=os.path.join(folder, "ollama.log"))
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].closed)                                    # nothing is left open in the window
