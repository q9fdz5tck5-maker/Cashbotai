# webinar-forge

A complete webinar funnel generator. One JSON config in; out comes a slide
presentation, narration in a locally cloned voice, a rendered MP4, and a sales
landing page that plays it. Runs entirely on this server — no external API
calls, no cloud TTS, no account needed.

If you are Claude working in this repo, this file is what you need to help the
operator. Read `README.md` for full detail.

## The one command

```bash
node bin/webinar-forge build projects/<name>/project.json
node bin/webinar-forge serve projects/<name>/project.json --port 8080
```

`build` produces `output/<name>/site/` — an `index.html` landing page plus the
`<name>.mp4` beside it. That folder is the deployable unit: serve it with the
built-in server, or copy it to any static host / nginx root.

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
  ├─ 4. src/video.js     png + mp3  -> ffmpeg   -> dist/<name>.mp4
  └─ 5. src/landing.js   landing[]  -> site/index.html + site/<name>.mp4

src/serve.js hosts site/ — page, video with Range/seek support, and
POST /register which appends opt-ins to output/<name>/registrations.jsonl.
```

Every stage caches, keyed to slide id. Editing one slide's narration
re-synthesizes only that slide. `--force` ignores caches, `--only
deck|narrate|capture` stops early.

## Editing a webinar

Everything lives in one `project.json`. Slides are data, not HTML — do not
hand-write deck markup. Each slide needs a `layout` and a `narration`; the
build refuses to start if either is missing.

Slide layouts: `title` `bullets` `stats` `compare` `quote` `myth` `pricing`
`faq` `cta` — defined in `src/deck.js`.

Landing sections (under `landing.sections`, each with a `type`): `hero`
`proof` `problem` `features` `stack` `pricing` `testimonials` `guarantee`
`deadline` `faq` `cta` — defined in `src/landing.js`. `hero` with
`"gate": true` hides the video behind an email opt-in.

`guarantee` and `deadline` state facts about your business, so they have no
defaults and stay out of a page until you fill them in:

- `guarantee` renders whatever refund terms you supply (`badge`, `headline`,
  `body`, `terms[]`). It never invents a policy — write only what you will
  actually honour.
- `deadline` counts down to one real ISO timestamp in `until`, and shows
  `expiredText` once it passes. There is no evergreen or per-visitor reset
  mode, on purpose: a clock that restarts for each viewer states something
  untrue about availability.

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

## Serving and leads

```bash
node bin/webinar-forge serve projects/<name>/project.json --port 8080
node bin/webinar-forge leads projects/<name>/project.json
```

The server is Node stdlib only. It serves the page, streams the MP4 with Range
support so viewers can seek, and captures opt-ins. It does **not** terminate
TLS — put nginx or Caddy in front for a public domain.

## Not included

No email sending (leads land in a JSONL file for the operator to export), and
no payment processing — pricing CTAs are plain links the operator points at
their own Stripe/PayPal/checkout URL. Say so plainly rather than implying
either exists.
