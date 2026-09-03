'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULTS = {
  voice: {
    name: 'default',
    engine: 'chatterbox',
    exaggeration: 0.15,   // locked-in value from the original tuning
    cfgWeight: 0.5,
  },
  video: {
    width: 1920,
    height: 1080,
    fps: 30,
    padSeconds: 1.0,      // silence held after each slide's narration
    fadeSeconds: 0.5,
    crf: 23,
    preset: 'medium',
    audioBitrate: '192k',
  },
  tts: {
    applyCompliance: true,
    pronunciation: {},
    compliance: null,     // null => use textnorm defaults
  },
};

function deepMerge(base, override) {
  if (override === null || override === undefined) return base;
  if (Array.isArray(base) || Array.isArray(override)) return override;
  if (typeof base !== 'object' || typeof override !== 'object') return override;
  const out = { ...base };
  for (const key of Object.keys(override)) {
    out[key] = key in base ? deepMerge(base[key], override[key]) : override[key];
  }
  return out;
}

const LAYOUTS = new Set([
  'title', 'bullets', 'stats', 'compare', 'quote', 'myth', 'pricing', 'faq', 'cta',
]);

function validate(cfg, file) {
  const errors = [];
  const where = path.basename(file);

  if (!cfg.name || !/^[a-z0-9][a-z0-9_-]*$/i.test(cfg.name)) {
    errors.push('"name" is required and must be filename-safe (letters, digits, - and _).');
  }
  if (!Array.isArray(cfg.slides) || cfg.slides.length === 0) {
    errors.push('"slides" must be a non-empty array.');
  } else {
    cfg.slides.forEach((s, i) => {
      const n = i + 1;
      if (!s.layout) errors.push(`slide ${n}: missing "layout".`);
      else if (!LAYOUTS.has(s.layout)) {
        errors.push(`slide ${n}: unknown layout "${s.layout}". Known: ${[...LAYOUTS].join(', ')}.`);
      }
      if (!s.narration || !String(s.narration).trim()) {
        errors.push(`slide ${n}: missing "narration" — every slide needs spoken text.`);
      }
    });
  }
  if (cfg.video && cfg.video.fps && cfg.video.fps < 1) errors.push('video.fps must be >= 1.');

  if (errors.length) {
    throw new Error(`Invalid project config (${where}):\n  - ${errors.join('\n  - ')}`);
  }
}

function load(configPath) {
  const file = path.resolve(configPath);
  if (!fs.existsSync(file)) {
    throw new Error(`Project config not found: ${file}`);
  }

  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    throw new Error(`Project config is not valid JSON (${file}): ${e.message}`);
  }

  const cfg = deepMerge(DEFAULTS, raw);
  validate(cfg, file);

  // Give every slide a stable id — ids drive both the DOM and the PNG filenames,
  // so they must not shift when a slide is inserted mid-deck.
  cfg.slides = cfg.slides.map((s, i) => ({ ...s, id: s.id || `s${i + 1}`, index: i + 1 }));

  const seen = new Set();
  for (const s of cfg.slides) {
    if (seen.has(s.id)) throw new Error(`Duplicate slide id "${s.id}" in ${file}.`);
    seen.add(s.id);
  }

  cfg.__file = file;
  cfg.__dir = path.dirname(file);
  return cfg;
}

module.exports = { load, DEFAULTS, LAYOUTS };
