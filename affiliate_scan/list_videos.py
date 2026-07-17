#!/usr/bin/env python3
import json
from yt import call

CH = "UC6z07Hh9Muy6urJgA0F0azg"
TABS = {"videos": "EgZ2aWRlb3PyBgQKAjoA", "shorts": "EgZzaG9ydHPyBgUKA5oBAA==", "streams": "EgdzdHJlYW1z8gYECgJ6AA=="}

def walk(node, key, out):
    if isinstance(node, dict):
        if key in node:
            out.append(node[key])
        for v in node.values():
            walk(v, key, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, key, out)

def texts(node):
    """collect all metadata text strings from a lockup"""
    out = []
    def rec(n):
        if isinstance(n, dict):
            if "content" in n and isinstance(n["content"], str):
                out.append(n["content"])
            for v in n.values():
                rec(v)
        elif isinstance(n, list):
            for v in n:
                rec(v)
    rec(node)
    return out

videos = {}
meta = {}

for tab, params in TABS.items():
    resp = call("browse", {"browseId": CH, "params": params})
    if not meta:
        m = resp.get("metadata", {}).get("channelMetadataRenderer", {})
        meta = {"title": m.get("title"), "description": m.get("description")}
    pages = 0
    while True:
        pages += 1
        new = 0
        # long-form / live
        lockups = []
        walk(resp, "lockupViewModel", lockups)
        for lv in lockups:
            vid = lv.get("contentId")
            if not vid or lv.get("contentType") not in (None, "LOCKUP_CONTENT_TYPE_VIDEO"):
                continue
            if vid in videos:
                continue
            md = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
            title = md.get("title", {}).get("content", "")
            mtexts = texts(md.get("metadata", {}))
            badge = ""
            for b in texts(lv.get("contentImage", {})):
                if ":" in b and len(b) <= 9:
                    badge = b
            views = next((t for t in mtexts if "view" in t.lower() or "watching" in t.lower()), "")
            age = next((t for t in mtexts if "ago" in t or "Stream" in t or "Premier" in t), "")
            videos[vid] = {"videoId": vid, "tab": tab, "title": title, "views": views, "published": age, "length": badge}
            new += 1
        # shorts
        shorts = []
        walk(resp, "shortsLockupViewModel", shorts)
        for sv in shorts:
            vid = (sv.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}) or {}).get("videoId") \
                or (sv.get("inlinePlayerData", {}).get("onVisible", {}).get("watchEndpoint", {}) or {}).get("videoId")
            if not vid or vid in videos:
                continue
            om = sv.get("overlayMetadata", {})
            videos[vid] = {"videoId": vid, "tab": tab,
                           "title": (om.get("primaryText", {}) or {}).get("content", ""),
                           "views": (om.get("secondaryText", {}) or {}).get("content", ""),
                           "published": "", "length": ""}
            new += 1
        conts = []
        walk(resp, "continuationCommand", conts)
        token = next((c.get("token") for c in conts if c.get("token")), None)
        if not token or new == 0 or pages > 30:
            break
        resp = call("browse", {"continuation": token})

print(json.dumps({"meta": meta, "count": len(videos), "videos": list(videos.values())}, indent=1))
