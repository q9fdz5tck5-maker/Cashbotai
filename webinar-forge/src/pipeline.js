'use strict';

const fs = require('fs');
const path = require('path');
const config = require('./config');
const deck = require('./deck');
const landing = require('./landing');
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
    site: path.join(work, 'site'),
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

  log.step('1/5  Render deck');
  fs.writeFileSync(dirs.deckHtml, deck.render(cfg));
  log.ok(`deck.html (${cfg.slides.length} slides)`);
  if (opts.only === 'deck') return { deck: dirs.deckHtml };

  log.step('2/5  Narrate');
  const narration = await narrateAll(cfg, dirs, bins, { force: opts.force });
  if (opts.only === 'narrate') return { narration };

  log.step('3/5  Capture slides');
  await captureSlides(cfg, dirs, bins, { force: opts.force });
  if (opts.only === 'capture') return { slides: dirs.slides };

  log.step('4/5  Build video');
  const result = await buildVideo(cfg, dirs, bins, narration, { force: opts.force });

  let site = null;
  if (cfg.landing) {
    log.step('5/5  Build landing page');
    site = buildSite(cfg, dirs, result.output);
    log.ok(`site -> ${site.dir}`);
  } else {
    log.info('no "landing" section in config — skipping landing page');
  }

  const mins = Math.floor(result.duration / 60);
  const secs = Math.round(result.duration % 60);
  log.step('Done');
  console.log(`  file      ${result.output}`);
  console.log(`  duration  ${mins}:${String(secs).padStart(2, '0')}`);
  console.log(`  size      ${result.sizeMB.toFixed(1)} MB`);
  console.log(`  slides    ${result.segments}`);
  if (site) {
    console.log(`  site      ${site.dir}`);
    console.log(`  serve     node bin/webinar-forge serve ${path.relative(process.cwd(), configPath) || configPath}`);
  }
  console.log('');

  return { ...result, site };
}

// The site directory is what gets deployed: one page plus the video, nothing
// else. The MP4 is copied rather than linked so the folder can be rsync'd or
// zipped as-is.
function buildSite(cfg, dirs, videoPath) {
  fs.mkdirSync(dirs.site, { recursive: true });

  const videoName = path.basename(videoPath);
  const html = landing.render({ ...cfg, __videoSrc: (cfg.landing || {}).videoSrc || videoName });
  fs.writeFileSync(path.join(dirs.site, 'index.html'), html);

  const target = path.join(dirs.site, videoName);
  if (!fs.existsSync(target) || fs.statSync(target).size !== fs.statSync(videoPath).size) {
    fs.copyFileSync(videoPath, target);
  }
  return { dir: dirs.site, videoName };
}

async function buildLandingOnly(configPath, opts = {}) {
  const cfg = config.load(configPath);
  if (!cfg.landing) {
    throw new Error(
      `No "landing" section in ${path.basename(configPath)}.\n` +
      `See projects/example/project.json for the full shape.`
    );
  }
  const outRoot = path.resolve(opts.output || process.env.OUTPUT_DIR || path.join(ROOT, 'output'));
  const dirs = workDirs(cfg, outRoot);
  const videoPath = path.join(dirs.dist, `${cfg.name}.mp4`);

  fs.mkdirSync(dirs.site, { recursive: true });
  const videoName = `${cfg.name}.mp4`;
  fs.writeFileSync(
    path.join(dirs.site, 'index.html'),
    landing.render({ ...cfg, __videoSrc: (cfg.landing || {}).videoSrc || videoName })
  );

  if (fs.existsSync(videoPath)) {
    fs.copyFileSync(videoPath, path.join(dirs.site, videoName));
    log.ok(`site -> ${dirs.site} (with video)`);
  } else {
    log.warn(`video not built yet — page references ${videoName}, which is missing`);
    log.info(`build it with:  node bin/webinar-forge build ${configPath}`);
  }
  return { dir: dirs.site, videoName };
}

module.exports = { build, buildLandingOnly, workDirs, ROOT };
