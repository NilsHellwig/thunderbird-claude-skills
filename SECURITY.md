# Security Policy

This project promises that an agent using it **cannot modify, delete or send mail**, and that it **never accesses the network**. Anything that breaks that promise is a security issue, for example:

- a way for `tb.py` to write to, lock, or corrupt files in a Thunderbird profile
- a command that gets past `hooks/guard.py` and modifies a profile or sends mail
- a network connection made by any code in this repository
- an email whose content makes the skills leak data or take actions (prompt injection) in a way the skill instructions should prevent

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please report privately via **[GitHub Security Advisories](https://github.com/NilsHellwig/thunderbird-claude-skills/security/advisories/new)**. Do not open a public issue.

Include:
- what you did (commands, tool calls, or a crafted test email)
- what happened and what you expected
- your OS, Python version and Thunderbird version

You can expect a first response within 7 days. Once a fix is released, you will be credited in the advisory unless you prefer otherwise.

## Scope notes

- The guard hook is a best-effort filter for shell commands, not a sandbox. Bypasses are still welcome reports.
- What your model provider does with mail content you send it is outside the scope of this project. See the privacy section in the README.
