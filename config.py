from __future__ import annotations

from pathlib import Path

APP_TITLE = "Penman"
DEFAULT_OUTPUT_DIR = Path("transcripts")
DEFAULT_SEGMENT_DIR = Path("temp_segments")
DEFAULT_SEGMENT_SECONDS = 300
DEFAULT_MODEL = "turbo"
DEFAULT_YT_DOWNLOAD_DIR = Path("yt_downloads")
DEFAULT_INPUT_FORMAT = "auto"
DEFAULT_OUTPUT_FORMAT = "txt"
DEFAULT_LANGUAGE = "auto"
DEFAULT_COMPUTE_DEVICE = "auto"

INPUT_FORMATS = [
    "auto",
    "mp3",
    "wav",
    "m4a",
    "flac",
    "ogg",
    "webm",
    "mp4",
    "mkv",
    "mov",
    "avi",
]

OUTPUT_FORMATS = ["txt", "json", "md"]

WHISPER_MODELS = ["turbo", "tiny", "base", "small", "medium", "large"]

COMPUTE_DEVICE_OPTIONS = [
    ("Auto", "auto"),
    ("CPU", "cpu"),
    ("GPU", "gpu"),
]

LANGUAGE_OPTIONS = [
    ("Auto detect", "auto"),
    ("Polski", "pl"),
    ("English", "en"),
    ("Deutsch", "de"),
    ("Espanol", "es"),
    ("Francais", "fr"),
    ("Italiano", "it"),
    ("Ukrainian", "uk"),
    ("Russian", "ru"),
]

INPUT_FILE_DIALOG_TYPES = [
    ("Media files", "*.mp3 *.wav *.m4a *.flac *.ogg *.webm *.mp4 *.mkv *.mov *.avi"),
    ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
    ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
    ("All files", "*.*"),
]

YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=",
    r"(?:https?://)?youtu\.be/",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/",
    r"(?:https?://)?(?:www\.)?youtube\.com/live/",
]
