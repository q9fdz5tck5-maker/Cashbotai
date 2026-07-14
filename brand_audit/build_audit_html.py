#!/usr/bin/env python3
"""
build_audit_html.py — render a Public Brand Audit report from JSON.

Takes the JSON emitted by brand_audit/PROMPT.md and produces a standalone
HTML report styled to match report_template.html.

Usage:
    python build_audit_html.py audit.json                 # -> audit_report.html
    python build_audit_html.py audit.json -o report.html
    python build_audit_html.py --demo                     # write a sample audit.json

Scope note: this renderer only lays out fields the audit already gathered from
public professional sources. It adds nothing and looks nothing up.
"""

import argparse
import html
import json
import sys
from pathlib import Path

# ---- styling (mirrors report_template.html) -------------------------------

STYLE = """
:root{
  --surface-1:#fcfcfb;--page:#f9f9f7;--ink-1:#0b0b0b;--ink-2:#52514e;--ink-3:#898781;
  --grid:#e1e0d9;--ring:rgba(11,11,11,.10);--blue:#2a78d6;--blue-deep:#0d366b;
  --good:#006300;--wash:#eaf1fb;
}
@media (prefers-color-scheme:dark){:root{
  --surface-1:#1a1a19;--page:#0d0d0d;--ink-1:#fff;--ink-2:#c3c2b7;--ink-3:#898781;
  --grid:#2c2c2a;--ring:rgba(255,255,255,.10);--blue:#3987e5;--blue-deep:#9ec5f4;
  --good:#0ca30c;--wash:#1c2a3d;
}}
:root[data-theme="dark"]{--surface-1:#1a1a19;--page:#0d0d0d;--ink-1:#fff;--ink-2:#c3c2b7;
  --ink-3:#898781;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);--blue:#3987e5;
  --blue-deep:#9ec5f4;--good:#0ca30c;--wash:#1c2a3d;}
:root[data-theme="light"]{--surface-1:#fcfcfb;--page:#f9f9f7;--ink-1:#0b0b0b;--ink-2:#52514e;
  --ink-3:#898781;--grid:#e1e0d9;--ring:rgba(11,11,11,.10);--blue:#2a78d6;
  --blue-deep:#0d366b;--good:#006300;--wash:#eaf1fb;}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink-1);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:0 20px 64px}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.hero{overflow:hidden;border-radius:0 0 20px 20px;
  background:linear-gradient(180deg,#0d366b 0%,#1c5cab 60%,#eb6834 100%);color:#fff}
.hero-inner{max-width:980px;margin:0 auto;padding:44px 20px 40px}
.hero h1{margin:0 0 6px;font-size:30px;letter-spacing:-.5px}
.hero p{margin:0 0 4px;max-width:640px;color:rgba(255,255,255,.88)}
.hero .stamp{display:inline-block;margin-top:12px;padding:4px 12px;border-radius:999px;
  background:rgba(255,255,255,.16);font-size:12.5px;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:-28px 0 36px}
.tile{background:var(--surface-1);border:1px solid var(--ring);border-radius:14px;
  padding:16px 18px;box-shadow:0 4px 18px rgba(0,0,0,.08)}
.tile .k{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)}
.tile .v{font-size:28px;font-weight:700;letter-spacing:-.5px;margin:2px 0}
.tile .d{font-size:12.5px;color:var(--ink-2)}
h2{font-size:20px;margin:40px 0 10px;letter-spacing:-.3px}
.lead{color:var(--ink-2);max-width:720px}
.card{background:var(--surface-1);border:1px solid var(--ring);border-radius:14px;padding:4px 0;margin:8px 0}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:11px 16px;border-bottom:1px solid var(--grid);vertical-align:top}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);font-weight:600}
tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;font-weight:600}
.bar{height:7px;border-radius:99px;background:var(--grid);overflow:hidden;min-width:90px;margin-top:5px}
.bar>span{display:block;height:100%;background:var(--blue)}
.score{font-weight:700;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:3px 10px;border-radius:999px;background:var(--wash);
  color:var(--blue-deep);font-size:12.5px;font-weight:600;margin:0 6px 6px 0}
.gap{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--grid)}
.gap>div{padding:11px 16px}.gap .obs{color:var(--ink-2)}.gap .opp{color:var(--good)}
.gap:last-child{border-bottom:none}
@media(max-width:640px){.gap{grid-template-columns:1fr}.gap .opp{padding-top:0}}
.note{font-size:12.5px;color:var(--ink-3)}
.foot{margin-top:44px;padding-top:18px;border-top:1px solid var(--grid);font-size:12.5px;color:var(--ink-3)}
.foot strong{color:var(--ink-2)}
"""

# ---- helpers --------------------------------------------------------------

