#!/usr/bin/env python3
"""Minimal InnerTube client via youtubei.googleapis.com."""
import json, ssl, sys, urllib.request, os

CA = "/root/.ccr/ca-bundle.crt"
PROXY = os.environ.get("HTTPS_PROXY", "")
KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"  # public web client key
BASE = "https://youtubei.googleapis.com/youtubei/v1"

CTX = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20260701.00.00", "hl": "en", "gl": "US"}}}

ctx = ssl.create_default_context(cafile=CA)
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": PROXY, "http": PROXY} if PROXY else {}),
    urllib.request.HTTPSHandler(context=ctx),
)

def call(endpoint, payload):
    body = dict(CTX)
    body.update(payload)
    req = urllib.request.Request(
        f"{BASE}/{endpoint}?key={KEY}&prettyPrint=false",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    import time
    for attempt in range(5):
        try:
            with opener.open(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)

if __name__ == "__main__":
    ep = sys.argv[1]
    payload = json.loads(sys.argv[2])
    out = call(ep, payload)
    json.dump(out, sys.stdout)
