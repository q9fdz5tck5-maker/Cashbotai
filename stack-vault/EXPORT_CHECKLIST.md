# Stack Vault — Export Checklist v1.0

Grab these files first; the AI does the data entry. You don't need all of them — every file you attach fills more of the vault, and the AI's Gap Report will tell you what was worth adding. Screenshots are fine anywhere a proper export doesn't exist.

**Name every file** `EXPORT_<platform>_<what>` (e.g. `EXPORT_cj_payouts.csv`, `EXPORT_ga4_traffic.pdf`). The names help the AI route the data.

**Before attaching anything, skim it.** Delete or black out any column containing passwords, API keys, tokens, full card/bank numbers, or customer personal data. The AI is instructed to redact secrets it finds — but the best secret is one that never leaves your machine.

| # | Source | Where to get it | Save as |
|---|--------|-----------------|---------|
| 1 | Affiliate networks (CJ, Impact, PartnerStack, in-house portals) | Each portal → Reports → earnings/payout report, plus your links list | `EXPORT_<network>_payouts.csv` |
| 2 | Email platform (Mailchimp, Klaviyo, ConvertKit…) | Audience/Subscribers page screenshot (shows list size) + list of automations | `EXPORT_<tool>_audience.png` |
| 3 | SMS platform | Contacts count screenshot | `EXPORT_<tool>_sms.png` |
| 4 | Analytics (GA4, Plausible) | Reports → Acquisition → last 90 days → export PDF/CSV | `EXPORT_ga4_traffic.pdf` |
| 5 | Ad platforms (Meta, Google, TikTok) | Ads manager → last 90 days spend report | `EXPORT_<platform>_adspend.csv` |
| 6 | Payments (Stripe, PayPal, Whop) | Payouts/balance report, last 90 days | `EXPORT_<platform>_payouts.csv` |
| 7 | Bank / credit card | Statement filtered to recurring charges — **black out account numbers** | `EXPORT_bank_recurring.pdf` |
| 8 | Phone subscriptions | iPhone: Settings → [your name] → Subscriptions → screenshot. Android: Play Store → Payments & subscriptions | `EXPORT_appstore_subs.png` |
| 9 | Browser bookmarks | Browser → Bookmarks manager → Export bookmarks (HTML) — an instant list of every tool you log into | `EXPORT_bookmarks.html` |
| 10 | Domains | Registrar → domain list with renewal dates screenshot | `EXPORT_domains.png` |
| 11 | CRM | Contacts count + tags/segments screenshot | `EXPORT_crm.png` |
| 12 | Communities (Facebook group, Whop, Discord, IG) | Member-count screenshots + the invite links | `EXPORT_communities.png` |
| 13 | Password manager | **Nothing.** Do not export it. You'll type entry *names* into the vault later if asked. |  |

Then: open a fresh AI chat, attach everything, paste the Master Prompt (`MASTER_PROMPT.md`, printed in the intake packet too), send. Save the JSON it returns as `stack-vault.json`.
