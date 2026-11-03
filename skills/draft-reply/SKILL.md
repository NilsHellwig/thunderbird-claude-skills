---
name: draft-reply
description: Draft a reply to an email in the user's local Thunderbird, matching how they usually write to that person. Use when the user wants to answer, respond to, or reply to a mail.
---

# draft-reply

You write a reply the user copies into Thunderbird and sends themselves. Read [`../thunderbird-mail/SKILL.md`](../thunderbird-mail/SKILL.md) first: its guardrails, its `TB` commands and its draft format all apply here.

## Steps

1. **Find the email.** Search for the message the user means. Confirm it in one line (sender, date, subject). Done when exactly one message is identified.
2. **Read the conversation.** Run `TB thread "<ref>"` so you know everything already said, by both sides. Done when you can state the open question or request the reply must answer.
3. **Learn the user's voice.** Run `TB sent-to <sender address> --limit 5`. If that returns nothing, fall back to `TB sent-to --limit 5`. Note what they actually do:
   - formal or informal address (e.g. *Du*/*Sie*, *tu*/*vous*, first name or surname)
   - greeting, sign-off and name they sign with
   - typical length, tone and formatting
   
   Done when you can name each of these from real examples, not guesses.
4. **Settle the content.** If the user's intent is clear (accept, decline, propose a time…), go ahead. If a decision only they can make is missing (a date, a price, yes or no), ask for it in one short question before drafting.
5. **Write the reply.**
   - Use the language of the incoming email, unless the user asks otherwise.
   - Answer every open point from step 2.
   - Write in the voice from step 3.
   - Leave out the quoted original: Thunderbird adds it when the user clicks *Reply*.
6. **Deliver it** in the draft format:
   - **To**: the original sender, plus anyone else from the thread the user wants to keep.
   - **Cc**: only when it applies.
   - **Subject**: `Re: <original subject>`, without stacking `Re: Re:`.
   - **Body**.
   
   Below the blocks, add one line naming the message to reply to (sender and date), so the user opens the right one in Thunderbird. Then ask if they want changes.
