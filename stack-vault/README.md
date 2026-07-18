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

The main path is **exports-first**: they don't type their data in, they download it and let an AI do the data entry.

1. **A — Export.** They work through [EXPORT_CHECKLIST.md](EXPORT_CHECKLIST.md): download reports and take screenshots from their affiliate portals, email tool, analytics, payments, bank, phone. 20–30 minutes; partial is fine.
2. **B — Build.** They open a **fresh chat** with any capable AI that accepts attachments (Claude recommended, default settings — the prompt works the same on any model because the rules and schema travel inside it), attach every export, and paste [MASTER_PROMPT.md](MASTER_PROMPT.md) verbatim.
3. **C — Save.** The AI returns an inventory of what it read, the structured vault as JSON, a gap report, and a money analysis. They save the JSON block as `stack-vault.json` — that's the deliverable they send back, and what they re-attach next time to update.
4. **Fallback — by hand.** No exports, or prefer typing? `cashbot-stack-vault.html` is the interactive form (autosaves, exports the same JSON), and the intake packet PDF has fillable pages plus the checklist and master prompt printed inside it.
5. **Re-import anytime.** The form's Import button loads any `stack-vault.json`, so the file is a living document, not a one-shot survey.

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
