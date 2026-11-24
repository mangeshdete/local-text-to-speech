# Local voiceover

A command-line tool that turns a script into a spoken WAV file on your own computer. The voice is the Kokoro model. Audio is generated locally. There is no account and no paid service.

Your script is not uploaded. The first run downloads the voice model from Hugging Face (a few hundred megabytes). After that, speech is produced on this machine. Each later start still contacts Hugging Face only to check that those saved files are current, unless you switch on offline mode (see below).

On this PC the project folder is:

```text
/home/mangesh-dete/Desktop/Projects/local-text-to-speech
```

Python 3.12 lives in `.python/` inside that folder, and the installed libraries live in `.venv/` there too. `./run.sh` calls `.venv/bin/python` directly. The voice model stays in `~/.cache/huggingface` (one copy, downloaded once).

## Open the page

A browser page is included for someone who does not want to use the terminal. It does not bundle a Windows `.exe`: that file would have to contain several gigabytes of voice software. The page is a small local server, and `./run.sh` still works for scripts.

```bash
cd /home/mangesh-dete/Desktop/Projects/local-text-to-speech
./open-gui.sh
```

That opens http://127.0.0.1:8765/ . Paste a script, pick a voice, and press **Make voiceover**. The recording plays in the page. Sound comes out of whatever speakers or headset the computer is using.

On this PC you can also open the app named **Local Voiceover**. The command line is unchanged:

```bash
./run.sh examples/script2.txt --voice am_adam --target 28 --play
```

The page keeps running in the background after you close the browser tab. To free that memory:

```bash
kill "$(cat output/gui.pid)"
```

## Choose a voice

The readers are the voices below. They are human-sounding voices built into Kokoro. This tool does not copy a real person's voice from a recording. You change the reader with `--voice`.

Hear the default, Heart:

```bash
./run.sh examples/hello.txt --voice af_heart --play
```

A different US woman, a US man, or a British man:

```bash
./run.sh examples/hello.txt --voice af_bella --play
./run.sh examples/hello.txt --voice am_adam --play
./run.sh examples/hello.txt --voice bm_george --play
```

Your own script, with the voice you want:

```bash
./run.sh /full/path/to/script.txt --voice af_sarah
```

Print the same list from the tool:

```bash
./run.sh --list-voices
```

The first time you pick a voice, that voice file is downloaded. Later runs reuse it.

US women: `af_heart` (default, Heart), `af_bella` (Bella), `af_sarah` (Sarah), `af_nicole` (Nicole), `af_sky` (Sky), `af_nova` (Nova), `af_jessica` (Jessica), `af_kore` (Kore), `af_alloy` (Alloy), `af_aoede` (Aoede), `af_river` (River)

US men: `am_adam` (Adam), `am_michael` (Michael), `am_echo` (Echo), `am_eric` (Eric), `am_liam` (Liam), `am_onyx` (Onyx), `am_puck` (Puck), `am_fenrir` (Fenrir), `am_santa` (Santa)

British women: `bf_alice` (Alice), `bf_emma` (Emma), `bf_isabella` (Isabella), `bf_lily` (Lily)

British men: `bm_george` (George), `bm_daniel` (Daniel), `bm_fable` (Fable), `bm_lewis` (Lewis)

## Settings

`./run.sh` always runs from the project folder, so a script path must be a full path, or you `cd` into this folder first.

```bash
cd /home/mangesh-dete/Desktop/Projects/local-text-to-speech
./run.sh /full/path/to/script.txt --target 28
```

Each run writes a new file in `output/`, named like `voiceover-20261124-001500.wav`, and a `.srt` subtitle file with one cue per sentence. Commas, question marks, exclamation marks, and `...` change the delivery.

`--target 28` tries to make the whole file 28 seconds. Speed changes stay inside about 15% so the voice still sounds natural. If the script is too long or too short for that, the file is still saved at a natural pace and the tool tells you to shorten or lengthen the script.

