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


# -- diagrams -----------------------------------------------------------------
#
# A whiteboard sketch is boxes with arrows between them, and no amount of
# bullet points says "this thing feeds that thing". Everything below is built
# from the same two ffmpeg primitives the rest of this module uses -- drawbox
# for rectangles and drawtext for words -- so a worker still needs nothing but
# ffmpeg and the DejaVu fonts.
#
# Arrowheads are drawn as text. DejaVu covers the geometric-shapes block on
# every distribution we have tried, but a missing glyph renders as a tofu box
# rather than failing, so ``arrow_glyphs`` degrades to ASCII when asked.

ARROWS_UNICODE = {"right": "▶", "left": "◀", "down": "▼"}
ARROWS_ASCII = {"right": ">", "left": "<", "down": "v"}


def arrow_glyphs(ascii_only=False):
    return ARROWS_ASCII if ascii_only else ARROWS_UNICODE


def render_diagram(spec, output, ctx, resolution="1920x1080", theme="dark"):
    """Render one diagram slide: a title, a row of boxes, arrows, a caption.

    Spec keys, all optional except that something must be drawable:
        title     heading across the top
        person    True to put a stick figure at the left of the row
        boxes     [{label, note}, ...] laid out left to right
        arrows    "right" between boxes, "loop" to also draw the return path
        outputs   numbered list drawn beneath the boxes
        caption   one line along the bottom
        ascii_arrows  draw arrows as > < v instead of triangles

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
    arrows = arrow_glyphs(bool(spec.get("ascii_arrows")))

    title = (spec.get("title") or "").strip()
    boxes = [b for b in (spec.get("boxes") or []) if b]
    outputs = [o for o in (spec.get("outputs") or []) if str(o).strip()]
    caption = (spec.get("caption") or "").strip()
    person = bool(spec.get("person"))
    arrow_mode = (spec.get("arrows") or "none").lower()

    if not (title or boxes or outputs or caption):
        raise HandlerError(
            "A diagram slide needs at least a title, some boxes, or outputs."
        )
    if len(boxes) > 5:
        raise HandlerError(
            "A diagram row holds at most 5 boxes; %d were given. Split this "
            "section in two -- five boxes is already past what reads at a "
            "glance." % len(boxes)
        )

    margin = int(110 * scale)
    title_size = int(64 * scale)
    box_label_size = int(36 * scale)
    note_size = int(26 * scale)
    output_size = int(38 * scale)
    caption_size = int(30 * scale)
    stroke = max(3, int(4 * scale))
    row_height = int(210 * scale)
    loop_drop = int(56 * scale)

    text_dir = safe_join(ctx.workdir, "_slidetext")
    os.makedirs(text_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(output))[0]

    filters = []
    counter = [0]

    def draw(text, size, color, x, y, bold=False):
        """Place one run of text. ``x`` may be an ffmpeg expression."""
        counter[0] += 1
        path = os.path.join(text_dir, "%s_%02d.txt" % (base, counter[0]))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        filters.append(
            "drawtext=fontfile='%s':textfile='%s':fontsize=%d:fontcolor=%s:"
            "x=%s:y=%d"
            % (_escape_path(FONT_BOLD if bold else FONT_REGULAR),
               _escape_path(path), size, color, x, int(y))
        )

    def centered(text, size, color, x0, box_width, y, bold=False):
        # drawtext resolves text_w itself, so centring needs no measuring here.
        draw(text, size, color, "%d+(%d-text_w)/2" % (x0, box_width), y, bold=bold)

    def rect(x, y, w, h, color, fill=False):
        filters.append(
            "drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=%s"
            % (int(x), int(y), int(w), int(h), color, "fill" if fill else stroke)
        )

    def fit(text, size):
        return _wrap(text, max(14, int((width - 2 * margin) / (size * 0.55))))

    # -- measure before drawing ------------------------------------------
    #
    # Drawing straight down from the title leaves the whole diagram pinned to
    # the top of the frame with a third of the slide empty beneath it. So
    # every block is measured first, then the body is centred in what is left
    # between the title and the caption.
    title_lines = fit(title, title_size) if title else []
    caption_lines = fit(caption, caption_size) if caption else []
    output_lines = [fit("%d.  %s" % (i, str(o).strip()), output_size)
                    for i, o in enumerate(outputs, start=1)]

    title_block = len(title_lines) * int(title_size * 1.25)
    caption_block = len(caption_lines) * int(caption_size * 1.3)
    outputs_block = sum(len(g) * int(output_size * 1.35) + int(10 * scale)
                        for g in output_lines)

    loop_active = arrow_mode == "loop" and len(boxes) > 1
    loop_label = (spec.get("loop_label") or "").strip()
    loop_block = 0
    if loop_active:
        loop_block = loop_drop + (int(22 * scale) + int(note_size * 1.4)
                                  if loop_label else int(30 * scale))

    body_block = ((row_height if boxes else 0) + loop_block
                  + (int(46 * scale) if boxes and outputs_block else 0)
                  + outputs_block)

    top = margin + title_block + (int(30 * scale) if title_lines else 0)
    bottom = height - margin - caption_block
    if body_block > bottom - top:
        raise HandlerError(
            "Diagram needs about %dpx of body but a %s frame leaves only %dpx "
            "between the title and the caption. Drop a box, shorten the "
            "caption, or split this section in two."
            % (body_block, resolution, max(0, bottom - top))
        )

    # -- draw -------------------------------------------------------------
    rect(0, 0, max(6, int(14 * scale)), height, colors["accent"], fill=True)

    y = margin
    for line in title_lines:
        centered(line, title_size, colors["title"], margin,
                 width - 2 * margin, y, bold=True)
        y += int(title_size * 1.25)

    row_top = top + max(0, (bottom - top - body_block) // 2)
    y = row_top

    if boxes:
        gap = int(84 * scale)
        left = margin
        usable = width - 2 * margin

        if person:
            person_width = int(150 * scale)
            _draw_person(rect, draw, left, row_top, row_height, scale,
                         colors, box_label_size)
            arrow_size = int(52 * scale)
            draw(arrows["right"], arrow_size, colors["accent"],
                 str(int(left + person_width + gap * 0.30)),
                 row_top + row_height / 2 - arrow_size * 0.62)
            left += person_width + gap
            usable -= person_width + gap

        count = len(boxes)
        box_width = int((usable - gap * (count - 1)) / count)
        if box_width < int(180 * scale):
            raise HandlerError(
                "%d boxes do not fit across a %s frame with readable labels. "
                "Use fewer boxes or a wider resolution." % (count, resolution)
            )

        for index, box in enumerate(boxes):
            x0 = left + index * (box_width + gap)
            rect(x0, row_top, box_width, row_height, colors["accent"])

            label = str(box.get("label") or "").strip()
            note = str(box.get("note") or "").strip()
            label_lines = _wrap(label, max(8, int(box_width / (box_label_size * 0.62)))) if label else []
            note_lines = _wrap(note, max(10, int(box_width / (note_size * 0.60)))) if note else []

            block = (len(label_lines) * int(box_label_size * 1.2)
                     + (int(14 * scale) if note_lines else 0)
                     + len(note_lines) * int(note_size * 1.25))
            ty = row_top + max(int(18 * scale), (row_height - block) // 2)
            for line in label_lines:
                centered(line, box_label_size, colors["title"], x0, box_width,
                         ty, bold=True)
                ty += int(box_label_size * 1.2)
            if note_lines:
                ty += int(14 * scale)
            for line in note_lines:
                centered(line, note_size, colors["body"], x0, box_width, ty)
                ty += int(note_size * 1.25)

            # The arrow lives in the gap. It is inset from the next box so the
            # head does not sit on top of that box's border.
            if arrow_mode in ("right", "loop") and index < count - 1:
                shaft_y = row_top + row_height // 2
                arrow_size = int(46 * scale)
                inset = int(10 * scale)
                rect(x0 + box_width, shaft_y - stroke // 2,
                     gap - inset, max(2, stroke - 1), colors["accent"], fill=True)
                draw(arrows["right"], arrow_size, colors["accent"],
                     "%d-text_w" % int(x0 + box_width + gap - inset),
                     shaft_y - arrow_size * 0.62)

        y = row_top + row_height

        if loop_active:
            # The return path: down from the last box, back along the bottom,
            # and up into the first. This is the whole point of the diagram --
            # what comes out becomes what goes in.
            first_mid = left + box_width // 2
            last_mid = left + (count - 1) * (box_width + gap) + box_width // 2
            loop_y = y + loop_drop
            line_w = max(2, stroke - 1)
            rect(last_mid, y, line_w, loop_y - y, colors["accent"], fill=True)
            rect(first_mid, y, line_w, loop_y - y, colors["accent"], fill=True)
            rect(first_mid, loop_y, last_mid - first_mid + line_w, line_w,
                 colors["accent"], fill=True)
            arrow_size = int(46 * scale)
            draw(arrows["left"], arrow_size, colors["accent"],
                 str(int(first_mid)), loop_y - arrow_size * 0.62)
            y = loop_y
            if loop_label:
                y += int(22 * scale)
                centered(loop_label, note_size, colors["body"], margin,
                         width - 2 * margin, y)
                y += int(note_size * 1.4)
            else:
                y += int(30 * scale)

        if outputs_block:
            y += int(46 * scale)

    for group in output_lines:
        for part in group:
            draw(part, output_size, colors["body"], str(margin), y)
            y += int(output_size * 1.35)
        y += int(10 * scale)

    cap_y = height - margin - caption_block
    for line in caption_lines:
        centered(line, caption_size, colors["accent"], margin,
                 width - 2 * margin, cap_y)
        cap_y += int(caption_size * 1.3)

    run_command([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=%s:s=%dx%d" % (colors["background"], width, height),
        "-vf", ",".join(filters),
        "-frames:v", "1",
        output,
    ], cwd=ctx.workdir, timeout=300, log=ctx.log)

    if not os.path.exists(output) or os.path.getsize(output) == 0:
        raise HandlerError("diagram render produced no image at %s" % output)
    return output


def _draw_person(rect, draw, x, top, height, scale, colors, label_size):
    """A stick figure, from a drawn 'O' head and four bars.

    Deliberately crude: this is the person on a whiteboard, and a polished
    illustration here would look out of place next to hand-drawn boxes.
    """
    bar = max(3, int(5 * scale))
    head_size = int(70 * scale)
    centre = x + int(75 * scale)

    # An 'O' gives a round head; drawbox can only make squares.
    draw("O", head_size, colors["title"], "%d-text_w/2" % centre,
         int(top + height * 0.10), bold=True)

    torso_top = int(top + height * 0.10 + head_size * 0.95)
    torso_height = int(height * 0.34)
    rect(centre - bar // 2, torso_top, bar, torso_height, colors["title"], fill=True)

    arm_span = int(48 * scale)
    rect(centre - arm_span, torso_top + int(torso_height * 0.34),
         arm_span * 2, bar, colors["title"], fill=True)

    leg_top = torso_top + torso_height
    leg_height = int(height * 0.30)
    leg_spread = int(26 * scale)
    rect(centre - leg_spread, leg_top, bar, leg_height, colors["title"], fill=True)
    rect(centre + leg_spread, leg_top, bar, leg_height, colors["title"], fill=True)

    draw("you", label_size, colors["body"], "%d-text_w/2" % centre,
         leg_top + leg_height + int(16 * scale))
