#!/usr/bin/env node

// ─── JITO BUNDLE SNIPER — Block-0 Entry ───
// Detects new Raydium pools at `processed` commitment (~0.4s)
// Builds raw swapBaseIn instruction locally (~30ms vs 800ms Jupiter)
// Submits via Jito bundle API for guaranteed block ordering
// Penny-sized buys (0.001-0.005 SOL) to minimize risk
// Hands confirmed positions off to scalper v17 for exit management

const { Connection, Keypair, PublicKey, Transaction, TransactionInstruction, SystemProgram, LAMPORTS_PER_SOL } = require('@solana/web3.js');
const { TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID, createAssociatedTokenAccountIdempotentInstruction, createSyncNativeInstruction, getAssociatedTokenAddressSync } = require('@solana/spl-token');
const BufferLayout = require('@solana/buffer-layout');
const http = require('http');
const fs = require('fs');
const path = require('path');
const bs58 = require('bs58');

// ─── Config ───
const CONFIG = {
  enabled: true,
  maxSpendSol: 0.005,
  defaultSpendLamports: 1_000_000,  // 0.001 SOL
  jitoTipLamports: 75_000,          // v24: higher tip for better block inclusion (was 50K)
  commitment: 'processed',
  maxSlippageBps: 5000,
  cooldownMs: 500,                   // v24: fire 4x faster between snipes (was 2000ms)
  blacklistFile: path.join(__dirname, '.mint-blacklist.json'),
  paperMode: process.env.PAPER_MODE === '1',  // log-only for testing (PAPER_MODE=1)
  scalperUrl: 'http://localhost:5555/api/sniper-position',
};

// Raydium AMM v4 program
const RAYDIUM_AMM_V4 = new PublicKey('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8');
const RAYDIUM_AUTHORITY = new PublicKey('5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1');
const SERUM_PROGRAM = new PublicKey('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX'); // OpenBook v1
const SOL_MINT = new PublicKey('So11111111111111111111111111111111111111112');

// Jito tip accounts (randomly selected per bundle)
const JITO_TIP_ACCOUNTS = [
  '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5',
  'HFqU5x63VTqvQss8hp11i4bPuZiGNqEDWBCRai68pmka',
  'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY',
  'ADaUMid9yfUytqMBgopwjb2DTLSLg21rmTiMYNBiLYeF',
  'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh',
  'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt',
  'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL',
  '3AVi9Tg9Uo68tJfuvoKvqKNWKkS5DGb5jhaMUmx94AmB',
].map(a => new PublicKey(a));

const JITO_BLOCK_ENGINE = 'https://mainnet.block-engine.jito.wtf/api/v1/bundles';

// ─── State ───
let wallet = null;
let connection = null;
let wsConnection = null;
let wsolAta = null;
let blacklist = {};
let lastSnipeTime = 0;
let stats = { detected: 0, sniped: 0, failed: 0, skipped: 0 };
let onPositionCallback = null;  // direct push callback (replaces HTTP handoff)
let sniperRunning = false;

// ─── Load wallet from jupiter-trader key file ───
function loadWallet() {
  const keyFile = path.join(__dirname, '.solana-trading-key');
  try {
    const data = JSON.parse(fs.readFileSync(keyFile, 'utf8'));
    const secretKey = Buffer.from(data.secretKey, 'base64');
    wallet = Keypair.fromSecretKey(new Uint8Array(secretKey));
    log(`Wallet loaded: ${wallet.publicKey.toBase58().slice(0, 8)}...`);
    return true;
  } catch (e) {
    log(`ERROR: No wallet — ${e.message}`);
    return false;
  }
}

// ─── RPC setup ───
const HELIUS_READ_URL = process.env.HELIUS_READ_KEY ? `https://mainnet.helius-rpc.com/?api-key=${process.env.HELIUS_READ_KEY}` : null;
const RPC_ENDPOINTS = [
  ...(HELIUS_READ_URL ? [HELIUS_READ_URL] : []),
  'https://api.mainnet-beta.solana.com',
  'https://rpc.ankr.com/solana',
];
let rpcIdx = 0;

