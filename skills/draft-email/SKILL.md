---
name: draft-email
description: Draft a new email (not a reply) in the user's own style, using their local Thunderbird mail for context. Use when the user wants to write, compose, or send a new message to someone.
---

# draft-email

You write a new email the user copies into Thunderbird and sends themselves. Read [`../thunderbird-mail/SKILL.md`](../thunderbird-mail/SKILL.md) first: its guardrails, its `TB` commands and its draft format all apply here.

## Steps

1. **Pin down the recipient.** Resolve names to addresses from real mail: `TB search --from "<name>" --limit 5` or `TB search --to "<name>" --limit 5`. Done when every recipient has one confirmed address. If a name matches several people, ask which one.
2. **Gather context.** If the email builds on earlier conversations with this person (a project, an appointment, an open question), skim the recent ones with `TB search` and `TB show`, so the draft is consistent with what was already said.
3. **Learn the user's voice.** Run `TB sent-to <address> --limit 5`. If that returns nothing, fall back to `TB sent-to --limit 5`. Note what they actually do:
   - formal or informal address
   - greeting, sign-off and name they sign with
   - typical length and tone
   
   Done when you can name each of these from real examples.
4. **Settle the content.** If something only the user can decide is missing (dates, figures, what exactly to ask for), ask for it in one short question before drafting.
5. **Write the email.**
   - Use the language the user gave you the task in, unless they ask otherwise or the history with this recipient is clearly in another language. In that case, ask which one to use.
   - Write a subject that is specific enough to find later.
6. **Deliver it** in the draft format: **To**, **Cc** only when it applies, **Subject**, **Body**. Then ask if they want changes.
