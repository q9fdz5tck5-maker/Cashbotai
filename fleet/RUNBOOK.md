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

## Not wired up

The affiliate link is used directly, as
`https://my.solidvps.com/aff.php?aff=579`, in `START-HERE.txt` and on the
closing slide of `webinars/what-is-this.json`.

A vanity redirect (`cash.bot/vps` → that URL) has **not** been built. It needs
access to wherever cash.bot is hosted, which this repository does not carry.
When it exists, the link appears in exactly those two files.
