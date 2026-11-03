# AGENTS.md

Guidance for coding agents working **on this repository**.

- Invariants: read-only, offline, standard library only, Python 3.8+. They are spelled out in [CONTRIBUTING.md](CONTRIBUTING.md) and enforced by `tests/test_static.py`. Treat a failing static test as a design error, not a test to relax.
- Run `python3 -m unittest discover -s tests` after every change.
- Test only against `tests/fixtures/`. Run `tb.py` on a real profile only when the maintainer asks.
- Skill files are agent-facing. Keep shared rules in `skills/thunderbird-mail/SKILL.md`.
- When you bump the version, update `.claude-plugin/plugin.json`, `scripts/tb.py` (`__version__`) and `CHANGELOG.md` together.
