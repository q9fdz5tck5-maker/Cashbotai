"""Video rendering via ffmpeg.

Modes:
    slideshow   images + an audio track -> a narrated video
    concat      join several clips into one
    transcode   re-encode / resize / change container
    raw         your own ffmpeg argument list, for anything the above misses

Every mode ends up as one ffmpeg invocation, so failures surface as ffmpeg's
own message rather than a generic "render failed".
"""

import json
import os

from .common import (HandlerError, media_duration, require_binary,
                     run_command, safe_join)

DEFAULT_VIDEO_ARGS = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                      "-preset", "medium"]
DEFAULT_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]


def run(payload, ctx):
    require_binary("ffmpeg", "apt-get install -y ffmpeg")
    mode = (payload.get("mode") or "slideshow").lower()
    handlers = {
        "slideshow": _slideshow,
        "concat": _concat,
        "transcode": _transcode,
        "raw": _raw,
    }
    if mode not in handlers:
        raise HandlerError(
            "Unknown render mode %r. Supported: %s"
            % (mode, ", ".join(sorted(handlers)))
        )
    return handlers[mode](payload, ctx)


def _fetch_inputs(payload, ctx):
    """Materialise every input the job references into the working directory."""
    local = []
    for spec in payload.get("inputs") or []:
        local.append(ctx.fetch(spec))
    return local


def _output_path(payload, ctx, default):
    return safe_join(ctx.workdir, payload.get("output") or default)


def _slideshow(payload, ctx):
    """Images (with per-slide durations) plus narration -> one MP4."""
    slides = payload.get("slides") or []
    if not slides:
        raise HandlerError(
            "slideshow render needs a 'slides' list of {image, duration}"
        )
    audio_spec = payload.get("audio")
    resolution = payload.get("resolution", "1920x1080")
    fps = int(payload.get("fps", 30))
    output = _output_path(payload, ctx, "webinar.mp4")

    # ffconcat is the reliable way to hold each still for an exact duration.
    entries = []
    total = 0.0
    for index, slide in enumerate(slides):
        image = ctx.fetch(slide.get("image"))
        duration = float(slide.get("duration", 5))
        if duration <= 0:
            raise HandlerError("slide %d has a non-positive duration" % index)
        total += duration
        entries.append("file '%s'\nduration %s" % (image.replace("'", r"\'"), duration))
    # The concat demuxer needs the final image repeated or it drops the last slide.
    entries.append("file '%s'" % ctx.fetch(slides[-1].get("image")).replace("'", r"\'"))

    list_path = safe_join(ctx.workdir, "slides.ffconcat")

    audio_path = ctx.fetch(audio_spec) if audio_spec else None

    # The finished video runs for as long as the pictures do -- no longer, and
    # never less.
    #
    # `-shortest` used to decide this, and it got both halves wrong. Ending on
    # whichever stream finished first meant a closing slide asked to hold for
    # sixteen seconds against thirteen seconds of narration was cut back to
    # thirteen, so the link it existed to show came off screen early; and audio
    # that outran the pictures had its tail dropped, losing the last words
    # spoken with nothing to say so. Both failures are silent -- the render
    # succeeds and the file looks fine.
    #
    # So: hold the last slide long enough to cover any audio overrun, pad the
    # audio with silence to cover any picture overrun, and cut at exactly the
    # picture length. Whichever way the two disagree, nothing is lost.
    if audio_path:
        narration = media_duration(audio_path)
        if narration > total + 0.05:
            ctx.log("narration runs %.2fs past the last slide; holding it "
                    "there rather than cutting the audio" % (narration - total))
            extra = narration - total
            entries[-2] = entries[-2].rsplit("\nduration ", 1)[0] + (
                "\nduration %s" % (float(slides[-1].get("duration", 5)) + extra))
            total = narration

    with open(list_path, "w", encoding="utf-8") as handle:
        handle.write("ffconcat version 1.0\n" + "\n".join(entries) + "\n")

    args = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
    if audio_path:
        args += ["-i", audio_path]
    args += [
        "-vf", "scale=%s:force_original_aspect_ratio=decrease,"
               "pad=%s:(ow-iw)/2:(oh-ih)/2,fps=%d"
               % (resolution.replace("x", ":"), resolution.replace("x", ":"), fps),
    ]
    args += DEFAULT_VIDEO_ARGS
    if audio_path:
        args += DEFAULT_AUDIO_ARGS
        # apad makes the audio stream endless; -t then cuts both streams at the
        # picture length. Without apad, -t would leave the video running past
        # the end of a short narration with no audio stream to mux.
        args += ["-af", "apad", "-t", "%.3f" % total]
    args.append(output)

    ctx.log("slideshow: %d slides, %.1fs of picture" % (len(slides), total))
    run_command(args, cwd=ctx.workdir, timeout=payload.get("timeout", 7200),
                log=ctx.log)
    return _finish(ctx, output, mode="slideshow", slides=len(slides),
                   picture_seconds=round(total, 2))


