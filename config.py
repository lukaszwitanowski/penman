from __future__ import annotations

from pathlib import Path
from ui_strings import (
    APP_TITLE,
    COMPUTE_DEVICE_OPTIONS_UI,
    INPUT_FILE_DIALOG_TYPES_UI,
    LANGUAGE_OPTIONS_UI,
)

DEFAULT_OUTPUT_DIR = Path("transcripts")
DEFAULT_SEGMENT_DIR = Path("temp_segments")
DEFAULT_SEGMENT_SECONDS = 300
DEFAULT_MODEL = "turbo"
DEFAULT_YT_DOWNLOAD_DIR = Path("yt_downloads")
DEFAULT_INPUT_FORMAT = "auto"
DEFAULT_OUTPUT_FORMAT = "txt"
DEFAULT_LANGUAGE = "auto"
DEFAULT_COMPUTE_DEVICE = "auto"
DEFAULT_INCLUDE_TIMESTAMPS = False
DEFAULT_RUN_POLICY = "continue"

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

OUTPUT_FORMATS = ["txt", "json", "md", "srt", "vtt"]

WHISPER_MODELS = ["turbo", "tiny", "base", "small", "medium", "large"]

COMPUTE_DEVICE_OPTIONS = COMPUTE_DEVICE_OPTIONS_UI

LANGUAGE_OPTIONS = LANGUAGE_OPTIONS_UI

INPUT_FILE_DIALOG_TYPES = INPUT_FILE_DIALOG_TYPES_UI

YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=",
    r"(?:https?://)?youtu\.be/",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/",
    r"(?:https?://)?(?:www\.)?youtube\.com/live/",
]

# In-session cache TTL for fetched YouTube metadata.
YOUTUBE_INFO_CACHE_TTL_SECONDS = 15 * 60