function initConnections() {
  connection = new Connection(RPC_ENDPOINTS[0], 'confirmed');
  const wsUrl = HELIUS_READ_URL || RPC_ENDPOINTS[0];
  wsConnection = new Connection(wsUrl, {
    commitment: 'processed',
    wsEndpoint: wsUrl.replace('https://', 'wss://'),
  });
  wsolAta = getAssociatedTokenAddressSync(SOL_MINT, wallet.publicKey);
  log(`WSOL ATA: ${wsolAta.toBase58().slice(0, 8)}...`);
}

function rotateRpc() {
  rpcIdx = (rpcIdx + 1) % RPC_ENDPOINTS.length;
  connection = new Connection(RPC_ENDPOINTS[rpcIdx], 'confirmed');
  log(`Rotated RPC → ${RPC_ENDPOINTS[rpcIdx].slice(0, 40)}...`);
}

// ─── Logging ───
function log(msg) {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}] [JITO-SNIPER] ${msg}`);
}

// ─── Blacklist ───
function loadBlacklist() {
  try {
    if (fs.existsSync(CONFIG.blacklistFile)) {
      blacklist = JSON.parse(fs.readFileSync(CONFIG.blacklistFile, 'utf8'));
      log(`Blacklist loaded: ${Object.keys(blacklist).length} mints`);
    }
  } catch { blacklist = {}; }
}

function addToBlacklist(mint, reason) {
  blacklist[mint] = (blacklist[mint] || 0) + 1;
  try { fs.writeFileSync(CONFIG.blacklistFile, JSON.stringify(blacklist, null, 2)); } catch {}
  log(`Blacklisted ${mint.slice(0, 8)}... (${reason})`);
}

// ─── Section 1: Pool Detection via WebSocket ───
let wsSubscriptionId = null;

function startPoolDetection() {
  log('Starting Raydium pool detection (processed commitment)...');

  // Subscribe to Raydium AMM program logs
  wsSubscriptionId = wsConnection.onLogs(
    RAYDIUM_AMM_V4,
    async (logInfo) => {
      try {
        // Look for initialize2 in logs — this is a new pool creation
        const hasInit = logInfo.logs.some(l => l.includes('initialize2'));
        if (!hasInit) return;

        stats.detected++;
        const sig = logInfo.signature;
        const detectTime = Date.now();
        log(`POOL DETECTED  sig=${sig.slice(0, 16)}... (${stats.detected} total)`);

        // Cooldown check
        if (detectTime - lastSnipeTime < CONFIG.cooldownMs) {
          stats.skipped++;
          log(`SKIP  cooldown (${detectTime - lastSnipeTime}ms < ${CONFIG.cooldownMs}ms)`);
          return;
        }

        // Parse the pool creation TX to extract pool keys
        const poolKeys = await parsePoolCreationTx(sig);
        if (!poolKeys) {
          stats.skipped++;
          log('SKIP  failed to parse pool keys');
          return;
        }

        // Check blacklist
        const newMint = poolKeys.coinMint.equals(SOL_MINT) ? poolKeys.pcMint.toBase58() : poolKeys.coinMint.toBase58();
        if (blacklist[newMint]) {
          stats.skipped++;
          log(`SKIP  ${newMint.slice(0, 8)}... blacklisted (${blacklist[newMint]}x)`);
          return;
        }

        log(`NEW TOKEN  ${newMint.slice(0, 8)}... — building snipe TX`);
        lastSnipeTime = detectTime;

        // Build and send the snipe
        await executeSnipe(poolKeys, newMint, detectTime);

      } catch (e) {
        log(`Detection error: ${e.message}`);
      }
    },
    CONFIG.commitment
  );

  log('WebSocket subscription active — listening for new pools');
}

// ─── Parse pool creation TX to extract all account keys ───
async function parsePoolCreationTx(sig) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const tx = await connection.getTransaction(sig, {
        maxSupportedTransactionVersion: 0,
        commitment: 'confirmed',
      });

      if (!tx) {
        // TX not yet confirmed — wait briefly and retry
        if (attempt < 2) { await sleep(200); continue; }
        // Try with processed commitment
        const txProcessed = await connection.getTransaction(sig, {
          maxSupportedTransactionVersion: 0,
          commitment: 'processed',
        });
        if (!txProcessed) return null;
        return extractPoolKeys(txProcessed);
      }

      return extractPoolKeys(tx);
    } catch (e) {
      if (attempt < 2) { rotateRpc(); await sleep(100); }
      else { log(`Parse TX failed after 3 attempts: ${e.message}`); return null; }
    }
  }
  return null;
}

function extractPoolKeys(tx) {
  // Find the Raydium initialize2 instruction
  const msg = tx.transaction.message;
  const accountKeys = msg.staticAccountKeys || msg.accountKeys;

  // Look through inner instructions for Raydium AMM
  // The initialize2 instruction accounts layout:
  //   0: tokenProgram, 1: ammAuthority, 2: ammOpenOrders, 3: lpMint,
  //   4: coinMint, 5: pcMint, 6: poolCoinTokenAccount, 7: poolPcTokenAccount,
  //   8: ammTargetOrders, 9: ammId, 10: serumMarket
  // Plus additional accounts for serum/openbook

  let raydiumIx = null;

  // Check outer instructions first
  const instructions = msg.compiledInstructions || msg.instructions || [];
  for (const ix of instructions) {
    const progIdx = ix.programIdIndex;
    const progKey = accountKeys[progIdx];
    if (progKey && progKey.toBase58 && progKey.toBase58() === RAYDIUM_AMM_V4.toBase58()) {
      raydiumIx = ix;
      break;
    }
    // Handle parsed format
    if (progKey && progKey.toString() === RAYDIUM_AMM_V4.toBase58()) {
      raydiumIx = ix;
      break;
    }
  }

  if (!raydiumIx) {
    // Check inner instructions
    const inner = tx.meta?.innerInstructions || [];
    for (const group of inner) {
      for (const ix of group.instructions) {
        if (ix.programId && ix.programId.toBase58() === RAYDIUM_AMM_V4.toBase58()) {
          raydiumIx = ix;
          break;
        }
      }
      if (raydiumIx) break;
    }
  }

  if (!raydiumIx) {
    log('Could not find Raydium initialize2 instruction');
    return null;
  }

  // Extract account indices
  const acctIndices = raydiumIx.accounts || raydiumIx.accountKeyIndexes || [];
  if (acctIndices.length < 11) {
    log(`initialize2 has only ${acctIndices.length} accounts (need 11+)`);
    return null;
  }

  // Resolve accounts — handle both legacy and v0 formats
  function resolveKey(idx) {
    if (idx < accountKeys.length) return accountKeys[idx];
    // Check address table lookups for v0 transactions
    const loadedAddresses = tx.meta?.loadedAddresses;
    if (loadedAddresses) {
      const offset = idx - accountKeys.length;
      const writable = loadedAddresses.writable || [];
      if (offset < writable.length) return new PublicKey(writable[offset]);
      const roOffset = offset - writable.length;
      const readonly = loadedAddresses.readonly || [];
      if (roOffset < readonly.length) return new PublicKey(readonly[roOffset]);
    }
    return null;
  }

  const keys = {
    tokenProgram: resolveKey(acctIndices[0]),
    ammAuthority: resolveKey(acctIndices[1]),
    ammOpenOrders: resolveKey(acctIndices[2]),
    lpMint: resolveKey(acctIndices[3]),
    coinMint: resolveKey(acctIndices[4]),
    pcMint: resolveKey(acctIndices[5]),
    poolCoinTokenAccount: resolveKey(acctIndices[6]),
    poolPcTokenAccount: resolveKey(acctIndices[7]),
    ammTargetOrders: resolveKey(acctIndices[8]),
    ammId: resolveKey(acctIndices[9]),
    serumMarket: resolveKey(acctIndices[10]),
  };

  // Resolve additional serum accounts if available
  if (acctIndices.length >= 16) {
    keys.serumBids = resolveKey(acctIndices[11]);
    keys.serumAsks = resolveKey(acctIndices[12]);
    keys.serumEventQueue = resolveKey(acctIndices[13]);
    keys.serumCoinVault = resolveKey(acctIndices[14]);
    keys.serumPcVault = resolveKey(acctIndices[15]);
    if (acctIndices.length >= 17) {
      keys.serumVaultSigner = resolveKey(acctIndices[16]);
    }
  }

  // Validate we got the critical keys
  for (const [name, key] of Object.entries(keys)) {
    if (!key) { log(`Missing pool key: ${name}`); return null; }
  }

  log(`Pool keys extracted: amm=${keys.ammId.toBase58().slice(0, 8)}... coin=${keys.coinMint.toBase58().slice(0, 8)}... pc=${keys.pcMint.toBase58().slice(0, 8)}...`);
  return keys;
}

// ─── Section 2: Raw Raydium Swap Builder ───
// swapBaseIn instruction discriminator = 9
const SWAP_LAYOUT = BufferLayout.struct([
  BufferLayout.u8('instruction'),
  BufferLayout.blob(8, 'amountIn'),
  BufferLayout.blob(8, 'minAmountOut'),
]);

function buildSwapInstruction(poolKeys, amountInLamports, minAmountOut, userSourceAta, userDestAta) {
  // Determine swap direction: if coinMint is SOL, we're swapping SOL for pcMint
  // if pcMint is SOL, we're swapping SOL for coinMint
  const isCoinSol = poolKeys.coinMint.equals(SOL_MINT);

  const data = Buffer.alloc(SWAP_LAYOUT.span);
  SWAP_LAYOUT.encode({
    instruction: 9, // swapBaseIn
    amountIn: encodeBigInt(amountInLamports),
    minAmountOut: encodeBigInt(minAmountOut),
  }, data);

  // 17 accounts for Raydium AMM swapBaseIn
  const keys = [
    { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
    { pubkey: poolKeys.ammId, isSigner: false, isWritable: true },
    { pubkey: poolKeys.ammAuthority, isSigner: false, isWritable: false },
    { pubkey: poolKeys.ammOpenOrders, isSigner: false, isWritable: true },
    { pubkey: poolKeys.ammTargetOrders, isSigner: false, isWritable: true },
    { pubkey: poolKeys.poolCoinTokenAccount, isSigner: false, isWritable: true },
    { pubkey: poolKeys.poolPcTokenAccount, isSigner: false, isWritable: true },
    { pubkey: SERUM_PROGRAM, isSigner: false, isWritable: false },
    { pubkey: poolKeys.serumMarket, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumBids, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumAsks, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumEventQueue, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumCoinVault, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumPcVault, isSigner: false, isWritable: true },
    { pubkey: poolKeys.serumVaultSigner, isSigner: false, isWritable: false },
    // User source (WSOL ATA) and destination (token ATA) — direction-dependent
    { pubkey: isCoinSol ? userSourceAta : userDestAta, isSigner: false, isWritable: true },
    { pubkey: isCoinSol ? userDestAta : userSourceAta, isSigner: false, isWritable: true },
    { pubkey: wallet.publicKey, isSigner: true, isWritable: false },
  ];

  return new TransactionInstruction({
    programId: RAYDIUM_AMM_V4,
    keys,
    data,
  });
}

function encodeBigInt(value) {
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64LE(BigInt(value));
  return buf;
}

// ─── Section 3: Jito Bundle Submission ───
async function submitJitoBundle(transaction) {
  const serialized = transaction.serialize();
  const encoded = bs58.encode(serialized);

  const payload = {
    jsonrpc: '2.0',
    id: 1,
    method: 'sendBundle',
    params: [[encoded]],
  };

  const body = JSON.stringify(payload);

  return new Promise((resolve, reject) => {
    const url = new URL(JITO_BLOCK_ENGINE);
    const req = http.request({
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          if (result.error) reject(new Error(result.error.message || JSON.stringify(result.error)));
          else resolve(result.result);
        } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// Use https for Jito
async function submitJitoBundleHttps(transaction) {
  const serialized = transaction.serialize();
  const encoded = bs58.encode(serialized);

  const payload = JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'sendBundle',
    params: [[encoded]],
  });

  const https = require('https');
  return new Promise((resolve, reject) => {
    const url = new URL(JITO_BLOCK_ENGINE);
    const req = https.request({
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          if (result.error) reject(new Error(result.error.message || JSON.stringify(result.error)));
          else resolve(result.result);
        } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

// ─── Section 4: Serum Account Resolution ───
async function resolveSerumAccounts(poolKeys) {
  // If serum accounts already present from initialize2 TX, return as-is
  if (poolKeys.serumBids && poolKeys.serumAsks && poolKeys.serumEventQueue &&
      poolKeys.serumCoinVault && poolKeys.serumPcVault && poolKeys.serumVaultSigner) {
    log('Serum accounts resolved from pool creation TX');
    return poolKeys;
  }

  // Fallback: fetch serum market account data to find bids/asks/event queue/vaults
  log('Serum accounts missing — fetching from market account...');
  try {
    const marketInfo = await connection.getAccountInfo(poolKeys.serumMarket);
    if (!marketInfo || !marketInfo.data) {
      log('WARNING: Could not fetch serum market data');
      return null;
    }

    // OpenBook/Serum market layout offsets (from serum-ts)
    const data = marketInfo.data;
    // Skip first 5 bytes (account flags) + 8 bytes padding
    poolKeys.serumBids = new PublicKey(data.slice(40, 72));          // offset 40
    poolKeys.serumAsks = new PublicKey(data.slice(72, 104));         // offset 72
    poolKeys.serumEventQueue = new PublicKey(data.slice(136, 168));  // offset 136
    poolKeys.serumCoinVault = new PublicKey(data.slice(168, 200));   // offset 168
    poolKeys.serumPcVault = new PublicKey(data.slice(200, 232));     // offset 200

    // Vault signer = PDA derived from market address
    const [vaultSigner] = PublicKey.findProgramAddressSync(
      [poolKeys.serumMarket.toBuffer()],
      SERUM_PROGRAM
    );
    poolKeys.serumVaultSigner = vaultSigner;

    log('Serum accounts resolved from market data');
    return poolKeys;
  } catch (e) {
    log(`Serum resolution failed: ${e.message}`);
    return null;
  }
}

// ─── Section 5: Execute Snipe ───
async function executeSnipe(poolKeys, newMint, detectTime) {
  try {
    // Resolve serum accounts if needed
    const resolved = await resolveSerumAccounts(poolKeys);
    if (!resolved) {
      stats.failed++;
      log('ABORT  could not resolve serum accounts');
      addToBlacklist(newMint, 'no-serum');
      return;
    }

    const tokenMint = new PublicKey(newMint);
    const amountIn = CONFIG.defaultSpendLamports;

    // Create destination token ATA
    const userTokenAta = getAssociatedTokenAddressSync(tokenMint, wallet.publicKey);

    // Build transaction with:
    // 1. Create + fund WSOL ATA (wrap the spend amount so the swap has a source)
    // 2. Create token ATA (idempotent — won't fail if exists)
    // 3. Raydium swapBaseIn
    // 4. Jito tip transfer
    const tx = new Transaction();

    // 1. Wrap SOL: idempotent WSOL ATA create, fund with amountIn, sync native
    tx.add(createAssociatedTokenAccountIdempotentInstruction(
      wallet.publicKey, wsolAta, wallet.publicKey, SOL_MINT
    ));
    tx.add(SystemProgram.transfer({
      fromPubkey: wallet.publicKey,
      toPubkey: wsolAta,
      lamports: amountIn,
    }));
    tx.add(createSyncNativeInstruction(wsolAta));

    // 2. Create token ATA
    tx.add(createAssociatedTokenAccountIdempotentInstruction(
      wallet.publicKey, userTokenAta, wallet.publicKey, tokenMint
    ));

    // 3. Swap instruction
    const swapIx = buildSwapInstruction(resolved, amountIn, 1, wsolAta, userTokenAta);
    tx.add(swapIx);

    // 4. Jito tip — random tip account
    const tipAccount = JITO_TIP_ACCOUNTS[Math.floor(Math.random() * JITO_TIP_ACCOUNTS.length)];
    tx.add(SystemProgram.transfer({
      fromPubkey: wallet.publicKey,
      toPubkey: tipAccount,
      lamports: CONFIG.jitoTipLamports,
    }));

    // Set recent blockhash
    const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash('processed');
    tx.recentBlockhash = blockhash;
    tx.lastValidBlockHeight = lastValidBlockHeight;
    tx.feePayer = wallet.publicKey;

    // Sign
    tx.sign(wallet);

    const buildTime = Date.now() - detectTime;
    log(`TX built in ${buildTime}ms — ${CONFIG.paperMode ? 'PAPER MODE' : 'submitting to Jito'}...`);

    if (CONFIG.paperMode) {
      log(`PAPER  Would snipe ${newMint.slice(0, 8)}... for ${amountIn / LAMPORTS_PER_SOL} SOL + ${CONFIG.jitoTipLamports / LAMPORTS_PER_SOL} tip`);
      log(`PAPER  TX size: ${tx.serialize().length} bytes`);
      stats.sniped++;
      return;
    }

    // Submit via Jito
    const bundleId = await submitJitoBundleHttps(tx);
    const totalTime = Date.now() - detectTime;

    log(`SNIPED  bundle=${bundleId} mint=${newMint.slice(0, 8)}... ${amountIn / LAMPORTS_PER_SOL} SOL in ${totalTime}ms`);
    stats.sniped++;

    // Hand off to scalper — direct callback or HTTP fallback
    const txId = bs58.encode(tx.signature);
    const positionData = {
      mint: newMint,
      symbol: `JITO-${newMint.slice(0, 4)}`,
      amount: 0, // unknown until confirmed
      entrySol: amountIn / LAMPORTS_PER_SOL,
      txId,
      entryPrice: 0,
      jitoSnipe: true,
      bundleId,
      detectToSubmitMs: totalTime,
    };

    if (onPositionCallback) {
      onPositionCallback(positionData);
    } else {
      await handoffToScalper(positionData);
    }

  } catch (e) {
    stats.failed++;
    log(`SNIPE FAILED  ${e.message}`);
    addToBlacklist(newMint, `error: ${e.message.slice(0, 50)}`);
  }
}

// ─── Section 6: Position Handoff to Scalper ───
async function handoffToScalper(position) {
  return new Promise((resolve) => {
    const body = JSON.stringify(position);
    const url = new URL(CONFIG.scalperUrl);

    const req = http.request({
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          if (result.ok) log(`HANDOFF  position sent to scalper — ${position.symbol}`);
          else log(`HANDOFF  scalper rejected: ${JSON.stringify(result)}`);
        } catch { log('HANDOFF  scalper response parse error'); }
        resolve();
      });
    });
    req.on('error', (e) => {
      log(`HANDOFF  scalper unreachable — ${e.message} (position will need manual entry)`);
      resolve();
    });
    req.write(body);
    req.end();
  });
}

// ─── Utility ───
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── Shutdown ───
function shutdown() {
  log('Shutting down...');
  stopJitoSniper();
  log(`Stats: detected=${stats.detected} sniped=${stats.sniped} failed=${stats.failed} skipped=${stats.skipped}`);
}

// ─── Exportable API ───
function startJitoSniper(onPosition, config) {
  if (sniperRunning) { log('Already running'); return; }

  if (onPosition) onPositionCallback = onPosition;
  if (config) Object.assign(CONFIG, config);

  if (!wallet && !loadWallet()) {
    log('ERROR: No wallet — cannot start');
    return;
  }

  initConnections();
  loadBlacklist();

  if (CONFIG.paperMode) {
    log('PAPER MODE — will detect and build TXs but NOT submit');
  }

  startPoolDetection();
  sniperRunning = true;
  log(`Ready — cooldown=${CONFIG.cooldownMs}ms spend=${CONFIG.defaultSpendLamports / LAMPORTS_PER_SOL} SOL tip=${CONFIG.jitoTipLamports / LAMPORTS_PER_SOL} SOL`);
}

function stopJitoSniper() {
  sniperRunning = false;
  onPositionCallback = null;
  if (wsSubscriptionId !== null) {
    wsConnection.removeOnLogsListener(wsSubscriptionId).catch(() => {});
    wsSubscriptionId = null;
  }
  log(`Stopped — detected=${stats.detected} sniped=${stats.sniped} failed=${stats.failed} skipped=${stats.skipped}`);
}

function getJitoStats() {
  return { ...stats, running: sniperRunning };
}

module.exports = { startJitoSniper, stopJitoSniper, getJitoStats };

// ─── Standalone Boot ───
if (require.main === module) {
  console.log('\n  ╔══════════════════════════════════════════╗');
  console.log('  ║   JITO BUNDLE SNIPER — Block-0 Entry     ║');
  console.log('  ║   Raw Raydium swap + Jito bundle API      ║');
  console.log('  ║   Penny snipes: 0.001-0.005 SOL           ║');
  console.log('  ╚══════════════════════════════════════════╝\n');

  startJitoSniper();

  process.on('SIGINT', () => { shutdown(); process.exit(0); });
  process.on('SIGTERM', () => { shutdown(); process.exit(0); });
}
