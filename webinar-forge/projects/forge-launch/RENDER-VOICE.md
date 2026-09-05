# Rendering the fleet act in your voice

The deck is now **57 slides**. Slides 1–43 are the original webinar and are
unchanged. Slides **s44–s57** are the new fleet act and have never been narrated.

This file is the whole handoff. Run it on the machine with the graphics card.

---

## What will happen

`narrate.js` keeps a stamp beside every MP3 recording the hash of the narration
text plus the voice settings that produced it. It skips any slide whose stamp
still matches. Because the new act was **appended** — no existing narration
string was touched, and the `voice` block was not touched — the existing audio
stays valid.

So the build should report:

```
[001] cached (27.8s)
[002] cached (35.1s)
...
[044] 133 words -> ...      <- the new act starts here
...
[057] 130 words -> ...
```

**43 cached, 14 generated.** That is roughly 15 minutes on a CUDA GPU rather
than the hour a full re-render costs.

If it starts generating slide 1, stop it. Something changed that should not
have — diff `projects/forge-launch/project.json` against the previous commit
before spending the GPU time.

### One slide will regenerate that you did not expect

`s38` (the FAQ, slide 42) has a **stale stamp** on this branch — its narration
was edited after its audio was last made. That is pre-existing and unrelated to
the fleet act. Expect **44 generated, not 14**, or re-check it first:

```bash
node -e '
const fs=require("fs"),crypto=require("crypto");
const d=JSON.parse(fs.readFileSync("projects/forge-launch/project.json","utf8"));
d.slides.forEach((s,i)=>{
  const p=`output/forge-launch/audio/${String(i+1).padStart(3,"0")}-${s.id}.mp3.json`;
  if(!fs.existsSync(p)) return console.log(`${s.id}: no audio yet`);
  const st=JSON.parse(fs.readFileSync(p,"utf8"));
  const h=crypto.createHash("sha256").update(s.narration).digest("hex");
  if(st.hash!==h) console.log(`${s.id}: STALE — will regenerate`);
});'
```

---

## Run it

```bash
git fetch origin
git checkout claude/fleet-packaging-webinar-yb1b0c
cd webinar-forge
npm install

# the voice sample is not on this branch — it lives on the branch that made it
git show origin/claude/webinar-voice-synthesis-5pcn6y:webinar-forge/engine/voices/myvoice.wav \
  > engine/voices/myvoice.wav

./engine/start.sh                  # chatterbox, CUDA
node bin/webinar-forge doctor      # expect: engine ok, voice "myvoice" listed
```

`doctor` must show the engine reachable and `myvoice` present before you build.
If it does not, nothing below will work and the error it prints is the real one.

```bash
node bin/webinar-forge build projects/forge-launch/project.json
```

Output lands in `output/forge-launch/`:

| | |
|---|---|
| `dist/forge-launch.mp4` | the finished video |
| `site/index.html` | the sales page, with the video already in it |
| `audio/` | one MP3 per slide, plus its stamp |
| `slides/` | one PNG per slide |

---

## Do not do these

- **Do not change the `voice` block.** `exaggeration` 0.15 and `cfgWeight` 0.5
  are tuned. Any change there re-synthesises all 57 slides. See `VOICE-NOTES.md`.
- **Do not re-record `myvoice.wav`** unless you mean to — same cost, all 57.
- **Do not run with `--force`** unless you want the full hour.
- **Do not edit narration on slides 1–43** while making unrelated changes. Every
  edited string is a slide that re-renders.

## If you want to hear the new act before committing GPU time

The mock engine returns correctly-timed silence, so you can check pacing and
slide timing for free:

```bash
python3 engine/mock_engine.py &
node bin/webinar-forge build projects/forge-launch/project.json --output /tmp/preview
```

Build mock output to a **separate directory**, as above. A mock MP3's stamp is
indistinguishable from a real one, so mock audio landing in
`output/forge-launch/audio/` would silently cache as real and ship silence.
