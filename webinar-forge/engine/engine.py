"""
Voice engine — Chatterbox / F5-TTS voice cloning over HTTP.

Adapted from the original phone.cash.bot voice-engine. The Twilio media
WebSocket, the Claude phone-agent and the persona prompt were removed; what
remains is the cloning API the webinar pipeline actually calls.

Endpoints
  GET    /health              service + device + model state
  GET    /voices              installed voice samples
  POST   /upload-sample       install a voice sample (multipart: file, name)
  DELETE /voices/{name}       remove a voice and its cache
  POST   /preprocess-voices   warm the preprocessing cache for every sample
  POST   /synthesize          text -> WAV in a cloned voice

Bind address and port come from VOICE_HOST / VOICE_PORT (default 127.0.0.1:5651).
Keep it bound to localhost unless you put an authenticating proxy in front:
there is no auth here, and anyone who can reach it can synthesize any
installed voice.
"""

import io
import os
import re
import uuid
import logging
from pathlib import Path
from typing import Optional

import torch
import torchaudio
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-5s %(message)s")
log = logging.getLogger("voice-engine")

app = FastAPI(title="Voice Engine")

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = Path(os.environ.get("VOICE_SAMPLES_DIR", BASE_DIR / "voices"))
DATA_DIR = Path(os.environ.get("VOICE_DATA_DIR", BASE_DIR / "data"))
PREPROCESSED_DIR = DATA_DIR / "preprocessed"

for d in (SAMPLES_DIR, DATA_DIR, PREPROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _pick_device() -> str:
    forced = os.environ.get("VOICE_DEVICE")
    if forced:
        return forced
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = _pick_device()
NATIVE_SR = 24000

# Locked in during the original tuning: low exaggeration keeps a presenter
# voice steady across a 40-minute deck instead of drifting theatrical.
DEFAULT_EXAGGERATION = float(os.environ.get("VOICE_EXAGGERATION", "0.15"))
DEFAULT_CFG_WEIGHT = float(os.environ.get("VOICE_CFG_WEIGHT", "0.5"))

AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".ogg")

_f5_model = None
_cb_model = None
_resamplers: dict = {}


def _get_resampler(orig: int, target: int):
    key = (orig, target)
    if key not in _resamplers:
        _resamplers[key] = torchaudio.transforms.Resample(orig_freq=orig, new_freq=target)
    return _resamplers[key]


def _empty_cache():
    if DEVICE == "mps":
        torch.mps.empty_cache()
    elif DEVICE == "cuda":
        torch.cuda.empty_cache()


def get_chatterbox():
    global _cb_model
    if _cb_model is None:
        from chatterbox.tts import ChatterboxTTS
        log.info("Loading Chatterbox on %s (first load downloads weights)...", DEVICE)
        _cb_model = ChatterboxTTS.from_pretrained(device=DEVICE)
        log.info("Chatterbox ready.")
    return _cb_model


def get_f5():
    global _f5_model
    if _f5_model is None:
        from f5_tts.api import F5TTS
        log.info("Loading F5-TTS...")
        _f5_model = F5TTS()
        log.info("F5-TTS ready.")
    return _f5_model


# ─── Reference preprocessing ─────────────────────────────────────────

def _cache_key(path: Path) -> str:
    st = path.stat()
    return f"{int(st.st_mtime)}_{st.st_size}"


def preprocess_reference(sample_path: Path) -> Path:
    """Normalise volume, trim leading/trailing silence, resample to 24 kHz.

    Cached by mtime+size: replacing a sample invalidates it automatically.
    """
    cached = PREPROCESSED_DIR / f"{sample_path.stem}_{_cache_key(sample_path)}.wav"
    if cached.exists():
        return cached

    log.info("Preprocessing reference: %s", sample_path.name)
    wav, sr = torchaudio.load(str(sample_path))

    if wav.shape[0] > 1:                       # downmix to mono
        wav = wav.mean(dim=0, keepdim=True)
    if sr != NATIVE_SR:
        wav = _get_resampler(sr, NATIVE_SR)(wav)

    peak = wav.abs().max()
    if peak > 0:
        wav = wav / peak * 0.95

    energy = wav.abs().squeeze(0)
    above = (energy > 0.01).nonzero()
    if above.numel() > 0:
        start = max(0, int(above[0]) - int(0.05 * NATIVE_SR))
        end = min(wav.shape[-1], int(above[-1]) + int(0.05 * NATIVE_SR))
        wav = wav[:, start:end]

    torchaudio.save(str(cached), wav, NATIVE_SR)
    return cached


def find_sample(voice: str) -> Optional[Path]:
    for ext in AUDIO_EXTS:
        candidate = SAMPLES_DIR / f"{voice}{ext}"
        if candidate.exists():
            return candidate
    return None


def get_preprocessed_sample(voice: str) -> Optional[Path]:
    raw = find_sample(voice)
    return preprocess_reference(raw) if raw else None


