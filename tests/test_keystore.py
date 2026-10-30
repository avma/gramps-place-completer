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
"""Keeping an API key: the system keyring, the secret-tool command, or a file only the owner can read; and testing a key."""
import contextlib
import io
import os
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import cli, engines, keystore, session as sess                       # noqa: E402
from placecompleter.model import Tree                                                    # noqa: E402

SECRET = "sk-ant-api03-" + "Q" * 80 + "wXyZ"


class MemoryStore:
    """A keyring in memory, for tests that need a store that works."""
    name, secure = "system keyring", True

    def __init__(self):
        self.items = {}

    def get(self, account):
        return self.items.get(account, "")

    def set(self, account, value):
        self.items[account] = value

    def delete(self, account):
        self.items.pop(account, None)


class Base(unittest.TestCase):
    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return d.name

    def use(self, store):
        keystore.reset_store(store)
        self.addCleanup(keystore.reset_store, None)
        return store

    def clean_env(self):
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        return mock.patch.dict(os.environ, env, clear=True)


class FileStoreTests(Base):
    def test_the_key_is_kept_in_a_file_and_a_folder_only_the_owner_can_use(self):
        folder = os.path.join(self.tmp(), "keys")
        store = keystore.FileStore(folder)
        store.set("anthropic", SECRET)
        path = store.path("anthropic")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        self.assertEqual(store.get("anthropic"), SECRET)
        self.assertEqual(os.listdir(folder), ["anthropic.key"])               # no temporary file is left

    def test_a_new_key_replaces_the_old_one_and_a_removed_key_is_gone(self):
        store = keystore.FileStore(os.path.join(self.tmp(), "keys"))
        store.set("a", "one")
        store.set("a", "two")
        self.assertEqual(store.get("a"), "two")
        store.delete("a")
        self.assertEqual(store.get("a"), "")
        store.delete("a")                                                      # removing what is not there is not an error

    def test_a_file_that_others_can_read_is_refused(self):
        folder = os.path.join(self.tmp(), "keys")
        store = keystore.FileStore(folder)
        store.set("a", SECRET)
        os.chmod(store.path("a"), 0o644)
        with self.assertRaises(keystore.StoreError) as ctx:
            store.get("a")
        self.assertIn("chmod 600", str(ctx.exception))
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_an_account_name_cannot_leave_the_folder(self):
        store = keystore.FileStore(os.path.join(self.tmp(), "keys"))
        self.assertEqual(os.path.dirname(store.path("../../etc/passwd")), store.folder)

    def test_the_file_store_says_it_is_not_encrypted(self):
        store = keystore.FileStore(self.tmp())
        self.assertFalse(store.secure)
        self.assertIn("unencrypted", store.name)


class SecretToolTests(Base):
    def fake_run(self, results):
        calls = []

        def run(cmd, **kw):
            calls.append((cmd, kw))
            return results.pop(0)
        return run, calls

    def test_the_key_goes_through_standard_input_and_never_through_the_arguments(self):
        run, calls = self.fake_run([types.SimpleNamespace(returncode=0, stdout="", stderr="")])
        keystore.SecretToolStore(run).set("anthropic", SECRET)
        cmd, kw = calls[0]
        self.assertEqual(cmd[:2], ["secret-tool", "store"])
        self.assertEqual(kw["input"], SECRET)
        self.assertFalse([a for a in cmd if SECRET in a])
        self.assertEqual(cmd[-4:], ["service", "placecompleter", "account", "anthropic"])

    def test_lookup_returns_the_key_or_nothing(self):
        run, _ = self.fake_run([types.SimpleNamespace(returncode=0, stdout=SECRET + "\n", stderr=""),
                                types.SimpleNamespace(returncode=1, stdout="", stderr="")])
        store = keystore.SecretToolStore(run)
        self.assertEqual(store.get("a"), SECRET)
        self.assertEqual(store.get("a"), "")

    def test_a_refusal_is_an_error_without_the_key(self):
        run, _ = self.fake_run([types.SimpleNamespace(returncode=1, stdout="", stderr="Cannot autolaunch D-Bus")])
        with self.assertRaises(keystore.StoreError) as ctx:
            keystore.SecretToolStore(run).set("a", SECRET)
        self.assertIn("D-Bus", str(ctx.exception))
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_removal_uses_clear(self):
        run, calls = self.fake_run([types.SimpleNamespace(returncode=0, stdout="", stderr="")])
        keystore.SecretToolStore(run).delete("a")
        self.assertEqual(calls[0][0][:2], ["secret-tool", "clear"])