def _concat(payload, ctx):
    inputs = _fetch_inputs(payload, ctx)
    if len(inputs) < 2:
        raise HandlerError("concat needs at least two 'inputs'")
    output = _output_path(payload, ctx, "joined.mp4")
    list_path = safe_join(ctx.workdir, "concat.txt")
    with open(list_path, "w", encoding="utf-8") as handle:
        for path in inputs:
            handle.write("file '%s'\n" % path.replace("'", r"\'"))

    args = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
    if payload.get("reencode", True):
        args += DEFAULT_VIDEO_ARGS + DEFAULT_AUDIO_ARGS
    else:
        # Stream copy is instant but only valid when every clip shares a codec.
        args += ["-c", "copy"]
    args.append(output)
    run_command(args, cwd=ctx.workdir, timeout=payload.get("timeout", 7200),
                log=ctx.log)
    return _finish(ctx, output, mode="concat", clips=len(inputs))


def _transcode(payload, ctx):
    source = payload.get("input") or (payload.get("inputs") or [None])[0]
    if not source:
        raise HandlerError("transcode needs an 'input'")
    source = ctx.fetch(source)
    output = _output_path(payload, ctx, "out.mp4")
    args = ["ffmpeg", "-y", "-i", source]
    if payload.get("resolution"):
        args += ["-vf", "scale=%s" % payload["resolution"].replace("x", ":")]
    if payload.get("fps"):
        args += ["-r", str(int(payload["fps"]))]
    args += DEFAULT_VIDEO_ARGS + DEFAULT_AUDIO_ARGS
    args.append(output)
    run_command(args, cwd=ctx.workdir, timeout=payload.get("timeout", 7200),
                log=ctx.log)
    return _finish(ctx, output, mode="transcode")


def _raw(payload, ctx):
    """Full control: you supply the ffmpeg args, we supply the sandbox."""
    args = payload.get("args")
    if not isinstance(args, list) or not args:
        raise HandlerError("raw render needs an 'args' list of ffmpeg arguments")
    for spec in payload.get("inputs") or []:
        ctx.fetch(spec)
    output = payload.get("output")
    if not output:
        raise HandlerError("raw render needs 'output' so the file can be collected")
    output_path = safe_join(ctx.workdir, output)
    run_command(["ffmpeg", "-y"] + [str(a) for a in args],
                cwd=ctx.workdir, timeout=payload.get("timeout", 7200), log=ctx.log)
    return _finish(ctx, output_path, mode="raw")


def _probe(path):
    """Best-effort duration/stream info; never fails the job on its own."""
    import shutil
    if shutil.which("ffprobe") is None:
        return {}
    try:
        raw = run_command([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ], timeout=120)
        info = json.loads(raw)
        return {
            "duration_seconds": round(float(info["format"]["duration"]), 2),
            "size_bytes": int(info["format"]["size"]),
        }
    except Exception:
        return {}


def _finish(ctx, output, **extra):
    if not os.path.exists(output) or os.path.getsize(output) == 0:
        raise HandlerError(
            "ffmpeg exited cleanly but produced no output at %s" % output
        )
    result = {"video": ctx.artifact(output), "bytes": os.path.getsize(output)}
    result.update(_probe(output))
    result.update(extra)
    return result
