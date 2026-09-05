'use strict';
// Convert a legacy hand-built deck + its narration JSON into a project.json.
//
// The old decks were bespoke HTML — one file per webinar, 50-96 KB, with the
// narration living in a separate JSON keyed by slide number. This pulls both
// into a single config so the deck becomes data.
//
// It is a best-effort structural import, not a pixel-perfect one:
//   - narration is carried across verbatim, never rewritten
//   - headings, kickers, stats, bullets and prices are mapped where recognised
//   - anything it cannot classify becomes a "title" slide and is listed in the
//     review report, so you know exactly what to look at
//
// Deliberately regex-based rather than pulling in a DOM parser: the input is a
// known family of decks, and the report tells you where it guessed.

const fs = require('fs');
const path = require('path');

const DEFAULT_SELECTORS = {
  slide: 'slide',
  kicker: 'kicker',
  title: 'slide-title',
  subtitle: 'slide-subtitle',
  stat: 'hero-stat',
  statValue: 'hero-stat-num',
  statLabel: 'hero-stat-label',
  bullet: 'bullet-item',
  step: 'demo-step',
  tier: 'stack-row',
  cta: 'cta-btn',
  lie: 'lie-text',
  stamp: 'wrong-stamp',
  truth: 'real-truth',
};

const ENTITIES = {
  '&rsquo;': "'", '&lsquo;': "'", '&ldquo;': '"', '&rdquo;': '"',
  '&mdash;': '—', '&ndash;': '–', '&amp;': '&', '&nbsp;': ' ',
  '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&middot;': '·',
  '&rarr;': '→', '&hellip;': '…',
};

function decode(s) {
  let out = String(s || '');
  for (const [k, v] of Object.entries(ENTITIES)) out = out.split(k).join(v);
  return out.replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)));
}

