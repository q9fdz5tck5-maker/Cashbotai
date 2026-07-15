# Public Brand Audit — copy-paste prompt

Copy the block below, swap the one `SUBJECT` line, and paste it into a fresh AI
session **with web browsing enabled**. The output JSON maps 1:1 onto
`report_template.html`; feed it to `build_audit_html.py` to get the finished report.

```text
You are a brand-presence analyst. Produce a PUBLIC BRAND AUDIT of the subject
below, using ONLY information they have intentionally published for professional
purposes.

SUBJECT: <name> — <company / website / handle>

RULES
- For every field you fill, include the source URL and the date you viewed it.
- If something is not publicly published, write "not public". Do not guess, and do
  not combine multiple sources to reconstruct anything the subject withheld.
- Do NOT collect: government IDs, financial account details, home address or precise
  location, physical description, or family members' details. Business contact info
  the subject lists on their own site is fine.

SEARCH THESE PUBLIC SURFACES (only those that apply)
1. Owned web — primary website, about/bio pages, blog, landing pages.
2. Business record — public company listing (entity type, founding year if published),
   Google Business Profile.
3. Content platforms — YouTube, TikTok, Instagram, X, LinkedIn, Facebook, Threads,
   Twitch, podcasts. Capture handle, follower count as displayed, posting cadence,
   and top content themes.
4. Professional — published title/role, speaking topics, published work, newsletter.
5. Reputation — press mentions, public reviews (Trustpilot / BBB / Google),
   notable collaborations.
6. Published contact — business email, phone, or booking link listed on their own site.

THEN PRODUCE
- Positioning: one paragraph — who they are, who they serve, what they're known for.
- Presence scorecard: reach, consistency, professionalism, contactability — score each
  1–5, with the evidence behind the score.
- Content themes: the 3–6 topics they publish about most.
- Gaps & opportunities: where the public presence is thin or inconsistent, and the
  concrete move that fixes each.
- Sources table: every URL used, what it provided, and the date.

OUTPUT FORMAT
Return a JSON object with these keys so it maps to the report template:
subject{name, entity, tagline, verified},
stats{reach, platforms, cadence, contactability},
positioning,
channels[]{platform, handle, url, followers, cadence, note},
themes[]{theme, note},
scorecard[]{metric, score_1_5, evidence},
contact[]{type, value, source_url},
gaps[]{observation, opportunity},
sources[]{url, what, seen_date}
```

## Workflow

1. **Edit one line.** Replace `<name> — <company / website / handle>` with your
   target. Keep the RULES block intact — it's what keeps the output clean and
   shareable.
2. **Use a browsing-capable model.** Without live web access it will invent sources.
3. **Save the JSON** it returns to a file, e.g. `audit.json`.
4. **Build the report:**

   ```bash
   python brand_audit/build_audit_html.py audit.json -o brand_audit_report.html
   ```

5. **Re-run anytime.** Same prompt, new SUBJECT line.

See `sample_audit.json` for a filled-in (fictional) example of the expected JSON.
