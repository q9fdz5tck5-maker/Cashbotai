# Selling XENOSNIPE — Two-SKU Playbook

Two clean offers, both hands-off after delivery:

- **SKU 1 — Codebase, $297.** They get the code and the prompt that built it.
  They run it themselves and figure it out with their own Claude.
- **SKU 2 — AI server setup.** The real product is "your own server with
  Claude on it, reachable from your phone." Everyone wants one, almost nobody
  can set one up, you can. XENOSNIPE is the demo proving the setup works
  end-to-end.

You are not selling trading help, profit, or ongoing hand-holding. You sell
software and setup, hand over the keys, and walk away.

---

## 1. What you are actually selling

- A live Solana mainnet terminal (MARKETS / SCANNER / PAPER / BOT):
  multi-timeframe charts, entry bands, targets/stops, confidence-gated
  signals that are willing to say **WAIT**.
- A memecoin scanner that quotes **real round-trip cost per token at actual
  position size** (memecoins measured at 0.73–1.78% per leg vs 0.0089% on
  SOL/USDC) plus rug-check fields: `mintAuthority`, `freezeAuthority`, pool
  liquidity, organic score, Token-2022 flag.
- Hardened safety architecture: control port (4173) never tunneled, only the
  read-only port (4174) exposed to the phone; no real order without explicit
  in-conversation approval; fee-reserve-breaching sells refused; paper trader
  never touches the wallet.
- **The build spec** (`PROMPT-TRADING.md`): the engineering brief Claude built
  it from. This is what makes "$297, figure it out with Claude" a real offer
  instead of a code dump — their Claude reads the spec and knows the system.
- Honest UI: the backtest panel shows its own hit rate and PnL with a
  disclaimer about small samples.

## 2. What you are NOT selling (say it out loud)

- Not trading advice. Not signals-as-a-service. Not profit, returns, or ROI.
- Not strategy tuning, not "help me win," not ongoing support.
- Not custody: their wallet, their keys, their Anthropic account, their VPS
  bill.

This boundary is both your legal protection and your positioning. The honest
backtest panel (33% hit rate, −3.94%, "don't trust small samples") is proof
you're not selling a dream — lead with it.

## 3. SKU 1 — Codebase, $297 one-time

**The pitch:** "$297. You get the full source and the prompt spec that built
it. Point Claude Code at the repo and figure it out. If you can't, this isn't
for you."

- The price filters for self-sufficient buyers, so no support debt.
- Non-exclusive license, personal use, no resale — one page, stated in the
  listing.
- Deliver via private repo invite after payment (escrow or a platform with
  buyer protection).
- Optional upsell for the stuck: one paid setup call, $100. Not included, not
  advertised heavily — it exists so "I can't get it running" has an answer
  that isn't a refund.

## 4. SKU 2 — AI server setup

**The pitch is bigger than the bot:** "Your own server with Claude living on
it. It runs your apps, watches its own logs, fixes itself when you tell it
to, and you talk to it from your phone. I set the whole thing up; here's mine
running a live Solana trading terminal to prove it."

XENOSNIPE is the demo, not the product. That widens the market from "people
who want a trading bot" to "anyone who's heard they should have their own AI
server and has no idea how" — which is most people.

**What's in the box (one-time setup, then it's theirs):**

1. VPS provisioned and hardened: Ubuntu LTS, SSH keys only, firewall,
   fail2ban; any control ports bound to localhost.
2. Claude Code installed **under the buyer's own Anthropic account** — you
   can't resell your subscription; you sell the installation and wiring.
   `CLAUDE.md` at the root so their Claude knows the box.
3. Phone bridge: stable tunnel or subdomain to a read-only dashboard —
   the "server in your pocket" moment that closes the sale.
4. Domain + clean landing/status page with proper meta tags, so the server
   has a home instead of a random tunnel URL.
5. XENOSNIPE deployed as the showcase app (or their app, if they have one).
6. Handover doc: how to SSH in, how to talk to Claude on the box, how to
   restart things, where the logs live. Then you're done.

