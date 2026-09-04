'use strict';
// Slide PNGs + narration MP3s -> final MP4.
//
// Each slide becomes an MPEG-TS segment, then all segments are concatenated
// with -c copy. Encoding per-segment keeps the work parallel and lets a failed
// build resume without re-rendering slides that already succeeded.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile, execFileSync } = require('child_process');
const log = require('./log');

// A segment's existence says nothing about which audio or image is inside it.
// Narration is cache-stamped in narrate.js, so editing one slide correctly
// re-synthesizes that mp3 — but without the same treatment here the video stage
// would reuse the segment built from the *previous* audio and silently ship a
// video that does not contain the edit. Stamp each segment with its inputs.
function inputSig(file) {
  try {
    const st = fs.statSync(file);
    return `${path.basename(file)}:${st.size}:${Math.floor(st.mtimeMs)}`;
  } catch {
    return `${path.basename(file)}:missing`;
  }
}

function segmentStamp(cfg, job) {
  const v = cfg.video;
  return crypto.createHash('sha256').update(JSON.stringify({
    audio: inputSig(job.audio),
    png: inputSig(job.png),
    duration: job.duration.toFixed(3),
    enc: [v.width, v.height, v.fps, v.crf, v.preset, v.audioBitrate, v.fadeSeconds],
  })).digest('hex');
}

function stampMatches(stampPath, stamp) {
  try {
    return fs.readFileSync(stampPath, 'utf8').trim() === stamp;
  } catch {
    return false;
  }
}

function run(bin, args) {
  return new Promise((resolve, reject) => {
    execFile(bin, args, { maxBuffer: 1 << 26 }, (err, stdout, stderr) => {
      if (err) reject(new Error(`${path.basename(bin)} failed: ${String(stderr).slice(-800)}`));
      else resolve(stdout);
    });
  });
}

function segmentArgs(cfg, pngPath, audioPath, duration, outPath) {
  const { width, height, fps, crf, preset, audioBitrate, fadeSeconds } = cfg.video;
  const fadeOut = Math.max(0, duration - fadeSeconds);

  return [
    '-y',
    '-loop', '1', '-framerate', String(fps), '-i', pngPath,
    '-i', audioPath,
    '-filter_complex',
    `[0:v]scale=${width}:${height}:force_original_aspect_ratio=decrease,` +
      `pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2,setsar=1,` +
      `fade=t=in:st=0:d=0.4,fade=t=out:st=${fadeOut.toFixed(3)}:d=${fadeSeconds}[v];` +
    `[1:a]apad=whole_dur=${duration.toFixed(3)},` +
      `afade=t=in:st=0:d=0.25,afade=t=out:st=${fadeOut.toFixed(3)}:d=${fadeSeconds}[a]`,
    '-map', '[v]', '-map', '[a]',
    '-c:v', 'libx264', '-preset', preset, '-tune', 'stillimage', '-crf', String(crf),
    '-r', String(fps), '-g', String(fps * 2), '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', audioBitrate, '-ar', '48000', '-ac', '2',
    '-t', duration.toFixed(3),
    '-f', 'mpegts',
    outPath,
  ];
}

async function buildVideo(cfg, dirs, bins, narration, { force = false } = {}) {
  fs.mkdirSync(dirs.segments, { recursive: true });
  fs.mkdirSync(dirs.dist, { recursive: true });

  const jobs = cfg.slides.map((slide, i) => {
    const num = String(slide.index).padStart(3, '0');
    const audio = narration[i];
    if (!audio || !audio.duration) {
      throw new Error(`No narration audio for slide ${slide.index} (${slide.id}).`);
    }
    return {
      num,
      id: slide.id,
      png: path.join(dirs.slides, `${num}-${slide.id}.png`),
      audio: audio.mp3Path,
      duration: audio.duration + (slide.padSeconds ?? cfg.video.padSeconds),
      out: path.join(dirs.segments, `seg-${num}.ts`),
    };
  });

  for (const job of jobs) {
    if (!fs.existsSync(job.png)) throw new Error(`Missing slide image: ${job.png}`);
  }

  const concurrency = Math.max(1, parseInt(process.env.RENDER_CONCURRENCY || '4', 10));
  log.info(`rendering ${jobs.length} segments (concurrency=${concurrency})`);

  let cursor = 0;
  let done = 0;
  async function worker() {
    while (cursor < jobs.length) {
      const job = jobs[cursor++];
      const stamp = segmentStamp(cfg, job);
      const stampPath = `${job.out}.sig`;
      if (!force && fs.existsSync(job.out) && fs.statSync(job.out).size > 1024 &&
          stampMatches(stampPath, stamp)) {
        done++;
        log.info(`[${done}/${jobs.length}] cached seg-${job.num}.ts`);
        continue;
      }
      const t0 = Date.now();
      await run(bins.ffmpeg, segmentArgs(cfg, job.png, job.audio, job.duration, job.out));
      fs.writeFileSync(stampPath, stamp);
      done++;
      const mb = (fs.statSync(job.out).size / 1048576).toFixed(1);
      log.ok(`[${done}/${jobs.length}] seg-${job.num}.ts ${job.duration.toFixed(1)}s ${mb}MB in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, jobs.length) }, () => worker()));

  const listPath = path.join(dirs.work, 'concat.txt');
  fs.writeFileSync(listPath, jobs.map((j) => `file '${j.out.replace(/'/g, "'\\''")}'`).join('\n'));

  const output = path.join(dirs.dist, `${cfg.name}.mp4`);
  log.info('concatenating segments…');
  await run(bins.ffmpeg, [
    '-y', '-f', 'concat', '-safe', '0', '-i', listPath,
    '-c', 'copy', '-movflags', '+faststart',
    output,
  ]);

  const duration = parseFloat(
    execFileSync(bins.ffprobe, [
      '-v', 'error', '-show_entries', 'format=duration',
      '-of', 'default=noprint_wrappers=1:nokey=1', output,
    ]).toString().trim()
  ) || 0;

  return {
    output,
    duration,
    sizeMB: fs.statSync(output).size / 1048576,
    segments: jobs.length,
  };
}

module.exports = { buildVideo };
