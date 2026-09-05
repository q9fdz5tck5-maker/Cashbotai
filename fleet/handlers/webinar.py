"""Webinar composite: narrate a script and cut it to slides in one job.

This is the whole-pipeline handler. Give it a script -- slides with narration
text -- and it produces the finished video on a single box: TTS per section,
then a slideshow render timed to the audio it just made.

Payload:
    title       used for the output filename
    voice       piper voice model (or engine-specific voice id)
    engine      tts engine, default piper
    resolution  default 1920x1080
    sections    [{image, narration, duration?}, ...]

Timing note: when a section has no explicit duration, the slide is held for
exactly as long as its narration runs. That is the behaviour you almost always
want and the reason this runs as one job rather than two -- the render needs
the measured audio length, which only exists after the speech is generated.

An explicit ``duration`` can hold a slide *longer* than its narration -- to
leave a closing link on screen after the words stop -- but never shorter. See
the comment in ``run`` for why a short slide corrupts everything after it.
"""

import os

from . import render as render_handler
from . import slides as slide_maker
from . import tts as tts_handler
from .common import (HandlerError, media_duration, require_binary,
                     run_command, safe_join)


def run(payload, ctx):
    require_binary("ffmpeg", "apt-get install -y ffmpeg")
    sections = payload.get("sections") or []
    if not sections:
        raise HandlerError(
            "webinar job needs a 'sections' list of {image, narration}"
        )

    title = payload.get("title") or "webinar"
    engine = payload.get("engine", "piper")
    voice = payload.get("voice")
    resolution = payload.get("resolution", "1920x1080")
    theme = payload.get("theme", "dark")

    slides = []
    audio_parts = []
    total_narration = 0.0

    for index, section in enumerate(sections):
        narration = (section.get("narration") or "").strip()
        image = section.get("image")
        if not image:
            # No picture supplied: draw one from the section's own words. This
            # is what lets a webinar be written as prose rather than assembled
            # from slides someone made in another program first.
            image = _draw_slide(section, index, ctx, resolution, theme)

        if narration:
            ctx.log("section %d/%d: generating narration" % (index + 1, len(sections)))
            speech_name = "section_%03d.wav" % index
            speech = tts_handler.run({
                "text": narration,
                "engine": engine,
                "voice": voice or section.get("voice"),
                "output": speech_name,
                # Keep intermediates local; only the final video is published.
                "_no_artifact": True,
            }, _SilentArtifacts(ctx))
            speech_path = safe_join(ctx.workdir, speech_name)
            duration = _audio_duration(speech_path)
            audio_parts.append(speech_path)
        else:
            duration = None

        # Without an explicit duration, the slide follows its narration.
        slide_duration = section.get("duration")
        if slide_duration is None:
            slide_duration = duration if duration else 5.0
        slide_duration = float(slide_duration)

        # An explicit duration may lengthen a slide but never shorten it below
        # its own narration. The audio track is one continuous piece spanning
        # every slide, so a slide cut short does not just clip its own voice --
        # it slides every later slide out of sync with the words being spoken
        # over it, and the tail of the track is dropped entirely when the video
        # ends first. That failure is silent: the render succeeds and only the
        # last seconds of speech go missing.
        if duration and slide_duration < duration:
            ctx.log(
                "section %d asked for %.1fs but its narration runs %.1fs; "
                "holding the slide for the narration instead"
                % (index + 1, slide_duration, duration))
            slide_duration = duration
        total_narration += duration or 0.0
        slides.append({"image": image, "duration": slide_duration})

    combined_audio = None
    if audio_parts:
        combined_audio = _join_audio(audio_parts, ctx)

    ctx.log("rendering %d slides (%.1fs narration)" % (len(slides), total_narration))
    result = render_handler.run({
        "mode": "slideshow",
        "slides": slides,
        "audio": combined_audio,
        "resolution": resolution,
        "fps": payload.get("fps", 30),
        "output": "%s.mp4" % _slug(title),
        "timeout": payload.get("timeout", 7200),
    }, ctx)

    result.update({
        "kind": "webinar",
        "title": title,
        "sections": len(sections),
        "narration_seconds": round(total_narration, 2),
    })
    return result


def _draw_slide(section, index, ctx, resolution, theme):
    """Render a section's words into a slide image and return its path.

    Two shapes are accepted. ``kind: "diagram"`` lays out labelled boxes joined
    by arrows -- the only way to show one thing feeding another. Anything else
    is a title/subtitle/bullets slide.
    """
    output = safe_join(ctx.workdir, "slide_%03d.png" % index)
    theme = section.get("theme") or theme
    if (section.get("kind") or "").lower() == "diagram":
        return slide_maker.render_diagram(
            section, output, ctx, resolution=resolution, theme=theme)
    if not any(section.get(k) for k in ("title", "subtitle", "bullets")):
        raise HandlerError(
            "section %d has no 'image' and no words to draw one from. Give it "
            "an image path, or a title/bullets, or kind='diagram' with boxes."
            % index
        )
    return slide_maker.render_slide(
        section, output, ctx, resolution=resolution, theme=theme)


class _SilentArtifacts:
    """Wraps the job context so intermediate TTS files are not published.

    A ten-section webinar would otherwise upload ten throwaway WAVs alongside
    the one video anybody actually wants.
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self.workdir = ctx.workdir

    def log(self, message):
        self._ctx.log(message)

    def fetch(self, spec):
        return self._ctx.fetch(spec)

    def artifact(self, path):
        return {"local": path, "published": False}


def _audio_duration(path):
    """Kept as a name of its own so tests can stub the measurement out."""
    return media_duration(path)


def _join_audio(parts, ctx):
    """Concatenate the per-section narration into one continuous track."""
    if len(parts) == 1:
        return parts[0]
    list_path = safe_join(ctx.workdir, "narration.txt")
    with open(list_path, "w", encoding="utf-8") as handle:
        for path in parts:
            handle.write("file '%s'\n" % path.replace("'", r"\'"))
    output = safe_join(ctx.workdir, "narration.wav")
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", output,
    ], cwd=ctx.workdir, timeout=1800, log=ctx.log)
    return output


def _slug(text):
    keep = [c.lower() if c.isalnum() else "-" for c in str(text)]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "webinar"
