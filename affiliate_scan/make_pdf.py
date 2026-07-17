#!/usr/bin/env python3
import json, re, datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, HRFlowable)

pdfmetrics.registerFont(TTFont("DVS", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVS-B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

a = json.load(open("analysis.json"))

INK = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#0f6b4f")
LIGHT = colors.HexColor("#eef5f1")
GRID = colors.HexColor("#c9d6cf")
MUTED = colors.HexColor("#5a6b62")

def st(name, **kw):
    base = dict(fontName="DVS", fontSize=9.5, leading=13, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)

S = {
    "h1": st("h1", fontName="DVS-B", fontSize=21, leading=26, textColor=INK),
    "h2": st("h2", fontName="DVS-B", fontSize=13.5, leading=17, textColor=ACCENT, spaceBefore=14, spaceAfter=6),
    "sub": st("sub", fontSize=10.5, leading=15, textColor=MUTED),
    "body": st("body"),
    "small": st("small", fontSize=8.5, leading=11.5),
    "smallm": st("smallm", fontSize=8.5, leading=11.5, textColor=MUTED),
    "cell": st("cell", fontSize=8.5, leading=11),
    "cellb": st("cellb", fontName="DVS-B", fontSize=8.5, leading=11),
    "big": st("big", fontName="DVS-B", fontSize=17, leading=20, textColor=ACCENT),
}

def esc(t):
    t = re.sub(r"[✀-➿\U0001f000-\U0001ffff️⃣❌⭐]", "", str(t))
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

story = []
tot = a["totals"]
ch = a["channel"]

story.append(Paragraph("Affiliate Link Deep-Scan Report", S["h1"]))
story.append(Spacer(1, 4))
story.append(Paragraph(
    f'Channel: <b>CA$H BOT</b> (@cash_bot_ai) &nbsp;·&nbsp; youtube.com/@cash_bot_ai &nbsp;·&nbsp; '
    f'Channel ID: {ch["id"]}<br/>Scan date: {datetime.date.today().strftime("%B %d, %Y")} '
    f'&nbsp;·&nbsp; Scope: all {ch["videos_scanned"]} public uploads '
    f'({ch["tabs"]["videos"]} videos, {ch["tabs"]["streams"]} past live streams, {ch["tabs"]["shorts"]} shorts) '
    f'— every title and full description', S["sub"]))
story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT))
story.append(Spacer(1, 10))

# Headline stats
stats = [
    (str(tot["affiliate_link_occurrences"]), "affiliate / referral\nlink occurrences"),
    (str(tot["distinct_programs"]), "distinct affiliate\nprograms"),
    (str(tot["videos_with_affiliate_links"]), "videos containing\naffiliate links"),
    (str(tot["affiliate_word_mentions"]), 'uses of the word\n"affiliate" in text'),
]
row1 = [Paragraph(esc(v), S["big"]) for v, _ in stats]
row2 = [Paragraph(esc(l).replace("\n", "<br/>"), S["smallm"]) for _, l in stats]
t = Table([row1, row2], colWidths=[1.72 * inch] * 4)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
    ("BOX", (0, 0), (-1, -1), 0.8, GRID),
    ("INNERGRID", (0, 0), (-1, 0), 0.8, GRID),
    ("LINEBEFORE", (1, 1), (-1, 1), 0.8, GRID),
    ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
]))
story.append(t)
story.append(Spacer(1, 6))
story.append(Paragraph(
    f'Baseline: {tot["videos_with_descriptions"]} of {ch["videos_scanned"]} uploads have descriptions, containing '
    f'{tot["total_urls_all"]:,} total URL occurrences ({tot["unique_urls_all"]} unique URLs). '
    f'Affiliate/referral links account for {tot["affiliate_link_occurrences"]} of those occurrences.', S["small"]))

# Section 1: master count table
story.append(Paragraph("1. Every affiliate / referral link, by count", S["h2"]))
story.append(Paragraph(
    "Each row is one affiliate or referral program found in video descriptions. "
    "“Occurrences” counts every time the link appears across all descriptions; "
    "“Videos” counts distinct uploads containing it.", S["small"]))
story.append(Spacer(1, 6))

head = [Paragraph(f"<b>{h}</b>", S["cellb"]) for h in ("#", "Program", "Link (tracking ID)", "Type", "Occurrences", "Videos")]
rows = [head]
for i, l in enumerate(a["links"], 1):
    rows.append([
        Paragraph(str(i), S["cell"]),
        Paragraph(esc(l["label"]), S["cell"]),
        Paragraph(esc(l["platform"]), S["cell"]),
        Paragraph(esc(l["kind"]), S["cell"]),
        Paragraph(f'<b>{l["occurrences"]}</b>', S["cell"]),
        Paragraph(str(l["videos"]), S["cell"]),
    ])
tot_row = [Paragraph("", S["cell"]), Paragraph("<b>TOTAL</b>", S["cellb"]), Paragraph("", S["cell"]),
           Paragraph("", S["cell"]),
           Paragraph(f'<b>{tot["affiliate_link_occurrences"]}</b>', S["cellb"]),
           Paragraph(f'<b>{tot["videos_with_affiliate_links"]} videos</b>', S["cellb"])]
