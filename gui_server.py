#!/usr/bin/env python3
"""Local browser page for the voiceover tool. CLI via ./run.sh is unchanged."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
PAGE = ROOT / "static" / "index.html"
HOST = "127.0.0.1"
PORT = 8765
_generate_lock = threading.Lock()


def make_voiceover(body: dict) -> dict:
    text = str(body.get("text") or "").strip()
    if not text:
        raise ValueError("Paste a script first.")
    voice = str(body.get("voice") or "af_heart")
    speed = float(body.get("speed") or 1)
    pause = int(200 if body.get("pause") is None else body.get("pause"))
    target = None
    if body.get("fit") and body.get("target") not in (None, ""):
        target = float(body["target"])
        if target <= 0:
            raise ValueError("Length must be more than 0 seconds.")
    if not 0.5 <= speed <= 2:
        raise ValueError("Speed must be between 0.5 and 2.")
    if pause < 0 or pause > 2000:
        raise ValueError("Pause must be between 0 and 2000 milliseconds.")

    from app import default_wav_path
    from timing import auto_fit, wav_to_mp3, write_srt, write_wav
    import tts_engine

    def generate_at(rate: float):
        return tts_engine.generate(text, voice=voice, speed=rate, pause_ms=pause)

    result = auto_fit(generate_at, speed, target)
    wav_path = default_wav_path()
    write_wav(wav_path, result.audio)
    srt_path = wav_path.with_suffix(".srt")
    write_srt(srt_path, result.timings)
    mp3_name = None
    if body.get("mp3"):
        mp3_path = wav_path.with_suffix(".mp3")
        wav_to_mp3(wav_path, mp3_path)
        mp3_name = mp3_path.name
    return {
        "wav": wav_path.name,
        "srt": srt_path.name,
        "mp3": mp3_name,
        "duration": round(result.duration, 1),
        "target": None if result.target is None else round(result.target, 1),
        "warning": result.warning,
        "device": tts_engine.describe_device(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._bytes(200, "text/html; charset=utf-8", PAGE.read_bytes())
            return
        if path == "/voices":
            from tts_engine import list_voices

            voices = [{"id": voice_id, "name": name, "kind": kind} for voice_id, name, kind in list_voices()]
            self._json(200, {"voices": voices})
            return
        if path.startswith("/files/"):
            self._send_file(unquote(path[len("/files/") :]))
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/generate":
            self._json(404, {"error": "Not found."})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 200_000:
            self._json(400, {"error": "That script is too long."})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "Could not read the form."})
            return
        if not _generate_lock.acquire(blocking=False):
            self._json(409, {"error": "A voiceover is already being made. Wait for it to finish."})
            return
        try:
            self._json(200, make_voiceover(body))
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Could not create the voiceover: {exc}"})
        finally:
            _generate_lock.release()

    def _send_file(self, name: str) -> None:
        if "/" in name or "\\" in name or name.startswith("."):
            self._json(404, {"error": "Not found."})
            return
        path = (OUTPUT / name).resolve()
        if path.parent != OUTPUT.resolve() or not path.is_file():
            self._json(404, {"error": "Not found."})
            return
        kinds = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".srt": "text/plain; charset=utf-8"}
        content_type = kinds.get(path.suffix.lower())
        if content_type is None:
            self._json(404, {"error": "Not found."})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        self._bytes(status, "application/json; charset=utf-8", json.dumps(payload).encode())

    def _bytes(self, status: int, content_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Voiceover page: http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
