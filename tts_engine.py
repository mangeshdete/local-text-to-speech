"""Kokoro voice generation with per-sentence timings."""

from __future__ import annotations

import logging
import os
import re
import threading
import warnings
from pathlib import Path

# Kokoro prints library warnings that do not affect the voiceover.
warnings.filterwarnings("ignore", message=".*dropout option adds dropout.*")
warnings.filterwarnings("ignore", message=".*weight_norm.*")
warnings.filterwarnings("ignore", message=".*torch.jit.script.*")
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

import numpy as np

from timing import SAMPLE_RATE, SentenceTiming

REPO_ID = "hexgrad/Kokoro-82M"

# Names checked against the voice files in hexgrad/Kokoro-82M.
VOICES: list[tuple[str, str, str]] = [
    ("af_heart", "Heart", "US woman"),
    ("af_bella", "Bella", "US woman"),
    ("af_sarah", "Sarah", "US woman"),
    ("af_nicole", "Nicole", "US woman"),
    ("af_sky", "Sky", "US woman"),
    ("af_nova", "Nova", "US woman"),
    ("af_jessica", "Jessica", "US woman"),
    ("af_kore", "Kore", "US woman"),
    ("af_alloy", "Alloy", "US woman"),
    ("af_aoede", "Aoede", "US woman"),
    ("af_river", "River", "US woman"),
    ("am_adam", "Adam", "US man"),
    ("am_michael", "Michael", "US man"),
    ("am_echo", "Echo", "US man"),
    ("am_eric", "Eric", "US man"),
    ("am_liam", "Liam", "US man"),
    ("am_onyx", "Onyx", "US man"),
    ("am_puck", "Puck", "US man"),
    ("am_fenrir", "Fenrir", "US man"),
    ("am_santa", "Santa", "US man"),
    ("bf_alice", "Alice", "British woman"),
    ("bf_emma", "Emma", "British woman"),
    ("bf_isabella", "Isabella", "British woman"),
    ("bf_lily", "Lily", "British woman"),
    ("bm_george", "George", "British man"),
    ("bm_daniel", "Daniel", "British man"),
    ("bm_fable", "Fable", "British man"),
    ("bm_lewis", "Lewis", "British man"),
]

_VOICE_IDS = {voice_id for voice_id, _, _ in VOICES}
_lock = threading.Lock()
_model = None
_pipelines: dict[str, object] = {}
_device_label = "not loaded"


def list_voices() -> list[tuple[str, str, str]]:
    return list(VOICES)


def _hub_dir() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def voice_is_saved(voice_id: str) -> bool:
    """True when this voice and the main model are already on disk."""
    root = _hub_dir() / "models--hexgrad--Kokoro-82M"
    has_model = any(root.glob("snapshots/*/kokoro-v1_0.pth"))
    has_voice = any(root.glob(f"snapshots/*/voices/{voice_id}.pt"))
    return has_model and has_voice


def prefer_saved_files(voice_id: str) -> None:
    """Skip the Hugging Face check when this voice is already saved."""
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        return
    if voice_is_saved(voice_id):
        os.environ["HF_HUB_OFFLINE"] = "1"


def voice_label(voice_id: str) -> str:
    for vid, name, kind in VOICES:
        if vid == voice_id:
            return f"{name}, {kind}"
    return voice_id


def describe_device() -> str:
    return _device_label


def split_sentences(text: str) -> list[str]:
    """Split on sentence endings and keep the punctuation that shapes delivery."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\u2026", "...")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n+", " ", cleaned).strip()
    if not cleaned:
        return []
    # Keep "..." inside the sentence so the voice can pause on the ellipsis.
    protected = cleaned.replace("...", "\u2026")
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [part.replace("\u2026", "...").strip() for part in parts if part.strip()]


def _lang_code(voice_id: str) -> str:
    if voice_id.startswith("b"):
        return "b"
    if voice_id.startswith("a"):
        return "a"
    raise ValueError(f"Unknown voice {voice_id!r}. Run with --list-voices.")


def _load_model():
    global _model, _device_label
    if _model is not None:
        return _model

    import torch
    from kokoro import KModel

    if torch.cuda.is_available():
        try:
            model = KModel(repo_id=REPO_ID).to("cuda").eval()
            _device_label = f"graphics card ({torch.cuda.get_device_name(0)})"
            _model = model
            return _model
        except RuntimeError as exc:
            print(
                f"The graphics card could not load the voice ({exc}). Using the processor instead.",
                flush=True,
            )

    _model = KModel(repo_id=REPO_ID).to("cpu").eval()
    _device_label = "processor (CPU)"
    return _model


def _pipeline_for(voice_id: str):
    lang = _lang_code(voice_id)
    with _lock:
        pipeline = _pipelines.get(lang)
        if pipeline is None:
            from kokoro import KPipeline

            model = _load_model()
            pipeline = KPipeline(lang_code=lang, repo_id=REPO_ID, model=model)
            _pipelines[lang] = pipeline
        return pipeline


def _to_audio(chunk) -> np.ndarray:
    audio = chunk.audio if hasattr(chunk, "audio") else chunk[-1]
    if audio is None:
        return np.zeros(0, dtype=np.float32)
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def generate(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0,
    pause_ms: int = 200,
) -> tuple[np.ndarray, list[SentenceTiming]]:
    """Read the script one sentence at a time and insert silence between sentences."""
    if voice not in _VOICE_IDS:
        raise ValueError(f"Unknown voice {voice!r}. Run with --list-voices.")
    if speed <= 0:
        raise ValueError("Speed must be greater than zero.")

    prefer_saved_files(voice)
    sentences = split_sentences(text)
    if not sentences:
        raise ValueError("The script is empty.")

    pipeline = _pipeline_for(voice)
    spoken: list[tuple[str, np.ndarray]] = []
    for sentence in sentences:
        pieces = [_to_audio(chunk) for chunk in pipeline(sentence, voice=voice, speed=speed, split_pattern=None)]
        pieces = [piece for piece in pieces if len(piece)]
        if not pieces:
            continue
        spoken.append((sentence, np.concatenate(pieces)))

    if not spoken:
        raise RuntimeError("The voice model returned no audio. Check the script and try again.")

    pause_samples = int(SAMPLE_RATE * max(0, pause_ms) / 1000)
    silence = np.zeros(pause_samples, dtype=np.float32) if pause_samples else None
    pieces: list[np.ndarray] = []
    timings: list[SentenceTiming] = []
    cursor = 0
    for index, (sentence, audio) in enumerate(spoken):
        start = cursor / SAMPLE_RATE
        pieces.append(audio)
        cursor += len(audio)
        timings.append(SentenceTiming(sentence, start, cursor / SAMPLE_RATE))
        if silence is not None and index < len(spoken) - 1:
            pieces.append(silence)
            cursor += pause_samples

    return np.concatenate(pieces), timings
