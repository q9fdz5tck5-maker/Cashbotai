"""AI voice generation.

Engines are pluggable because the right one depends on what you are willing to
run and pay for:

``piper``   local neural TTS, free, good quality, needs the piper binary + a
            voice model on the box. This is the one to use on your own VPS.
``espeak``  local, instant, robotic. Useful for timing a webinar cut before you
            spend money on the real voice.
``http``    any REST voice API (ElevenLabs, OpenAI, PlayHT). You supply the
            URL, headers, and request shape, so no vendor is hard-coded.

Payload:
    text            required, the words to speak
    engine          piper | espeak | http   (default: piper)
    voice           engine-specific voice/model id
    output          output filename (default speech.wav / .mp3 for http)
    speed           engine-specific rate multiplier
    api             for engine=http: {url, method, headers, body_template, audio_field}
"""

import base64
import json
import os

from ..fleetlib.client import FleetClient, FleetError
from .common import HandlerError, require_binary, run_command, safe_join


def run(payload, ctx):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HandlerError("tts job has no 'text' to speak")

    engine = (payload.get("engine") or "piper").lower()
    if engine == "piper":
        return _piper(payload, ctx, text)
    if engine == "espeak":
        return _espeak(payload, ctx, text)
    if engine == "http":
        return _http_api(payload, ctx, text)
    raise HandlerError(
        "Unknown tts engine %r. Supported: piper, espeak, http." % engine
    )


def _piper(payload, ctx, text):
    binary = require_binary(
        "piper",
        "Install it with the bootstrap script's --with-tts flag, or see "
        "https://github.com/rhasspy/piper for the release binaries.",
    )
    voice = payload.get("voice") or os.environ.get("FLEET_PIPER_VOICE")
    if not voice:
        raise HandlerError(
            "piper needs a voice model: set payload.voice to the .onnx path, "
            "or FLEET_PIPER_VOICE on the worker."
        )
    if not os.path.exists(voice):
        raise HandlerError("piper voice model not found at %r" % voice)

    output = safe_join(ctx.workdir, payload.get("output") or "speech.wav")
    args = [binary, "--model", voice, "--output_file", output]
    if payload.get("speed"):
        # piper expresses speed as length_scale, where >1 is slower.
        args += ["--length_scale", str(round(1.0 / float(payload["speed"]), 4))]

    ctx.log("piper: synthesising %d characters" % len(text))
    import subprocess
    completed = subprocess.run(
        args, input=text.encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800,
    )
    if completed.returncode != 0:
        raise HandlerError(
            "piper failed (exit %d): %s"
            % (completed.returncode,
               completed.stdout.decode("utf-8", "replace")[-800:])
        )
    return _finish(ctx, output, engine="piper", voice=voice, characters=len(text))


def _espeak(payload, ctx, text):
    binary = require_binary("espeak-ng", "apt-get install -y espeak-ng")
    output = safe_join(ctx.workdir, payload.get("output") or "speech.wav")
    args = [binary, "-w", output]
    if payload.get("voice"):
        args += ["-v", str(payload["voice"])]
    if payload.get("speed"):
        args += ["-s", str(int(175 * float(payload["speed"])))]
    args.append(text)
    run_command(args, timeout=900, log=ctx.log)
    return _finish(ctx, output, engine="espeak", characters=len(text))


def _http_api(payload, ctx, text):
    """Call an arbitrary voice API described entirely by the payload."""
    api = payload.get("api") or {}
    url = api.get("url")
    if not url:
        raise HandlerError("engine=http needs payload.api.url")

    # Secrets come from the worker's environment, never from the job payload,
    # so an API key is never stored in the hub database or a job record.
    headers = {}
    for key, value in (api.get("headers") or {}).items():
        if isinstance(value, str) and value.startswith("env:"):
            env_name = value[4:]
            resolved = os.environ.get(env_name)
            if not resolved:
                raise HandlerError(
                    "header %r wants environment variable %s, which is not set "
                    "on this worker" % (key, env_name)
                )
            headers[key] = resolved
        else:
            headers[key] = value

    template = api.get("body_template") or {"text": "{{text}}"}
    body = json.loads(json.dumps(template).replace("{{text}}", json.dumps(text)[1:-1]))
    if payload.get("voice"):
        body.setdefault("voice", payload["voice"])

    ctx.log("http tts: POST %s" % url)
    client = FleetClient(url, timeout=300, extra_headers=headers)
    try:
        response = client.post("", body=body)
    except FleetError as exc:
        raise HandlerError("voice API rejected the request: %s" % exc)

    audio_field = api.get("audio_field", "audio")
    encoded = response.get(audio_field) if isinstance(response, dict) else None
    if not encoded:
        raise HandlerError(
            "voice API responded but had no %r field to read audio from. "
            "Response keys: %s"
            % (audio_field,
               ", ".join(response) if isinstance(response, dict) else type(response))
        )
    output = safe_join(ctx.workdir, payload.get("output") or "speech.mp3")
    with open(output, "wb") as handle:
        handle.write(base64.b64decode(encoded))
    return _finish(ctx, output, engine="http", characters=len(text))


def _finish(ctx, output, **extra):
    if not os.path.exists(output) or os.path.getsize(output) == 0:
        raise HandlerError(
            "tts engine reported success but produced no audio at %s" % output
        )
    artifact = ctx.artifact(output)
    result = {"audio": artifact, "bytes": os.path.getsize(output)}
    result.update(extra)
    return result
