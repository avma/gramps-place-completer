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
"""Any AI can answer: a link template, the clipboard, or an API with the user's own key."""
import argparse
import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"      # never the user's own file
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import clipboard, cli, engines, prompts                                 # noqa: E402
from test_ai_mode import JOHNSTON, NO_ANSWER_TEXT, AmbiguityTests, read                     # noqa: E402


class Recorder:
    """A stand-in for the network: remembers the request, answers what it is told to."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, headers, body, timeout=120):
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self.answers.pop(0)


def claude_reply(text, model="claude-sonnet-5-5"):
    return {"model": model, "stop_reason": "end_turn", "content": [
        {"type": "text", "text": "I will search."},
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "Johnston Iowa history"}},
        {"type": "web_search_tool_result", "content": [{"type": "web_search_result", "url": "https://en.wikipedia.org/wiki/Johnston,_Iowa"}]},
        {"type": "text", "text": text}]}


class RegistryTests(unittest.TestCase):
    def test_the_built_in_engines_cover_the_three_kinds(self):
        found = engines.load_engines("/nonexistent.json")
        self.assertEqual({found[k]["kind"] for k in found}, {"browser", "manual", "api"})
        self.assertTrue({"google", "chatgpt", "gemini", "manual", "anthropic", "openai", "ollama"} <= set(found))

    def test_the_users_file_adds_an_engine_and_changes_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "engines.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"engines": {"perplexity": {"kind": "browser", "label": "Perplexity", "url": "https://www.perplexity.ai/search?q={q}"},
                                       "anthropic": {"model": "my-model"}}}, fh)
            found = engines.load_engines(path)
            self.assertEqual(found["perplexity"]["label"], "Perplexity")
            self.assertEqual((found["anthropic"]["model"], found["anthropic"]["api"]), ("my-model", "anthropic"))      # changed, the rest kept
            self.assertEqual(engines.load_engines("/nonexistent.json")["anthropic"]["model"], "claude-sonnet-5-5")

    def test_a_broken_file_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "engines.json")
            with open(path, "w") as fh:
                fh.write("{not json")
            with self.assertRaises(engines.EngineError):
                engines.load_engines(path)

    def test_an_unknown_engine_lists_the_available_ones(self):
        with self.assertRaises(engines.EngineError) as ctx:
            engines.pick("nobody", "/nonexistent.json")
        self.assertIn("anthropic", str(ctx.exception))

    def test_the_template_puts_the_whole_question_into_the_link(self):
        cfg = engines.pick("google", "/nonexistent.json")
        p = prompts.build_prompt("Johnston, Iowa", "1950")
        url = engines.browser_url(cfg, p)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"], [p])
        self.assertIn("udm=50", url)


class ClaudeApiTests(unittest.TestCase):
    def cfg(self):
        return engines.pick("anthropic", "/nonexistent.json")

    def test_the_request_has_the_key_the_version_and_the_web_search_tool(self):
        rec = Recorder(claude_reply("PLACE_NAME_ON_DATE: Johnston"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-SECRET"}):
            got = engines.ask(self.cfg(), "the question", http=rec)
        call = rec.calls[0]
        self.assertEqual(call["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual((call["headers"]["x-api-key"], call["headers"]["anthropic-version"]), ("sk-test-SECRET", "2023-06-01"))
        self.assertEqual(call["body"]["messages"], [{"role": "user", "content": "the question"}])
        self.assertEqual(call["body"]["tools"], [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}])
        self.assertEqual(call["body"]["model"], "claude-sonnet-5-5")
        self.assertEqual(got["text"], "PLACE_NAME_ON_DATE: Johnston")      # the text after the last tool block, not the "I will search" line
        self.assertEqual(got["model"], "claude-sonnet-5-5")

    def test_the_strict_system_message_goes_with_the_question(self):
        rec = Recorder(claude_reply("x"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            engines.ask(self.cfg(), "the question", http=rec)
        system = rec.calls[0]["body"]["system"]
        self.assertIn("NOTES:", system)
        self.assertIn("UNKNOWN only as the whole value of a field", system)
        self.assertEqual(rec.calls[0]["body"]["messages"], [{"role": "user", "content": "the question"}])      # the question itself is unchanged

    def test_the_model_that_answered_is_the_one_the_service_reports(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            got = engines.ask(self.cfg(), "q", http=Recorder(claude_reply("x", model="claude-sonnet-5-5-20261001")))
        self.assertEqual(got["model"], "claude-sonnet-5-5-20261001")

    def test_when_the_model_writes_nothing_after_its_tools_the_earlier_text_is_used(self):
        reply = {"model": "m", "content": [{"type": "text", "text": "the whole answer"}, {"type": "server_tool_use", "name": "web_search"}]}
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            self.assertEqual(engines.ask(self.cfg(), "q", http=Recorder(reply))["text"], "the whole answer")

    def test_web_search_can_be_turned_off(self):
        cfg = {**self.cfg(), "web_search": False}
        rec = Recorder(claude_reply("x"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            engines.ask(cfg, "q", http=rec)
        self.assertNotIn("tools", rec.calls[0]["body"])

    def test_a_missing_key_says_which_variable_to_set_and_asks_nothing(self):
        rec = Recorder(claude_reply("x"))
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(self.cfg(), "q", http=rec)
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
        self.assertEqual(rec.calls, [])

    def test_an_answer_without_text_is_an_error(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            with self.assertRaises(engines.EngineError):
                engines.ask(self.cfg(), "q", http=Recorder({"content": [{"type": "server_tool_use"}], "stop_reason": "max_tokens"}))


class OpenAiCompatibleTests(unittest.TestCase):
    def test_the_endpoint_and_the_bearer_key(self):
        cfg = {**engines.pick("openai", "/nonexistent.json"), "model": "some-model"}
        rec = Recorder({"model": "some-model-2026", "choices": [{"message": {"content": " the answer "}}]})
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-SECRET"}):
            got = engines.ask(cfg, "q", http=rec)
        self.assertEqual(rec.calls[0]["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(rec.calls[0]["headers"]["authorization"], "Bearer sk-test-SECRET")
        self.assertEqual(rec.calls[0]["body"]["temperature"], 0)
        self.assertEqual([m["role"] for m in rec.calls[0]["body"]["messages"]], ["system", "user"])
        self.assertEqual(got, {"text": "the answer", "model": "some-model-2026"})

    def test_a_local_model_needs_no_key(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")}):
            rec = Recorder({"choices": [{"message": {"content": "local answer"}}]})
            listing = {"data": [{"id": "llama3.1:latest", "created": 5}]}
            got = engines.ask(engines.pick("ollama", "/nonexistent.json"), "q", http=rec, http_get=lambda url, headers, timeout=20: listing)
        self.assertEqual(rec.calls[0]["url"], "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("authorization", rec.calls[0]["headers"])
        self.assertEqual(got["model"], "llama3.1:latest")                # the answer did not report one: the model that was found

    def test_an_endpoint_whose_models_cannot_be_listed_says_so(self):
        """No model is written, so the service is asked which it has; when that fails the reason is said (the question itself is never sent)."""
        def refused(url, headers, timeout=20):
            raise engines.EngineError("cannot reach %s: refused" % url)
        post = Recorder()
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k", "PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")}):
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(engines.pick("openai", "/nonexistent.json"), "q", http=post, http_get=refused)
        self.assertIn("https://api.openai.com/v1/models", str(ctx.exception))
        self.assertEqual(post.calls, [])

    def test_an_unexpected_shape_is_an_error(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")}):
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(engines.pick("ollama", "/nonexistent.json"), "q", http=Recorder({"oops": 1}),
                            http_get=lambda url, headers, timeout=20: {"data": [{"id": "llama3.1", "created": 1}]})
        self.assertIn("response structure is invalid", str(ctx.exception))


class KeyReportTests(unittest.TestCase):
    CFG = engines.BUILTIN["anthropic"]

    def report(self, value):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": value}):
            return engines.key_report(self.CFG)

    def test_a_good_key_has_no_problems_and_the_report_has_its_length_only(self):
        rep = self.report("sk-ant-api03-" + "A" * 80)
        self.assertEqual((rep["set"], rep["length"], rep["problems"]), (True, 93, []))
        self.assertNotIn("sk-ant", json.dumps(rep))

    def test_what_pasting_breaks_is_named(self):
        self.assertTrue(any("leading/trailing whitespace" in p for p in self.report("sk-ant-x\n")["problems"]))
        self.assertTrue(any("enclosed in quotation marks" in p for p in self.report('"sk-ant-x"')["problems"]))
        self.assertTrue(any("internal spaces or line breaks" in p for p in self.report("sk-ant-xx yy")["problems"]))
        self.assertTrue(any("non-ASCII characters" in p for p in self.report("sk-ant-x\u200fy")["problems"]))
        self.assertTrue(any("must begin with 'sk-ant-'" in p for p in self.report("key-1234")["problems"]))

    def test_the_program_removes_the_newline_spaces_and_quotes_before_sending(self):
        rec = Recorder(claude_reply("x"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": '  "sk-ant-api03-ABC"\r\n'}):
            engines.ask(engines.pick("anthropic", "/nonexistent.json"), "q", http=rec)
        self.assertEqual(rec.calls[0]["headers"]["x-api-key"], "sk-ant-api03-ABC")

    def test_a_key_the_service_refuses_gets_a_hint_that_does_not_contain_the_key(self):
        def refuse(url, headers, body, timeout=120):
            raise engines.EngineError("the service answered HTTP 401: invalid x-api-key")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-SECRETSECRET"}):
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(engines.pick("anthropic", "/nonexistent.json"), "q", http=refuse)
        self.assertIn("rejected API key authentication", str(ctx.exception))
        self.assertIn("Verify key active status", str(ctx.exception))
        self.assertNotIn("SECRETSECRET", str(ctx.exception))

    def test_the_engines_command_reports_the_state_of_the_key_without_showing_it(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "wrong-key-SECRETSECRET"}):
            with contextlib.redirect_stdout(buf):
                cli.main(["engines"])
        out = buf.getvalue()
        self.assertIn("key format (must begin with 'sk-ant-')", out)
        self.assertIn("22 characters", out)
        self.assertNotIn("SECRETSECRET", out)


class KeyFileTests(unittest.TestCase):
    """Gramps started from a menu does not see the variables of a terminal: the key may be in a file only its owner can read."""
    def cfg(self, path, env="ANTHROPIC_API_KEY"):
        return {**engines.BUILTIN["anthropic"], "id": "anthropic", "key_env": env, "key_file": path}

    def keyfile(self, text, mode=0o600):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "claude.key")
        with open(path, "w") as fh:
            fh.write(text)
        os.chmod(path, mode)
        return path

    def clean_env(self):
        return mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}, clear=True)

    def test_the_key_is_read_from_the_file_when_the_variable_is_not_set(self):
        rec = Recorder(claude_reply("x"))
        with self.clean_env():
            engines.ask(self.cfg(self.keyfile("sk-ant-api03-FROMFILE\n")), "q", http=rec)
        self.assertEqual(rec.calls[0]["headers"]["x-api-key"], "sk-ant-api03-FROMFILE")

    def test_the_variable_wins_over_the_file(self):
        rec = Recorder(claude_reply("x"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-FROMENV"}):
            engines.ask(self.cfg(self.keyfile("sk-ant-api03-FROMFILE")), "q", http=rec)
        self.assertEqual(rec.calls[0]["headers"]["x-api-key"], "sk-ant-api03-FROMENV")

    def test_a_file_that_others_can_read_is_refused_with_the_command_to_fix_it(self):
        with self.clean_env():
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(self.cfg(self.keyfile("sk-ant-api03-x", mode=0o644)), "q", http=Recorder())
        self.assertIn("chmod 600", str(ctx.exception))
        self.assertNotIn("sk-ant-api03-x", str(ctx.exception))

    def test_without_variable_or_file_both_ways_are_explained(self):
        with self.clean_env():
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask(self.cfg("/nonexistent/none.key"), "q", http=Recorder())
        msg = str(ctx.exception)
        self.assertIn("ANTHROPIC_API_KEY", msg)
        self.assertIn("starting Gramps from the matching terminal", msg)
        self.assertIn("key_file", msg)

    def test_the_report_and_the_status_know_about_the_file_and_never_show_the_key(self):
        cfg = self.cfg(self.keyfile("sk-ant-api03-" + "B" * 40))
        with self.clean_env():
            rep = engines.key_report(cfg)
            status = engines.key_status(cfg)
        self.assertEqual((rep["set"], rep["length"], rep["problems"]), (True, 53, []))
        self.assertIn("key in file", status)
        self.assertIn("53 characters", status)
        self.assertNotIn("BBBB", status)

    def test_readiness_names_what_is_missing(self):
        with self.clean_env():
            ready, problems, fix = engines.readiness({**engines.BUILTIN["anthropic"], "id": "anthropic"})
            self.assertEqual((ready, problems), (False, ["no key"]))
            self.assertIn("ANTHROPIC_API_KEY", fix)
            self.assertTrue(engines.readiness(self.cfg(self.keyfile("sk-ant-api03-x")))[0])
            self.assertEqual(engines.readiness(self.cfg(self.keyfile("x", mode=0o666)))[1], ["key file permissions are insecure (readable by others)"])
        self.assertTrue(engines.readiness({**engines.BUILTIN["google"], "id": "google"})[0])
        with mock.patch.object(engines, "_listening", lambda host, port, timeout=0.5: True):
            self.assertTrue(engines.readiness({**engines.BUILTIN["ollama"], "id": "ollama"})[0])    # a local model needs no key
        ready, problems, fix = engines.readiness({**engines.BUILTIN["openai"], "id": "openai", "key_env": ""})
        self.assertEqual((ready, problems), (True, []))                          # no model written is no reason to refuse: it is found by itself


class LocalServerAndGeminiTests(unittest.TestCase):
    """Ollama is a program on this computer: when nobody started it the engine is not ready (it was shown as ready and failed with
    'Connection refused'); and Gemini ignores a question put in its address, so the question is copied instead."""
    OLLAMA = {**engines.BUILTIN["ollama"], "id": "ollama"}

    def test_a_local_server_that_nobody_started_is_not_ready_and_says_what_to_do(self):
        with mock.patch.object(engines, "_listening", lambda host, port, timeout=0.5: False):
            ready, problems, fix = engines.readiness(self.OLLAMA)
        self.assertEqual((ready, problems), (False, ["no response from host localhost:11434"]))
        self.assertIn("ollama.com", fix)

    def test_a_local_server_that_answers_is_ready(self):
        with mock.patch.object(engines, "_listening", lambda host, port, timeout=0.5: True):
            self.assertEqual(engines.readiness(self.OLLAMA)[:2], (True, []))

    def test_a_server_somewhere_else_is_not_probed(self):
        def never(*a, **k):
            raise AssertionError("a remote server must not be probed")
        with mock.patch.object(engines, "_listening", never), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}):
            self.assertTrue(engines.readiness({**engines.BUILTIN["openai"], "id": "openai"})[0])

    def test_the_probe_sees_a_listening_port_and_a_closed_one(self):
        import socket
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        self.assertTrue(engines._listening("127.0.0.1", port))
        server.close()
        self.assertFalse(engines._listening("127.0.0.1", port))

    def test_a_refused_connection_to_this_computer_is_explained(self):
        import socket
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()                                                                   # nothing listens here now
        with self.assertRaises(engines.EngineError) as ctx:
            engines.post_json("http://localhost:%d/v1/chat/completions" % port, {}, {}, timeout=2)
        self.assertIn("cannot connect to http://localhost:%d/v1/chat/completions" % port, str(ctx.exception))
        self.assertIn("Destination unreachable", str(ctx.exception))
        self.assertIn("e.g. Ollama", str(ctx.exception))

    def local(self, listing, **extra):
        """Ask Ollama with this list of installed models; the choice is kept in a temporary file."""
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")}):
            post = Recorder({"model": "", "choices": [{"message": {"content": "A"}}]})
            got = engines.ask({**self.OLLAMA, **extra}, "q", http=post, http_get=lambda url, headers, timeout=20: listing)
        return got, post

    def test_ollama_uses_the_newest_model_that_is_installed_and_not_one_for_embeddings(self):
        listing = {"data": [{"id": "nomic-embed-text:latest", "created": 900}, {"id": "llama3.1:latest", "created": 100},
                            {"id": "qwen2.5:7b", "created": 300}]}
        got, post = self.local(listing)
        self.assertEqual(post.calls[0]["body"]["model"], "qwen2.5:7b")
        self.assertEqual(post.calls[0]["url"], "http://localhost:11434/v1/chat/completions")

    def test_ollama_with_no_model_says_what_to_run(self):
        with self.assertRaises(engines.EngineError) as ctx:
            self.local({"data": []})
        self.assertIn("ollama pull llama3.2", str(ctx.exception))
        self.assertIsInstance(ctx.exception, engines.NeedsSetup)                                    # the window offers to download one
        self.assertIn("no models installed", str(ctx.exception))
        with self.assertRaises(engines.EngineError) as ctx:
            self.local({"data": [{"id": "nomic-embed-text", "created": 1}]})                       # only an embedding model: nothing to ask
        self.assertIn("nomic-embed-text", str(ctx.exception))

    def test_a_model_written_in_engines_json_is_used_and_if_it_is_not_installed_the_way_to_get_it_is_said(self):
        got, post = self.local({"data": [{"id": "other", "created": 1}]}, model="mine:7b")
        self.assertEqual(post.calls[0]["body"]["model"], "mine:7b")

        def missing(url, headers, body, timeout=120):
            raise engines.EngineError("the service answered HTTP 404: model 'mine:7b' not found, try pulling it first")
        with self.assertRaises(engines.EngineError) as ctx:
            engines.ask({**self.OLLAMA, "model": "mine:7b"}, "q", http=missing)
        self.assertIn("Target model missing: download using 'ollama pull mine:7b'", str(ctx.exception))

    def test_the_message_for_ollama_that_is_not_running_gives_the_steps_and_no_file_to_edit(self):
        with mock.patch.object(engines, "_listening", lambda host, port, timeout=0.5: False):
            ready, problems, fix = engines.readiness(self.OLLAMA)
        self.assertFalse(ready)
        for step in ("Click Ask to run guided setup", "1) Install from ollama.com", "ollama serve", "ollama pull llama3.2"):
            self.assertIn(step, fix)
        self.assertNotIn("base_url", fix)
        self.assertNotIn("engines.json", fix)

    def test_another_local_server_still_says_where_its_address_is(self):
        other = {**engines.BUILTIN["openai"], "id": "lmstudio", "base_url": "http://localhost:1234/v1", "key_env": ""}
        with mock.patch.object(engines, "_listening", lambda host, port, timeout=0.5: False):
            ready, problems, fix = engines.readiness(other)
        self.assertEqual(problems, ["no response from host localhost:1234"])
        self.assertIn("base_url", fix)

    def test_gemini_is_opened_without_a_question_in_its_address_and_asks_for_the_copy(self):
        gemini = {**engines.BUILTIN["gemini"], "id": "gemini"}
        self.assertTrue(gemini["copy"])
        self.assertEqual(engines.browser_url(gemini, "a question & more"), "https://gemini.google.com/app")      # nothing to ignore in the address
        self.assertNotIn("copy", engines.BUILTIN["google"])
        self.assertNotIn("copy", engines.BUILTIN["chatgpt"])


class ModelChoiceTests(unittest.TestCase):
    """An OpenAI-compatible engine needs no model written by hand: the service is asked which models it has, one is chosen and kept."""
    OPENAI = {"data": [{"id": "gpt-4.1", "created": 100}, {"id": "gpt-5", "created": 300}, {"id": "gpt-5-mini", "created": 400},
                       {"id": "gpt-5-2025-08-07", "created": 310}, {"id": "gpt-5-pro", "created": 500}, {"id": "gpt-4o-audio-preview", "created": 600},
                       {"id": "gpt-4o-realtime-preview", "created": 610}, {"id": "gpt-image-1", "created": 620}, {"id": "o3", "created": 700},
                       {"id": "text-embedding-3-large", "created": 50}, {"id": "whisper-1", "created": 10}, {"id": "dall-e-3", "created": 20},
                       {"id": "gpt-5-search-api", "created": 630}, {"id": "gpt-5-codex", "created": 640}]}

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(self.dir, "models.json"), "OPENAI_API_KEY": "sk-test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = {**engines.BUILTIN["openai"], "id": "openai"}

    @staticmethod
    def getter(answer):
        calls = []

        def get(url, headers, timeout=20):
            calls.append((url, dict(headers)))
            if isinstance(answer, Exception):
                raise answer
            return answer
        return get, calls

    def test_the_newest_plain_text_model_is_chosen_for_openai(self):
        self.assertEqual(engines.choose_model(self.OPENAI, "api.openai.com"), "gpt-5")         # not a mini, a snapshot, audio, search, codex, pro

    def test_a_snapshot_is_chosen_only_when_there_is_nothing_plainer(self):
        only = {"data": [{"id": "gpt-5-2025-08-07", "created": 310}, {"id": "gpt-5-mini-2025-08-07", "created": 320}]}
        self.assertEqual(engines.choose_model(only, "api.openai.com"), "gpt-5-2025-08-07")
        small = {"data": [{"id": "gpt-5-mini", "created": 400}, {"id": "gpt-5-nano", "created": 410}, {"id": "whisper-1", "created": 1}]}
        self.assertEqual(engines.choose_model(small, "api.openai.com"), "gpt-5-nano")

    def test_nothing_suitable_chooses_nothing(self):
        self.assertEqual(engines.choose_model({"data": [{"id": "whisper-1"}, {"id": "dall-e-3"}]}, "api.openai.com"), "")
        self.assertEqual(engines.choose_model({"data": []}, "api.openai.com"), "")
        self.assertEqual(engines.choose_model("not a listing", "api.openai.com"), "")

    def test_another_service_with_one_model_uses_it_and_with_several_asks_the_user(self):
        self.assertEqual(engines.choose_model({"data": [{"id": "my-model"}]}, "llm.example.org"), "my-model")
        self.assertEqual(engines.choose_model({"data": [{"id": "a"}, {"id": "b"}]}, "llm.example.org"), "")

    def test_the_model_is_found_asked_once_and_kept(self):
        get, calls = self.getter(self.OPENAI)
        post = Recorder({"model": "gpt-5-2025-08-07", "choices": [{"message": {"content": "A"}}]},
                        {"model": "gpt-5-2025-08-07", "choices": [{"message": {"content": "B"}}]})
        first = engines.ask(self.cfg, "q", http=post, http_get=get)
        self.assertEqual(first["text"], "A")
        self.assertEqual(post.calls[0]["body"]["model"], "gpt-5")
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/models")
        self.assertEqual(calls[0][1], {"authorization": "Bearer sk-test-key"})
        self.assertEqual(engines.remembered_model("openai"), "gpt-5")
        engines.ask(self.cfg, "q", http=post, http_get=get)
        self.assertEqual(len(calls), 1)                                                     # the second time nobody asks the service

    def test_a_model_written_in_engines_json_is_never_replaced(self):
        get, calls = self.getter(self.OPENAI)
        post = Recorder({"model": "mine", "choices": [{"message": {"content": "A"}}]})
        engines.ask({**self.cfg, "model": "mine"}, "q", http=post, http_get=get)
        self.assertEqual((post.calls[0]["body"]["model"], calls, engines.remembered_model("openai")), ("mine", [], ""))

    def test_when_no_model_can_be_chosen_it_is_said_what_the_service_has_and_how_to_name_one(self):
        get, _ = self.getter({"data": [{"id": "alpha"}, {"id": "beta"}]})
        with self.assertRaises(engines.EngineError) as ctx:
            engines.ask({**self.cfg, "base_url": "https://llm.example.org/v1"}, "q", http=Recorder(), http_get=get)
        self.assertIn("alpha, beta", str(ctx.exception))
        self.assertIn('{"engines": {"openai": {"model": "model-name"}}}', str(ctx.exception))
        self.assertEqual(engines.remembered_model("openai"), "")

    def test_a_service_that_cannot_list_its_models_is_explained(self):
        get, _ = self.getter(engines.EngineError("the service answered HTTP 401: bad key"))
        with self.assertRaises(engines.EngineError) as ctx:
            engines.ask(self.cfg, "q", http=Recorder(), http_get=get)
        self.assertIn("HTTP 401", str(ctx.exception))

    def test_a_model_the_service_dropped_is_forgotten_so_the_next_try_chooses_again(self):
        engines.remember_model("openai", "gone-model")
        post = Recorder(engines.EngineError("the service answered HTTP 404: The model `gone-model` does not exist"))

        def failing(url, headers, body, timeout=120):
            raise engines.EngineError("the service answered HTTP 404: The model `gone-model` does not exist")
        with self.assertRaises(engines.EngineError) as ctx:
            engines.ask(self.cfg, "q", http=failing, http_get=self.getter(self.OPENAI)[0])
        self.assertIn("host (the service", str(ctx.exception))
        self.assertEqual(engines.remembered_model("openai"), "")

    def test_a_model_that_refuses_a_temperature_is_asked_again_without_one(self):
        calls = []

        def post(url, headers, body, timeout=120):
            calls.append(dict(body))
            if "temperature" in body:
                raise engines.EngineError("the service answered HTTP 400: Unsupported value: 'temperature' does not support 0 with this model")
            return {"model": "gpt-5", "choices": [{"message": {"content": "answer"}}]}
        got = engines.ask({**self.cfg, "model": "gpt-5"}, "q", http=post)
        self.assertEqual(got["text"], "answer")
        self.assertEqual(["temperature" in c for c in calls], [True, False])

    def test_the_choice_is_kept_in_a_file_without_any_key(self):
        engines.remember_model("openai", "gpt-5")
        with open(os.environ["PLACECOMPLETER_MODELS"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("gpt-5", text)
        self.assertNotIn("sk-test-key", text)
        engines.remember_model("openai", "")
        self.assertEqual(engines.remembered_model("openai"), "")


class RealHttpTests(unittest.TestCase):
    """post_json against a small server on this computer: success and the error that carries no key."""
    def serve(self, status, body):
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path
                seen["auth"] = self.headers.get("x-api-key")
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:%d/v1/messages" % server.server_port, seen

    def test_a_json_answer_is_returned(self):
        url, seen = self.serve(200, {"ok": True})
        self.assertEqual(engines.post_json(url, {"x-api-key": "k1"}, {"a": 1}), {"ok": True})
        self.assertEqual((seen["auth"], seen["body"]), ("k1", {"a": 1}))

    def test_an_http_error_is_explained_without_the_key(self):
        url, _ = self.serve(401, {"error": "invalid x-api-key"})
        with self.assertRaises(engines.EngineError) as ctx:
            engines.post_json(url, {"x-api-key": "sk-test-SECRET"}, {})
        self.assertIn("HTTP error 401:", str(ctx.exception))
        self.assertNotIn("sk-test-SECRET", str(ctx.exception))

    def test_a_server_that_is_not_there_is_explained(self):
        with self.assertRaises(engines.EngineError) as ctx:
            engines.post_json("http://127.0.0.1:9/none", {}, {}, timeout=2)
        self.assertIn("cannot connect", str(ctx.exception))


class FlowTests(unittest.TestCase):
    def go(self, engine, replies, env=None, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            args = AmbiguityTests().args(tmp, hint="Iowa", engine=engine, **kw)
            rec = Recorder(*replies)
            buf = io.StringIO()

            def never(*a):
                raise AssertionError("an API engine must not open a browser or wait for the clipboard")
            # the environment is exactly what the test says: a real key on the computer must not leak in
            clean = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
            clean.update(env if env is not None else {"ANTHROPIC_API_KEY": "sk-test-SECRET"})
            with mock.patch.dict(os.environ, clean, clear=True):
                with contextlib.redirect_stdout(buf):
                    code = cli.ai_complete(args, opener=never, wait=never, read=never, choose=lambda n: 1, http=rec)
            metas = [json.load(open(os.path.join(args.save_dir, f), encoding="utf-8")) for f in sorted(os.listdir(args.save_dir)) if f.endswith(".meta.json")] \
                if os.path.isdir(args.save_dir) else []
            return code, buf.getvalue(), rec, metas

    def test_an_api_engine_answers_without_a_browser_and_the_model_is_written_down(self):
        code, out, rec, metas = self.go("anthropic", [claude_reply(read(JOHNSTON), model="claude-sonnet-5-5-20261001")])
        self.assertEqual(code, 0)
        self.assertEqual(len(rec.calls), 1)
        self.assertIn("PLACE 'Johnston' on 1996", out)
        self.assertEqual(metas[0]["engine"], "anthropic")
        self.assertEqual(metas[0]["model"], "claude-sonnet-5-5-20261001")
        self.assertEqual((metas[0]["form"], metas[0]["kind"]), ("classic", "api"))
        self.assertEqual(len(metas[0]["prompt_sha256"]), 64)
        self.assertNotIn("sk-test-SECRET", out + json.dumps(metas))

    def test_a_no_answer_from_an_api_moves_to_the_next_form_too(self):
        code, out, rec, metas = self.go("anthropic", [claude_reply(NO_ANSWER_TEXT), claude_reply(read(JOHNSTON))], form="auto")
        self.assertEqual((code, len(rec.calls)), (0, 2))
        self.assertEqual(metas[0]["form"], prompts.AUTO_ORDER[1])

    def test_a_failing_engine_ends_with_its_message_and_not_a_traceback(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        code, out, rec, _ = self.go("anthropic", [], env=env)
        self.assertEqual(code, 2)
        self.assertIn("ANTHROPIC_API_KEY", out)

    def test_an_unknown_engine_says_what_exists(self):
        code, out, _, _ = self.go("nobody", [])
        self.assertEqual(code, 2)
        self.assertIn("no engine called 'nobody'", out)

    def test_a_browser_engine_keeps_the_provenance_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = AmbiguityTests().args(tmp, hint="Iowa", engine="google")
            queue = iter([read(JOHNSTON)])
            opened = []
            with contextlib.redirect_stdout(io.StringIO()):
                cli.ai_complete(args, opener=lambda u: opened.append(u) or True, wait=lambda: None, read=lambda: next(queue), choose=lambda n: 1)
            meta = json.load(open(os.path.join(args.save_dir, "Johnston_1996.meta.json"), encoding="utf-8"))
        self.assertEqual((meta["engine"], meta["kind"]), ("google", "browser"))
        self.assertEqual(meta["model"], "not disclosed by the service")
        self.assertTrue(meta["url"].startswith("https://www.google.com/search?udm=50"))

    def test_the_manual_engine_copies_the_question_and_reads_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = AmbiguityTests().args(tmp, hint="Iowa", engine="manual")
            queue, copied = iter([read(JOHNSTON)]), []
            with mock.patch.object(clipboard, "write_clipboard", lambda t: copied.append(t) or True):
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    code = cli.ai_complete(args, wait=lambda: None, read=lambda: next(queue), choose=lambda n: 1)
            self.assertEqual(code, 0)
            self.assertIn("Place: Johnston, Iowa. Date: 1996.", copied[0])
            meta = json.load(open(os.path.join(args.save_dir, "Johnston_1996.meta.json"), encoding="utf-8"))
        self.assertEqual(meta["model"], "unknown (pasted by the user)")


class CommandTests(unittest.TestCase):
    def test_the_list_shows_every_engine_and_never_a_key(self):
        buf = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        env["ANTHROPIC_API_KEY"] = "sk-test-SECRET"
        with mock.patch.dict(os.environ, env, clear=True):
            with contextlib.redirect_stdout(buf):
                code = cli.main(["engines"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("key in $ANTHROPIC_API_KEY: configured, 14 characters;", out)
        self.assertIn("key in $OPENAI_API_KEY: MISSING", out)
        self.assertNotIn("sk-test-SECRET", out)
        for name in ("google", "chatgpt", "manual", "anthropic", "ollama"):
            self.assertIn(name, out)

    def test_search_ai_explains_that_an_api_engine_answers_by_itself(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.search_ai(argparse.Namespace(place="X", date="1900", short=False, form="classic", hint="", engine="anthropic",
                                                    show=False, no_open=True))
        self.assertEqual(code, 2)
        self.assertIn("use ai-complete", buf.getvalue())

    def test_search_ai_with_the_manual_engine_copies_the_question(self):
        with mock.patch.object(clipboard, "write_clipboard", lambda t: True):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code = cli.search_ai(argparse.Namespace(place="X", date="1900", short=False, form="classic", hint="", engine="manual",
                                                        show=False, no_open=True))
        self.assertEqual(code, 0)
        self.assertIn("copied to the clipboard", buf.getvalue())


class ProvenanceTests(unittest.TestCase):
    def test_what_is_kept_is_enough_to_ask_again_and_to_compare(self):
        cfg = engines.pick("google", "/nonexistent.json")
        meta = engines.provenance(cfg, "classic", "Johnston, Iowa", "1950", "the question", when="2026-10-13T12:00:00+03:00")
        self.assertEqual((meta["engine"], meta["form"], meta["asked_at"]), ("google", "classic", "2026-10-13T12:00:00+03:00"))
        self.assertEqual(meta["prompt_sha256"], __import__("hashlib").sha256(b"the question").hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class OnlyHttpTests(unittest.TestCase):
    """The address of a service comes from the settings of the user: a file or another kind of address is not opened."""

    def test_an_address_that_is_not_http_or_https_is_refused_before_anything_is_opened(self):
        for url in ("file:///etc/passwd", "ftp://example.org/x", "gopher://x", "/etc/passwd", ""):
            for call in (lambda u: engines.post_json(u, {}, {}), lambda u: engines.get_json(u, {})):
                with mock.patch("urllib.request.urlopen") as opened:
                    with self.assertRaises(engines.EngineError) as caught:
                        call(url)
                    opened.assert_not_called()
                self.assertIn("only http and https", str(caught.exception))

    def test_http_and_https_are_allowed(self):
        engines.require_http("http://localhost:11434/v1")
        engines.require_http("https://api.openai.com/v1")


class WorkDirTests(unittest.TestCase):
    """One place decides where the work of the user is kept, and the window, Ollama and the command line all ask it."""

    def test_the_default_is_the_folder_in_the_home_and_the_variable_changes_it(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_WORK": ""}):
            self.assertEqual(engines.work_dir(), os.path.join(os.path.expanduser("~"), "gramps-place-work"))
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_WORK": "~/elsewhere"}):
            self.assertEqual(engines.work_dir(), os.path.join(os.path.expanduser("~"), "elsewhere"))

    def test_the_log_of_ollama_is_kept_in_it(self):
        from placecompleter import ollama
        seen = []
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"PLACECOMPLETER_WORK": folder}):
            ollama.start_server(popen=lambda command, **kw: seen.append(kw["stdout"].name), listening=lambda h, p: True, sleep=lambda s: None,
                                which=lambda n: "/usr/bin/ollama")
        self.assertEqual(seen, [os.path.join(folder, "ollama-serve.log")])

    def test_the_window_and_the_command_line_use_the_same_folder_as_the_engine(self):
        from placecompleter import cli
        self.assertEqual(cli.WORK, engines.work_dir())
        import importlib.util
        spec = importlib.util.spec_from_file_location("pc_tool_for_work", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "placecompleter_tool.py"))
        source = open(spec.origin, encoding="utf-8").read()
        self.assertIn("WORK = engines.work_dir()", source)                                  # (the window is run in Gramps: it is read here, not imported)

    def test_deploy_cleans_into_a_folder_under_it(self):
        import deploy_addon
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_WORK": "~/elsewhere"}):
            import importlib
            importlib.reload(deploy_addon)
            self.assertEqual(deploy_addon.BACKUP_ROOT, os.path.join(os.path.expanduser("~"), "elsewhere", "backups"))
        importlib.reload(deploy_addon)
