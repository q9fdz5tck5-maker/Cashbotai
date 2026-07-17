#!/usr/bin/env python3
import json, re
from collections import Counter, defaultdict

d = json.load(open("descriptions.json"))
vmeta = {v["videoId"]: v for v in json.load(open("videos.json"))["videos"]}
url_re = re.compile(r'https?://[^\s)"\'<>\]]+')

# (label, platform, regex, kind)
RULES = [
    ("Replit referral", "replit.com/refer/rebootbase", r"replit\.com/refer/", "referral"),
    ("Honeygain referral", "join.honeygain.com/CENTRFAD3A", r"join\.honeygain\.com/", "referral"),
    ("Whop affiliate (?a=80t)", "whop.com/...?a=80t", r"whop\.com/.*[?&]a=80t", "affiliate"),
    ("Kraken invite", "invite.kraken.com/JDNW/*", r"invite\.kraken\.com/", "referral"),
    ("Crown Coins Casino referral", "crowncoinscasino.com (friends campaign)", r"crowncoinscasino\.com/\?utm_campaign", "referral"),
    ("Fetch Rewards referral", "referral.fetch.com (code 3AX5JU)", r"referral\.fetch\.com/", "referral"),
    ("Pawns.app referral", "pawns.app/?r=chase + discoverpawns.eu/chase", r"(pawns\.app/\?r=|discoverpawns\.eu/)", "referral"),
    ("GoHighLevel affiliate", "gohighlevel.com (fp_ref=chase-96)", r"gohighlevel\.com/.*fp_ref=", "affiliate"),
    ("MoneyLion referral", "mlion.us/$AudibleChase497", r"mlion\.us/", "referral"),
    ("Crypto.com referral", "crypto.com/app/2gk8q3vvmd", r"crypto\.com/app/", "referral"),
    ("Rakuten referral", "rakuten.com/r/CENTRA1199", r"rakuten\.com/r/", "referral"),
    ("Ibotta referral", "ibotta.onelink.me (friend_code=pyntmly)", r"ibotta\.onelink\.me/", "referral"),
    ("SoFi invite", "sofi.com/invite/money", r"sofi\.com/invite/", "referral"),
    ("OnePay refer-a-friend", "web.onepay.com (code 1Gtw8URPu)", r"onepay\.com/wlink/refer-a-friend", "referral"),
    ("MEXC referral", "promote.mexc.co/r/vY9aUpkt", r"promote\.mexc\.co/r/", "referral"),
    ("Freecash referral", "freecash.com/r/8PGVI", r"freecash\.com/r/", "referral"),
    ("KashKick referral", "kashkick.com?ref=...", r"kashkick\.com\?ref=", "referral"),
    ("BigCashWeb referral", "bigcashweb.com/refer/htpzgbht", r"bigcashweb\.com/refer/", "referral"),
    ("Swagbucks referral", "swagbucks.com/profile/r_229374557", r"swagbucks\.com/profile/r_", "referral"),
    ("SurveySavvy affiliate", "surveysavvy.com/?m=9031152", r"surveysavvy\.com/\?m=", "affiliate"),
    ("Cash App invite", "cash.app/app/S9F8ZJF", r"cash\.app/app/", "referral"),
    ("Coinbase join", "coinbase.com/join/W88AC66", r"coinbase\.com/join/", "referral"),
    ("Kling AI invitation", "pro.klingai.com (code 7BELXWWVFR6D)", r"klingai\.com/.*invitation", "referral"),
    ("SEOprofiler affiliate", "seoprofiler.com/#a_aid=chasereiner", r"seoprofiler\.com/#a_aid=", "affiliate"),
    ("Claude referral", "claude.ai/referral/-D2ekibIbQ", r"claude\.ai/referral/", "referral"),
    ("Vultr affiliate", "vultr.com/?ref=9906626", r"vultr\.com/\?ref=", "affiliate"),
    ("KWFinder discount (likely affiliate)", "kwfinder.com/15%", r"kwfinder\.com/15", "likely"),
]

link_counts = Counter()          # per rule label -> total occurrences
video_hits = defaultdict(set)    # label -> set(videoId)
per_video = Counter()            # videoId -> affiliate occurrences
all_urls = Counter()

for vid, v in d.items():
    desc = v.get("description") or ""
    for u in url_re.findall(desc):
        u = u.rstrip(".,;:!?")
        all_urls[u] += 1
        for label, plat, pat, kind in RULES:
            if re.search(pat, u, re.I):
                link_counts[label] += 1
                video_hits[label].add(vid)
                per_video[vid] += 1
                break

# textual "affiliate" mentions
kw_lines = Counter()
kw_total = 0
kw_videos = set()
for vid, v in d.items():
    desc = v.get("description") or ""
    c = desc.lower().count("affiliate")
    if c:
        kw_total += c
        kw_videos.add(vid)
    for line in desc.splitlines():
        if "affiliate" in line.lower():
            kw_lines[line.strip()[:160]] += 1

title_aff = [(vid, d[vid]["title"]) for vid in d if "affiliate" in (d[vid].get("title") or "").lower()]

rules_meta = {lab: (plat, kind) for lab, plat, pat, kind in RULES}
out = {
    "channel": {"name": "CA$H BOT", "handle": "@cash_bot_ai", "id": "UC6z07Hh9Muy6urJgA0F0azg",
                "videos_scanned": len(d),
                "tabs": dict(Counter(vmeta[v]["tab"] for v in d if v in vmeta))},
    "totals": {
        "affiliate_link_occurrences": sum(link_counts.values()),
        "distinct_programs": len(link_counts),
        "videos_with_affiliate_links": len(set().union(*video_hits.values())) if video_hits else 0,
        "affiliate_word_mentions": kw_total,
        "videos_mentioning_affiliate_word": len(kw_videos),
        "total_urls_all": sum(all_urls.values()),
        "unique_urls_all": len(all_urls),
        "videos_with_descriptions": sum(1 for v in d.values() if (v.get("description") or "").strip()),
    },
    "links": [
        {"label": lab, "platform": rules_meta[lab][0], "kind": rules_meta[lab][1],
         "occurrences": c, "videos": len(video_hits[lab])}
        for lab, c in link_counts.most_common()
    ],
    "affiliate_word_lines": [{"line": l, "count": c} for l, c in kw_lines.most_common(15)],
    "titles_with_affiliate": [{"videoId": vid, "title": t} for vid, t in title_aff],
    "top_videos": [
        {"videoId": vid, "title": (d[vid].get("title") or "")[:90],
         "published": d[vid].get("publishDate", ""), "views": d[vid].get("viewCount", ""),
         "affiliate_links": c}
        for vid, c in per_video.most_common(15)
    ],
}
json.dump(out, open("analysis.json", "w"), indent=1)
print(json.dumps(out, indent=1))
