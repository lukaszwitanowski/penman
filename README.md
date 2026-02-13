# Penman

Desktop application for transcribing audio and video files using OpenAI Whisper. Built with Python and tkinter, Penman provides a straightforward GUI for converting speech to text with support for batch processing, YouTube video downloads, multiple languages, and various export formats.

## Features

### YouTube Integration
- Paste a YouTube URL and download audio directly for transcription
- Automatic metadata fetching (title, duration) before download
- Multiple download strategies with DRM workaround — cycles through YouTube client APIs (`android`, `web`, `mweb`) to find non-DRM audio streams
- Downloaded audio is converted to 16 kHz mono WAV via ffmpeg and cleaned up after transcription
- YouTube metadata (URL, title, duration) is embedded in transcription output
- Queue supports mixing local files and YouTube URLs — YouTube entries are displayed with a `[YT]` prefix
- Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) (already included in dependencies)

### Transcription Engine
- Powered by [OpenAI Whisper](https://github.com/openai/whisper) speech recognition model
- Six model sizes available: `turbo`, `tiny`, `base`, `small`, `medium`, `large` — choose between speed and accuracy
- Automatic language detection or manual selection from 9 supported languages: Polish, English, German, Spanish, French, Italian, Ukrainian, Russian
- Automatic audio extraction from video files and segmentation into configurable chunks via ffmpeg
- Default segment length of 300 seconds (5 minutes), adjustable per session

### Compute Device Support
- **Auto** — automatically selects the best available device
- **CPU** — forces CPU-only inference
- **GPU** — uses CUDA (NVIDIA) or MPS (Apple Silicon) when available

### Input Formats
Supports 11 media formats:

| Audio | Video |
|-------|-------|
| MP3   | MP4   |
| WAV   | MKV   |
| M4A   | MOV   |
| FLAC  | AVI   |
| OGG   | WebM  |

### Output Formats

- **TXT** — plain text transcript
- **JSON** — structured output with metadata, per-segment text, detected language, and error info
- **Markdown** — formatted transcript with metadata header and segment sections

Output files are saved with a timestamp in the filename (e.g., `recording_transcript_20260212_143000.txt`) to prevent overwrites.

### Batch Processing
- Add multiple files to a processing queue via file dialog or manual path entry
- Queue management: add, remove selected, or clear all entries
- Duplicate detection prevents adding the same file twice
- Per-file progress tracking across the entire batch
- Failed files are retained in the queue after batch completion for easy retry

### User Interface
- Responsive tkinter GUI (980x740, minimum 820x620)
- Real-time progress bar with percentage tracking
- Timestamped log panel showing each processing step with **Clear log** button
- **Clear queue** resets queue, YouTube info cache, and input fields
- All controls are locked during transcription to prevent conflicts
- Cancel button for graceful mid-transcription abort
- Confirmation dialog when closing the app during active transcription

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) installed and available in PATH
- NVIDIA GPU with CUDA (optional, for GPU acceleration)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/lukaszwitanowski/penman.git
   cd penman
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux / macOS
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Verify ffmpeg is installed:
   ```bash
   ffmpeg -version
   ```

## Usage

```bash
python main.py
```

**Local files:**
1. Click **Browse...** to select an audio or video file, or add multiple files to the queue using **Add many...**
2. Choose the output folder, language, Whisper model, compute device, and export format
3. Adjust segment length if needed (default: 300s)
4. Click **Start transcription**
5. Monitor progress in the log panel; use **Cancel** to abort at any time

**YouTube videos:**
1. Paste a YouTube URL in the **YouTube URL** field
2. Click **Fetch info** to preview the video title and duration
3. Click **Add YT to queue** to add it to the processing queue
4. Configure output settings and click **Start transcription**
5. Audio is downloaded automatically, transcribed, and the temporary file is cleaned up

## Project Structure

```
penman/
├── main.py                   # Entry point
├── config.py                 # App constants and default settings
├── gui.py                    # Tkinter GUI (TranscriberApp class)
├── transcription_service.py  # Whisper transcription pipeline
├── youtube_service.py        # YouTube download via yt-dlp
├── exporters.py              # TXT, JSON, and Markdown export functions
├── runtime_env.py            # ffmpeg PATH setup for PyInstaller builds
└── requirements.txt          # Python dependencies
```

### Module Details

| Module | Responsibility |
|--------|---------------|
| `main.py` | Configures runtime paths and launches the GUI |
| `config.py` | Defines app title, default values, supported formats, model list, language options, and compute device options |
| `gui.py` | Implements the full tkinter interface including file selection, queue management, settings panel, progress bar, log panel, and worker thread orchestration |
| `transcription_service.py` | Handles input validation, compute device resolution (CPU/CUDA/MPS), audio segmentation via ffmpeg-python, Whisper model loading and inference, and output file generation |
| `youtube_service.py` | YouTube URL validation, metadata fetching, and audio download with multi-strategy DRM workaround via yt-dlp |
| `exporters.py` | Provides `export_txt()`, `export_json()`, and `export_md()` functions for writing transcription results; includes YouTube metadata rendering |
| `runtime_env.py` | Adds bundled ffmpeg to PATH when running as a PyInstaller executable |

## License

MIT