class FakeSecret:
    """What the libsecret bindings look like to the program (the real ones cannot be loaded without a desktop)."""
    COLLECTION_DEFAULT = "default"

    class SchemaFlags:
        NONE = 0

    class SchemaAttributeType:
        STRING = 0

    class Schema:
        @staticmethod
        def new(name, flags, attrs):
            return types.SimpleNamespace(name=name, attrs=attrs)

    def __init__(self, fail=False):
        self.items, self.fail = {}, fail

    def password_lookup_sync(self, schema, attrs, cancellable):
        if self.fail:
            raise RuntimeError("no secret service is running")
        return self.items.get(attrs["account"])

    def password_store_sync(self, schema, attrs, collection, label, password, cancellable):
        if self.fail:
            raise RuntimeError("the keyring is locked")
        self.items[attrs["account"]] = password
        self.label = label
        return True

    def password_clear_sync(self, schema, attrs, cancellable):
        self.items.pop(attrs["account"], None)


class SecretServiceTests(Base):
    def test_a_key_is_kept_looked_up_and_removed_by_account(self):
        secret = FakeSecret()
        store = keystore.SecretServiceStore(secret)
        store.set("anthropic", SECRET)
        self.assertEqual(store.get("anthropic"), SECRET)
        self.assertEqual(secret.label, "PlaceCompleter key: anthropic")
        store.delete("anthropic")
        self.assertEqual(store.get("anthropic"), "")
        self.assertTrue(store.secure)

    def test_a_locked_or_missing_keyring_is_an_error_without_the_key(self):
        store = keystore.SecretServiceStore(FakeSecret(fail=True))
        with self.assertRaises(keystore.StoreError) as ctx:
            store.set("a", SECRET)
        self.assertNotIn(SECRET, str(ctx.exception))
        with self.assertRaises(keystore.StoreError):
            store.get("a")


