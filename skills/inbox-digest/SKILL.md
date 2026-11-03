---
name: inbox-digest
description: Summarize unread mail in the user's local Thunderbird inboxes and flag what needs action. Use when the user asks what's new, what they missed, or for an inbox overview or digest.
---

# inbox-digest

You give the user a digest of their unread mail: what arrived and what needs them. Read [`../thunderbird-mail/SKILL.md`](../thunderbird-mail/SKILL.md) first: its guardrails and `TB` commands apply here.

## Steps

1. **Collect.** Run `TB list --unread --since 7d --limit 0`.
   - The user can change the scope: another period (`--since`), one account (`--account`), one folder (`--folder`), or read mail too (drop `--unread`).
   - Messages without read status in Thunderbird appear as unread.
   
   Done when you have the full list for the scope.
2. **Read.** Run `TB show "<ref>"` for every message, except bulk mail (newsletters, notifications, receipts) that the headers already identify. For a long list, go through it in batches. Done when every non-bulk message has been read in full.
3. **Write the digest** in the user's language, grouped by account. List each message on one line:
   - sender, short date
   - a one-sentence gist
   - **Action** if they must reply, decide, pay, attend or deliver something, with the deadline if the mail states one
   
   Put action items first within each account. Collapse bulk mail into one line per account with a count (e.g. "4 newsletters, 2 shipping notifications").
4. **Offer next steps.** Offer to draft replies (via draft-reply) for the action items. Leave the mail itself as it is: marking as read, archiving and deleting are for the user to do in Thunderbird.
