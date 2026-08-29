# Jito Sniper — VPS Startup Runbook

How to get the sniper running on the VPS, from a cold start.

## Prerequisites (one-time setup)

1. **Node.js 18+** installed (`node --version` to check).
2. **Wallet key file**: `.solana-trading-key` must sit next to `jito-sniper.js`.
   Format: JSON with a base64 `secretKey` field (same file the jupiter-trader uses).
   Never commit this file — it is gitignored.
3. **Helius API key** (optional but strongly recommended — public RPC websockets
   are slow and rate-limited): set `HELIUS_READ_KEY` in the environment.
4. Install dependencies once:
   ```
   cd <folder with jito-sniper.js>
   npm install
   ```

## Start it (paper mode first — always)

Paper mode detects pools and builds transactions but submits nothing:

```
PAPER_MODE=1 HELIUS_READ_KEY=your-key-here node jito-sniper.js
```

Let it run a few minutes. You want to see:
- `Wallet loaded: ...`
- `WebSocket subscription active — listening for new pools`
- `POOL DETECTED` lines, followed by `PAPER  Would snipe ...`

If pool detections show up and TXs build without errors, the pipeline works.

## Start it live

```
HELIUS_READ_KEY=your-key-here node jito-sniper.js
```

The wallet needs enough SOL for: spend (0.001/snipe) + Jito tip (0.000075/snipe)
+ ATA rent (~0.002 per new token) + fees.

Start the scalper (port 5555) first if you want automatic position handoff;
otherwise sniped positions log `scalper unreachable` and need manual entry.

## Keep it running after you disconnect

Use pm2 so it survives closing Remote Desktop and reboots:

```
npm install -g pm2
HELIUS_READ_KEY=your-key-here pm2 start jito-sniper.js --name sniper --time
pm2 save
pm2 startup   # follow the printed instructions once
```

Check on it: `pm2 logs sniper` / `pm2 status`. Stop it: `pm2 stop sniper`.

On Windows (no pm2 startup support), use `pm2-installer` or run it inside a
scheduled task; or simply keep a terminal open with the plain `node` command.

## Troubleshooting

- `ERROR: No wallet` — `.solana-trading-key` missing or malformed in this folder.
- No `POOL DETECTED` lines for 10+ minutes — websocket endpoint is throttling;
  set `HELIUS_READ_KEY`.
- `429` / rate-limit errors — same fix: use the Helius key, public RPCs throttle.
- Snipes land but swap fails on-chain — check the wallet's WSOL account and SOL
  balance; the TX wraps the spend amount automatically each snipe.
