import unittest

from helpers import run_guard

MAC = "/Users/u/Library/Thunderbird/Profiles/x.default-release"
LINUX = "/home/u/.thunderbird/x.default-release"
WIN = "C:\\Users\\u\\AppData\\Roaming\\Thunderbird\\Profiles\\x.default-release"
FLATPAK = "/home/u/.var/app/org.mozilla.Thunderbird/.thunderbird/x"


def bash(command, cwd=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd:
        payload["cwd"] = cwd
    return run_guard(payload)[0]


def tool(name, **tool_input):
    return run_guard({"tool_name": name, "tool_input": tool_input})[0]


class GuardBlocks(unittest.TestCase):
    def test_file_tools_on_profiles(self):
        for path in (MAC + "/prefs.js", LINUX + "/ImapMail/x/INBOX", WIN + "\\prefs.js", FLATPAK + "/prefs.js"):
            for name in ("Edit", "Write", "MultiEdit"):
                self.assertEqual(tool(name, file_path=path), 2, (name, path))

    def test_mutating_shell_commands_on_profiles(self):
        cmds = [
            "rm -rf %s/Mail" % MAC,
            "mv %s/ImapMail/x/INBOX /tmp/" % LINUX,
            "cp /tmp/evil %s/prefs.js" % MAC,
            "echo x > %s/prefs.js" % MAC,
            "sed -i 's/a/b/' %s/prefs.js" % LINUX,
            "sqlite3 %s/global-messages-db.sqlite 'DELETE FROM messages'" % MAC,
            "find %s -name '*.msf' -delete" % LINUX,
            "python3 -c \"open('%s/prefs.js','w')\"" % LINUX,
            "cd %s && rm Inbox" % MAC,
            "Remove-Item '%s\\prefs.js'" % WIN,
            "open -a Thunderbird",
            "killall thunderbird",
        ]
        for c in cmds:
            self.assertEqual(bash(c), 2, c)

    def test_mutating_command_inside_profile_cwd(self):
        self.assertEqual(bash("rm Inbox", cwd=MAC + "/Mail/Local Folders"), 2)

    def test_sending_mail(self):
        cmds = [
            "echo hi | mail -s test a@example.com",
            "sendmail a@example.com < msg.txt",
            "/usr/sbin/sendmail -t < msg",
            "msmtp a@example.com < m",
            "curl --url smtps://smtp.example.com:465 --mail-rcpt a@example.com",
            "python3 -c 'import smtplib'",
            "thunderbird -compose \"to=a@example.com,subject=hi\"",
            "osascript -e 'tell application \"Thunderbird\" to activate'",
            "Send-MailMessage -To a@example.com",
        ]
        for c in cmds:
            self.assertEqual(bash(c), 2, c)


class GuardAllows(unittest.TestCase):
    def test_reading(self):
        cmds = [
            "ls %s" % MAC,
            "ls -la %s 2>/dev/null" % LINUX,
            "cat %s/profiles.ini" % MAC,
            "grep -c 'From ' %s/ImapMail/x/INBOX" % LINUX,
            "python3 /plugins/thunderbird-mail/scripts/tb.py search --from alice",
            "python3 \"/a b/scripts/tb.py\" show \"sam@example.com/INBOX#0\"",
            "python3 /p/scripts/tb.py list --profile-dir %s" % LINUX,
            "python3 /p/scripts/tb.py list --limit 5 | head -40",
        ]
        for c in cmds:
            self.assertEqual(bash(c), 0, c)

    def test_unrelated_work(self):
        cmds = [
            "rm -rf build",
            "cd ~/Projects/thunderbird-claude-skills && rm -rf dist",
            "ls ~/mail",
            "git commit -m 'improve mail parsing'",
            "python3 -m unittest discover -s tests",
        ]
        for c in cmds:
            self.assertEqual(bash(c), 0, c)
        self.assertEqual(tool("Write", file_path="/Users/u/Projects/thunderbird-claude-skills/README.md"), 0)
        self.assertEqual(tool("Read", file_path=MAC + "/prefs.js"), 0)

    def test_garbage_input_is_ignored(self):
        self.assertEqual(run_guard("not a dict")[0], 0)


if __name__ == "__main__":
    unittest.main()
