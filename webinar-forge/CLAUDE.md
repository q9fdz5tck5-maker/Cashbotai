# webinar-forge

A webinar generator. One JSON config in, one narrated MP4 out, using a locally
cloned voice. Runs entirely on this server — no external API calls, no cloud
TTS, no account needed.

If you are Claude working in this repo, this file is what you need to help the
operator. Read `README.md` for full detail.

## The one command

```bash
node bin/webinar-forge build projects/<name>/project.json
# -> output/<name>/dist/<name>.mp4
```

## First-run checklist

Run this before anything else. It names exactly what is missing and how to fix
it, so prefer it over guessing:

```bash
node bin/webinar-forge doctor
```

Setup order on a fresh server:

1. `./install.sh` — ffmpeg, chromium, node deps. Does **not** install torch.
2. `npm run mock-engine` — a dependency-free stand-in that returns silent audio
   with realistic timings. Use it to prove the pipeline works before spending
   time on the ML install.
3. `./install.sh --engine` — installs torch + Chatterbox. Slow (several minutes,
   multi-GB). Only needed for real voice output.
4. `./engine/start.sh` — starts the real voice engine on :5651. First run also
   downloads model weights.
5. `node bin/webinar-forge add-voice <name> <sample.wav>` — 10–30s of clean
   speech. This is the voice clone step.

## How it fits together

```
project.json
  ├─ 1. src/deck.js      slides[]   -> deck.html
  ├─ 2. src/narrate.js   narration  -> voice engine (:5651) -> audio/*.mp3
  ├─ 3. src/capture.js   deck.html  -> chromium -> slides/*.png
  └─ 4. src/video.js     png + mp3  -> ffmpeg   -> dist/<name>.mp4
```

Every stage caches, keyed to slide id. Editing one slide's narration
re-synthesizes only that slide. `--force` ignores caches, `--only
deck|narrate|capture` stops early.

## Editing a webinar

Everything lives in one `project.json`. Slides are data, not HTML — do not
hand-write deck markup. Each slide needs a `layout` and a `narration`; the
build refuses to start if either is missing.

Layouts: `title` `bullets` `stats` `compare` `quote` `myth` `pricing` `faq` `cta`

`projects/example/project.json` is a small annotated example.
`projects/three-secrets-v8/project.json` is a real 37-slide deck.
`src/deck.js` is the reference for every layout's fields.

## Converting an existing deck

If the operator already has hand-built webinar HTML plus a narration JSON:

```bash
node tools/import-deck.js --html <deck.html> --narration <narration.json> \
  --name <name> --out projects/<name>/project.json
```

It reports what it mapped and lists anything it could not classify. Class names
are overridable (`--selector-slide`, `--selector-title`, `--selector-lie`, …).

## Things to know before changing code

- **Never hardcode binary paths.** ffmpeg, ffprobe and chromium resolve at
  runtime in `src/paths.js`. This package exists because the original was
  hardcoded to one Mac.
- **Capture reads `file://`.** Do not reintroduce a static server on a fixed
  port; concurrent builds collided that way before.
- **Slide ids drive filenames.** Cache keys use the id, not array position, so
  inserting a slide mid-deck does not invalidate the rest.
- **Dependencies are deliberately minimal** — `puppeteer-core` is the only Node
  dependency. Prefer stdlib over adding more.

## Voice engine

FastAPI on `127.0.0.1:5651`. Endpoints: `/health`, `/voices`, `/upload-sample`,
`DELETE /voices/{name}`, `/preprocess-voices`, `/synthesize`.

Device auto-detects CUDA → MPS → CPU. CPU works but is slow — hours for a long
deck. `exaggeration 0.15` and `cfgWeight 0.5` are tuned defaults; raising
exaggeration makes delivery theatrical and inconsistent between slides.

**It has no authentication.** Anyone who can reach the port can synthesize any
installed voice. Keep it on loopback unless there is an authenticating proxy in
front of it.

## Voice samples are not distributed

`engine/voices/` is empty in the zip, and `make-zip.sh` excludes audio from it.
A sample is all anyone needs to generate unlimited speech in that person's
voice. Each operator adds their own. Do not commit or bundle samples unless the
person they belong to agreed to that specific distribution.

## Not included

There is no landing page builder, no video hosting/player page, no email
campaign step and no checkout. This package generates the webinar video and
stops. Say so plainly if the operator asks for those.
