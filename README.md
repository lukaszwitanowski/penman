# Penman

Penman is a desktop GUI app for transcribing audio and video with OpenAI Whisper.
It supports local media files and YouTube URLs, batch processing, and multiple export formats.

## Features

- Local and YouTube sources in one queue.
- YouTube metadata fetch before download (`Fetch info`).
- Batch queue tools: add/remove, move up/down, clear queue, retry failed items.
- Run policy selection: continue on errors or stop on first error.
- Whisper model options: `turbo`, `tiny`, `base`, `small`, `medium`, `large`.
- Compute device options: `auto`, `cpu`, `gpu`.
- Output formats: `txt`, `json`, `md`, `srt`, `vtt`.
- Optional timestamps in TXT and Markdown exports.
- Adaptive segmentation for long inputs and model reuse during batch runs.
- Session JSONL logs in `<output_dir>/logs/`.
- Post-run output actions: `Open containing folder` and `Edit in Notepad`.
- Settings persistence across app restarts.

## Supported Media Formats

- Audio: `mp3`, `wav`, `m4a`, `flac`, `ogg`
- Video: `mp4`, `mkv`, `mov`, `avi`, `webm`

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available in `PATH`
- Optional GPU acceleration with NVIDIA CUDA or Apple MPS

## Installation

1. Clone the repository.
```bash
git clone https://github.com/lukaszwitanowski/penman.git
cd penman
```

2. Create and activate a virtual environment.
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

3. Install dependencies.
```bash
pip install -r requirements.txt
```

4. Verify `ffmpeg` installation.
```bash
ffmpeg -version
ffprobe -version
```

## Run

```bash
python main.py
```

## Basic Usage

1. Add input from a local file (`Browse...`, `Add from path`, `Add many...`) or from YouTube (`Fetch info`, then `Add YT to queue`).
2. Select output folder and transcription options.
3. Choose output format (`txt`, `json`, `md`, `srt`, `vtt`).
4. Click `Start transcription`.
5. After completion, use `Open containing folder` or `Edit in Notepad`.

## Settings and Data

- Default output directory: `./transcripts`
- App settings file on Windows: `%APPDATA%\Penman\settings.json`
- App settings file on Linux/macOS: `~/.config/penman/settings.json`
- Session logs: `<selected_output_dir>/logs/session_YYYYMMDD_HHMMSS.jsonl`

## Project Layout

```text
main.py                  # Entry point
gui.py                   # Tkinter application UI and workflow orchestration
transcription_service.py # Whisper pipeline, segmentation, export dispatch
youtube_service.py       # YouTube URL validation, metadata, download, retries
exporters.py             # TXT/JSON/MD/SRT/VTT writers
config.py                # App defaults and option lists
ui_strings.py            # User-facing text constants
settings_service.py      # Persistent app settings
logging_service.py       # Structured session logging
app_controller.py        # Controller root for app services
queue_service.py         # Queue operations
job_runner.py            # Stage/ETA helpers
models.py                # Typed dataclasses
runtime_env.py           # Runtime PATH setup for bundled ffmpeg
requirements.txt         # Python dependencies
```

## License

MIT
