"""Generate slide images from text, with ffmpeg and nothing else.

The webinar generator takes a script of words and returns a narrated video, so
something has to turn "title plus three bullets" into a picture. Doing that with
ffmpeg's drawtext filter keeps the promise that a worker needs only ffmpeg --
no Pillow, no headless browser, no fonts to install beyond what ships with the
distribution.

Text reaches drawtext through ``textfile=`` rather than being inlined. Inlined
text has to escape backslashes, colons, quotes and percent signs, and a missed
one either corrupts the slide or fails the render -- a script is user prose, so
it *will* contain apostrophes and colons. A file sidesteps the whole problem.
"""

import os
import textwrap

from .common import HandlerError, require_binary, run_command, safe_join

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

THEMES = {
    "dark": {
        "background": "0x11161d",
        "title": "0xffffff",
        "body": "0xc7d2de",
        "accent": "0x4c9aff",
    },
    "light": {
        "background": "0xf7f8fa",
        "title": "0x11161d",
        "body": "0x39424e",
        "accent": "0x1f6feb",
    },
    "midnight": {
        "background": "0x1a1030",
        "title": "0xffffff",
        "body": "0xd6ccf0",
        "accent": "0xb388ff",
    },
}


def theme_for(name):
    theme = THEMES.get((name or "dark").lower())
    if theme is None:
        raise HandlerError(
            "Unknown slide theme %r. Available: %s"
            % (name, ", ".join(sorted(THEMES)))
        )
    return theme


def _wrap(text, width):
    return textwrap.wrap(str(text), width=width) or [""]


def _escape_path(path):
    """drawtext parses its own option string, so ':' in a path must be escaped."""
    return path.replace("\\", "/").replace(":", r"\:")


def render_slide(spec, output, ctx, resolution="1920x1080", theme="dark"):
    """Render one slide PNG from {title, subtitle, bullets}.

    Returns the output path.
    """
    require_binary("ffmpeg", "apt-get install -y ffmpeg")
    if not os.path.exists(FONT_REGULAR):
        raise HandlerError(
            "No DejaVu fonts at %s. Install fonts-dejavu-core on this worker, "
            "or supply pre-made slide images instead of text." % FONT_DIR
        )

    try:
        width, height = (int(v) for v in str(resolution).lower().split("x"))
    except ValueError:
        raise HandlerError("resolution must look like 1920x1080, got %r" % resolution)

    colors = theme_for(theme)
    scale = height / 1080.0
    title_size = int(72 * scale)
    subtitle_size = int(38 * scale)
    body_size = int(42 * scale)
    margin = int(140 * scale)

    title = (spec.get("title") or "").strip()
    subtitle = (spec.get("subtitle") or "").strip()
    bullets = [b for b in (spec.get("bullets") or []) if str(b).strip()]

    if not title and not bullets:
        raise HandlerError(
            "A generated slide needs at least a 'title' or some 'bullets'."
        )

    # Each drawtext gets its own file, so nothing in the prose needs escaping.
    text_dir = safe_join(ctx.workdir, "_slidetext")
    os.makedirs(text_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(output))[0]

    # Lay the slide out in two passes: measure every line first, then place the
    # whole block vertically centred. Drawing straight down from the top margin
    # leaves a short slide hugging the ceiling with dead space beneath it.
    usable = width - 2 * margin

    def wrap_for(text, size):
        return _wrap(text, max(12, int(usable / (size * 0.55))))

    lines = []          # (text, size, color, bold, advance)
    if title:
        for line in wrap_for(title, title_size):
            lines.append((line, title_size, colors["title"], True,
                          int(title_size * 1.25)))
        lines.append((None, 0, None, False, int(20 * scale)))

    if subtitle:
        for line in wrap_for(subtitle, subtitle_size):
            lines.append((line, subtitle_size, colors["accent"], False,
                          int(subtitle_size * 1.35)))

    if bullets:
        lines.append((None, 0, None, False, int(40 * scale)))
        for bullet in bullets:
            wrapped = wrap_for(bullet, body_size)
            for index, line in enumerate(wrapped):
                # Continuation lines hang under the text, not under the dot.
                prefix = "\u2022  " if index == 0 else "    "
                lines.append((prefix + line, body_size, colors["body"], False,
                              int(body_size * 1.45)))
            lines.append((None, 0, None, False, int(16 * scale)))

    content_height = sum(advance for _, _, _, _, advance in lines)
    if content_height > height - 2 * margin:
        raise HandlerError(
            "Slide content needs about %dpx but a %s frame only offers %dpx. "
            "Shorten the bullets or split this section in two."
            % (content_height, resolution, height - 2 * margin)
        )

    filters = []
    counter = [0]

    def draw(line, size, color, y, bold=False):
        counter[0] += 1
        path = os.path.join(text_dir, "%s_%02d.txt" % (base, counter[0]))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(line)
        filters.append(
            "drawtext=fontfile='%s':textfile='%s':fontsize=%d:fontcolor=%s:"
            "x=%d:y=%d"
            % (_escape_path(FONT_BOLD if bold else FONT_REGULAR),
               _escape_path(path), size, color, margin, y)
        )

    # A left accent bar gives the deck a consistent identity across slides.
    filters.append(
        "drawbox=x=0:y=0:w=%d:h=%d:color=%s:t=fill"
        % (max(6, int(14 * scale)), height, colors["accent"])
    )

    y = max(margin, (height - content_height) // 2)
    for text, size, color, bold, advance in lines:
        if text is not None:
            draw(text, size, color, y, bold=bold)
        y += advance

    run_command([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=%s:s=%dx%d" % (colors["background"], width, height),
        "-vf", ",".join(filters),
        "-frames:v", "1",
        output,
    ], cwd=ctx.workdir, timeout=300, log=ctx.log)

    if not os.path.exists(output) or os.path.getsize(output) == 0:
        raise HandlerError("slide render produced no image at %s" % output)
    return output


def run(payload, ctx):
    """Job kind 'deck': render a set of slides without building a video."""
    slides = payload.get("slides") or []
    if not slides:
        raise HandlerError("deck job needs a 'slides' list")
    resolution = payload.get("resolution", "1920x1080")
    theme = payload.get("theme", "dark")

    produced = []
    for index, spec in enumerate(slides):
        output = safe_join(ctx.workdir, "slide_%03d.png" % index)
        render_slide(spec, output, ctx, resolution=resolution, theme=theme)
        produced.append(ctx.artifact(output))
    return {"slides": produced, "count": len(produced), "theme": theme}
