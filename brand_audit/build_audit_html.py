#!/usr/bin/env python3
"""Build a finished brand-audit HTML report from the audit JSON.

Usage:
    python brand_audit/build_audit_html.py audit.json -o brand_audit_report.html

The JSON must follow the schema produced by the prompt in PROMPT.md:
    subject{name, entity, tagline, verified}
    stats{reach, platforms, cadence, contactability}
    positioning
    channels[]{platform, handle, url, followers, cadence, note}
    themes[]{theme, note}
    scorecard[]{metric, score_1_5, evidence}
    contact[]{type, value, source_url}
    gaps[]{observation, opportunity}
    sources[]{url, what, seen_date}

Missing or "not public" fields render as a muted "not public" marker.
Stdlib only — no dependencies.
"""

import argparse
import datetime
import html
import json
import pathlib
import sys

TEMPLATE = pathlib.Path(__file__).with_name("report_template.html")

NOT_PUBLIC = '<span class="np">not public</span>'


def esc(value, fallback=NOT_PUBLIC):
    """HTML-escape a scalar; blank/missing/'not public' becomes the muted marker."""
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "not public":
        return fallback
    return html.escape(text)


def link(url, label=None):
    if not url or str(url).strip().lower() in ("", "not public"):
        return NOT_PUBLIC
    url = str(url).strip()
    href = html.escape(url, quote=True)
    return f'<a href="{href}" rel="noopener">{html.escape(label or url)}</a>'


def render_channels(channels):
    out = []
    for ch in channels:
        handle = esc(ch.get("handle"))
        url = str(ch.get("url") or "").strip()
        if url and url.lower() != "not public":
            handle = link(url, str(ch.get("handle") or url))
        out.append(f"""    <div class="card">
      <span class="plat">{esc(ch.get("platform"), "—")}</span>
      <h3>{handle}</h3>
      <div class="nums">
        <span>Followers<b>{esc(ch.get("followers"))}</b></span>
        <span>Cadence<b>{esc(ch.get("cadence"))}</b></span>
      </div>
      <div class="note">{esc(ch.get("note"), "")}</div>
    </div>""")
    return "\n".join(out) or '<div class="prose">No public channels found.</div>'


def render_themes(themes):
    out = []
    for t in themes:
        note = str(t.get("note") or "").strip()
        note_html = f' <span>— {html.escape(note)}</span>' if note else ""
        out.append(f'    <div class="chip"><b>{esc(t.get("theme"), "—")}</b>{note_html}</div>')
    return "\n".join(out) or '<div class="chip"><span>No recurring themes identified.</span></div>'


def render_scorecard(scorecard):
    out = []
    for item in scorecard:
        try:
            score = max(0, min(5, int(item.get("score_1_5") or 0)))
        except (TypeError, ValueError):
            score = 0
        segs = "".join(
            f'<span class="seg{" on" if i < score else ""}"></span>' for i in range(5)
        )
        metric = esc(item.get("metric"), "—")
        out.append(f"""    <div class="score-card">
      <div class="score-head"><h3>{metric}</h3><span class="score-num">{score}/5</span></div>
      <div class="meter" role="img" aria-label="{html.escape(str(item.get("metric") or ""), quote=True)}: {score} out of 5">{segs}</div>
      <div class="ev">{esc(item.get("evidence"), "")}</div>
    </div>""")
    return "\n".join(out)


def render_contact(contact):
    out = []
    for c in contact:
        out.append(
            f"        <tr><td>{esc(c.get('type'), '—')}</td>"
            f"<td>{esc(c.get('value'))}</td>"
            f"<td>{link(c.get('source_url'))}</td></tr>"
        )
    return "\n".join(out) or f"        <tr><td>—</td><td>{NOT_PUBLIC}</td><td>{NOT_PUBLIC}</td></tr>"


def render_gaps(gaps):
    out = []
    for g in gaps:
        out.append(f"""    <div class="card gap-card">
      <span class="lab">Observation</span>
      <div class="obs">{esc(g.get("observation"), "—")}</div>
      <span class="lab">Opportunity</span>
      <div class="fix"><b>Move:</b> {esc(g.get("opportunity"), "—")}</div>
    </div>""")
    return "\n".join(out) or '<div class="prose">No material gaps identified.</div>'


def render_sources(sources):
    out = []
    for i, s in enumerate(sources, 1):
        out.append(
            f"        <tr><td>{i}</td><td>{link(s.get('url'))}</td>"
            f"<td>{esc(s.get('what'), '')}</td>"
            f"<td>{esc(s.get('seen_date'))}</td></tr>"
        )
    return "\n".join(out) or "        <tr><td>—</td><td colspan=\"3\">No sources recorded.</td></tr>"


def build(audit: dict) -> str:
    subject = audit.get("subject") or {}
    stats = audit.get("stats") or {}

    verified = subject.get("verified")
    if isinstance(verified, bool):
        verified_stamp = "✔ verified profiles" if verified else "unverified"
    else:
        verified_stamp = str(verified).strip() if verified else "unverified"

    replacements = {
        "{{SUBJECT_NAME}}": esc(subject.get("name"), "Unknown subject"),
        "{{SUBJECT_ENTITY}}": esc(subject.get("entity"), ""),
        "{{SUBJECT_TAGLINE}}": esc(subject.get("tagline"), ""),
        "{{VERIFIED_STAMP}}": html.escape(verified_stamp),
        "{{GENERATED_DATE}}": datetime.date.today().isoformat(),
        "{{STAT_REACH}}": esc(stats.get("reach")),
        "{{STAT_PLATFORMS}}": esc(stats.get("platforms")),
        "{{STAT_CADENCE}}": esc(stats.get("cadence")),
        "{{STAT_CONTACTABILITY}}": esc(stats.get("contactability")),
        "{{POSITIONING}}": esc(audit.get("positioning"), "No positioning published."),
        "{{CHANNELS}}": render_channels(audit.get("channels") or []),
        "{{THEMES}}": render_themes(audit.get("themes") or []),
        "{{SCORECARD}}": render_scorecard(audit.get("scorecard") or []),
        "{{CONTACT}}": render_contact(audit.get("contact") or []),
        "{{GAPS}}": render_gaps(audit.get("gaps") or []),
        "{{SOURCES}}": render_sources(audit.get("sources") or []),
    }

    page = TEMPLATE.read_text(encoding="utf-8")
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page


def main():
    ap = argparse.ArgumentParser(description="JSON brand audit → finished HTML report")
    ap.add_argument("audit_json", help="Path to the audit JSON returned by the prompt")
    ap.add_argument("-o", "--out", default="brand_audit_report.html",
                    help="Output HTML path (default: brand_audit_report.html)")
    args = ap.parse_args()

    try:
        audit = json.loads(pathlib.Path(args.audit_json).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"error: could not read audit JSON: {e}")
    if not isinstance(audit, dict):
        sys.exit("error: audit JSON must be an object with the schema from PROMPT.md")

    out = pathlib.Path(args.out)
    out.write_text(build(audit), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
