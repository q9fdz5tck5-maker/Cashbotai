# Selling XENOSNIPE — Two-Tier Playbook

Strategy for selling the XENOSNIPE Solana market-intelligence agent in two forms:
**(A)** the codebase alone, or **(B)** a turnkey managed server with an SEO-ready
site, Claude Code installed locally on the VPS to administer it, and the
read-only phone bridge.

---

## 1. What you are actually selling

Not returns. Not a money printer. You are selling **infrastructure and
discipline**:

- A live Solana mainnet terminal (MARKETS / SCANNER / PAPER / BOT) with
  multi-timeframe charting, entry bands, targets/stops, and confidence-gated
  signals that are willing to say **WAIT**.
- A memecoin scanner that quotes **real round-trip cost per token at your
  actual position size** (memecoins measured at 0.73–1.78% per leg vs 0.0089%
  on SOL/USDC) and surfaces rug-check fields: `mintAuthority`,
  `freezeAuthority`, pool liquidity, organic score, Token-2022 flag.
- A hardened safety architecture: control port (4173) never tunneled, only the
  read-only port (4174) exposed to the phone; no real order without explicit
  in-conversation approval; sells that would breach `FEE_RESERVE_SOL` are
  refused; paper trader never touches the wallet.
- An **AI-native build system**: the `PROMPT-TRADING.md` spec means the buyer's
  own Claude can maintain, audit, and extend the bot. The codebase ships with
  its own engineering brief.
- Radical honesty baked into the UI: the backtest panel shows its own hit rate
  and PnL *with a disclaimer telling you when the sample is too small to
  trust*.

## 2. The positioning angle

Every sniper bot on Telegram promises 100x and hides its numbers. Yours
displays **33% hit rate, −3.94% cumulative** on a small sample and tells the
user not to trust it yet. That is the pitch, not the flaw:

> **"The only Solana sniper that tells you when NOT to trade."**

Supporting lines to reuse anywhere:

- "It shows you the real cost of the trade before you take it — most memecoin
  round trips are 1.5–3.5% before gas. This bot puts that number in the token
  picker."
- "Read-only on your phone by design. The port that can place orders is never
  exposed to the internet."
- "It refuses orders. On purpose. Wallet locked → clean refusal. Fee reserve
  breach → refusal. No in-chat approval → refusal."
- "Built and documented by Claude, for Claude — buy it and your own Claude can
  keep building it."

## 3. Offer structure

### Tier A — Codebase license (one-time)

**What they get:** full source, `PROMPT-TRADING.md` build spec, setup guide,
paper-trading mode, scanner, signal engine, tunnel configs.

- Non-exclusive license: **$297–$497** (recommend **$450**).
- Exclusive buyout (you stop selling it): **$2,500–$5,000**.
- Position the spec file as a feature: "the repo ships with the prompt that
  built it — point Claude Code at it and extend the bot yourself."

### Tier B — Turnkey managed server (setup + monthly)

**What they get:**

1. VPS provisioned and hardened (firewall, fail2ban, the 4173/4174 split
   enforced — control port bound to localhost only).
2. Domain + SEO-ready landing/status site on the VPS (fast static page, proper
   meta/OG tags, indexed — their bot has a home, not a random tunnel URL).
3. **Claude Code installed on the server under the buyer's own Anthropic
   account** — it can administer the box, read logs, restart services, and
   extend the bot using the shipped spec. (You cannot resell your own Claude
   access; the buyer signs in with theirs. Sell the *installation and
   configuration*, not the subscription.)
4. Phone bridge: stable tunnel (or subdomain) to the read-only 4174 UI, so the
   dashboard in their pocket looks exactly like your screenshot.
5. Wallet stays theirs. You never hold keys. Document this loudly — it is a
   selling point and it protects you.

- Setup fee: **$997–$1,497** (recommend **$1,250**).
- Managed hosting/maintenance: **$99–$199/mo** (recommend **$149/mo**; VPS
  cost is theirs or baked in).
- Add-ons: custom strategy prompt tuning ($250/strategy), white-label rename
  ($500).