rows.append(tot_row)
t = Table(rows, colWidths=[0.4 * inch, 1.8 * inch, 2.65 * inch, 0.65 * inch, 0.7 * inch, 0.8 * inch], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dcebe3")),
    ("GRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
for i, hdr in enumerate(rows[0]):
    pass
# white header text
for c in range(6):
    rows[0][c] = Paragraph(f'<font color="white"><b>{["#","Program","Link (tracking ID)","Type","Occur.","Videos"][c]}</b></font>', S["cellb"])
t = Table(rows, colWidths=[0.4 * inch, 1.8 * inch, 2.65 * inch, 0.65 * inch, 0.7 * inch, 0.8 * inch], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dcebe3")),
    ("GRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(t)

# Section 2: word mentions
story.append(Paragraph('2. Mentions of the word “affiliate” in descriptions', S["h2"]))
story.append(Paragraph(
    f'The word “affiliate” appears <b>{tot["affiliate_word_mentions"]} times</b> across '
    f'<b>{tot["videos_mentioning_affiliate_word"]} video descriptions</b>. Recurring lines:', S["small"]))
story.append(Spacer(1, 6))
rows = [[Paragraph('<font color="white"><b>Count</b></font>', S["cellb"]),
         Paragraph('<font color="white"><b>Line (as it appears in descriptions)</b></font>', S["cellb"])]]
for l in a["affiliate_word_lines"]:
    rows.append([Paragraph(f'<b>{l["count"]}×</b>', S["cell"]), Paragraph(esc(l["line"]), S["cell"])])
t = Table(rows, colWidths=[0.7 * inch, 6.3 * inch], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ("GRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(t)

# Section 3: titles
story.append(Paragraph('3. Videos with “affiliate” in the title', S["h2"]))
rows = [[Paragraph('<font color="white"><b>Video ID</b></font>', S["cellb"]),
         Paragraph('<font color="white"><b>Title</b></font>', S["cellb"])]]
for tt in a["titles_with_affiliate"]:
    rows.append([Paragraph(esc(tt["videoId"]), S["cell"]), Paragraph(esc(tt["title"]), S["cell"])])
t = Table(rows, colWidths=[1.15 * inch, 5.85 * inch], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ("GRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(t)

# Section 4: top videos
story.append(Paragraph("4. Videos ranked by affiliate-link count", S["h2"]))
rows = [[Paragraph(f'<font color="white"><b>{h}</b></font>', S["cellb"])
         for h in ("Links", "Video ID", "Published", "Views", "Title")]]
for v in a["top_videos"]:
    rows.append([
        Paragraph(f'<b>{v["affiliate_links"]}</b>', S["cell"]),
        Paragraph(esc(v["videoId"]), S["cell"]),
        Paragraph(esc((v["published"] or "")[:10]), S["cell"]),
        Paragraph(esc(v["views"]), S["cell"]),
        Paragraph(esc(v["title"]), S["cell"]),
    ])
t = Table(rows, colWidths=[0.55 * inch, 1.1 * inch, 0.95 * inch, 0.65 * inch, 3.75 * inch], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ("GRID", (0, 0), (-1, -1), 0.5, GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(t)

# Section 5: notes
story.append(Paragraph("5. Method & limitations", S["h2"]))
notes = [
    "Data source: YouTube InnerTube API (the same backend the YouTube web player uses). All 655 public uploads on the "
    "channel's Videos, Shorts and Live tabs were enumerated and each video's full description and metadata were retrieved (0 fetch errors).",
    "A link was counted as affiliate/referral when its URL carries commission or invite attribution: referral paths "
    "(/refer/, /invite/, /join/, /r/), tracking parameters (?ref=, ?a=, fp_ref=, a_aid=, friend_code=, ?m=), or personal invite codes.",
    "Counts are occurrences: the same link pasted in 10 descriptions counts 10 times. Distinct-video counts are shown alongside.",
    "Not counted as affiliate: the creator's own product/funnel links (cash.bot, chasereiner.com, getaichecklist.com, shineranker.com), "
    "social profiles, Facebook Messenger m.me?ref= deep links (17×, not commission links), and donation links (Streamlabs, Patreon).",
    "Unresolved short links that could not be expanded from this environment and may hide affiliate destinations: "
    "bit.ly/3fHNTVb (381×, labeled “free checklist”), bit.ly/39bCc48 (2×), and three goo.gl links (1× each).",
    "Scope: titles + descriptions only. Spoken mentions (transcripts), pinned comments, and community posts were not scanned — "
    "YouTube does not expose captions for these videos via the accessible API endpoints from this environment.",
    "Disclosure observation: 124 descriptions include an ad-blocker warning about affiliate tracking, and 3 descriptions include a "
    "“VERIFIED AFFILIATE LINKS” section; a formal FTC-style disclosure statement (“I earn a commission…”) was not found.",
]
for n in notes:
    story.append(Paragraph("• &nbsp;" + esc(n).replace("“", "&#8220;").replace("”", "&#8221;"), S["small"]))
    story.append(Spacer(1, 3))

def footer(canv, doc):
    canv.saveState()
    canv.setFont("DVS", 7.5)
    canv.setFillColor(MUTED)
    canv.drawString(0.75 * inch, 0.5 * inch, "Affiliate Link Deep-Scan — CA$H BOT (@cash_bot_ai)")
    canv.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canv.restoreState()

doc = SimpleDocTemplate("affiliate_link_report.pdf", pagesize=letter,
                        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                        title="Affiliate Link Deep-Scan Report - CA$H BOT (@cash_bot_ai)")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote affiliate_link_report.pdf")