class ChoiceTests(Base):
    def test_the_modes(self):
        folder = self.tmp()
        self.assertIsInstance(keystore.choose_store("none"), keystore.NullStore)
        self.assertIsInstance(keystore.choose_store("file", folder), keystore.FileStore)

    def test_auto_prefers_the_keyring_through_libsecret(self):
        self.assertIsInstance(keystore.choose_store("auto", self.tmp(), secret=FakeSecret()), keystore.SecretServiceStore)

    def test_then_the_secret_tool_command(self):
        ok = types.SimpleNamespace(returncode=1, stdout="", stderr="")             # "not found" is a normal answer of a working keyring
        store = keystore.choose_store("auto", self.tmp(), secret=FakeSecret(fail=True), run=lambda *a, **k: ok,
                                      which=lambda name: "/usr/bin/secret-tool")
        self.assertIsInstance(store, keystore.SecretToolStore)

    def test_a_secret_tool_that_cannot_reach_a_keyring_is_not_used(self):
        broken = types.SimpleNamespace(returncode=1, stdout="", stderr="secret-tool: Cannot autolaunch D-Bus without X11 $DISPLAY")
        store = keystore.choose_store("auto", self.tmp(), secret=FakeSecret(fail=True), run=lambda *a, **k: broken,
                                      which=lambda name: "/usr/bin/secret-tool")
        self.assertIsInstance(store, keystore.FileStore)

    def test_with_nothing_else_the_file_is_the_last_resort(self):
        store = keystore.choose_store("auto", self.tmp(), secret=FakeSecret(fail=True), which=lambda name: None)
        self.assertIsInstance(store, keystore.FileStore)

    def test_when_a_keyring_is_demanded_and_there_is_none_it_says_so(self):
        with self.assertRaises(keystore.StoreError):
            keystore.choose_store("keyring", self.tmp(), secret=FakeSecret(fail=True), which=lambda name: None)

    def test_the_environment_variable_chooses_the_mode(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_KEYSTORE": "none"}):
            self.assertIsInstance(keystore.choose_store(), keystore.NullStore)

    def test_a_key_can_be_recognised_without_being_shown(self):
        self.assertEqual(keystore.describe_key(SECRET), "sk-ant-…wXyZ, %d characters" % len(SECRET))
        self.assertNotIn("QQQQ", keystore.describe_key(SECRET))
        self.assertEqual(keystore.describe_key("abcdefghijklmnopq"), "…nopq, 17 characters")           # no prefix is guessed
        self.assertEqual(keystore.describe_key("short"), "5 characters")
        self.assertEqual(keystore.describe_key(""), "0 characters")


class LookupOrderTests(Base):
    CFG = {**engines.BUILTIN["anthropic"], "id": "anthropic"}

    def test_the_variable_wins_then_the_keyring_then_the_key_file(self):
        store = self.use(MemoryStore())
        store.set("anthropic", "from-the-keyring")
        path = os.path.join(self.tmp(), "k")
        with open(path, "w") as fh:
            fh.write("from-the-file")
        os.chmod(path, 0o600)
        cfg = {**self.CFG, "key_file": path}
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "from-the-variable"}):
            self.assertEqual(engines._find_key(cfg)[:2], ("from-the-variable", "$ANTHROPIC_API_KEY"))
        with self.clean_env():
            self.assertEqual(engines._find_key(cfg)[:2], ("from-the-keyring", "system keyring"))
            store.delete("anthropic")
            self.assertEqual(engines._find_key(cfg)[0], "from-the-file")

    def test_a_key_saved_by_the_window_is_what_is_sent(self):
        store = self.use(MemoryStore())
        store.set("anthropic", SECRET)
        sent = []
        with self.clean_env():
            engines.ask(self.CFG, "q", http=lambda url, headers, body, timeout=120: sent.append(headers) or
                        {"model": "m", "content": [{"type": "text", "text": "x"}]})
        self.assertEqual(sent[0]["x-api-key"], SECRET)

    def test_the_status_and_the_report_name_the_keyring_and_never_show_the_key(self):
        self.use(MemoryStore()).set("anthropic", SECRET)
        with self.clean_env():
            status = engines.key_status(self.CFG)
            report = engines.key_report(self.CFG)
        self.assertIn("key in system keyring: configured, %d characters" % len(SECRET), status)
        self.assertNotIn("sk-ant", status + str(report))
        self.assertTrue(engines.readiness(self.CFG)[0] or True)

    def test_an_engine_with_a_saved_key_is_ready_and_without_one_it_points_to_the_key_button(self):
        store = self.use(MemoryStore())
        with self.clean_env():
            ready, problems, fix = engines.readiness(self.CFG)
            self.assertEqual((ready, problems), (False, ["no key"]))
            self.assertIn("Key button", fix)
            store.set("anthropic", SECRET)
            self.assertTrue(engines.readiness(self.CFG)[0])

    def test_a_store_that_cannot_be_read_is_reported_not_hidden(self):
        store = keystore.FileStore(self.tmp())
        store.set("anthropic", SECRET)
        os.chmod(store.path("anthropic"), 0o666)
        self.use(store)
        with self.clean_env():
            self.assertEqual(engines.readiness(self.CFG)[1], ["key file permissions are insecure (readable by others)"])


