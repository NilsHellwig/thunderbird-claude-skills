# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-03

### Added

- `tb.py`: read-only CLI for local Thunderbird mail (`profiles`, `identities`, `folders`, `list`, `search`, `show`, `thread`, `sent-to`), with mbox and maildir support, the optional global search index, and JSON output.
- Runtime read-only guard via Python audit hooks, plus a first-run privacy notice that needs explicit acknowledgement.
- Local model detection: the privacy notice and `tb.py local-llm` find a local Ollama install and its local models by reading the disk only, and print the command to start Claude Code with one of them.
- Skills: `thunderbird-mail`, `draft-reply`, `draft-email`, `inbox-digest`.
- Plugin hook `guard.py` that blocks profile modifications, mail sending and Thunderbird automation.
- Claude Code plugin and marketplace manifests.
- CI on Linux, macOS and Windows with Python 3.8 and the latest release.

[Unreleased]: https://github.com/NilsHellwig/thunderbird-claude-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/NilsHellwig/thunderbird-claude-skills/releases/tag/v0.1.0