function text(html) {
  return decode(String(html || '').replace(/<[^>]+>/g, ' '))
    .replace(/\s+/g, ' ')
    // Stripping inline tags leaves "one sentence ." where the source had
    // "<span>one sentence</span>." — pull punctuation back onto the word.
    .replace(/\s+([.,!?;:%)\]])/g, '$1')
    .replace(/([(\[$])\s+/g, '$1')
    .trim();
}

// Class match that tolerates multi-class attributes ("kicker gold").
function classRe(cls, tag = '[a-z0-9]+') {
  return new RegExp(`<(${tag})[^>]*class="[^"]*\\b${cls}\\b[^"]*"[^>]*>([\\s\\S]*?)<\\/\\1>`, 'gi');
}

function firstByClass(chunk, cls) {
  const m = classRe(cls).exec(chunk);
  return m ? text(m[2]) : null;
}

function allByClass(chunk, cls) {
  const out = [];
  let m;
  const re = classRe(cls);
  while ((m = re.exec(chunk))) out.push(m[2]);
  return out;
}

function headingOf(chunk, sel) {
  return (
    firstByClass(chunk, sel.title) ||
    text((/<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(chunk) || [])[1]) ||
    text((/<h2[^>]*>([\s\S]*?)<\/h2>/i.exec(chunk) || [])[1]) ||
    null
  );
}

function splitSlides(html, sel) {
  // Matches <div class="slide" id="x"> and <section class="slide" id="x">.
  const re = new RegExp(`<(?:div|section)[^>]*class="[^"]*\\b${sel.slide}\\b[^"]*"[^>]*id="([^"]+)"`, 'gi');
  const marks = [];
  let m;
  while ((m = re.exec(html))) marks.push({ id: m[1], start: m.index });
  return marks.map((mark, i) => ({
    id: mark.id,
    html: html.slice(mark.start, i + 1 < marks.length ? marks[i + 1].start : html.length),
  }));
}

function classify(chunk, sel) {
  // Myth first: these slides carry no heading element, so without this they
  // import as empty "title" slides and lose their whole message.
  if (firstByClass(chunk, sel.lie) && firstByClass(chunk, sel.truth)) return 'myth';

  const stats = allByClass(chunk, sel.stat);
  if (stats.length >= 2) return 'stats';

  const steps = allByClass(chunk, sel.step);
  const bullets = allByClass(chunk, sel.bullet);
  if (bullets.length >= 2 || steps.length >= 2) return 'bullets';

  if (new RegExp(`\\b${sel.cta}\\b`).test(chunk)) return 'cta';
  return 'title';
}

function buildSlide(chunk, sel) {
  const layout = classify(chunk, sel);
  const slide = { layout };

  const kicker = firstByClass(chunk, sel.kicker);
  if (kicker) slide.kicker = kicker;

  const headline = headingOf(chunk, sel);
  const sub = firstByClass(chunk, sel.subtitle);

  if (layout === 'myth') {
    slide.lie = firstByClass(chunk, sel.lie) || '';
    slide.stamp = firstByClass(chunk, sel.stamp) || 'WRONG';
    slide.truth = firstByClass(chunk, sel.truth) || '';
    if (sub) slide.sub = sub;
  } else if (layout === 'stats') {
    slide.headline = headline || '';
    slide.stats = allByClass(chunk, sel.stat).map((s) => ({
      value: firstByClass(s, sel.statValue) || text(s).split(' ')[0] || '',
      label: firstByClass(s, sel.statLabel) || text(s),
    }));
  } else if (layout === 'bullets') {
    slide.headline = headline || '';
    const items = allByClass(chunk, sel.bullet).length
      ? allByClass(chunk, sel.bullet)
      : allByClass(chunk, sel.step);
    slide.bullets = items.map(text).filter(Boolean);
  } else if (layout === 'cta') {
    slide.headline = headline || '';
    if (sub) slide.sub = sub;
    const btn = firstByClass(chunk, sel.cta);
    if (btn) slide.button = btn;
  } else {
    slide.headline = headline || '';
    if (sub) slide.sub = sub;
  }

  return slide;
}

function importDeck({ htmlPath, narrationPath, name, selectors = {} }) {
  const sel = { ...DEFAULT_SELECTORS, ...selectors };
  const html = fs.readFileSync(htmlPath, 'utf8');
  const chunks = splitSlides(html, sel);
  if (!chunks.length) {
    throw new Error(
      `No slides found in ${path.basename(htmlPath)}.\n` +
      `Expected elements like <div class="${sel.slide}" id="...">. ` +
      `Override with --selector-slide if the deck uses a different class.`
    );
  }

  const narration = JSON.parse(fs.readFileSync(narrationPath, 'utf8'));
  const scriptOf = (entry) => entry && (entry.script || entry.text || entry.narration || '');

  // Legacy decks number their DOM ids s1..sN while the narration file may use
  // its own ids (s1..s19 then t1..t18). The build scripts paired them by
  // position, so that is what we reproduce - with a warning if lengths differ.
  const warnings = [];
  if (narration.length !== chunks.length) {
    warnings.push(
      `Slide count mismatch: deck has ${chunks.length}, narration has ${narration.length}. ` +
      `Paired by position; the extra entries were dropped.`
    );
  }

  const review = [];
  const slides = chunks.map((chunk, i) => {
    const slide = buildSlide(chunk.html, sel);
    slide.id = chunk.id;
    slide.narration = scriptOf(narration[i]);

    if (!slide.narration) review.push(`${chunk.id}: no narration found for position ${i + 1}`);
    if (!slide.headline && slide.layout !== 'myth') {
      review.push(`${chunk.id}: no headline detected`);
    }
    if (slide.layout === 'title' && !slide.sub) review.push(`${chunk.id}: fell back to "title" layout — check it`);
    return slide;
  });

  return {
    project: {
      name,
      title: text((/<title[^>]*>([\s\S]*?)<\/title>/i.exec(html) || [])[1]) || name,
      brand: { product: 'YOUR PRODUCT', accent: '#f5c518' },
      voice: { name: 'my-voice', engine: 'chatterbox', exaggeration: 0.15, cfgWeight: 0.5 },
      video: { width: 1920, height: 1080, fps: 30, padSeconds: 1.0 },
      tts: { applyCompliance: true, pronunciation: {} },
      slides,
    },
    warnings,
    review,
  };
}

module.exports = { importDeck, DEFAULT_SELECTORS };

if (require.main === module) {
  const args = process.argv.slice(2);
  const flag = (n, d) => {
    const i = args.indexOf(`--${n}`);
    return i === -1 ? d : args[i + 1];
  };

  const htmlPath = flag('html');
  const narrationPath = flag('narration');
  const out = flag('out');

  if (!htmlPath || !narrationPath || !out) {
    console.log(`
Convert a legacy deck into a webinar-forge project.

  node tools/import-deck.js --html <deck.html> --narration <narration.json> --out <project.json>

Options
  --name <name>            project name (default: derived from --out)
  --selector-slide <cls>   slide container class   (default: slide)
  --selector-title <cls>   headline class          (default: slide-title)
  --selector-kicker <cls>  kicker class            (default: kicker)
`);
    process.exit(1);
  }

  const selectors = {};
  for (const key of ['slide', 'title', 'kicker', 'subtitle', 'stat', 'bullet', 'step', 'cta', 'lie', 'stamp', 'truth']) {
    const v = flag(`selector-${key}`);
    if (v) selectors[key] = v;
  }

  const name = flag('name', path.basename(path.dirname(path.resolve(out))));
  const { project, warnings, review } = importDeck({ htmlPath, narrationPath, name, selectors });

  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(project, null, 2) + '\n');

  console.log(`Imported ${project.slides.length} slides -> ${out}`);
  const words = project.slides.reduce((a, s) => a + s.narration.split(/\s+/).filter(Boolean).length, 0);
  console.log(`Narration: ${words} words (~${(words / 150).toFixed(0)} min spoken)`);

  const counts = {};
  for (const s of project.slides) counts[s.layout] = (counts[s.layout] || 0) + 1;
  console.log(`Layouts: ${Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(' ')}`);

  for (const w of warnings) console.log(`\nWARNING  ${w}`);
  if (review.length) {
    console.log(`\nReview these ${review.length} item(s) before building:`);
    for (const r of review) console.log(`  - ${r}`);
  }
  console.log('\nNext:  node bin/webinar-forge build ' + out);
}