# ─── Chunking ────────────────────────────────────────────────────────

def chunk_text(text: str, max_sentences: int = 2) -> list:
    """Short chunks produce markedly better quality than long paragraphs."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return [
        " ".join(sentences[i:i + max_sentences])
        for i in range(0, len(sentences), max_sentences)
    ]


@torch.inference_mode()
def synthesize_full(text: str, sample_path: Path, engine: str = "chatterbox",
                    exaggeration: float = DEFAULT_EXAGGERATION,
                    cfg_weight: float = DEFAULT_CFG_WEIGHT):
    if engine == "f5":
        tmp_path = DATA_DIR / f"_tmp_{uuid.uuid4().hex[:8]}.wav"
        get_f5().infer(ref_file=str(sample_path), ref_text="",
                       gen_text=text, file_wave=str(tmp_path))
        wav, sr = torchaudio.load(str(tmp_path))
        tmp_path.unlink(missing_ok=True)
        _empty_cache()
        return wav, sr

    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Empty text")

    model = get_chatterbox()
    model.prepare_conditionals(str(sample_path), exaggeration=exaggeration)

    sr = model.sr
    gap = torch.zeros(1, int(0.1 * sr))
    parts = []
    for chunk in chunks:
        parts.append(model.generate(chunk, exaggeration=exaggeration, cfg_weight=cfg_weight))
        parts.append(gap)
    parts.pop()

    combined = torch.cat(parts, dim=-1)
    del parts
    _empty_cache()
    return combined, sr


# ─── API ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "chatterbox_loaded": _cb_model is not None,
        "f5_loaded": _f5_model is not None,
        "samples_dir": str(SAMPLES_DIR),
    }


@app.get("/voices")
async def list_voices():
    voices = []
    for ext in AUDIO_EXTS:
        for f in sorted(SAMPLES_DIR.glob(f"*{ext}")):
            preprocessed = PREPROCESSED_DIR / f"{f.stem}_{_cache_key(f)}.wav"
            voices.append({
                "name": f.stem,
                "file": f.name,
                "size": f.stat().st_size,
                "preprocessed": preprocessed.exists(),
            })
    return {"voices": voices}


@app.post("/upload-sample")
async def upload_sample(file: UploadFile = File(...), name: str = Form(None)):
    stem = name or Path(file.filename).stem
    safe = "".join(c for c in stem if c.isalnum() or c in "-_")
    if not safe:
        raise HTTPException(status_code=400, detail="Voice name is empty after sanitisation.")

    ext = Path(file.filename).suffix.lower() or ".wav"
    if ext not in AUDIO_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type '{ext}'.")

    dest = SAMPLES_DIR / f"{safe}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    try:
        return {"saved": dest.name, "size": len(content),
                "preprocessed": preprocess_reference(dest).name}
    except Exception as e:
        log.warning("Preprocessing failed for %s: %s", dest.name, e)
        return {"saved": dest.name, "size": len(content), "preprocessed": None}


@app.delete("/voices/{name}")
async def delete_voice(name: str):
    for ext in AUDIO_EXTS:
        candidate = SAMPLES_DIR / f"{name}{ext}"
        if candidate.exists():
            candidate.unlink()
            for cached in PREPROCESSED_DIR.glob(f"{name}_*.wav"):
                cached.unlink()
            return {"deleted": name}
    raise HTTPException(status_code=404, detail=f"Voice '{name}' not found")


@app.post("/preprocess-voices")
async def preprocess_voices():
    results = []
    for ext in AUDIO_EXTS:
        for f in SAMPLES_DIR.glob(f"*{ext}"):
            try:
                results.append({"voice": f.stem, "preprocessed": preprocess_reference(f).name, "ok": True})
            except Exception as e:
                results.append({"voice": f.stem, "error": str(e), "ok": False})
    return {"processed": len(results), "results": results}


@app.post("/synthesize")
async def synthesize(
    text: str = Form(...),
    voice: str = Form("default"),
    engine: str = Form("chatterbox"),
    exaggeration: float = Form(DEFAULT_EXAGGERATION),
    cfg_weight: float = Form(DEFAULT_CFG_WEIGHT),
):
    sample_path = get_preprocessed_sample(voice)
    if not sample_path:
        raise HTTPException(
            status_code=404,
            detail=f"Voice '{voice}' not found. Upload one via POST /upload-sample.",
        )

    wav, sr = synthesize_full(text, sample_path, engine, exaggeration, cfg_weight)

    buf = io.BytesIO()
    torchaudio.save(buf, wav.cpu(), sr, format="wav")
    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/wav")


if __name__ == "__main__":
    host = os.environ.get("VOICE_HOST", "127.0.0.1")
    port = int(os.environ.get("VOICE_PORT", "5651"))
    log.info("Voice engine on %s:%s  device=%s  samples=%s", host, port, DEVICE, SAMPLES_DIR)
    uvicorn.run(app, host=host, port=port)
