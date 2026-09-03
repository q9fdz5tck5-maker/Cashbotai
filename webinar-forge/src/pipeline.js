'use strict';

const fs = require('fs');
const path = require('path');
const config = require('./config');
const deck = require('./deck');
const { narrateAll } = require('./narrate');
const { captureSlides } = require('./capture');
const { buildVideo } = require('./video');
const { requireAll } = require('./paths');
const log = require('./log');

const ROOT = path.resolve(__dirname, '..');

function workDirs(cfg, outRoot) {
  const work = path.join(outRoot, cfg.name);
  return {
    root: outRoot,
    work,
    deckHtml: path.join(work, 'deck.html'),
    slides: path.join(work, 'slides'),
    audio: path.join(work, 'audio'),
    segments: path.join(work, 'segments'),
    tmp: path.join(work, 'tmp'),
    dist: path.join(work, 'dist'),
  };
}

async function build(configPath, opts = {}) {
  const cfg = config.load(configPath);
  const bins = requireAll();
  const outRoot = path.resolve(opts.output || process.env.OUTPUT_DIR || path.join(ROOT, 'output'));
  const dirs = workDirs(cfg, outRoot);

  fs.mkdirSync(dirs.work, { recursive: true });

  log.info(`project   ${cfg.name}  (${cfg.slides.length} slides)`);
  log.info(`voice     ${cfg.voice.name} via ${cfg.voice.engine}`);
  log.info(`output    ${dirs.work}`);
  log.info(`ffmpeg    ${bins.ffmpeg}`);
  log.info(`chrome    ${bins.chrome}`);

  log.step('1/4  Render deck');
  fs.writeFileSync(dirs.deckHtml, deck.render(cfg));
  log.ok(`deck.html (${cfg.slides.length} slides)`);
  if (opts.only === 'deck') return { deck: dirs.deckHtml };

  log.step('2/4  Narrate');
  const narration = await narrateAll(cfg, dirs, bins, { force: opts.force });
  if (opts.only === 'narrate') return { narration };

  log.step('3/4  Capture slides');
  await captureSlides(cfg, dirs, bins, { force: opts.force });
  if (opts.only === 'capture') return { slides: dirs.slides };

  log.step('4/4  Build video');
  const result = await buildVideo(cfg, dirs, bins, narration, { force: opts.force });

  const mins = Math.floor(result.duration / 60);
  const secs = Math.round(result.duration % 60);
  log.step('Done');
  console.log(`  file      ${result.output}`);
  console.log(`  duration  ${mins}:${String(secs).padStart(2, '0')}`);
  console.log(`  size      ${result.sizeMB.toFixed(1)} MB`);
  console.log(`  slides    ${result.segments}\n`);

  return result;
}

module.exports = { build, workDirs, ROOT };
