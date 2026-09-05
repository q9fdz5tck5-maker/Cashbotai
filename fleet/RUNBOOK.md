# Running this fleet

Notes for the person who owns this repository. The giveaway bundle stays
generic on purpose — everything specific to us lives here instead.

## Our hub

    hub.cash.bot

Point that name at the hub box first, then:

    sudo bash deploy/bootstrap_hub.sh --domain hub.cash.bot

It prints an admin token and an enrolment token, once. They also land in
`/etc/fleet-hub.env` on that machine, mode 600. Nothing in this repository
contains them and nothing should.

Driving it from anywhere:

    export FLEET_HUB=https://hub.cash.bot
    export FLEET_TOKEN=<admin token>
    python3 fleet.py status

## Why the bundle does not say hub.cash.bot

`pack/setup.sh` asks each recipient for their own address and defaults to a
placeholder. If the bundle shipped our hostname, a recipient pasting the
example would quietly point their workers at *our* hub — and they would
appear in *our* `fleet status` rather than their own. That is a correctness
bug, not a style preference, so the two are kept apart.

## Building the tutorial video

    python3 fleet.py webinar webinars/what-is-this.json

Needs a worker carrying the `webinar` role with ffmpeg, and a voice. For
piper, put the model on the worker and point `FLEET_PIPER_VOICE` at it:

    FLEET_PIPER_VOICE=/opt/voices/en_US-amy-medium.onnx

The model is `en_US-amy-medium` from the `rhasspy/piper-voices` repository on
HuggingFace. The script names `piper` as its engine but no voice path, so the
script stays portable and the machine decides which voice it has.

## Narrating in my own voice

The tutorial video currently shipped in `webinars/out/` is narrated by
**piper's stock `en_US-amy-medium`**, not by the clone. It was built before the
clone path existed.

To rebuild it in the real voice:

1. On a box with a GPU, run the webinar-forge engine from
   `claude/webinar-forge-video-rebuild-innj40` (`engine/requirements.txt`;
   install the matching CUDA torch build first). Put `myvoice.wav` in
   `engine/voices/` -- it lives on `claude/webinar-voice-synthesis-5pcn6y`.
2. Give that box the `audio` role and point it at the engine:

       FLEET_VOICE_URL=http://127.0.0.1:8001
       FLEET_VOICE_NAME=myvoice

3. Switch the script's engine and rebuild:

       "engine": "clone", "voice": "myvoice"
       python3 fleet.py webinar webinars/what-is-this.json

Two things about the sample worth fixing while you are there. It is 84 seconds
at 16 kHz; forge's own `voices/README.md` asks for 10-30 seconds at 24 kHz or
better, because the clone copies pacing and energy and cannot recover detail
that was never recorded. A shorter, cleaner, higher-rate take will sound
markedly better than this one.

**Chatterbox does not install in the Claude build sandbox.** `chatterbox-tts`
pulls `antlr4-python3-runtime==4.9.3`, which ships no wheel and whose
`setup.py` fails against modern setuptools. That is a sandbox limitation, not
a fleet one -- the engine is meant to run on your CUDA box regardless.

## Not wired up

The affiliate link is used directly, as
`https://my.solidvps.com/aff.php?aff=579`, in `START-HERE.txt` and on the
closing slide of `webinars/what-is-this.json`.

A vanity redirect (`cash.bot/vps` → that URL) has **not** been built. It needs
access to wherever cash.bot is hosted, which this repository does not carry.
When it exists, the link appears in exactly those two files.
