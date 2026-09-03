# webinar-forge

Turns a JSON config into a narrated webinar video: slide deck, cloned-voice
narration, rendered MP4. One command, repeatable, no Mac required.

```bash
node bin/webinar-forge build projects/my-webinar/project.json
# -> output/my-webinar/dist/my-webinar.mp4
```

This is a portable repackaging of a pipeline that previously existed as a set
of per-webinar scripts. See [Origin](#origin) for what changed and why.

---

## What it does

```
project.json
    │
    ├─ 1. render deck    slides[]  ──────────────►  deck.html
    │
    ├─ 2. narrate        narration ──► voice engine ──►  audio/NNN.mp3
    │                                  (Chatterbox / F5-TTS, local)
    │
    ├─ 3. capture        deck.html ──► chromium ──►  slides/NNN.png
    │
    └─ 4. build video    png + mp3 ──► ffmpeg  ──►  dist/<name>.mp4
```

Every stage caches. Re-running only redoes what changed, so fixing one line of
narration re-synthesizes one slide instead of the whole deck. `--force` ignores
the cache; `--only deck|narrate|capture` stops early.

## Requirements

| | |
|---|---|
| Node.js | 18 or newer |
| Python | 3.9+ (voice engine only) |
| ffmpeg | with libx264 and libmp3lame |
| chromium | or Chrome, for slide capture |
| GPU | optional — CUDA or Apple MPS. CPU works, slowly. |

`./install.sh` handles all of it on Debian/Ubuntu and macOS.

## Commands

```
webinar-forge build <project.json>       build a webinar
  --output <dir>                         artifact directory (default ./output)
  --force                                ignore all caches
  --only deck|narrate|capture            stop after a stage

webinar-forge doctor                     check this machine can build
webinar-forge voices                     list installed voices
webinar-forge add-voice <name> <sample>  install a voice sample
webinar-forge init <dir>                 scaffold a project from the example
```

## The project config

One file defines the whole webinar. `projects/example/project.json` is a
complete working example.

```jsonc
{
  "name": "my-webinar",            // filename-safe; names the output
  "brand": { "product": "…", "accent": "#f5c518" },
  "voice": { "name": "my-voice", "engine": "chatterbox",
             "exaggeration": 0.15, "cfgWeight": 0.5 },
  "video": { "width": 1920, "height": 1080, "fps": 30, "padSeconds": 1.0 },
  "tts":   { "applyCompliance": true,
             "pronunciation": { "mysite.com": "my site dot com" } },
  "slides": [
    { "layout": "title", "headline": "…", "narration": "…" }
  ]
}
```

Every slide needs a `layout` and a `narration`. The build refuses to start if
one is missing, rather than shipping a silent slide.

### Layouts

`title` · `bullets` · `stats` · `compare` · `quote` · `myth` · `pricing` · `faq` · `cta`

`myth` is the false-belief beat — state the lie, stamp it wrong, replace it
with the truth:

```json
{ "layout": "myth",
  "kicker": "Secret 1 of 3",
  "lie": "\"Shipping a website is a 14-step nightmare.\"",
  "stamp": "WRONG",
  "truth": "The truth: shipping is one sentence.",
  "narration": "…" }
```

Wrap text in `[ACCENT]…[/ACCENT]` to colour it. Layout fields are documented by
example in `projects/example/project.json`, and `src/deck.js` is the reference.

### Voice tuning

`exaggeration` 0.15 and `cfgWeight` 0.5 are the values the original pipeline
settled on after testing. Low exaggeration keeps a presenter voice steady over
a long deck; raising it makes delivery theatrical and inconsistent between
slides. Change one variable at a time on a single slide (`--only narrate`).

### Pronunciation and compliance

`tts.pronunciation` rewrites text before synthesis, so a domain is spoken
rather than spelled. Longest key wins, so `"site.com/order"` beats `"site.com"`.

`tts.applyCompliance` (on by default) rewrites guarantee language to
"satisfaction policy" in the **spoken audio only** — your slides are untouched.
It is a convenience, not legal review. Set your own rules with `tts.compliance`,
or `"applyCompliance": false` to disable. What you claim in a sales asset is
yours to get right.

## Importing an existing deck

If you already have hand-built decks, `tools/import-deck.js` converts one into
a project config. Narration is carried across verbatim; headings, kickers,
stats, bullets and myth beats are mapped where recognised.

```bash
node tools/import-deck.js \
  --html      path/to/webinar-3secrets-v8.html \
  --narration path/to/narration-3sv8.json \
  --name      three-secrets-v8 \
  --out       projects/three-secrets-v8/project.json
```

It reports what it produced and lists anything it could not classify, so you
know exactly which slides to review:

```
Imported 37 slides -> projects/three-secrets-v8/project.json
Narration: 2164 words (~14 min spoken)
Layouts: stats=1 title=30 bullets=1 myth=3 cta=2
```

Override the class names with `--selector-slide`, `--selector-title`,
`--selector-lie` and friends if a deck uses different markup. It is a
structural import, not a pixel-perfect one — expect to adjust layouts
afterwards, which is the point: after importing once, the deck is data.

`projects/three-secrets-v8/` is a real 37-slide deck imported this way, kept
as a second worked example.

## Performance

TTS dominates. Rough figures for a 40-slide deck:

| Hardware | Narration | Video render |
|---|---|---|
| CUDA GPU | 5–15 min | 3–8 min |
| Apple silicon (MPS) | 15–40 min | 5–12 min |
| CPU only | hours | 5–15 min |

Tune with `TTS_CONCURRENCY` (1 on CPU, 2–4 on a GPU) and `RENDER_CONCURRENCY`
(match CPU cores; lower it on a small VPS).

## Security

**The voice engine has no authentication.** Anyone who can reach port 5651 can
synthesize any installed voice. It binds to `127.0.0.1` by default and the
compose file publishes it loopback-only. Keep it that way unless you put an
authenticating proxy in front.

**Voice samples are not in the zip.** A sample is all anyone needs to generate
unlimited speech in that person's voice. `make-zip.sh` excludes
`engine/voices/*` so each operator adds their own. `--with-voices` overrides
this — only use it when every recipient is meant to have that voice, and the
person it belongs to agreed.

## Building the zip

```bash
./make-zip.sh                 # webinar-forge-1.0.0.zip, no voices
./make-zip.sh --with-voices   # includes samples — read the warning above
```

Excludes `node_modules`, `output`, the engine venv, `.env` and `.git`. It
expands into a single `webinar-forge/` directory on the target server.

## Origin

Repackaged from the `cash-bot` pipeline: the voice engine from
`apps/phone.cash.bot/voice-engine/`, narration from
`marketing/webinar/generate-narration.js`, and video assembly from
`apps/webinar.cash.bot/scripts/build-v*-video.js`.

What changed to make it portable and repeatable:

- **Paths resolve at runtime.** `/opt/homebrew/bin/ffmpeg`,
  `/Applications/Google Chrome.app`, `/Volumes/srv/...` and
  `/tmp/webinar-capture/node_modules` are gone. See `src/paths.js`.
- **Slides are data.** Each webinar previously needed its own 50–96 KB
  hand-written HTML file *and* its own build script hardcoded to that deck's
  slide count and CSS selectors. Now layouts are shared and slides are JSON.
- **No static server.** Capture reads `file://` instead of spawning
  `python3 -m http.server` on a fixed port, which collided between builds.
- **Every stage caches and resumes**, keyed to slide id rather than array
  position, so inserting a slide mid-deck does not invalidate the rest.
- **The engine is trimmed** to the cloning API. The Twilio media WebSocket,
  the phone agent and its persona prompt were dropped, along with the
  `anthropic`, `faster-whisper` and `websockets` dependencies.
- **A mock engine** ships alongside it, so the pipeline can be validated
  before torch is installed.

The original decks still work: point `capture.js` at any HTML that exposes
`window.showSlide(id)` and uses `.slide` elements.
