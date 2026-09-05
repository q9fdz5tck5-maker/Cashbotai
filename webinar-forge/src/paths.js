'use strict';
// Resolves external binaries. Every path the old pipeline hardcoded to a Mac
// (/opt/homebrew/bin/ffmpeg, "Google Chrome.app", /tmp/webinar-capture) is
// looked up here instead, so the same zip runs on macOS, Debian and in Docker.

const fs = require('fs');
const { execFileSync } = require('child_process');

function fromPath(bin) {
  try {
    const out = execFileSync('which', [bin], { stdio: ['ignore', 'pipe', 'ignore'] });
    const p = out.toString().trim();
    return p && fs.existsSync(p) ? p : null;
  } catch {
    return null;
  }
}

function firstExisting(candidates) {
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  return null;
}

function resolveFfmpeg() {
  return (
    firstExisting([process.env.FFMPEG_PATH]) ||
    fromPath('ffmpeg') ||
    firstExisting([
      '/usr/bin/ffmpeg',
      '/usr/local/bin/ffmpeg',
      '/opt/homebrew/bin/ffmpeg',
      '/snap/bin/ffmpeg',
    ])
  );
}

function resolveFfprobe() {
  return (
    firstExisting([process.env.FFPROBE_PATH]) ||
    fromPath('ffprobe') ||
    firstExisting([
      '/usr/bin/ffprobe',
      '/usr/local/bin/ffprobe',
      '/opt/homebrew/bin/ffprobe',
    ])
  );
}

function resolveChrome() {
  return (
    firstExisting([process.env.CHROME_PATH, process.env.PUPPETEER_EXECUTABLE_PATH]) ||
    fromPath('chromium') ||
    fromPath('chromium-browser') ||
    fromPath('google-chrome') ||
    firstExisting([
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/usr/bin/google-chrome',
      '/opt/pw-browsers/chromium',
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ])
  );
}

function resolveAll() {
  return {
    ffmpeg: resolveFfmpeg(),
    ffprobe: resolveFfprobe(),
    chrome: resolveChrome(),
  };
}

function requireAll() {
  const bins = resolveAll();
  const missing = Object.entries(bins).filter(([, v]) => !v).map(([k]) => k);
  if (missing.length) {
    throw new Error(
      `Missing required binaries: ${missing.join(', ')}.\n` +
      `Install them (see install.sh) or set FFMPEG_PATH / FFPROBE_PATH / CHROME_PATH.`
    );
  }
  return bins;
}

module.exports = { resolveAll, requireAll };
