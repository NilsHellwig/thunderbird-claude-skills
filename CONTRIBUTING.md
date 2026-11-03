# Contributing

Thanks for helping out! Bug reports, profile layouts we don't handle yet, and skill improvements are all welcome.

## Ground rules

These are the project's invariants. A pull request that breaks one will not be merged.

1. **Read-only.** Nothing may write to, delete from, or move anything in a Thunderbird profile. The only file `tb.py` writes is its acknowledgement marker in `write_ack_marker()`.
2. **Offline.** No network access of any kind: no SMTP/IMAP/POP, no HTTP, no sockets.
3. **Standard library only.** Python 3.8+, no third-party packages, not even optional ones.
4. **Drafts go to the user.** Skills present drafts as text. They never send, schedule or hand mail to Thunderbird.

CI enforces 1–3 statically and at runtime (see `tests/test_static.py` and `tests/test_tb.py`).

## Development setup

```bash
git clone https://github.com/NilsHellwig/thunderbird-claude-skills.git
cd thunderbird-claude-skills
python3 -m unittest discover -s tests
```

To try the plugin in Claude Code without installing it, run `claude --plugin-dir .`.

## Tests and fixtures

- `tests/fixtures/home/` is a synthetic Thunderbird home with an IMAP account, Local Folders and a maildir account. All data in it is fictional. **Never add real mail, real addresses or real profile files.**
- When you fix a parsing bug, add a minimal fixture message that reproduces it, plus a test.
- Fixtures are stored byte-exact (`.gitattributes`), so line endings are preserved.

## Changing skills

Skills live in `skills/<name>/SKILL.md` and are written for agents, not humans:
- Keep shared rules in `skills/thunderbird-mail/SKILL.md` (guardrails, commands, draft format) and point to it from the other skills.
- Give every step a checkable "done when".
- Keep descriptions short: they are loaded into every session.

## Pull requests

- Keep each pull request to one topic. Add an entry under `Unreleased` in `CHANGELOG.md`.
- Run the test suite locally. CI runs it on Linux, macOS and Windows with Python 3.8 and the latest release.
- Describe how you tested it, ideally including the Thunderbird version and store type (mbox or maildir).

## Reporting security issues

Please don't open a public issue. See [SECURITY.md](SECURITY.md).
