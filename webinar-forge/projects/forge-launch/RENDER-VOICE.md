# Rendering the fleet act in your voice

The deck is now **56 slides**. Slides 1–36 are the original webinar.
Slides **40–56** are the fleet act. Slides 37–39 (pricing, FAQ, close) have been
moved to the end (indices 54–56) as a restructuring optimization for conversion.

This is the complete handoff for rendering on your GPU box.

---

## Critical: Audio cache resync before the build

The close triplet (slides s37, s38, s39) moved from their original indices 41–43
to new indices 54–56. Their cached MP3 files are still in the old locations:

```
output/forge-launch/audio/041-s37.mp3     (old location)
output/forge-launch/audio/042-s38.mp3     (old location)
output/forge-launch/audio/043-s39.mp3     (old location)
```

The build expects them at:

```
output/forge-launch/audio/054-s37.mp3     (new location)
output/forge-launch/audio/055-s38.mp3     (new location)
output/forge-launch/audio/056-s39.mp3     (new location)
```

**Before running `node bin/webinar-forge build`**, rename these files or the
entire deck will regenerate unnecessarily (~1 hour GPU cost for slides 1–39 alone).

### Resync script

```bash
cd webinar-forge/output/forge-launch/audio/

# Backup originals (optional, safe to delete after renaming succeeds)
cp 041-s37.mp3 041-s37.mp3.bak
cp 042-s38.mp3 042-s38.mp3.bak
cp 043-s39.mp3 043-s39.mp3.bak

# Rename to new indices
mv 041-s37.mp3 054-s37.mp3
mv 042-s38.mp3 055-s38.mp3
mv 043-s39.mp3 056-s39.mp3

# Also resync the stamps (metadata files)
mv 041-s37.mp3.json 054-s37.mp3.json
mv 042-s38.mp3.json 055-s38.mp3.json
mv 043-s39.mp3.json 056-s39.mp3.json
```

If the audio directory doesn't exist yet or the old files are missing, skip this
— they'll be generated fresh (no cache to resync).

---

## What will happen

After you resync the audio, the build will report:

```
[001] cached (27.8s)
...
[040] cached
[041] 127 words -> ...      <- fleet act slides start here (s44)
...
[053] 140 words -> ...
[054] cached (45.2s)        <- resynced close triplet
[055] cached (19.3s)
[056] cached (38.1s)
```

**Expected:** slides 1–40 + 54–56 report `cached` (if audio properly resynced);
slides 41–53 (13 fleet act slides) are newly narrated. That is roughly **13–15 minutes**
on a CUDA GPU rather than an hour.

If it starts generating slides 1–40, something changed that should not have —
diff `projects/forge-launch/project.json` against the previous commit before
spending the GPU time. If it regenerates 54–56 after resyncing, the stamp
mismatch checker below will tell you why.

### Checking for stamp mismatches (optional safety check)

If you want to confirm which slides will regenerate before spending GPU time:

```bash
node -e '
const fs=require("fs"),crypto=require("crypto");
const d=JSON.parse(fs.readFileSync("projects/forge-launch/project.json","utf8"));
d.slides.forEach((s,i)=>{
  const p=`output/forge-launch/audio/${String(i+1).padStart(3,"0")}-${s.id}.mp3.json`;
  if(!fs.existsSync(p)) return console.log(`[${String(i+1).padStart(3,"0")}] ${s.id}: no audio yet`);
  const st=JSON.parse(fs.readFileSync(p,"utf8"));
  const h=crypto.createHash("sha256").update(s.narration).digest("hex");
  if(st.hash!==h) console.log(`[${String(i+1).padStart(3,"0")}] ${s.id}: STALE — will regenerate`);
  else console.log(`[${String(i+1).padStart(3,"0")}] ${s.id}: ✓ cached`);
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

# Resync the audio cache BEFORE starting the engine (see above for the renaming script)
cd projects/forge-launch
# [run the Resync script from above]
cd ../..

./engine/start.sh                  # chatterbox, CUDA
node bin/webinar-forge doctor      # expect: engine ok, voice "myvoice" listed
```

`doctor` must show the engine reachable and `myvoice` present before you build.
If it does not, nothing below will work and the error it prints is the real one.

```bash
node bin/webinar-forge build projects/forge-launch/project.json
```

The build will take roughly **15 minutes on a CUDA GPU** (13 new slides + validation).
The output `dist/forge-launch.mp4` will be roughly **27–28 minutes long**.

Output lands in `output/forge-launch/`:

| | |
|---|---|
| `dist/forge-launch.mp4` | the finished video (27–28 min, H.264 + AAC) |
| `site/index.html` | the sales page, with the video embedded |
| `audio/` | one MP3 per slide, plus its stamp (056 files after resync + build) |
| `slides/` | one PNG per slide (56 files) |

---

## Do not do these

- **Do not change the `voice` block.** `exaggeration` 0.15 and `cfgWeight` 0.5
  are tuned. Any change there re-synthesises all 56 slides. See `VOICE-NOTES.md`.
- **Do not re-record `myvoice.wav`** unless you mean to — same cost, all 56.
- **Do not run with `--force`** unless you want the full 15 minutes.
- **Do not edit narration on slides 1–40** or 54–56 while making unrelated changes.
  Every edited string is a slide that re-renders. The fleet act spans slides 41–53.

---

## Summary: what changed

**Original structure:** 43 slides, then 14 fleet act slides appended (s44–s57).
Total: 57 slides, two competing closes (Forge $297 at index 41, Fleet at end).

**Current structure:** Restructured for single unified offer (index 39 onward).
- Slides 1–36: unchanged (s1–s36, existing product content)
- Slides 37–39: Pricing triplet moved to end (s37 Forge pricing, s38 FAQ, s39 CTA)
- Slides 40–53: Fleet act content (13 slides: s44–s56)
- Slides 54–56: Close triplet (same s37–s39, but now at the end)

**Result:** 56 slides, one price anchor, one close. Better conversion.

**Cost:** Audio cache broken — the close triplet moved. Resync (above) fixes it.
