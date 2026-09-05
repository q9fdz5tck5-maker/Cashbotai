# Voice samples

Drop reference recordings here as `<name>.wav` (also accepts `.mp3`, `.m4a`, `.ogg`),
then reference the name in your project config:

```json
"voice": { "name": "my-voice" }
```

Or install one through the running engine, which preprocesses it immediately:

```bash
node bin/webinar-forge add-voice my-voice /path/to/sample.wav
```

## What makes a good sample

- **10–30 seconds.** Longer is not better; it mostly adds noise.
- **Clean speech.** No music, no second speaker, no room echo.
- **Normal delivery.** The clone copies energy and pacing, so record at the
  pace you want the webinar narrated.
- **Mono, 24 kHz or higher.** The engine downmixes and resamples anyway, but
  it cannot recover detail that was never recorded.

## Before you ship this

**This directory is intentionally empty in the distributed zip.** A voice sample
is all anyone needs to synthesize unlimited speech in that person's voice, so a
sample committed here travels to every server the zip lands on, and to everyone
who is ever handed a copy.

If you are packaging for other operators, leave it empty and let each of them
add their own voice. Only bake a sample in when every recipient of the zip is
meant to have that voice — and make sure the person it belongs to agreed to that.
