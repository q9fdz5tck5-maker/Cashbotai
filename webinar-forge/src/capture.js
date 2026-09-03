'use strict';
// Deck HTML -> one PNG per slide.
//
// Loads the deck from the filesystem via file:// — the original scripts spun up
// a python http.server on a fixed port for this, which collided whenever two
// builds ran at once. No server, no port, no collision.

const fs = require('fs');
const path = require('path');
const log = require('./log');

async function captureSlides(cfg, dirs, bins, { force = false } = {}) {
  fs.mkdirSync(dirs.slides, { recursive: true });

  const pending = cfg.slides.filter((s) => {
    const png = path.join(dirs.slides, `${String(s.index).padStart(3, '0')}-${s.id}.png`);
    return force || !fs.existsSync(png);
  });

  if (pending.length === 0) {
    log.info(`all ${cfg.slides.length} slide images cached`);
    return cfg.slides.map((s) => path.join(dirs.slides, `${String(s.index).padStart(3, '0')}-${s.id}.png`));
  }

  const puppeteer = require('puppeteer-core');
  const browser = await puppeteer.launch({
    executablePath: bins.chrome,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',   // small VPSes have a tiny /dev/shm
      '--disable-gpu',
      '--hide-scrollbars',
      `--window-size=${cfg.video.width},${cfg.video.height}`,
    ],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({
      width: cfg.video.width,
      height: cfg.video.height,
      deviceScaleFactor: 1,
    });
    await page.goto(`file://${dirs.deckHtml}`, { waitUntil: 'load', timeout: 60000 });

    // Fonts must be resolved before the first screenshot or slide 1 renders
    // in a fallback face while the rest render correctly.
    await page.evaluate(() => document.fonts && document.fonts.ready);

    for (const slide of cfg.slides) {
      const num = String(slide.index).padStart(3, '0');
      const png = path.join(dirs.slides, `${num}-${slide.id}.png`);
      if (!force && fs.existsSync(png)) {
        log.info(`[${num}] cached ${slide.id}.png`);
        continue;
      }

      const found = await page.evaluate((id) => window.showSlide(id), slide.id);
      if (!found) throw new Error(`Slide "${slide.id}" not present in rendered deck.`);

      await new Promise((r) => setTimeout(r, 120));
      await page.screenshot({ path: png, type: 'png' });
      log.ok(`[${num}] ${slide.id}.png`);
    }
  } finally {
    await browser.close();
  }

  return cfg.slides.map((s) =>
    path.join(dirs.slides, `${String(s.index).padStart(3, '0')}-${s.id}.png`));
}

module.exports = { captureSlides };
