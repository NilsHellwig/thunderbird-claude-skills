<p align="center">
  <img src="docs/assets/banner.jpg" alt="thunderbird-claude-skills banner" width="100%">
</p>

# thunderbird-claude-skills

[![CI](https://github.com/NilsHellwig/thunderbird-claude-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/NilsHellwig/thunderbird-claude-skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

Agent skills for [Claude Code](https://claude.com/claude-code) that read your **local Thunderbird mail** and help you **write emails in your own style**.

They are **strictly read-only**. They never send, delete, move or modify mail, and they never contact a mail server. They only read what Thunderbird has already stored on your disk, and every draft lands in the chat for you to copy and send yourself.

> [!WARNING]
> **Your emails are sent to the model you run.** Every message a skill reads becomes part of the model's context. With a hosted model, your mail content leaves your machine and is processed by the model provider.
>
> **For confidential mail, use a local or self-hosted open-source model.** See [Privacy](#privacy) for how to point Claude Code at one.

## Skills

| Skill | What it does |
|---|---|
| `thunderbird-mail` | Search and read local mail: folders, messages, conversations, attachments. Also holds the shared rules for the other skills. |
| `draft-reply` | Drafts a reply to an email. It reads the whole thread first and matches how you usually write to that person. |
| `draft-email` | Drafts a new email. It resolves recipients from your mail and matches your style. |
| `inbox-digest` | Summarizes unread mail from the last 7 days, grouped by account, with action items first. |

Drafts come as separate copyable blocks for **To**, **Cc**, **Subject** and **Body**.

### Example prompts

```text
What did Alice write about the kickoff?
Reply to Alice's last mail: Thursday works, but only after 2pm.
Write an email to Bob asking for the signed contract by Friday.
What's new in my inbox?
```

## Safety model

Read-only is enforced in three independent layers:

1. **The tool itself** (`scripts/tb.py`):
   - opens files only for reading, and the SQLite search index only with `mode=ro&immutable=1`
   - imports no network or mail modules
   - installs a Python [audit hook](https://docs.python.org/3/library/sys.html#sys.addaudithook) that aborts the process on any file write, delete, subprocess or socket
   - The only file it ever writes is its own first-run marker, outside every Thunderbird profile.
2. **A plugin hook** (`hooks/guard.py`) runs before every tool call. It blocks:
   - edits or shell commands that would touch a Thunderbird profile
   - any attempt to send mail (`sendmail`, `mail`, `msmtp`, SMTP URLs, `smtplib`, …)
   - any attempt to drive Thunderbird (`-compose`, AppleScript, `open -a`)
3. **The skill instructions** forbid all of the above and tell the agent to stop when something is blocked.

CI checks all three:
- static checks that only allow-listed standard-library modules are imported and no writing calls exist
- tests that every command leaves the fixture profile byte-for-byte unchanged
- tests of the audit hook and of the guard

## Privacy

Every email a skill reads is sent as context to the model behind your agent. With a hosted model, your mail content leaves your machine.

On first use the skills therefore stop and show a privacy notice. They only continue after you explicitly agree. The agent then runs `tb.py acknowledge`, which writes a marker to `~/.config/thunderbird-mail/` (on Windows `%APPDATA%\thunderbird-mail\`).

**For confidential mail, use a local or self-hosted open-source model.**

The privacy notice checks for a local [Ollama](https://ollama.com) install by looking at the disk only, without contacting any server. If Ollama is there, the notice lists the local models (cloud-hosted `:cloud` models are skipped) and gives you a ready-to-paste command that restarts Claude Code with one of them. You can run the same check any time with `python3 scripts/tb.py local-llm`.

In general, Claude Code can talk to any server that implements the Anthropic Messages API:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080   # your local server
export ANTHROPIC_AUTH_TOKEN=local                 # if your server needs one
export ANTHROPIC_MODEL=<your-model>
claude
```

## Requirements

- Thunderbird with mail stored locally (mbox or maildir, the defaults for all account types)
- Python **3.8+**, standard library only. Nothing to `pip install`.
- macOS, Linux (including Snap and Flatpak installs) or Windows
- Claude Code

> **IMAP accounts:** only messages Thunderbird has downloaded can be read. Enable *Account Settings → Synchronization & Storage → Keep messages for this account on this computer* to make message bodies available. Messages that were never downloaded show *"Body not available locally"*.

## Installation

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add NilsHellwig/thunderbird-claude-skills
/plugin install thunderbird-mail@thunderbird-claude-skills
```

This installs all four skills plus the guard hook.

### From a local clone

```bash
git clone https://github.com/NilsHellwig/thunderbird-claude-skills.git
```

```text
/plugin marketplace add ./thunderbird-claude-skills
/plugin install thunderbird-mail@thunderbird-claude-skills
```

For a single session without installing anything, use `claude --plugin-dir ./thunderbird-claude-skills`.

### Extra protection without the plugin hook

If you copy the skills somewhere manually instead of installing the plugin, the guard hook does not run. In that case, merge the deny rules from [`settings.example.json`](settings.example.json) into your `~/.claude/settings.json`.

## Using `tb.py` directly

The tool also works on its own:

```bash
python3 scripts/tb.py profiles
python3 scripts/tb.py folders --count
python3 scripts/tb.py list --unread --since 7d
python3 scripts/tb.py search --from alice --text invoice --since 3m
python3 scripts/tb.py show "work@example.com/INBOX#123456"
python3 scripts/tb.py thread "<message-id@example.com>"
python3 scripts/tb.py sent-to alice@example.com --limit 5
python3 scripts/tb.py --help
```

Every command supports `--json`, `--profile NAME` and `--profile-dir PATH`. Without them, the active profile is detected from `profiles.ini`.

## Limitations

- Attachments are listed. Only text attachments (`.txt`, `.csv`, `.ics`, `.md`, `.vcf`) are read. PDF and Office files would need third-party libraries, which this project deliberately avoids.
- Folder scans read the mbox files directly. On very large mailboxes, narrow searches with `--folder`, `--since` or `--from`, or use `search --index` (Thunderbird's global search database).
- Read/unread status comes from Thunderbird's `X-Mozilla-Status` header. Very recent flag changes may only be written to disk after Thunderbird syncs them.

## Development

```bash
python3 -m unittest discover -s tests
```

The tests run against a synthetic profile in [`tests/fixtures/`](tests/fixtures/). See [CONTRIBUTING.md](CONTRIBUTING.md) for the project rules.

## License

[MIT](LICENSE) © Nils Hellwig

*Thunderbird is a trademark of the Mozilla Foundation. This project is not affiliated with or endorsed by Mozilla or Anthropic.*
