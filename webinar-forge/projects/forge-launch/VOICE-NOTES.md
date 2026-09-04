# Reducing the regional accent on forge-launch

There is no accent setting. The clone reproduces whatever is in the sample, so
there are exactly three levers. They are listed in order of effect, and that is
also the order you should pull them in.

Current state of the deck:

- `voice.exaggeration` = 0.15, `voice.cfgWeight` = 0.5 — **unchanged**, deliberately.
- `engine/voices/myvoice.wav` — 84 s, mono, 16 kHz PCM.
- `tts.pronunciation` — unchanged. After the de-jargon rewrite only three of its
  entries are still exercised by the script (`nginx`, `CUDA`, `TLS`), all inside
  the FAQ. The rest are harmless and worth keeping for future decks.

---

## Lever A — the sample (biggest, and the only one that needs you)

The clone mirrors the sample's *delivery*, not just its timbre. A neutral sample
is the whole game. Everything below is about how you read, not what you say.

**Re-record `engine/voices/myvoice.wav`:**

- 30–60 s is plenty. The current sample is 84 s, which is longer than this tool's
  own guidance (10–30 s) — length past a point adds drawl to copy, not clarity.
- Read **slower than feels natural**. Roughly 15% slower than conversation.
- Keep long vowels short and flat. The drawl lives in *I*, *my*, *time*, *right*,
  *down*, *out*, *about* — clip them.
- **No upspeak.** Every sentence ends flat or falling, never rising.
- Flat, even energy. Do not perform it. Broadcast-neutral, not enthusiastic —
  the deck gets its energy from the writing, not from the sample.
- Quiet room, one mic position, no processing, no music, no room echo.
- Mono, 16-bit, 24 kHz if you can (the engine resamples to 24 kHz anyway).

**A read script that exercises the sounds without inviting the drawl.** It is
deliberately flat and boring — that is the point:

> The system builds a complete presentation from a single file. It reads the
> text, renders each slide in order, and writes the finished video to disk.
> Setup takes about twenty minutes on a standard machine. There are no accounts
> to create and no monthly fees to track. Each section is stored separately, so
> a correction to one line changes only that line. The output is a single folder
> you can copy anywhere. Nothing is uploaded, and nothing is shared without your
> instruction. That is the entire process, start to finish.

Install it:

```bash
node bin/webinar-forge add-voice myvoice <new-sample.wav>
```

**Cost:** re-recording the sample changes the audio for every slide, so the next
build re-synthesizes **all 39**. Budget for that — hours on CPU, 5–15 minutes on
a CUDA GPU.

---

## Lever B — the pronunciation dictionary (surgical, free)

`cfg.tts.pronunciation` maps a string to a phonetic respelling. This is the
right tool for the two or three specific words where the accent lands hardest,
*after* you have heard a render.

Do this **after** a test build, not before — respelling a word you have not
actually heard go wrong usually makes it worse. Listen, note the exact words,
then add entries like:

```json
"oil":   "oyl",
"about": "uh bout"
```

**Cost:** only the slides containing that word re-synthesize. This is the cheap
lever, which is why it comes after the sample and before the parameters.

---

## Lever C — the parameters (blunt, expensive) — NOT CHANGED

```json
"voice": { "exaggeration": 0.15, "cfgWeight": 0.5 }
```

- Raising `cfgWeight` tightens adherence to the sample.
- Raising `exaggeration` makes delivery more theatrical and, per the tool's own
  `CLAUDE.md`, less consistent between slides. A higher-energy read might want
  ~0.3.

**Any change here re-synthesizes all 39 slides.** So if you want to try it, test
on 2–3 slides first:

```bash
# copy the project, keep only slides 1, 14 and 39, change the params there,
# build that, and listen before touching the real deck.
```

These were left at the tuned defaults because the brief was explicit that a
parameter change is a deliberate, separate decision — and because the accent
problem is a *sample* problem, not a parameter problem. Pulling lever C to fix
something lever A causes costs a full re-render and does not fix it.
