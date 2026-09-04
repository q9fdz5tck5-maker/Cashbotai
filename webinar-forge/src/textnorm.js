'use strict';
// Text normalisation before TTS.
//
// Ported from the original pipeline, where these rules lived inline in
// generate-webinar-video.js. Two jobs:
//   1. pronunciation  - stop the model spelling out brand names and URLs
//   2. compliance     - strip claim language you do not want in a sales asset
// Both are config-driven so each deployment sets its own.

// Order matters: the article-aware rule runs first so "an iron-clad guarantee"
// does not become "an satisfaction policy", and the replacement never carries a
// hardcoded term length ("30-day") that would double up against copy already
// saying "a 30-day money-back guarantee".
const DEFAULT_COMPLIANCE = [
  { pattern: '\\ban?\\s+(?:money.?back|satisfaction|100%|iron.?clad)\\s+guarantee\\b', replace: 'a satisfaction policy' },
  { pattern: '\\b(?:money.?back|satisfaction|100%|iron.?clad)\\s+guarantee\\b', replace: 'satisfaction policy' },
  { pattern: '\\bguaranteed\\b', replace: 'backed by our satisfaction policy' },
  { pattern: '\\ban\\s+guarantee\\b', replace: 'a satisfaction policy' },
  { pattern: '\\bguarantees\\b', replace: 'satisfaction policies' },
  { pattern: '\\bguarantee[sd]?\\b', replace: 'satisfaction policy' },
];

function stripHtml(text) {
  return String(text)
    .replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

// Longest-first so "cash.bot/order" wins over "cash.bot".
function applyPronunciation(text, map) {
  const keys = Object.keys(map || {}).sort((a, b) => b.length - a.length);
  let out = text;
  for (const key of keys) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp(escaped, 'gi'), map[key]);
  }
  return out;
}

function applyRules(text, rules) {
  let out = text;
  for (const rule of rules || []) {
    out = out.replace(new RegExp(rule.pattern, 'gi'), rule.replace);
  }
  return out;
}

function normalize(text, opts = {}) {
  const {
    pronunciation = {},
    compliance = DEFAULT_COMPLIANCE,
    applyCompliance = true,
  } = opts;

  let out = stripHtml(text);
  out = applyPronunciation(out, pronunciation);
  if (applyCompliance) out = applyRules(out, compliance);
  return out.replace(/\s+/g, ' ').trim();
}

module.exports = { normalize, stripHtml, DEFAULT_COMPLIANCE };
