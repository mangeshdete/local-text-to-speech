#!/usr/bin/env python3
"""Local voiceover tool. A script goes in, a WAV file comes out. No window, no account."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "output"

EXAMPLES = """
examples:
  ./run.sh examples/hello.txt
  ./run.sh examples/script-110.txt --target 28
  ./run.sh --text "Hello, this is a test. Does it pause correctly?" --play
  ./run.sh --list-voices
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.sh",
        description="Turn a script into a voiceover WAV on this computer.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("script", nargs="?", help="Text file to read. Use - to paste text into the terminal.")
    parser.add_argument("--text", help="Script text, instead of a file.")
    parser.add_argument("--voice", default="af_heart", help="Voice id. Default: af_heart. See --list-voices.")
    parser.add_argument("--speed", type=float, default=1.0, help="Speaking speed. 1.0 is normal. Useful range: 0.7 to 1.3.")
    parser.add_argument("--pause", type=int, default=200, help="Silence between sentences, in milliseconds. Default: 200.")
    parser.add_argument("--target", type=float, help="Fit the voiceover to this many seconds, within about 15%%.")
    parser.add_argument("--out", type=Path, help="WAV file to write. Default: a new file in output/.")
    parser.add_argument("--mp3", action="store_true", help="Also write an MP3 next to the WAV.")
    parser.add_argument("--no-srt", action="store_true", help="Do not write the subtitle timing file.")
    parser.add_argument("--play", action="store_true", help="Play the voiceover when it is ready.")
    parser.add_argument("--list-voices", action="store_true", help="Print the English voices and exit.")
    return parser


def print_voices() -> None:
    from tts_engine import list_voices

    current = None
    for voice_id, name, kind in list_voices():
        if kind != current:
            print(f"\n{kind}")
            current = kind
        print(f"  {voice_id:<14} {name}")
    print("\nDefault voice: af_heart")


def read_script(args: argparse.Namespace) -> str:
    if args.text and args.script:
        raise SystemExit("Use either a script file or --text, not both.")
    if args.text:
        return args.text.strip()
    if not args.script:
        raise SystemExit("Give a script file, --text, or - to read what you paste. Try --help.")
    if args.script == "-":
        return sys.stdin.read().strip()
    path = Path(args.script)
    if not path.is_file():
        raise SystemExit(f"Cannot find the script file: {path}")
    return path.read_text(encoding="utf-8-sig").strip()


def default_wav_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT / f"voiceover-{stamp}.wav"


def _audio_targets() -> tuple[str | None, str, str | None]:
    """Return the laptop-speaker target, its label, and the current default output name."""
    try:
        status = subprocess.run(["wpctl", "status"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None, "", None
    speaker_id = None
    default_name = None
    in_sinks = False
    for line in status.stdout.splitlines():
        if "Sinks:" in line:
            in_sinks = True
            continue
        if in_sinks and ("Sources:" in line or "Filters:" in line):
            break
        if not in_sinks:
            continue
        stripped = line.strip().lstrip("│").strip()
        if stripped.startswith("*"):
            default_name = stripped.lstrip("*").strip()
            default_name = default_name.split(".", 1)[-1].strip()
            default_name = default_name.split("[", 1)[0].strip()
        if "Analog Stereo" in line:
            token = stripped.lstrip("*").strip()
            speaker_id = token.split(".", 1)[0].strip()
    if not speaker_id:
        return None, "", default_name
    try:
        info = subprocess.run(["wpctl", "inspect", speaker_id], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None, "", default_name
    name = description = None
    for line in info.stdout.splitlines():
        if "node.name" in line and "=" in line:
            name = line.split("=", 1)[1].strip().strip('"')
        if "node.description" in line and "=" in line:
            description = line.split("=", 1)[1].strip().strip('"')
    return name, description or "laptop speakers", default_name


def play_file(path: Path) -> None:
    player = shutil_which("pw-play") or shutil_which("aplay")
    if player is None:
        print("The file is saved. This computer has no pw-play or aplay command to play it.")
        return
    command = [player, str(path)]
    if player.endswith("pw-play"):
        target, label, default_name = _audio_targets()
        if target:
            command[1:1] = ["--target", target]
            print(f"Playing through the laptop speakers ({label}).")
            if default_name and "Analog Stereo" not in default_name:
                print(f"The system sound output is {default_name}, so the speakers were used instead.")
        else:
            print("Playing through the current sound output.")
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print("Playback failed. The WAV file is saved.")


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def model_is_cached() -> bool:
    cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--hexgrad--Kokoro-82M"
    return cache.exists()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_voices:
        print_voices()
        return 0

    if not 0.5 <= args.speed <= 2.0:
        print("Speed must be between 0.5 and 2.0. A natural voice stays around 0.7 to 1.3.", file=sys.stderr)
        return 2
    if args.pause < 0 or args.pause > 2000:
        print("Pause must be between 0 and 2000 milliseconds.", file=sys.stderr)
        return 2
    if args.target is not None and args.target <= 0:
        print("Target length must be a number of seconds greater than zero.", file=sys.stderr)
        return 2

    try:
        script = read_script(args)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    if not script:
        print("The script is empty.", file=sys.stderr)
        return 2

    from timing import auto_fit, wav_to_mp3, write_srt, write_wav
    import tts_engine

    if not model_is_cached():
        print("First run downloads the voice model. This needs internet once, then it stays on this computer.")

    word_count = len(script.split())
    print(f"{word_count} words. Voice {args.voice} ({tts_engine.voice_label(args.voice)}). Pause {args.pause} ms.")
    if args.target is not None:
        print(f"Fitting to {args.target:.1f} seconds, without stretching the voice more than about 15%.")

    def generate_at(speed: float):
        return tts_engine.generate(script, voice=args.voice, speed=speed, pause_ms=args.pause)

    try:
        result = auto_fit(generate_at, args.speed, args.target)
    except Exception as exc:
        print(f"Could not create the voiceover: {exc}", file=sys.stderr)
        return 1

    wav_path = args.out if args.out is not None else default_wav_path()
    if wav_path.suffix.lower() != ".wav":
        wav_path = wav_path.with_suffix(".wav")
    try:
        write_wav(wav_path, result.audio)
        srt_path = None
        if not args.no_srt:
            srt_path = wav_path.with_suffix(".srt")
            write_srt(srt_path, result.timings)
        mp3_path = None
        if args.mp3:
            mp3_path = wav_path.with_suffix(".mp3")
            wav_to_mp3(wav_path, mp3_path)
    except Exception as exc:
        print(f"The voice was generated, but saving it failed: {exc}", file=sys.stderr)
        return 1

    print(f"Using the {tts_engine.describe_device()}.")
    if result.target is None:
        print(f"Saved {wav_path} ({result.duration:.1f} seconds).")
    else:
        gap = result.duration - result.target
        print(f"Saved {wav_path} ({result.duration:.1f} seconds, target {result.target:.1f}, difference {gap:+.1f}).")
    if abs(result.speed - args.speed) >= 0.01 or abs(result.stretch - 1) >= 0.02:
        print(f"Speed used: {result.speed:.2f}.")
    if result.warning:
        print(result.warning)
    if srt_path is not None:
        print(f"Subtitles {srt_path}")
    if mp3_path is not None:
        print(f"MP3 {mp3_path}")
    if args.play:
        play_file(wav_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