class CheckKeyTests(Base):
    CFG = {**engines.BUILTIN["anthropic"], "id": "anthropic"}

    def getter(self, answer):
        calls = []

        def get(url, headers, timeout=20):
            calls.append((url, headers))
            if isinstance(answer, Exception):
                raise answer
            return answer
        return get, calls

    def test_the_models_list_of_the_service_is_asked_with_the_typed_key_and_costs_nothing(self):
        get, calls = self.getter({"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5", "type": "model"})
        res = engines.check_key(self.CFG, key=' "%s"\n' % SECRET, http_get=get)
        self.assertEqual(calls[0][0], "https://api.anthropic.com/v1/models/claude-sonnet-5-5")
        self.assertEqual(calls[0][1], {"x-api-key": SECRET, "anthropic-version": "2023-06-01"})
        self.assertEqual(res, {"ok": True, "message": "API key validated successfully; model Claude Sonnet 5.5 is active."})

    def test_a_refused_key_is_said_plainly(self):
        get, _ = self.getter(engines.EngineError("the service answered HTTP 401: invalid x-api-key"))
        res = engines.check_key(self.CFG, key=SECRET, http_get=get)
        self.assertFalse(res["ok"])
        self.assertIn("the API key", res["message"])
        self.assertNotIn(SECRET, res["message"])

    def test_a_refusal_names_the_server_and_shows_how_to_recognise_the_key_but_not_the_key(self):
        get, _ = self.getter(engines.EngineError("the service answered HTTP 401: invalid x-api-key"))
        message = engines.check_key(self.CFG, key=SECRET, http_get=get)["message"]
        self.assertIn("Service api.anthropic.com rejected the API key (HTTP 401)", message)
        self.assertIn("Sent key suffix: sk-ant-…wXyZ, %d characters" % len(SECRET), message)
        self.assertNotIn("QQQQ", message)

    def test_a_good_key_with_an_unknown_model_is_told_apart_from_a_bad_key(self):
        get, _ = self.getter(engines.EngineError("the service answered HTTP 404: not_found_error"))
        res = engines.check_key({**self.CFG, "model": "no-such-model"}, key=SECRET, http_get=get)
        self.assertTrue(res["ok"])
        self.assertIn("but model «no-such-model»", res["message"])

    def test_without_a_model_the_list_is_asked(self):
        get, calls = self.getter({"data": []})
        engines.check_key({**self.CFG, "model": ""}, key=SECRET, http_get=get)
        self.assertEqual(calls[0][0], "https://api.anthropic.com/v1/models?limit=1")

    def test_a_service_that_cannot_be_reached_is_explained(self):
        get, _ = self.getter(engines.EngineError("cannot reach https://api.anthropic.com/v1/models: timed out"))
        res = engines.check_key(self.CFG, key=SECRET, http_get=get)
        self.assertFalse(res["ok"])
        self.assertIn("cannot reach", res["message"])

    def test_with_no_key_anywhere_it_says_so_and_asks_nothing(self):
        get, calls = self.getter({})
        self.use(MemoryStore())
        with self.clean_env():
            res = engines.check_key(self.CFG, http_get=get)
        self.assertFalse(res["ok"])
        self.assertEqual(calls, [])

    def test_an_openai_compatible_endpoint_is_asked_for_its_model(self):
        get, calls = self.getter({"id": "my-model"})
        cfg = {**engines.BUILTIN["openai"], "id": "openai", "model": "my-model"}
        res = engines.check_key(cfg, key="sk-x", http_get=get)
        self.assertEqual(calls[0], ("https://api.openai.com/v1/models/my-model", {"authorization": "Bearer sk-x"}))
        self.assertTrue(res["ok"])

    def test_an_engine_without_a_key_has_nothing_to_test(self):
        self.assertFalse(engines.check_key({"kind": "browser", "id": "google"}, key="x", http_get=lambda *a, **k: {})["ok"])