| Option | Meaning | Default |
|---|---|---|
| script file | Text file to read | required, unless `--text` or `-` |
| `-` | Read text you paste into the terminal. Press Ctrl+D when finished | |
| `--text "..."` | The script itself. Do not also pass a file | |
| `--voice` | Which reader to use. Ids are listed above | `af_heart` |
| `--speed` | Speaking speed. Allowed 0.5 to 2.0. Natural range is 0.7 to 1.3. Lower is slower | `1.0` |
| `--pause` | Extra silence between sentences, in milliseconds. Allowed 0 to 2000 | `200` |
| `--target` | Aim for this many seconds, within about 15% speed change | off |
| `--out` | WAV path to write. `.wav` is added if the name does not end in `.wav` | a new file in `output/` |
| `--mp3` | Also write an MP3 next to the WAV | off |
| `--no-srt` | Skip the subtitle file | subtitles are written |
| `--play` | Play when the file is ready | off |
| `--list-voices` | Print the voices and exit | |
| `--help` | Print this same option list from the tool | |

Every option together:

```bash
./run.sh /full/path/to/script.txt \
  --voice bm_george \
  --speed 1.05 \
  --pause 250 \
  --target 28 \
  --out output/take1.wav \
  --mp3 \
  --play
```

Paste a line instead of a file:

```bash
./run.sh --text "Hello, this is a test. Does it pause correctly? Yes... it does!" --voice af_bella --play
```

```bash
./run.sh -
./run.sh --help
```

Play a finished file again:

```bash
pw-play output/voiceover-YYYYMMDD-HHMMSS.wav
```

`aplay` works if `pw-play` is not installed.

## What you need

- A computer with a few free gigabytes of disk. The Python libraries, mostly PyTorch, take several GB.
- Python **3.12**. Kokoro 0.9.4 installs on Python 3.10, 3.11, or 3.12. It does not install on 3.13 or 3.14.
- `ffmpeg`, for fitting the length and for MP3.
- `libsndfile`, so the WAV writer can run.
- An NVIDIA graphics card is optional. If PyTorch can see it, the tool uses it. Otherwise it uses the processor, which is slower.

On the machine this was built on, the card is a GeForce GTX 1660 Ti (6 GB) and memory is 6.7 GB. That is enough. Close the browser first if the machine is already low on memory.

## 1. Install system packages

Ubuntu:

```bash
sudo apt update
sudo apt install -y ffmpeg libsndfile1
```

Check Python:

```bash
python3 --version
```

If that prints 3.10, 3.11, or 3.12, also install the virtual-environment package and use that Python in the next step:

```bash
sudo apt install -y python3-venv python3-pip
```

If it prints 3.13 or 3.14, do not use it for this project. Install Python 3.12 with [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv python install 3.12
```

## 2. Create the project environment

```bash
git clone <your-repo-url> local-tts
cd local-tts
```

With system Python 3.12 (or 3.10 / 3.11):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

With uv, because the system Python is too new:

```bash
source "$HOME/.local/bin/env"
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

`requirements.txt` installs PyTorch, Kokoro, `soundfile`, and `numpy`. The PyTorch build published on PyPI for the 2.15 release is the CUDA 13.2 build. `nvidia-smi` should show CUDA Version 13.2 (or a newer driver that still runs that build). An older driver needs a different PyTorch build from https://pytorch.org/get-started/locally/ — install that torch build first, then `pip install "kokoro>=0.9.4" soundfile numpy`.

## 3. Check the graphics card

```bash
source .venv/bin/activate
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
```

`True` and the card name means the GPU will be used. `False` means speech still works on the processor.

## 4. First run

This needs internet once. It downloads the Kokoro model and the default voice into `~/.cache/huggingface`.

```bash
./run.sh examples/hello.txt --play
```

You should hear a short line, and a WAV plus a subtitle file should appear in `output/`.

Play a file again later with:

```bash
pw-play output/voiceover-YYYYMMDD-HHMMSS.wav
```

`aplay` works if `pw-play` is not installed.

## Stay offline after the download

The first time you use a voice, its file is saved in `~/.cache/huggingface`. Later runs of a saved voice stay on this computer and do not contact Hugging Face. A voice you have never used still needs internet once. To force that even for a missing voice:

```bash
HF_HUB_OFFLINE=1 ./run.sh examples/hello.txt
```

## What not to put in git

`.gitignore` already leaves these out. They are large or they are generated on each machine:

- `.venv/` — the Python environment (several GB)
- `output/` — generated audio and subtitles
- `*.wav`, `*.mp3`
- `vendor/ffmpeg` — only needed if `ffmpeg` is not installed on the system

Create the git repo from this folder, commit the program files, and push. A friend clones it and follows the steps above. They do not copy your `.venv` or your audio files.
