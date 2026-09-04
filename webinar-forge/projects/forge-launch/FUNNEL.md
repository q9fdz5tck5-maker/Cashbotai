# What $1,000,000 actually requires from this funnel

The script is now good. The script is not what is capping this. This document
is the arithmetic, because the arithmetic changes what is worth working on
next — and it points somewhere other than the copy.

Everything below uses **illustrative industry-typical conversion rates, not
measured ones.** Nothing has been sold through this funnel yet, so there is no
real data. Treat the shape of the conclusion as reliable and the exact figures
as placeholders to replace with your own numbers the moment you have them.

Assumed throughout: **2% of registrants buy** and **30% of visitors register**.
For an automated $297 webinar those are reasonable-to-good, not pessimistic.

---

## 1. The headline number

$1,000,000 ÷ $297 = **3,368 sales.**

| scenario | AOV | customers | registrants | visitors |
| --- | ---: | ---: | ---: | ---: |
| **Today: $297, nothing else** | $297 | 3,368 | 168,351 | **561,168** |
| + $97 order bump @ 35% | $331 | 3,022 | 151,081 | 503,601 |
| + $997 upsell @ 15% | $481 | 2,082 | 104,059 | 346,861 |
| + $2,000 high-ticket @ 3% | $541 | 1,851 | 92,507 | 308,357 |
| **Reprice core to $997** | $997 | 1,004 | 50,151 | **167,169** |
| $997 core + full ladder | $1,366 | 733 | 36,617 | 122,056 |

Read the first and fifth rows against each other. Same webinar, same page, same
traffic engine — and **repricing alone removes 70% of the traffic you need.**

No amount of copy work moves a number like that. This is the single most
important fact in the document.

## 2. The three structural caps

### Cap 1 — "Text To Buy" is a throughput ceiling, not a conversion problem

Every sale currently requires a human text conversation. That is not a leaky
funnel; it is a funnel with a person standing in the middle of it.

| texters who buy | conversations/day | conversations needed | days of solid texting |
| ---: | ---: | ---: | ---: |
| 70% | 20 | 4,811 | 241 |
| 70% | 50 | 4,811 | 97 |
| 50% | 20 | 6,735 | 337 |
| 30% | 20 | 11,224 | 562 |

At 20 conversations a day, $1M is **roughly a year of doing nothing but
answering texts** — no traffic work, no product work, no support. The goal is
not hard through this door; it is arithmetically closed.

It is also worth being clear about *where* the loss happens. The buyer decides
at the moment the video ends. Texting inserts compose → send → **wait for a
human** → receive link → pay. The wait is the killer, because intent decays in
minutes and your reply may take hours.

**This is the highest-leverage fix available and it is not a copy change.** It
is one line: point the CTA `href` at a real checkout URL. The tool already
supports it — CTAs are plain links, by design, so they can point anywhere.

Keeping SMS is entirely compatible with fixing this: make instant checkout the
primary button and keep "or text (805) 453-3586" as the secondary path for
people who genuinely want to talk first. You lose nothing and unblock the
ceiling.

### Cap 2 — one price point, no ladder

There is one product at one price and nothing after it. Every framework that
reliably clears seven figures does so on **average order value**, not on
conversion rate, because AOV is the only term you can multiply without buying
more traffic.

Concretely, from the table above: a bump alone is nearly worthless here (+10%),
because $97 at a 35% take rate adds $34 to a $297 order. The **upsell** is
where the money is (−38% traffic), and **repricing** beats everything (−70%).

### Cap 3 — no follow-up

Opt-ins land in `registrations.jsonl` and stop there. The tool does not send
email, and says so honestly. But in webinar funnels a large share of sales
happen *after* the event — in the replay push, the deadline reminders, the
objection-handling sequence. Right now every registrant who does not buy on the
first watch is simply lost.

This does not need the tool to grow an email sender. It needs the JSONL piped
into whatever you already send with.

## 3. What is worth doing, in order

| # | move | effect | who decides |
| --- | --- | --- | --- |
| 1 | Real checkout URL on the CTAs, SMS kept as secondary | Removes the throughput ceiling entirely | You — I need the URL |
| 2 | Revisit the $297 price | Up to −70% traffic for the same $1M | You — business call |
| 3 | Add an upsell after purchase | −38% traffic | You — product does not exist yet |
| 4 | Risk reversal (guarantee) | Standard, large, well-documented lift | You — terms must be real |
| 5 | Follow-up sequence off the JSONL | Recovers non-first-watch buyers | You — needs your sender |
| 6 | Honest deadline | Compresses decision time | You — must be a real date |
| 7 | Further copy tuning | Marginal next to 1–6 | Me, any time |

Note where item 7 sits. The webinar is not the bottleneck any more.

## 4. What is already built for this

Shipped and tested, inert until you supply the content:

- **`guarantee` landing section** — badge, headline, body, terms. It has no
  default policy on purpose: it renders only terms you write and intend to
  honour.
- **`deadline` landing section** — counts down to one real ISO timestamp and
  shows an expiry message when it passes. There is deliberately **no evergreen
  mode**. A clock that resets per visitor asserts something false about
  availability; that is a lie to buyers and it is what gets pages reported.
- **Compliance filter fixed** — it previously turned "a 30-day money-back
  guarantee" into "a 30-day 30-day satisfaction policy" and "an iron-clad
  guarantee" into "an satisfaction policy". Any guarantee you add would have
  been *spoken* as broken English. That is repaired.

## 5. The honest part

I can build the machine. I cannot promise the number.

$1M from this funnel needs roughly **half a million visitors at today's price
and offer**, or about **167,000 at $997**. Traffic at that scale is its own
discipline with its own budget, and no funnel copy substitutes for it. What the
work above does is make each visitor worth several times more, and remove a
manual step that currently makes the target unreachable regardless of traffic.

Replace the assumed 2% and 30% with your real numbers as soon as you have a
hundred registrants, and re-run the table. Everything here is downstream of
those two figures, and yours will not be mine.