def esc(v):
    """HTML-escape a value; None/empty -> em-dash placeholder."""
    if v is None or v == "":
        return "&mdash;"
    return html.escape(str(v))


def link(url, text=None):
    if not url or url in ("not public", "—"):
        return esc(text or url)
    u = html.escape(str(url))
    return f'<a href="{u}" target="_blank" rel="noopener">{esc(text or url)}</a>'


def clamp_score(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(5.0, n))


def rows(items, render, empty_cols):
    if not items:
        return f'<tr><td colspan="{empty_cols}" class="note">No public data found.</td></tr>'
    return "\n".join(render(it) for it in items)


# ---- section renderers ----------------------------------------------------

def render_channels(items):
    def row(c):
        return (
            "<tr>"
            f"<td>{esc(c.get('platform'))}</td>"
            f"<td>{link(c.get('url'), c.get('handle') or c.get('url'))}</td>"
            f"<td class='num'>{esc(c.get('followers'))}</td>"
            f"<td>{esc(c.get('cadence'))}</td>"
            f"<td>{esc(c.get('note'))}</td>"
            "</tr>"
        )
    return rows(items, row, 5)


def render_themes(items):
    if not items:
        return '<span class="note">No public data found.</span>'
    out = []
    for t in items:
        label = t.get("theme") if isinstance(t, dict) else t
        out.append(f'<span class="chip">{esc(label)}</span>')
    return "\n".join(out)


def render_scorecard(items):
    def row(s):
        sc = clamp_score(s.get("score_1_5"))
        pct = 0 if sc is None else round(sc / 5 * 100)
        disp = "&mdash;/5" if sc is None else f"{sc:g}/5"
        return (
            "<tr>"
            f"<td>{esc(s.get('metric'))}</td>"
            f"<td><span class='score'>{disp}</span>"
            f"<div class='bar'><span style='width:{pct}%'></span></div></td>"
            f"<td>{esc(s.get('evidence'))}</td>"
            "</tr>"
        )
    return rows(items, row, 3)


def render_contact(items):
    def row(c):
        return (
            "<tr>"
            f"<td>{esc(c.get('type'))}</td>"
            f"<td>{esc(c.get('value'))}</td>"
            f"<td class='note'>{link(c.get('source_url'), c.get('source_url'))}</td>"
            "</tr>"
        )
    return rows(items, row, 3)


def render_gaps(items):
    if not items:
        return '<div class="gap"><div class="obs note">No public data found.</div><div></div></div>'
    out = []
    for g in items:
        out.append(
            '<div class="gap">'
            f'<div class="obs">{esc(g.get("observation"))}</div>'
            f'<div class="opp">{esc(g.get("opportunity"))}</div>'
            "</div>"
        )
    return "\n".join(out)


def render_sources(items):
    def row(s):
        return (
            "<tr>"
            f"<td>{link(s.get('url'), s.get('url'))}</td>"
            f"<td>{esc(s.get('what'))}</td>"
            f"<td class='note'>{esc(s.get('seen_date'))}</td>"
            "</tr>"
        )
    return rows(items, row, 3)


# ---- page assembly --------------------------------------------------------

def build(data):
    subj = data.get("subject", {})
    stats = data.get("stats", {})
    title = f"Public Brand Audit — {subj.get('entity') or subj.get('name') or 'Report'}"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<div class="hero"><div class="hero-inner">
  <h1>{esc(subj.get('name'))}{(' — ' + esc(subj.get('entity'))) if subj.get('entity') else ''}</h1>
  <p>{esc(subj.get('tagline'))}</p>
  <p class="note" style="color:rgba(255,255,255,.7)">Public brand &amp; presence audit — published professional sources only.</p>
  <span class="stamp">Audit run: {esc(subj.get('verified'))}</span>
</div></div>

