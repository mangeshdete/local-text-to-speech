"""Duration measurement, natural auto-fit, and subtitle export."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000
# Stay inside this speed change so the voice still sounds natural.
NATURAL_LIMIT = 0.15
CLOSE_ENOUGH_SECONDS = 0.3


@dataclass(frozen=True)
class SentenceTiming:
    text: str
    start: float
    end: float


@dataclass
class FitResult:
    audio: np.ndarray
    timings: list[SentenceTiming]
    duration: float
    target: float | None
    speed: float
    stretch: float
    warning: str | None


def measure(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    return len(audio) / sample_rate


def ffmpeg_bin() -> str:
    bundled = Path(__file__).resolve().parent / "vendor" / "ffmpeg"
    if bundled.is_file() and os_access(bundled):
        return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg was not found. Expected the bundled program at vendor/ffmpeg.")


def os_access(path: Path) -> bool:
    return path.stat().st_mode & 0o111 != 0


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(audio, dtype=np.float32), sample_rate)


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            str(mp3_path),
        ]
    )


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(path: Path, timings: list[SentenceTiming]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    index = 1
    for timing in timings:
        if timing.end <= timing.start:
            continue
        blocks.append(
            f"{index}\n{format_timestamp(timing.start)} --> {format_timestamp(timing.end)}\n{timing.text}\n"
        )
        index += 1
    path.write_text("\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def scale_timings(timings: list[SentenceTiming], scale: float) -> list[SentenceTiming]:
    return [SentenceTiming(item.text, item.start * scale, item.end * scale) for item in timings]


def atempo_filter(factor: float) -> str:
    if factor <= 0:
        raise ValueError("Timing factor must be greater than zero.")
    parts: list[str] = []
    remaining = factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def time_stretch(audio: np.ndarray, factor: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Change duration without changing pitch. factor > 1 makes the audio shorter."""
    if abs(factor - 1.0) < 0.001:
        return np.asarray(audio, dtype=np.float32)
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "in.wav"
        target = Path(folder) / "out.wav"
        write_wav(source, audio, sample_rate)
        _run_ffmpeg(
            [
                ffmpeg_bin(),
                "-y",
                "-i",
                str(source),
                "-filter:a",
                atempo_filter(factor),
                str(target),
            ]
        )
        stretched, read_rate = sf.read(str(target), dtype="float32")
    if read_rate != sample_rate:
        raise RuntimeError(f"ffmpeg returned {read_rate} Hz audio; expected {sample_rate} Hz.")
    return np.asarray(stretched, dtype=np.float32).reshape(-1)


def auto_fit(generate, base_speed: float, target: float | None) -> FitResult:
    """Fit the voiceover to target seconds, staying within about ±15% speed change.

    generate(speed) -> (audio, timings). Kokoro speed is adjusted first. ffmpeg
    atempo only trims the small remainder, and never past the 15% limit.
    """
    audio, timings = generate(base_speed)
    original = measure(audio)
    if original <= 0:
        raise RuntimeError("Generated audio is empty.")
    if target is None or target <= 0:
        return FitResult(audio, timings, original, None, base_speed, 1.0, None)

    desired_rate = original / target
    limited_rate = min(1 + NATURAL_LIMIT, max(1 - NATURAL_LIMIT, desired_rate))
    over_limit = abs(desired_rate - limited_rate) > 1e-3
    goal = original / limited_rate
    speed = base_speed
    stretch = 1.0

    if abs(original - goal) > CLOSE_ENOUGH_SECONDS:
        speed = min(base_speed * (1 + NATURAL_LIMIT), max(base_speed * (1 - NATURAL_LIMIT), base_speed * (original / goal)))
        if abs(speed - base_speed) >= 0.01:
            audio, timings = generate(speed)
        current = measure(audio)
        if abs(current - goal) > 0.05:
            stretch = current / goal
            before = current
            audio = time_stretch(audio, stretch)
            after = measure(audio)
            if before > 0:
                timings = scale_timings(timings, after / before)

    duration = measure(audio)
    warning = None
    if over_limit:
        change = abs(desired_rate - 1) * 100
        warning = (
            f"Hitting {target:.1f} seconds would change the speed by about {change:.0f}%. "
            f"More than 15% starts to sound unnatural, so this file was kept at {duration:.1f} seconds. "
            "Shorten the script to make the voiceover shorter, or add a sentence to make it longer."
        )
    return FitResult(audio, timings, duration, target, speed, stretch, warning)


def _run_ffmpeg(command: list[str]) -> None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg was not found.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail = " ".join(detail[-3:]) if detail else f"exit code {completed.returncode}"
        raise RuntimeError(f"ffmpeg failed: {tail}")
