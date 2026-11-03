import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from helpers import FIXTURE_HOME, FIXTURE_PROFILE, ROOT, TB, TbRunner


def snapshot(root):
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.stat(full)
            digest = ""
            if os.path.isfile(full):
                with open(full, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            state[os.path.relpath(full, root)] = (st.st_mtime_ns, st.st_size, digest)
    return state


class FirstRunTest(unittest.TestCase):
    def test_commands_refuse_until_acknowledged(self):
        r = TbRunner(acknowledged=False)
        try:
            code, out, _ = r.run("list")
            self.assertEqual(code, 3)
            self.assertIn("PRIVACY NOTICE", out)
            self.assertIn("ANTHROPIC_BASE_URL", out)
            self.assertNotIn("Project kickoff", out)
            code, out, _ = r.run("acknowledge")
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(r.config_dir, "acknowledged")))
            code, out, _ = r.run("list")
            self.assertEqual(code, 0)
            self.assertIn("Project kickoff", out)
        finally:
            r.close()


class LocalLlmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        self.models = os.path.join(self.tmp, "models")
        os.makedirs(self.bin)
        self.r = TbRunner(acknowledged=False)
        self.r.env["PATH"] = self.bin
        self.r.env["TB_MAIL_OLLAMA_EXTRA_DIRS"] = ""
        self.r.env["OLLAMA_MODELS"] = self.models

    def tearDown(self):
        self.r.close()
        shutil.rmtree(self.tmp)

    def _install_ollama(self):
        for name in ("ollama", "ollama.exe"):
            open(os.path.join(self.bin, name), "w").close()

    def _add_model(self, repo, tag, size, registry="registry.ollama.ai"):
        d = os.path.join(self.models, "manifests", registry, *repo.split("/"))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, tag), "w") as fh:
            fh.write('{"layers": [{"size": %d}, {"size": 10}]}' % size)

    def test_nothing_installed(self):
        info = self.r.json("local-llm")
        self.assertIsNone(info["ollama"])
        self.assertEqual(info["models"], [])
        code, out, _ = self.r.run("list")
        self.assertEqual(code, 3)
        self.assertIn("No local model runtime found", out)
        self.assertIn("https://ollama.com", out)

    def test_ollama_without_models(self):
        self._install_ollama()
        code, out, _ = self.r.run("list")
        self.assertIn("no local models are installed", out)
        self.assertIn("claude --model <model>", out)

    def test_suggests_largest_local_model_and_skips_cloud(self):
        self._install_ollama()
        self._add_model("library/small", "latest", 2000000000)
        self._add_model("library/big", "32b", 20000000000)
        self._add_model("library/remote", "cloud", 99000000000000)
        self._add_model("library/remote2", "120b-cloud", 99000000000000)
        self._add_model("org/model", "q4", 5000000000, registry="hf.co")
        info = self.r.json("local-llm")
        names = [m["name"] for m in info["models"]]
        self.assertEqual(names, ["big:32b", "hf.co/org/model:q4", "small:latest"])
        self.assertEqual(info["suggested_model"], "big:32b")
        self.assertIn("ANTHROPIC_BASE_URL", info["command"])
        self.assertIn("http://localhost:11434", info["command"])
        self.assertIn("claude --model big:32b", info["command"])
        code, out, _ = self.r.run("list")
        self.assertEqual(code, 3)
        self.assertIn("LOCAL MODEL FOUND", out)
        self.assertIn("claude --model big:32b", out)
        self.assertNotIn("remote", out)

    def test_local_llm_needs_no_acknowledgement(self):
        code, _, _ = self.r.run("local-llm")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.r.config_dir, "acknowledged")))


class ReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = TbRunner()

    @classmethod
    def tearDownClass(cls):
        cls.r.close()

    def test_profiles_detects_active_install_default(self):
        profiles = self.r.json("profiles")
        active = [p for p in profiles if p["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["name"], "default-release")

    def test_folders(self):
        paths = {f["path"]: f for f in self.r.json("folders")}
        self.assertIn("sam@example.com/INBOX", paths)
        self.assertIn("sam@example.com/INBOX/Projects", paths)
        self.assertIn("maildir.example.org/Inbox", paths)
        self.assertEqual(paths["maildir.example.org/Inbox"]["kind"], "maildir")
        self.assertTrue(paths["sam@example.com/Trash"]["trash"])
        self.assertTrue(paths["sam@example.com/Sent"]["sent"])
        self.assertFalse(any(p.endswith(".msf") or p.endswith(".dat") for p in paths))

    def test_list_inboxes_newest_first_without_deleted(self):
        msgs = self.r.json("list", "--limit", "0")
        subjects = [m["subject"] for m in msgs]
        self.assertEqual(subjects[0], "Maildir hello")
        self.assertIn("Project kickoff", subjects)
        self.assertNotIn("Expunged secret", subjects)
        self.assertNotIn("Weekly newsletter", subjects)
        self.assertNotIn("Re: Project kickoff", subjects)  # lives in Sent / a subfolder

    def test_unread_filter(self):
        subjects = {m["subject"] for m in self.r.json("list", "--unread", "--limit", "0")}
        self.assertEqual(subjects, {"Maildir hello", "Project kickoff"})

    def test_search_filters(self):
        self.assertEqual([m["subject"] for m in self.r.json("search", "--from", "jürgen")],
                         ["Grüße aus Köln"])
        self.assertEqual([m["subject"] for m in self.r.json("search", "--text", "payment due")],
                         ["Your invoice"])
        hits = self.r.json("search", "--since", "2026-11-02", "--until", "2026-11-02", "--limit", "0")
        self.assertEqual(sorted(m["subject"] for m in hits),
                         ["Project kickoff", "Re: Project kickoff", "Re: Project kickoff"])

    def test_trash_only_on_request(self):
        self.assertEqual(self.r.json("search", "--text", "unsubscribe"), [])
        hits = self.r.json("search", "--text", "unsubscribe", "--include-trash")
        self.assertEqual([m["subject"] for m in hits], ["Weekly newsletter"])

    def test_deleted_messages_never_shown(self):
        self.assertEqual(self.r.json("search", "--text", "secret", "--include-trash"), [])

    def test_show_html_and_attachments(self):
        ref = self.r.json("search", "--subject", "invoice")[0]["ref"]
        m = self.r.json("show", ref)
        self.assertIn("please find the invoice attached & the notes.", m["body"])
        self.assertIn("- Item A", m["body"])
        self.assertNotIn("color:red", m["body"])
        names = {a["filename"]: a for a in m["attachments"]}
        self.assertEqual(set(names), {"notes.txt", "invoice.pdf"})
        self.assertEqual(names["notes.txt"]["text"].strip(), "Payment due in 14 days.")
        self.assertNotIn("text", names["invoice.pdf"])

    def test_show_by_message_id_and_charset(self):
        m = self.r.json("show", "<latin@example.de>")
        self.assertEqual(m["subject"], "Grüße aus Köln")
        self.assertIn("viele Grüße", m["body"])

    def test_body_with_from_line_is_not_split(self):
        m = self.r.json("show", "<frombody@example.net>")
        self.assertIn("From here on, the body continues.", m["body"])
        self.assertIn("Last line", m["body"])

    def test_header_only_message(self):
        m = self.r.json("show", "<hdr-only@example.net>")
        self.assertIn("Body not available locally", m["body"])

    def test_thread_spans_folders(self):
        msgs = self.r.json("thread", "<reply-1@example.com>")
        self.assertEqual([m["message_id"] for m in msgs],
                         ["<kickoff-1@example.net>", "<reply-1@example.com>", "<followup-1@example.net>"])

    def test_sent_to(self):
        msgs = self.r.json("sent-to", "alice@example.net")
        self.assertEqual([m["subject"] for m in msgs], ["Re: Project kickoff", "Slides"])
        self.assertIn("Cheers", msgs[0]["body"])
        self.assertEqual(len(self.r.json("sent-to", "--limit", "1")), 1)

    def test_identities(self):
        self.assertEqual(self.r.json("identities")[0]["email"], "sam@example.com")

    def test_explicit_profile_dir(self):
        msgs = self.r.json("list", "--profile-dir", FIXTURE_PROFILE, "--limit", "1")
        self.assertEqual(len(msgs), 1)


class IndexSearchTest(unittest.TestCase):
    def test_search_index_reads_gloda_db(self):
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "global-messages-db.sqlite")
            con = sqlite3.connect(db)
            con.executescript(
                "CREATE TABLE folderLocations (id INTEGER PRIMARY KEY, folderURI TEXT, dirtyStatus INTEGER,"
                " name TEXT, indexingPriority INTEGER);"
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, folderID INTEGER, messageKey INTEGER,"
                " conversationID INTEGER, date INTEGER, headerMessageID TEXT, deleted INTEGER,"
                " jsonAttributes TEXT, notability INTEGER);"
                "CREATE TABLE messagesText_content (docid INTEGER PRIMARY KEY, c0body TEXT, c1subject TEXT,"
                " c2attachmentNames TEXT, c3author TEXT, c4recipients TEXT);"
                "INSERT INTO folderLocations VALUES (1, 'imap://x/INBOX', 0, 'INBOX', 0);"
                "INSERT INTO messages VALUES (1, 1, 1, 1, 1793606400000000, 'a@x', 0, '{}', 0);"
                "INSERT INTO messages VALUES (2, 1, 2, 2, 1793606400000000, 'b@x', 1, '{}', 0);"
                "INSERT INTO messagesText_content VALUES (1, 'budget numbers', 'Q4 budget', '', 'Alice', 'sam');"
                "INSERT INTO messagesText_content VALUES (2, 'budget deleted', 'old', '', 'Alice', 'sam');"
            )
            con.commit()
            con.close()
            before = os.stat(db).st_mtime_ns
            r = TbRunner()
            try:
                hits = r.json("search", "--index", "--profile-dir", tmp, "--text", "budget")
            finally:
                r.close()
            self.assertEqual([h["subject"] for h in hits], ["Q4 budget"])
            self.assertEqual(os.stat(db).st_mtime_ns, before)
            self.assertEqual(sorted(os.listdir(tmp)), ["global-messages-db.sqlite"])
        finally:
            shutil.rmtree(tmp)


class ReadOnlyTest(unittest.TestCase):
    def test_fixture_profile_untouched_by_every_command(self):
        before = snapshot(FIXTURE_HOME)
        r = TbRunner()
        try:
            for args in (["profiles"], ["identities"], ["folders", "--count"], ["list", "--limit", "0"],
                         ["search", "--text", "a", "--include-trash", "--limit", "0"],
                         ["show", "<reply-1@example.com>"], ["thread", "<kickoff-1@example.net>"],
                         ["sent-to"]):
                code, _, err = r.run(*args)
                self.assertEqual(code, 0, "%s: %s" % (args, err))
        finally:
            r.close()
        self.assertEqual(before, snapshot(FIXTURE_HOME))

    def _guarded(self, code):
        prog = ("import sys; sys.path.insert(0, %r); import tb; tb.install_readonly_guard()\n%s"
                % (os.path.join(ROOT, "scripts"), code))
        env = dict(os.environ, TB_MAIL_CONFIG_DIR=tempfile.gettempdir() + os.sep + "tb-mail-test-cfg")
        return subprocess.run([sys.executable, "-c", prog], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_runtime_guard_blocks_writes(self):
        target = os.path.join(tempfile.gettempdir(), "tb-mail-should-not-exist.txt")
        proc = self._guarded("open(%r, 'w')" % target)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"ReadOnlyViolation", proc.stderr)
        self.assertFalse(os.path.exists(target))

    def test_runtime_guard_blocks_network(self):
        proc = self._guarded("import socket; socket.socket()")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"ReadOnlyViolation", proc.stderr)

    def test_runtime_guard_blocks_delete_and_subprocess(self):
        for code in ("import os; os.remove('nothing-here')", "import subprocess; subprocess.run(['true'])"):
            proc = self._guarded(code)
            self.assertIn(b"ReadOnlyViolation", proc.stderr, code)

    def test_runtime_guard_blocks_writable_sqlite(self):
        proc = self._guarded("import sqlite3; sqlite3.connect(':memory:')")
        if sys.version_info >= (3, 10):  # sqlite3.connect audit event exists since 3.10
            self.assertIn(b"ReadOnlyViolation", proc.stderr)


if __name__ == "__main__":
    unittest.main()
