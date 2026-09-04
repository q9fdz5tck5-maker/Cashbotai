#!/usr/bin/env node
'use strict';
// Does the finished MP4 actually show slide N while slide N is being narrated?
//
// The build is a chain of caches (mp3 -> png -> ts segment -> mp4). Every link
// is stamped, but a stamp only proves the inputs were the ones on disk; it
// cannot prove the ordering survived concatenation. This checks the artifact
// itself: seek to the midpoint of each slide's narration, grab that frame, and
// compare it against that slide's reference capture.
//
//   node tools/verify-sync.js projects/forge-launch/project.json
//
// Exits non-zero if any slide's frame fails to match its capture.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const config = require('../src/config');
const { workDirs } = require('../src/pipeline');
const { requireAll } = require('../src/paths');

// x264 at the project's CRF reproduces a still frame far above this; anything
// near or below it is a different picture, not a compression artifact.
const MIN_PSNR_DB = 30;

function psnr(ffmpeg, a, b) {
  const out = execFileSync(ffmpeg, [
    '-hide_banner', '-nostats',
    '-i', a, '-i', b,
    '-filter_complex', '[0:v][1:v]psnr',
    '-f', 'null', '-',
  ], { stdio: ['ignore', 'ignore', 'pipe'] }).toString();
  const m = out.match(/average:([0-9.]+|inf)/);
  if (!m) throw new Error(`could not read PSNR from ffmpeg output:\n${out.slice(-400)}`);
  return m[1] === 'inf' ? Infinity : parseFloat(m[1]);
}

function main() {
  const configPath = process.argv[2];
  if (!configPath) {
    console.error('usage: node tools/verify-sync.js <project.json>');
    process.exit(2);
  }

  const cfg = config.load(configPath);
  const bins = requireAll();
  const outRoot = path.resolve(process.env.OUTPUT_DIR || path.join(__dirname, '..', 'output'));
  const dirs = workDirs(cfg, outRoot);

  const mp4 = path.join(dirs.dist, `${cfg.name}.mp4`);
  const manifest = path.join(dirs.work, 'narration.json');
  for (const f of [mp4, manifest]) {
    if (!fs.existsSync(f)) {
      console.error(`missing ${f} — run a build first.`);
      process.exit(2);
    }
  }
  const narration = JSON.parse(fs.readFileSync(manifest, 'utf8'));

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'verify-sync-'));
  let start = 0;
  let failures = 0;

  try {
    for (let i = 0; i < cfg.slides.length; i++) {
      const slide = cfg.slides[i];
      const audio = narration[i];
      const pad = slide.padSeconds ?? cfg.video.padSeconds;
      // Sample mid-narration: past the 0.4s fade-in, before the fade-out.
      const at = start + audio.duration / 2;
      start += audio.duration + pad;

      const num = String(slide.index).padStart(3, '0');
      const ref = path.join(dirs.slides, `${num}-${slide.id}.png`);
      const frame = path.join(tmp, `${num}.png`);

      execFileSync(bins.ffmpeg, [
        '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', at.toFixed(3), '-i', mp4, '-frames:v', '1', frame,
      ], { stdio: ['ignore', 'ignore', 'pipe'] });

      const db = psnr(bins.ffmpeg, frame, ref);
      const ok = db >= MIN_PSNR_DB;
      if (!ok) failures++;
      const shown = db === Infinity ? 'inf' : db.toFixed(1);
      console.log(
        `${ok ? 'ok  ' : 'FAIL'} [${num}] ${slide.id.padEnd(5)} @ ${at.toFixed(1).padStart(7)}s  PSNR ${shown} dB`
      );
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  console.log('');
  if (failures) {
    console.error(`${failures}/${cfg.slides.length} slides do not match their capture.`);
    process.exit(1);
  }
  console.log(`all ${cfg.slides.length} slides match their captures (>= ${MIN_PSNR_DB} dB) — video is in sync.`);
}

main();