<div class="wrap">
  <div class="tiles">
    <div class="tile"><div class="k">Public reach</div><div class="v num">{esc(stats.get('reach'))}</div><div class="d">summed public following, as displayed</div></div>
    <div class="tile"><div class="k">Active platforms</div><div class="v num">{esc(stats.get('platforms'))}</div><div class="d">public channels found</div></div>
    <div class="tile"><div class="k">Posting cadence</div><div class="v">{esc(stats.get('cadence'))}</div><div class="d">typical publishing rhythm</div></div>
    <div class="tile"><div class="k">Contact channels</div><div class="v num">{esc(stats.get('contactability'))}</div><div class="d">published business contacts</div></div>
  </div>

  <h2>Positioning</h2>
  <p class="lead">{esc(data.get('positioning'))}</p>

  <h2>Public channels</h2>
  <div class="card"><table>
    <thead><tr><th>Platform</th><th>Handle</th><th>Followers</th><th>Cadence</th><th>Note</th></tr></thead>
    <tbody>{render_channels(data.get('channels'))}</tbody>
  </table></div>
  <p class="note">Only channels the subject publicly operates. Counts shown as the platform displays them.</p>

  <h2>Content themes</h2>
  <div>{render_themes(data.get('themes'))}</div>

  <h2>Presence scorecard</h2>
  <div class="card"><table>
    <thead><tr><th>Metric</th><th style="width:130px">Score</th><th>Evidence</th></tr></thead>
    <tbody>{render_scorecard(data.get('scorecard'))}</tbody>
  </table></div>

  <h2>Published business contact</h2>
  <div class="card"><table>
    <thead><tr><th>Type</th><th>Value</th><th>Source</th></tr></thead>
    <tbody>{render_contact(data.get('contact'))}</tbody>
  </table></div>
  <p class="note">Business-facing details the subject lists publicly. No personal, home, or non-published information.</p>

  <h2>Gaps &amp; opportunities</h2>
  <div class="card">{render_gaps(data.get('gaps'))}</div>

  <h2>Sources</h2>
  <div class="card"><table>
    <thead><tr><th>URL</th><th>What it provided</th><th>Seen</th></tr></thead>
    <tbody>{render_sources(data.get('sources'))}</tbody>
  </table></div>

  <div class="foot">
    <strong>Scope:</strong> Uses only information the subject intentionally published
    for professional purposes. Excludes government IDs, financial accounts, home
    address, physical description, and family details by design.
    <br><br>Generated by build_audit_html.py · fields map to brand_audit/PROMPT.md.
  </div>
</div>
</body>
</html>
"""


# ---- demo payload ---------------------------------------------------------

DEMO = {
    "subject": {
        "name": "Chase Reiner",
        "entity": "Shine Ranker LLC",
        "tagline": "SEO & AI-marketing educator; founder of the Shine Ranker toolset and community.",
        "verified": "2026-07-14",
    },
    "stats": {"reach": "not public", "platforms": 4, "cadence": "Several videos/week", "contactability": 2},
    "positioning": "Fill from audit — one paragraph on who they are, who they serve, and what they're known for, drawn only from their own published bios and site copy.",
    "channels": [
        {"platform": "Website", "handle": "shineranker.com", "url": "https://shineranker.com", "followers": "n/a", "cadence": "—", "note": "Primary owned property"},
        {"platform": "YouTube", "handle": "not public", "url": "", "followers": "not public", "cadence": "not public", "note": "Fill from public channel page"},
    ],
    "themes": [{"theme": "SEO"}, {"theme": "AI marketing"}, {"theme": "Agency growth"}, {"theme": "Tool tutorials"}],
    "scorecard": [
        {"metric": "Reach", "score_1_5": None, "evidence": "Fill: audience size across public platforms."},
        {"metric": "Consistency", "score_1_5": None, "evidence": "Fill: posting rhythm & cross-platform coherence."},
        {"metric": "Professionalism", "score_1_5": None, "evidence": "Fill: branding, site quality, clarity of offer."},
        {"metric": "Contactability", "score_1_5": None, "evidence": "Fill: how easily a prospect can reach them."},
    ],
    "contact": [
        {"type": "Business email", "value": "central@shineranker.com", "source_url": "https://shineranker.com"},
        {"type": "Website", "value": "shineranker.com", "source_url": "https://shineranker.com"},
    ],
    "gaps": [
        {"observation": "e.g. No booking link on the public contact card.", "opportunity": "Add a scheduling link to shorten lead-to-call."},
    ],
    "sources": [
        {"url": "https://shineranker.com", "what": "Business name, positioning, contact email", "seen_date": "2026-07-14"},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="Render a Public Brand Audit JSON into an HTML report.")
    ap.add_argument("json_file", nargs="?", help="Audit JSON produced by PROMPT.md")
    ap.add_argument("-o", "--out", help="Output HTML path (default: <input>_report.html)")
    ap.add_argument("--demo", action="store_true", help="Write a sample audit.json and render it")
    args = ap.parse_args()

    if args.demo:
        Path("audit.json").write_text(json.dumps(DEMO, indent=2), encoding="utf-8")
        out = Path(args.out or "audit_report.html")
        out.write_text(build(DEMO), encoding="utf-8")
        print(f"Wrote sample audit.json and {out}")
        return

    if not args.json_file:
        ap.error("provide a JSON file, or use --demo")

    src = Path(args.json_file)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"error: {src} not found")
    except json.JSONDecodeError as e:
        sys.exit(f"error: {src} is not valid JSON — {e}")

    out = Path(args.out) if args.out else src.with_name(src.stem + "_report.html")
    out.write_text(build(data), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
