# CASH.BOT Stack Vault

One place for everything about your business and every tool / affiliate program in your stack — structured so a human can fill it in without thinking, and an AI can read it without guessing.

This replaces the emoji-divider text document. Same information, three problems fixed:

1. **Copy-paste drift.** In the old doc, Whop's block said `business: Name.com` and carried Pictory's login URL, because every record was a hand-copied checklist. Here there is exactly one template, and records are generated from it.
2. **Secrets in plaintext.** The old doc had a live API key sitting in it. The Vault stores **references** to secrets (the name of the entry in your password manager), never the secret itself. See [Security rules](#security-rules).
3. **Not machine-readable.** ✅/❌/🌊 markers mean nothing to a parser. The Vault's canonical format is JSON with a fixed field dictionary ([SCHEMA.md](SCHEMA.md)), and every export is valid input for an AI prompt.

## What's in here

| Path | What it is |
|---|---|
| `intake/cashbot-stack-vault.html` | **The thing you send people.** A self-contained intake form — works offline, saves as you type, exports JSON + AI-ready Markdown. No server, no account, nothing leaves their machine. |
| `SCHEMA.md` | The field dictionary. Every field, what it means, what goes in it. |
| `templates/business-profile.md` | Blank business profile (markdown, for people who insist on text). |
| `templates/tool-record.md` | Blank per-tool/affiliate record (markdown). |
| `data/cashbot-example.json` | Your own data, converted into the new structure — the worked example you show recipients. |

## The process you hand to people

1. **Send them the form.** Email `cashbot-stack-vault.html` or send the link. They open it in any browser. It autosaves locally, so they can do it over days.
2. **They fill in the Business Profile** — identity, brand, audience, traffic, money, stack, KPIs. Every field has a hint saying where to find the answer.
3. **They add one Tool Record per app/affiliate program** — pick a category, fill what they know, skip what they don't. Blank fields are fine; the export marks them `MISSING` so the gaps are data too.
4. **They export** — one click gives them `stack-vault.json` (send it back to you / keep as their source of truth) and one click copies **AI-ready Markdown** to paste straight into Claude/ChatGPT with any of the starter prompts below.
5. **You (or they) re-import anytime.** The form's Import button loads a previous JSON, so the file is a living document, not a one-shot survey.

## Starter prompts (paste after the exported Markdown)

- *"Rank every tool in this stack by (pending payout + payout %) vs. % learned. Tell me the 5 affiliate programs I'm leaving the most money on and the first action for each."*
- *"List every record with MISSING affiliate fields and generate the exact steps to apply for each program, using the application page URLs."*
- *"Based on my business profile and this stack, write my next 7 days of content, one tool per day, using my affiliate link for each."*
- *"Which tools are marked not-relevant or rated under 5? Draft the cancel/downgrade checklist and estimate monthly savings."*

## Security rules

- **Never** put passwords, API keys, or 2FA seeds in the Vault — not in the form, not in the JSON, not in the markdown. The `credential_ref` / `api.key_ref` fields hold the *name of the entry in your password manager* (1Password, Bitwarden, iCloud Keychain), nothing more.
- The old document contained a live Name.com API key. **Rotate it** (Name.com → Account → Settings → API) — treat it as burned.
- The exported JSON still contains business-sensitive data (revenue, contacts, pending payouts). Share it like a bank statement, not like a flyer.

## Categories

Domain Registrars · Hosting & Infrastructure · Social & Community Platforms · AI Video · AI Writing & Prompting · AI Audio & Voice · Design & Creative · Email & SMS Marketing · CRM & Sales · Automation & Integrations · Analytics & SEO · Payments & Finance · Marketplaces & E-commerce · Education & Courses · Other

Categories are a field on each record, not sections of a document — that's what lets this scale to hundreds of tools without dividers to maintain.