**Pricing:** $750–$1,000 one-time setup (recommend **$850**; VPS and
Anthropic bills are theirs). Optional $99/mo maintenance only if *they* ask —
the default is a clean handover with no ongoing obligation, which is exactly
the "I'm not babysitting anyone" posture.

**Why two SKUs works:** $297 anchors the setup fee. Every "I can't set this
up myself" objection to SKU 1 is the pitch for SKU 2 — and SKU 2 buyers
don't even need to care about trading.

## 5. Ready-to-use post copy

**SKU 1 listing:**

> XENOSNIPE — Solana mainnet trading terminal. Live charts, confidence-gated
> signals that say WAIT, a scanner that shows the real round-trip cost of
> every token before you buy, rug-check fields, paper trading, hardened
> read-only phone dashboard. $297 gets you the full source plus the AI build
> spec — point Claude Code at the repo and it knows the whole system. You run
> it, you own it. Sold as-is as software: no profit claims, no support, your
> wallet, your keys.

**SKU 2 post:**

> Everyone wants their own server with AI on it. Almost nobody can set one
> up.
>
> I put Claude on a VPS: it deploys apps, reads its own logs, fixes what you
> tell it to fix, and you talk to it from your phone. Mine runs a live Solana
> trading terminal 24/7 — screenshot below is my phone.
>
> I'll build you one. Flat fee, your accounts, your keys, then it's yours.

**X thread opener (either SKU):**

> I built a Solana sniper that refuses to trade.
>
> Wallet locked? Refuses. Fee reserve at risk? Refuses. No explicit approval?
> Refuses. Confidence 50/100? It says WAIT and shows you why.
>
> Selling the code for $297 — comes with the prompt that built it, so your
> Claude can run it. Or I'll set up the whole server for you. 🧵

## 6. Objection handling

| Objection | Answer |
|---|---|
| "Does it make money?" | "I'm not selling returns and won't pretend to. It's software — it even shows you its own hit rate on screen. You get paper mode to test before risking anything." |
| "Why is the backtest negative?" | "Because it's real, in-sample, and small — and the UI says so. That honesty is the product." |
| "Will you help me set it up?" (SKU 1) | "That's the $297 deal: you and your Claude figure it out — the build spec is included so Claude knows the system. If you want it done for you, that's the server setup." |
| "Do you hold my keys / accounts?" | "Never. Your wallet, your Anthropic login, your VPS. I set it up, hand it over, and I'm out." |
| "What if it breaks later?" (SKU 2) | "The handover doc covers the basics, and Claude is on the box — ask it. Ongoing maintenance is available but optional." |

## 7. Guardrails

- **Zero profit claims, ever.** No ROI, no "passive income," no gain
  screenshots as marketing. You're already not helping them profit — make
  sure the marketing never implies otherwise.
- Every listing: *"Software sold as-is for educational/technical use. Not
  financial advice. Trading cryptocurrencies risks total loss."*
- SKU 1: escrow/platform protection, private repo invite, one-page license.
- SKU 2: one-page scope sheet — what setup includes, what it doesn't
  (trading outcomes, free lifetime support). Signed or acknowledged before
  payment.
- Buyer's own Anthropic account always — never share or resell yours.
- Demo stays read-only on 4174. **Never expose 4173.**

## 8. SKU 2 delivery checklist

1. VPS (2 vCPU / 4GB), Ubuntu LTS, SSH keys only.
2. Firewall: 80/443 open; control ports on 127.0.0.1; dashboard behind
   tunnel/reverse proxy.
3. Deploy the showcase app, systemd units, log rotation.
4. Domain, TLS, landing page with real meta/OG tags.
5. Claude Code installed, buyer authenticates; `CLAUDE.md` +
   `PROMPT-TRADING.md` in place.
6. Stable phone bridge to the read-only UI.
7. Handover doc; collect final payment; done.

---

*Written from the dashboard screenshot and the `PROMPT-TRADING.md` spec
visible in it; the trycloudflare link wasn't reachable from this environment
(egress-blocked). Splice your original post's voice into the copy blocks.*