### Why two tiers works

Tier A anchors Tier B. The codebase buyer self-selects as technical; the
server buyer is paying to skip DevOps. Most objections to A ("I can't set this
up") are the pitch for B.

## 4. Ready-to-use post copy

**Marketplace / listing blurb:**

> XENOSNIPE — Solana mainnet trading terminal with a conscience. Live charts,
> confidence-gated signals that say WAIT, a memecoin scanner that shows the
> real round-trip cost of every token before you buy, rug-check fields
> (mint/freeze authority, Token-2022), paper trading, and a hardened
> phone-viewable dashboard where the order-placing port is never exposed to
> the internet. Ships with the full AI build spec so Claude Code can maintain
> and extend it for you. Sold as software — no profit claims, your wallet,
> your keys.

**X/Twitter thread opener:**

> I built a Solana sniper that refuses to trade.
>
> Wallet locked? Refuses. Fee reserve at risk? Refuses. No explicit approval
> in chat? Refuses. Signal confidence 50/100? It says WAIT and shows you why.
>
> Now selling it two ways: code only, or a managed server with Claude running
> on the box. 🧵

**Reddit-style long post:** lead with the honest backtest panel screenshot,
explain the cost-truth column ("most bots hide that a memecoin round trip is
3%; mine puts it in the dropdown"), end with the two offers and "DM for
either."

## 5. Objection handling

| Objection | Answer |
|---|---|
| "Does it make money?" | "It's an intelligence and execution layer, sold as software. It shows you its own live hit rate and refuses low-confidence trades. Nobody selling you guaranteed returns is telling the truth." |
| "Why is the backtest negative?" | "Because it's real and in-sample over a small window — and the UI says so. That honesty is the product. You get paper mode to build your own sample before risking anything." |
| "Do you hold my keys?" | "Never. Wallet stays on your box, control port never leaves localhost, and the phone view is read-only by architecture, not by promise." |
| "What about the Claude part?" | "You bring your own Anthropic account; I install and wire Claude Code into the server so it can administer the box and extend the bot from the shipped spec." |
| "Can I resell it?" | Non-exclusive license: personal use, no resale. Put it in a one-page license. |

## 6. Guardrails (do these or the offer bites you)

- **Zero profit claims, ever.** No "ROI", no "passive income", no screenshots
  of gains as marketing. Sell software + service. Performance claims around
  trading tools invite regulatory and refund trouble.
- Every listing carries: *"Software sold as-is for educational/technical use.
  Not financial advice. Trading cryptocurrencies risks total loss."*
- Buyer's own wallet, buyer's own Anthropic account, buyer's own exchange
  risk. You never custody anything.
- Use escrow or a platform with buyer/seller protection for codebase sales;
  deliver via private repo invite.
- For the managed tier, a simple service agreement: what "managed" covers
  (uptime, updates, tunnel), what it doesn't (trading outcomes).
- Keep the live demo read-only (4174) — exactly what the tunnel link already
  does. Never expose 4173.

## 7. Server-tier delivery checklist

1. Provision VPS (2 vCPU / 4GB is plenty), Ubuntu LTS, SSH keys only.
2. Firewall: 80/443 open, 4173 bound to 127.0.0.1, 4174 behind the tunnel or
   reverse proxy with auth.
3. Deploy bot + dashboard, systemd units, log rotation.
4. Domain, TLS, static landing page with proper meta tags (title,
   description, OG image of the dashboard) so the product page indexes.
5. Install Claude Code, buyer authenticates with their account; drop
   `CLAUDE.md` + `PROMPT-TRADING.md` in the repo root so their Claude has the
   full context.
6. Stable phone bridge (named tunnel or subdomain) to the read-only UI.
7. Handover doc: how to approve a live trade, how to lock the wallet, how to
   ask Claude on the box to update the bot.

---

*Note: written from the dashboard screenshot and the `PROMPT-TRADING.md` spec
visible in it; the trycloudflare link wasn't reachable from this environment
(egress-blocked), and the original post text wasn't available — splice your
post's voice into the copy blocks above.*