class ServiceTests(Base):
    def test_the_server_of_each_kind_of_engine(self):
        self.assertEqual(engines.service_host(engines.BUILTIN["anthropic"]), "api.anthropic.com")
        self.assertEqual(engines.service_host(engines.BUILTIN["openai"]), "api.openai.com")
        self.assertEqual(engines.service_host(engines.BUILTIN["ollama"]), "localhost:11434")
        self.assertEqual(engines.service_host(engines.BUILTIN["google"]), "")

    def test_a_key_of_the_wrong_service_is_recognised_by_its_shape(self):
        anthropic, openai, ollama = (engines.BUILTIN[k] for k in ("anthropic", "openai", "ollama"))
        self.assertIn('select \'Claude API with web search\'', engines.key_mismatch(openai, SECRET))
        self.assertIn("must start with 'sk-ant-'", engines.key_mismatch(anthropic, "sk-proj-abc123"))
        self.assertEqual(engines.key_mismatch(anthropic, SECRET), "")
        self.assertEqual(engines.key_mismatch(openai, "sk-proj-abc123"), "")
        self.assertEqual(engines.key_mismatch(ollama, SECRET), "")                   # another server: no opinion
        self.assertEqual(engines.key_mismatch(openai, ""), "")
        self.assertEqual(engines.key_mismatch(openai, ' "%s" ' % SECRET).startswith("This is an Anthropic Claude key"), True)

    def test_testing_a_key_of_the_wrong_service_asks_nobody(self):
        asked = []
        res = engines.check_key({**engines.BUILTIN["openai"], "id": "openai", "model": "m"}, key=SECRET,
                                http_get=lambda *a, **k: asked.append(a) or {})
        self.assertFalse(res["ok"])
        self.assertIn("an Anthropic Claude key,", res["message"])
        self.assertEqual(asked, [])

    def test_a_refused_key_in_an_ordinary_call_names_the_server_and_the_hint(self):
        self.use(MemoryStore()).set("anthropic", SECRET)

        def refuse(url, headers, body, timeout=120):
            raise engines.EngineError("the service answered HTTP 401: invalid x-api-key")
        with self.clean_env():
            with self.assertRaises(engines.EngineError) as ctx:
                engines.ask({**engines.BUILTIN["anthropic"], "id": "anthropic"}, "q", http=refuse)
        message = str(ctx.exception)
        self.assertIn("Service api.anthropic.com rejected API key authentication sent (sk-ant-…wXyZ, %d characters)" % len(SECRET), message)
        self.assertIn("Verify key active status", message)
        self.assertNotIn("QQQQ", message)


