#!/usr/bin/env python3
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from yt import call

d = json.load(open("videos.json"))
vids = [v["videoId"] for v in d["videos"]]
try:
    done = json.load(open("descriptions.json"))
except Exception:
    done = {}

def fetch(vid):
    r = call("player", {"videoId": vid})
    det = r.get("videoDetails", {})
    ms = r.get("microformat", {}).get("playerMicroformatRenderer", {})
    return vid, {
        "title": det.get("title"),
        "channelId": det.get("channelId"),
        "author": det.get("author"),
        "lengthSeconds": det.get("lengthSeconds"),
        "viewCount": det.get("viewCount"),
        "isLive": det.get("isLiveContent"),
        "publishDate": ms.get("publishDate"),
        "description": det.get("shortDescription", ""),
        "playability": r.get("playabilityStatus", {}).get("status"),
    }

todo = [v for v in vids if v not in done]
print(f"{len(todo)} to fetch", file=sys.stderr)
errs = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(fetch, v): v for v in todo}
    for i, f in enumerate(as_completed(futs)):
        try:
            vid, info = f.result()
            done[vid] = info
        except Exception as e:
            errs += 1
            print("ERR", futs[f], repr(e)[:120], file=sys.stderr)
        if (i + 1) % 50 == 0:
            print(f"{i+1}/{len(todo)}", file=sys.stderr)
            json.dump(done, open("descriptions.json", "w"))
json.dump(done, open("descriptions.json", "w"))
print(f"done={len(done)} errs={errs}", file=sys.stderr)
