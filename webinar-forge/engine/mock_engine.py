"""
Mock voice engine — same HTTP contract as engine.py, no ML dependencies.

Speaks in silence: it returns a correctly-formed WAV whose duration matches the
word count at a realistic speaking rate. That is enough to exercise the whole
pipeline (deck -> narration timings -> capture -> ffmpeg -> MP4) on a machine
where torch is not installed yet, and to check slide pacing before committing
an hour of GPU time.

Stdlib only. Run:  python3 engine/mock_engine.py
"""

import io
import json
import math
import os
import re
import struct
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = Path(os.environ.get("VOICE_SAMPLES_DIR", BASE_DIR / "voices"))
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 24000
WORDS_PER_MINUTE = 150.0
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".ogg")


def make_wav(seconds: float) -> bytes:
    """A quiet 110 Hz tone — audible enough to confirm sync, quiet enough to ignore."""
    n = max(1, int(SAMPLE_RATE * seconds))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i in range(n):
            v = int(1200 * math.sin(2 * math.pi * 110.0 * i / SAMPLE_RATE))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def parse_form(body: bytes, content_type: str) -> dict:
    """Handles urlencoded and the multipart subset the CLI sends."""
    if "multipart/form-data" in content_type:
        m = re.search(r"boundary=(.+)$", content_type)
        if not m:
            return {}
        boundary = ("--" + m.group(1).strip('"')).encode()
        fields = {}
        for part in body.split(boundary):
            if b"\r\n\r\n" not in part:
                continue
            head, _, value = part.partition(b"\r\n\r\n")
            name = re.search(rb'name="([^"]+)"', head)
            if name:
                fields[name.group(1).decode()] = value.rstrip(b"\r\n--")
        return fields

    from urllib.parse import parse_qs
    return {k: v[0].encode() for k, v in parse_qs(body.decode("utf-8")).items()}


def list_voices():
    voices = []
    for ext in AUDIO_EXTS:
        for f in sorted(SAMPLES_DIR.glob(f"*{ext}")):
            voices.append({"name": f.stem, "file": f.name,
                           "size": f.stat().st_size, "preprocessed": True})
    # Always offer one voice so a dry run works on a box with no samples at all.
    if not voices:
        voices.append({"name": "mock", "file": "mock.wav", "size": 0, "preprocessed": True})
    return voices


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[mock-engine] {fmt % args}")

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "device": "mock",
                             "chatterbox_loaded": False, "f5_loaded": False,
                             "mock": True, "samples_dir": str(SAMPLES_DIR)})
        elif self.path == "/voices":
            self._send(200, {"voices": list_voices()})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        fields = parse_form(body, self.headers.get("Content-Type", ""))

        if self.path == "/synthesize":
            text = fields.get("text", b"").decode("utf-8", "replace")
            words = len([w for w in text.split() if w])
            seconds = max(1.0, words / WORDS_PER_MINUTE * 60.0)
            print(f"[mock-engine] synthesize {words} words -> {seconds:.1f}s")
            self._send(200, make_wav(seconds), "audio/wav")

        elif self.path == "/upload-sample":
            name = fields.get("name", b"mock").decode()
            safe = "".join(c for c in name if c.isalnum() or c in "-_") or "mock"
            (SAMPLES_DIR / f"{safe}.wav").write_bytes(fields.get("file", b""))
            self._send(200, {"saved": f"{safe}.wav", "size": len(fields.get("file", b"")),
                             "preprocessed": f"{safe}.wav"})

        elif self.path == "/preprocess-voices":
            self._send(200, {"processed": 0, "results": []})
        else:
            self._send(404, {"detail": "not found"})


if __name__ == "__main__":
    host = os.environ.get("VOICE_HOST", "127.0.0.1")
    port = int(os.environ.get("VOICE_PORT", "5651"))
    print(f"[mock-engine] MOCK voice engine on {host}:{port} — silent audio, real timings")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
