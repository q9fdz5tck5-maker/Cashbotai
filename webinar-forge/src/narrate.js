'use strict';
// Slide narration -> one MP3 per slide, via the voice engine's /synthesize.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const crypto = require('crypto');
const { normalize } = require('./textnorm');
const log = require('./log');

function engineUrl() {
  return (process.env.VOICE_ENGINE_URL || 'http://127.0.0.1:5651').replace(/\/+$/, '');
}

async function health() {
  const res = await fetch(`${engineUrl()}/health`, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) throw new Error(`/health returned ${res.status}`);
  return res.json();
}

async function listVoices() {
  const res = await fetch(`${engineUrl()}/voices`, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) throw new Error(`/voices returned ${res.status}`);
  return res.json();
}

async function assertReady(voiceName) {
  let h;
  try {
    h = await health();
  } catch (e) {
    throw new Error(
      `Voice engine unreachable at ${engineUrl()}: ${e.message}\n` +
      `Start it with:  ./engine/start.sh   (or: npm run mock-engine for a dry run)`
    );
  }
  log.info(`voice engine ok — device=${h.device}`);

  const { voices } = await listVoices();
  const names = (voices || []).map((v) => v.name);
  if (!names.includes(voiceName)) {
    throw new Error(
      `Voice "${voiceName}" is not installed on the engine.\n` +
      `Installed: ${names.length ? names.join(', ') : '(none)'}\n` +
      `Add one with:  node bin/webinar-forge add-voice <name> <sample.wav>`
    );
  }
  return h;
}

// Synthesis on CPU can run many minutes per slide, so the timeout is generous.
async function synthesize(text, voice, opts) {
  const form = new FormData();
  form.append('text', text);
  form.append('voice', voice);
  form.append('engine', opts.engine);
  form.append('exaggeration', String(opts.exaggeration));
  form.append('cfg_weight', String(opts.cfgWeight));

  const res = await fetch(`${engineUrl()}/synthesize`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(30 * 60 * 1000),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`/synthesize ${res.status}: ${body.slice(0, 300)}`);
  }
  return Buffer.from(await res.arrayBuffer());
}

function wavToMp3(ffmpeg, wavPath, mp3Path, bitrate) {
  execFileSync(ffmpeg, [
    '-y', '-i', wavPath,
    '-codec:a', 'libmp3lame', '-b:a', bitrate, '-ar', '44100',
    mp3Path,
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
}

function durationOf(ffprobe, file) {
  try {
    const out = execFileSync(ffprobe, [
      '-v', 'error',
      '-show_entries', 'format=duration',
      '-of', 'default=noprint_wrappers=1:nokey=1',
      file,
    ]).toString().trim();
    const d = parseFloat(out);
    return Number.isFinite(d) ? d : 0;
  } catch {
    return 0;
  }
}

// A cached MP3's existence says nothing about *what* was said or *who* said it.
// Each MP3 gets a sidecar stamp recording the narration hash and the voice
// settings that produced it, so editing narration or switching voices
// invalidates the cache instead of silently reusing the previous audio.
function stampFor(text, voice) {
  return {
    hash: crypto.createHash('sha256').update(text).digest('hex'),
    voice: voice.name,
    engine: voice.engine,
    exaggeration: voice.exaggeration,
    cfgWeight: voice.cfgWeight,
  };
}

function stampMatches(stampPath, stamp) {
  try {
    const prev = JSON.parse(fs.readFileSync(stampPath, 'utf8'));
    return Object.keys(stamp).every((k) => prev[k] === stamp[k]);
  } catch {
    return false;
  }
}

async function narrateAll(cfg, dirs, bins, { force = false } = {}) {
  const voice = cfg.voice;
  await assertReady(voice.name);

  fs.mkdirSync(dirs.audio, { recursive: true });
  fs.mkdirSync(dirs.tmp, { recursive: true });

  const concurrency = Math.max(1, parseInt(process.env.TTS_CONCURRENCY || '1', 10));
  const results = new Array(cfg.slides.length);
  let cursor = 0;

  async function worker() {
    while (cursor < cfg.slides.length) {
      const i = cursor++;
      const slide = cfg.slides[i];
      const num = String(slide.index).padStart(3, '0');
      const mp3Path = path.join(dirs.audio, `${num}-${slide.id}.mp3`);
      const stampPath = `${mp3Path}.json`;

      const text = normalize(slide.narration, {
        pronunciation: cfg.tts.pronunciation,
        compliance: cfg.tts.compliance || undefined,
        applyCompliance: cfg.tts.applyCompliance,
      });
      const stamp = stampFor(text, voice);

      if (!force && fs.existsSync(mp3Path) && fs.statSync(mp3Path).size > 1024 &&
          stampMatches(stampPath, stamp)) {
        const d = durationOf(bins.ffprobe, mp3Path);
        log.info(`[${num}] cached (${d.toFixed(1)}s)`);
        results[i] = { id: slide.id, index: slide.index, mp3Path, duration: d, cached: true };
        continue;
      }

      const words = text.split(/\s+/).filter(Boolean).length;
      log.info(`[${num}] synthesizing ${words} words…`);
      const t0 = Date.now();

      const wavBuf = await synthesize(text, voice.name, voice);
      const wavPath = path.join(dirs.tmp, `${num}-${slide.id}.wav`);
      fs.writeFileSync(wavPath, wavBuf);
      wavToMp3(bins.ffmpeg, wavPath, mp3Path, cfg.video.audioBitrate);
      fs.unlinkSync(wavPath);

      fs.writeFileSync(stampPath, JSON.stringify(stamp, null, 2));

      const duration = durationOf(bins.ffprobe, mp3Path);
      const wall = ((Date.now() - t0) / 1000).toFixed(1);
      log.ok(`[${num}] ${duration.toFixed(1)}s audio in ${wall}s`);
      results[i] = { id: slide.id, index: slide.index, mp3Path, duration, cached: false };
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, cfg.slides.length) }, () => worker())
  );

  const manifestPath = path.join(dirs.work, 'narration.json');
  fs.writeFileSync(manifestPath, JSON.stringify(results, null, 2));
  const total = results.reduce((a, r) => a + r.duration, 0);
  log.ok(`narration complete — ${(total / 60).toFixed(1)} min across ${results.length} slides`);
  return results;
}

module.exports = { narrateAll, health, listVoices, assertReady, durationOf, engineUrl };
