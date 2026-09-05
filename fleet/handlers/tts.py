"""AI voice generation.

Engines are pluggable because the right one depends on what you are willing to
run and pay for:

``piper``   local neural TTS, free, good quality, needs the piper binary + a
            voice model on the box. This is the one to use on your own VPS.
``espeak``  local, instant, robotic. Useful for timing a webinar cut before you
            spend money on the real voice.
``http``    any REST voice API (ElevenLabs, OpenAI, PlayHT). You supply the
            URL, headers, and request shape, so no vendor is hard-coded.
``clone``   your own voice, spoken by a webinar-forge engine box running
            chatterbox or f5. The reference recording never leaves that
            machine -- the job sends words and a voice *name*, nothing else.

Payload:
    text            required, the words to speak
    engine          piper | espeak | http   (default: piper)
    voice           engine-specific voice/model id
    output          output filename (default speech.wav / .mp3 for http)
    speed           engine-specific rate multiplier
    api             for engine=http: {url, method, headers, body_template, audio_field}
                    for engine=clone: {url, engine, exaggeration, cfg_weight}
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
    if engine in ("clone", "forge"):
        return _clone(payload, ctx, text)
    raise HandlerError(
        "Unknown tts engine %r. Supported: piper, espeak, http, clone." % engine
    )


def _multipart(fields):
    """Encode form fields the way FastAPI's ``Form(...)`` expects.

    Written out by hand because the fleet is standard library only, and
    because the alternative -- shelling out to curl -- would put the narration
    text on a command line where it lands in the process table.
    """
    boundary = "----fleet%s" % base64.urlsafe_b64encode(os.urandom(12)).decode().strip("=")
    lines = []
    for name, value in fields.items():
        if value is None:
            continue
        lines.append(("--%s\r\n" % boundary).encode("utf-8"))
        lines.append(
            ('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode("utf-8")
        )
        lines.append(str(value).encode("utf-8"))
        lines.append(b"\r\n")
    lines.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(lines), "multipart/form-data; boundary=%s" % boundary


def _clone(payload, ctx, text):
    """Speak in a cloned voice via a webinar-forge engine box.

    The engine holds the reference recording and answers with raw WAV bytes.
    Only the words and the voice's *name* cross the wire, so the sample stays
    on the one machine that needs it rather than being copied into every job
    record and every worker's scratch directory.
    """
    api = payload.get("api") or {}
    url = (api.get("url") or os.environ.get("FLEET_VOICE_URL") or "").rstrip("/")
    if not url:
        raise HandlerError(
            "engine=clone needs the voice engine's address: set payload.api.url "
            "or FLEET_VOICE_URL on this worker (e.g. http://voice-01:8001)."
        )
    voice = payload.get("voice") or os.environ.get("FLEET_VOICE_NAME")
    if not voice:
        raise HandlerError(
            "engine=clone needs a 'voice' name -- whichever sample is loaded "
            "on the engine box. Ask it: GET %s/voices" % url
        )

    body, content_type = _multipart({
        "text": text,
        "voice": voice,
        "engine": api.get("engine", "chatterbox"),
        "exaggeration": api.get("exaggeration"),
        "cfg_weight": api.get("cfg_weight"),
    })

    ctx.log("clone: %d characters as %r via %s" % (len(text), voice, url))
    client = FleetClient(url, timeout=int(api.get("timeout", 1800)))
    try:
        audio = client.post_bytes("/synthesize", body,
                                  headers={"Content-Type": content_type,
                                           "Accept": "audio/wav"},
                                  raw=True)
    except FleetError as exc:
        raise HandlerError(
            "voice engine at %s refused the request: %s\n"
            "Check it is running and that voice %r exists (GET %s/voices)."
            % (url, exc, voice, url)
        )
    if not audio:
        raise HandlerError("voice engine returned an empty response")
    if audio[:4] != b"RIFF":
        # A JSON error body decoded as audio would otherwise be written to
        # disk as a .wav and fail much later, in ffprobe, with no clue why.
        raise HandlerError(
            "voice engine did not return WAV audio. First bytes: %r"
            % audio[:80]
        )

    output = safe_join(ctx.workdir, payload.get("output") or "speech.wav")
    with open(output, "wb") as handle:
        handle.write(audio)
    return _finish(ctx, output, engine="clone", voice=voice,
                   characters=len(text))


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
