# Public Brand & Presence Audit — Prompt

A reusable prompt for auditing the **public, intentionally-published** professional
footprint of a person or business. Built for lead enrichment, competitive research,
and auditing your own brand.

## Scope & ground rules (do not remove)

This audit uses **only information the subject has chosen to publish** — their website,
business listing, public social profiles, published contact details, press, and content.

**In scope:** public professional profiles, published contact info, business
registration that is public record, content themes, reach/engagement that platforms
display openly, press mentions, positioning.

**Out of scope — never collect or infer:** government IDs (SSN, license, passport),
non-public financial account details, home address / precise geolocation, physical
description, family members' details, "impersonation risk" tradecraft, or anything
behind a login, paywall, or privacy setting. If a data point isn't clearly published
by the subject for professional purposes, leave the field blank and note it as
`not public`. Never aggregate breadcrumbs to reconstruct something the subject
withheld. Cite a source URL for every filled field.

This scope is a feature, not a limitation — it keeps the output useful, shareable,
and safe to hand to a client.

---

## The prompt

> You are a brand-presence analyst. Produce a **public brand audit** of the subject
> below using only information they have intentionally published for professional
> purposes. For every field you fill, include the source URL and the date you saw it.
> If something is not publicly published, write `not public` — do not guess, and do not
> combine sources to reconstruct private details. Skip government IDs, financial
> accounts, home address, physical description, and family details entirely.
>
> **Subject:** `<name>` — `<company / handle / website>`
>
> Search these public surfaces (only those that apply):
> 1. **Owned web** — primary website, landing pages, about/bio pages, blog.
> 2. **Business record** — public company listing (state entity type, founding year if published), Google Business Profile.
> 3. **Content platforms** — YouTube, TikTok, Instagram, X, LinkedIn, Facebook, Threads, Twitch, podcast feeds. Capture handle, follower count as shown, posting cadence, and top content themes.
> 4. **Professional** — published title/role, speaking topics, published work, newsletter platform.
> 5. **Reputation** — press mentions, public reviews (Trustpilot/BBB/Google), notable collaborations.
> 6. **Published contact** — business email, business phone, booking link, as listed on their own site.
>
> Then produce:
> - A one-paragraph **positioning summary** (who they are, who they serve, what they're known for).
> - A **presence scorecard**: reach, consistency, professionalism, contactability (1–5 each, with the evidence behind each score).
> - **Content themes** — the 3–6 topics they publish about most.
> - **Gaps & opportunities** — where their public presence is thin or inconsistent.
> - A **sources table** — every URL used, with the date.
>
> Output as structured data that maps to `report_template.html` (see field ids below).

---

## Field ids (map output → HTML template)

| id | meaning |
|----|---------|
| `subject.name` | display name |
| `subject.entity` | company / brand |
| `subject.tagline` | one-line positioning |
| `subject.verified` | date audit was run |
| `stats.reach` | total public following (summed, as displayed) |
| `stats.platforms` | count of active public platforms |
| `stats.cadence` | typical posting frequency |
| `stats.contactability` | published contact channels count |
| `positioning` | positioning paragraph |
| `channels[]` | {platform, handle, url, followers, cadence, note} |
| `themes[]` | {theme, note} |
| `scorecard[]` | {metric, score_1_5, evidence} |
| `contact[]` | {type, value, source_url} — published business contact only |
| `gaps[]` | {observation, opportunity} |
| `sources[]` | {url, what, seen_date} |

---

## Why the prompt is written this way (portability note)

The scope block isn't boilerplate to strip out on the next run — it's what keeps the
task legitimate and the output shareable. A prompt only "works" once it silences
safety checks is a prompt pointed at the wrong target. Keep the guardrails in; swap
only the `<name>` / `<company>` line between runs.