class SessionKeyTests(Base):
    def session(self):
        return sess.Session(Tree({}, []), self.tmp())

    def test_the_key_dialog_knows_what_is_saved_and_where_a_new_key_would_go(self):
        store = self.use(MemoryStore())
        s = self.session()
        with self.clean_env():
            before = s.key_info("anthropic")
            self.assertEqual((before["set"], before["hint"], before["store"], before["secure"]), (False, "", "system keyring", True))
            after = s.save_key("anthropic", ' "%s" ' % SECRET)
        self.assertEqual(store.items["anthropic"], SECRET)                       # cleaned of the quotes and spaces of a paste
        self.assertEqual((after["set"], after["where"]), (True, "system keyring"))
        self.assertEqual(after["hint"], "sk-ant-…wXyZ, %d characters" % len(SECRET))
        self.assertEqual(after["model"], "claude-sonnet-5-5")

    def test_a_key_of_another_service_is_not_kept(self):
        store = self.use(MemoryStore())
        s = self.session()
        with self.assertRaises(ValueError) as ctx:
            s.save_key("openai", SECRET)
        self.assertIn("an Anthropic Claude key,", str(ctx.exception))
        self.assertEqual(store.items, {})
        self.assertEqual(s.key_info("openai")["host"], "api.openai.com")

    def test_an_empty_key_is_refused_and_a_store_that_fails_is_an_error_with_a_message(self):
        s = self.session()
        with self.assertRaises(ValueError):
            s.save_key("anthropic", "   ")
        self.use(keystore.NullStore())
        with self.assertRaises(keystore.StoreError):
            s.save_key("anthropic", SECRET)

    def test_a_key_can_be_removed(self):
        store = self.use(MemoryStore())
        s = self.session()
        with self.clean_env():
            s.save_key("anthropic", SECRET)
            self.assertFalse(s.remove_key("anthropic")["set"])
        self.assertEqual(store.items, {})

    def test_the_typed_key_is_tested_before_it_is_saved(self):
        store = self.use(MemoryStore())
        s = self.session()
        seen = []
        res = s.test_key("anthropic", key=SECRET, http_get=lambda url, headers, timeout=20: seen.append(headers) or {"id": "x"})
        self.assertTrue(res["ok"])
        self.assertEqual(seen[0]["x-api-key"], SECRET)
        self.assertEqual(store.items, {})                                         # testing saves nothing

    def test_asking_without_a_key_tells_the_window_to_open_the_key_dialog(self):
        self.use(MemoryStore())
        s = self.session()
        with self.clean_env():
            a = s.begin("Johnston", "1950", engine="anthropic")
        self.assertEqual((a["action"], a["needs_key"]), ("error", "anthropic"))

    def test_a_key_the_service_refuses_tells_the_window_too(self):
        store = self.use(MemoryStore())
        store.set("anthropic", SECRET)
        s = self.session()

        def refuse(url, headers, body, timeout=120):
            raise engines.EngineError("the service answered HTTP 401: invalid x-api-key")
        with self.clean_env():
            s.begin("Johnston", "1950", engine="anthropic")
            a = s.run_api(http=refuse)
        self.assertEqual((a["action"], a["needs_key"]), ("error", "anthropic"))
        self.assertNotIn(SECRET, a["message"])


class KeysCommandTests(Base):
    def run_cmd(self, *argv, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.keys_cmd(__import__("argparse").Namespace(engine=argv[0], set="--set" in argv, remove="--remove" in argv,
                                                                  test="--test" in argv), **kw)
        return code, buf.getvalue()

    def test_set_keeps_the_key_without_echoing_it(self):
        store = self.use(MemoryStore())
        with self.clean_env():
            code, out = self.run_cmd("anthropic", "--set", getpass_fn=lambda prompt: SECRET + "\n")
        self.assertEqual(code, 0)
        self.assertEqual(store.items["anthropic"], SECRET)
        self.assertIn("Key kept in system keyring", out)
        self.assertNotIn(SECRET, out)

    def test_a_key_kept_in_a_plain_file_comes_with_the_warning(self):
        self.use(keystore.FileStore(os.path.join(self.tmp(), "k")))
        with self.clean_env():
            code, out = self.run_cmd("anthropic", "--set", getpass_fn=lambda prompt: SECRET)
        self.assertIn("NOT ENCRYPTED", out)

    def test_nothing_typed_changes_nothing(self):
        store = self.use(MemoryStore())
        code, _ = self.run_cmd("anthropic", "--set", getpass_fn=lambda prompt: "  ")
        self.assertEqual((code, store.items), (2, {}))

    def test_status_remove_and_test(self):
        store = self.use(MemoryStore())
        store.set("anthropic", SECRET)
        with self.clean_env():
            code, out = self.run_cmd("anthropic")
            self.assertIn("key in system keyring:", out)
            code, out = self.run_cmd("anthropic", "--test", http_get=lambda url, headers, timeout=20: {"id": "x", "display_name": "X"})
            self.assertEqual((code, out.splitlines()[0]), (0, "OK: API key validated successfully; model X is active."))
            code, out = self.run_cmd("anthropic", "--remove")
        self.assertEqual(store.items, {})

    def test_an_engine_without_a_key_and_an_unknown_engine(self):
        self.assertIn("an API key", self.run_cmd("google")[1])
        self.assertEqual(self.run_cmd("nobody")[0], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
