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

## 5. Decisions taken, and what they change

| question | decision | status |
| --- | --- | --- |
| Checkout | Stripe and PayPal are not available | Needs a merchant-of-record — see below |
| Price | Hold $297, add a done-for-you upsell | Needs a DFY price to wire in |
| Guarantee | 30-day full refund | **Shipped** — landing section + slide 37 narration |
| Deadline | No real deadline | **Correctly skipped** — no clock without something at the end of it |

### Checkout without Stripe or PayPal

The thing that unblocks this is a **merchant of record**. An MoR platform is
the legal seller of your product: it owns the transaction, collects and remits
tax, and absorbs fraud and compliance liability. Practically, that means **you
do not need your own Stripe or PayPal merchant account** — theirs is the
account being used.

Established options for a $297 digital product: **Paddle** (largest, software-
focused), **Lemon Squeezy** (creator/indie-focused, no monthly fee),
**FastSpring** (digital goods, 200+ regions), **2Checkout** (190+ countries),
**Freemius**, **Dodo Payments**.

Caveat worth stating plainly: an MoR still runs its own approval. If Stripe and
PayPal declined for a reason that follows you — a prohibited category, a
chargeback history — an MoR may decline too. If the reason was jurisdictional,
account-level, or simply not having a merchant account, an MoR solves it
outright.

CTAs in this tool are already plain links, so switching is a one-field change
per CTA once a URL exists. Nothing needs to be rebuilt.

### The done-for-you upsell — and why it should be priced HIGH

DFY does not scale like software; it is capacity-limited. That inverts the
usual pricing instinct. Assuming 12 hours to deliver one done-for-you webinar:

| DFY price | attach | AOV | buyers for $1M | visitors | DFY units | delivery hours |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| $997 | 12% | $417 | 2,401 | 400,026 | 289 | 3,457 |
| $997 | 8% | $377 | 2,655 | 442,369 | 213 | 2,549 |
| $1,997 | 8% | $457 | 2,190 | 364,889 | 176 | 2,102 |
| **$2,997** | **8%** | **$537** | **1,864** | **310,506** | **150** | **1,789** |
| $2,997 | 12% | $657 | 1,523 | 253,818 | 183 | 2,193 |

Compare row 1 and row 4. **$997 at a 12% attach is nearly double the delivery
work of $2,997 at 8%, for a smaller revenue contribution.** With a
capacity-limited offer, a higher price is strictly better on every axis that
matters — fewer clients, more revenue per client, less of your calendar sold.

3,457 hours is more than a full-time year of delivery. 1,789 is still a lot.
Price DFY high enough that the delivery load is survivable, or cap the number
of slots.

### The one place SMS is genuinely the right tool

This is the useful consequence of the checkout constraint.

- **$297 core:** ~3,368 text conversations. SMS is a ceiling here. Needs an MoR
  checkout.
- **$2,997 DFY:** ~150–220 conversations *a year* — three or four a week. High
  ticket sells better by conversation than by button anyway.

So the honest architecture is not "replace SMS." It is **automate the $297 and
keep SMS for the done-for-you**, where a human conversation is an asset rather
than a bottleneck.

## 6. The honest part

I can build the machine. I cannot promise the number.

$1M from this funnel needs roughly **half a million visitors at today's price
and offer**, or about **167,000 at $997**. Traffic at that scale is its own
discipline with its own budget, and no funnel copy substitutes for it. What the
work above does is make each visitor worth several times more, and remove a
manual step that currently makes the target unreachable regardless of traffic.

Replace the assumed 2% and 30% with your real numbers as soon as you have a
hundred registrants, and re-run the table. Everything here is downstream of
those two figures, and yours will not be mine.
