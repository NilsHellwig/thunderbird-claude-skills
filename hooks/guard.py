#!/usr/bin/env python3
"""PreToolUse guard for the thunderbird-mail plugin.

Blocks any tool call that could modify a Thunderbird profile, control
Thunderbird, or send mail. Reading stays allowed.

Input: the hook JSON on stdin. Exit code 2 blocks the call; the message on
stderr is shown to the agent. Standard library only. Python 3.8+.
"""

import json
import re
import sys

# A path segment that identifies Thunderbird data:
#   ~/Library/Thunderbird, ~/.thunderbird, %APPDATA%\Thunderbird,
#   ~/snap/thunderbird, ~/.var/app/org.mozilla.Thunderbird, Thunderbird.app
TB_PATH_RE = re.compile(
    r"(?:^|[/\\\s\"'=:])(?:\.?thunderbird|org\.mozilla\.thunderbird|thunderbird\.app)(?=[/\\\s\"']|$)",
    re.IGNORECASE,
)

# Commands that write, move, delete or otherwise mutate files.
MUTATING_RE = re.compile(
    r"""
    (?:^|[;&|(`\s]|\$\()\s*(?:sudo\s+)?(?:\S*/)?
    (?:rm|rmdir|mv|cp|dd|truncate|touch|tee|ln|unlink|shred|chmod|chown|chflags|xattr|
       rsync|install|mkdir|sqlite3|patch|git|tar|zip|unzip|ditto|trash|srm|open|osascript|
       defaults|killall|pkill|kill|thunderbird|thunderbird-bin)
    (?=\s|$|;|&|\|)
    |\bsed\s+(?:-[a-zA-Z]*i|--in-place)
    |\bperl\s+-[a-zA-Z]*i
    |\bfind\b.*\s-(?:delete|exec|execdir|ok)\b
    |>{1,2}
    |\b(?:python3?|python\d[\d.]*|perl|ruby|node|deno|bun|php|pwsh|powershell)\b
    |\b(?:Remove-Item|Move-Item|Copy-Item|Set-Content|Add-Content|Out-File|Rename-Item|del|erase|rd|ren|move|copy)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Sending mail or talking to mail servers, regardless of any path.
# Mail programs only count in command position, so `ls ~/mail` stays allowed.
SEND_RE = re.compile(
    r"""
    (?:^|[;&|(`\n]|\$\()\s*(?:(?:sudo|env|exec|nohup|command|xargs)\s+(?:-\S+\s+)*)*(?:\S*/)?
    (?:sendmail|mail|mailx|msmtp|ssmtp|mutt|neomutt|swaks|s-nail|exim|postfix|nail|mailsend)
    (?=\s|$|;|&|\|)
    |\b(?:smtps?|imaps?|pop3s?)://
    |\b(?:smtplib|imaplib|poplib)\b
    |\bSend-MailMessage\b
    |\bthunderbird\b[^;&|]*\s-compose\b
    |\btell\s+application\s+["']?thunderbird
    """,
    re.IGNORECASE | re.VERBOSE,
)

# The read-only tool shipped with this plugin is always fine to run.
TB_TOOL_RE = re.compile(r"""^\s*(?:"[^"]*"|\S*)python[\d.]*(?:\.exe)?"?\s+(?:-I\s+)?["']?[^\s"']*tb\.py["']?(?:\s|$)""",
                        re.IGNORECASE)
SHELL_META_RE = re.compile(r"[;&|`<>]|\$\(")
# Harmless redirections that would otherwise look like writes.
HARMLESS_REDIRECT_RE = re.compile(r"\d?>{1,2}\s*/dev/null|\d>&\d|<\s*/dev/null")

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def deny(reason):
    sys.stderr.write(
        "Blocked by thunderbird-mail guard: %s\n"
        "Thunderbird data is strictly read-only and mail is never sent by the agent. "
        "Use tb.py to read mail and present drafts to the user as text.\n" % reason
    )
    sys.exit(2)


def is_tb_path(path):
    return bool(path) and bool(TB_PATH_RE.search(" " + str(path)))


def check_file_tool(tool_input):
    for key in ("file_path", "notebook_path", "path"):
        if is_tb_path(tool_input.get(key)):
            deny("writing to a Thunderbird path (%s)" % tool_input.get(key))


def check_bash(command, cwd=""):
    if not command:
        return
    if SEND_RE.search(command):
        deny("command looks like it sends mail or contacts a mail server")
    if TB_TOOL_RE.match(command) and not SHELL_META_RE.search(command):
        return
    stripped = HARMLESS_REDIRECT_RE.sub(" ", command)
    if (is_tb_path(command) or is_tb_path(cwd)) and MUTATING_RE.search(stripped):
        deny("command could modify Thunderbird data or control Thunderbird")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    if tool in FILE_TOOLS:
        check_file_tool(tool_input)
    elif tool in ("Bash", "PowerShell"):
        check_bash(tool_input.get("command", ""), data.get("cwd", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
