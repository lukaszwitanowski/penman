from __future__ import annotations

APP_TITLE = "Penman"

# General UI labels/buttons
LABEL_YOUTUBE_URL = "YouTube URL"
LABEL_INPUT_FILE = "Input file"
LABEL_QUEUE = "Queue"
LABEL_INPUT_FORMAT = "Input format"
LABEL_OUTPUT_FOLDER = "Output folder"
LABEL_LANGUAGE = "Language"
LABEL_OUTPUT_FORMAT = "Output format"
LABEL_WHISPER_MODEL = "Whisper model"
LABEL_COMPUTE_DEVICE = "Compute device"
LABEL_SEGMENT_LENGTH = "Segment length (s)"
LABEL_RUN_POLICY = "Run policy"
LABEL_INCLUDE_TIMESTAMPS = "Include timestamps in TXT/MD"
LOG_PANEL_TITLE = "Log"

BUTTON_FETCH_INFO = "Fetch info"
BUTTON_ADD_YT_TO_QUEUE = "Add YT to queue"
BUTTON_BROWSE = "Browse..."
BUTTON_ADD_FROM_PATH = "Add from path"
BUTTON_ADD_MANY = "Add many..."
BUTTON_REMOVE_SELECTED = "Remove selected"
BUTTON_CLEAR_QUEUE = "Clear queue"
BUTTON_MOVE_UP = "Move up"
BUTTON_MOVE_DOWN = "Move down"
BUTTON_RETRY_FAILED = "Retry failed"
BUTTON_SELECT = "Select..."
BUTTON_START_TRANSCRIPTION = "Start transcription"
BUTTON_CANCEL = "Cancel"
BUTTON_OPEN_CONTAINING_FOLDER = "Open containing folder"
BUTTON_EDIT_IN_NOTEPAD = "Edit in Notepad"
BUTTON_CLEAR_LOG = "Clear log"
BUTTON_OK = "OK"

# Dialog titles
TITLE_MISSING_DATA = "Missing data"
TITLE_VALIDATION_ERROR = "Validation error"
TITLE_QUEUE = "Queue"
TITLE_YOUTUBE = "YouTube"
TITLE_DONE = "Done"
TITLE_FINISHED_WITH_ERRORS = "Finished with errors"
TITLE_CANCELLED = "Cancelled"
TITLE_ERROR = "Error"
TITLE_EXIT = "Exit"
TITLE_TRANSCRIPTION_FILE = "Transcription file"

# Dialog messages
MSG_ENTER_YOUTUBE_URL = "Enter YouTube URL first."
MSG_ENTER_VALID_YOUTUBE_URL = "Enter a valid YouTube URL."
MSG_URL_ALREADY_QUEUED = "URL was not added (already queued)."
MSG_SELECT_INPUT_FILE_FIRST = "Select an input file first."
MSG_FILE_NOT_ADDED = "File was not added (already queued or path is invalid)."
MSG_SELECT_INPUT_OR_QUEUE = "Select an input file or add files to the queue first."
MSG_SELECT_OUTPUT_FOLDER = "Select an output folder."
MSG_SEGMENT_LENGTH_POSITIVE = "Segment length must be a positive integer."
MSG_EXIT_WHILE_RUNNING = "Transcription is still running. Exit and cancel the task?"
MSG_PROCESSED_SUMMARY = "Processed files: {success}\nFailed files: {failed}"
MSG_NO_TRANSCRIPTION_FILE_AVAILABLE = "No transcription file available yet."
MSG_NO_FAILED_ITEMS = "No failed items from the previous run."

# File dialog titles
FILE_DIALOG_SELECT_INPUT = "Select input audio/video file"
FILE_DIALOG_SELECT_QUEUE_FILES = "Select files for queue"
FILE_DIALOG_SELECT_OUTPUT_FOLDER = "Select output folder"
FILE_DIALOG_SELECTED_FORMAT_LABEL = "{format} files"
FILE_DIALOG_SELECTED_FORMAT_PATTERN = "*.{format}"
FILE_DIALOG_ALL_FILES_LABEL = "All files"
FILE_DIALOG_ALL_FILES_PATTERN = "*.*"

# Status values
STATUS_READY = "Ready"
STATUS_RUNNING = "Running"
STATUS_FINISHED = "Finished"
STATUS_FAILED = "Failed"
STATUS_FINISHED_WITH_ERRORS = "Finished with errors"
STATUS_CANCELLED = "Cancelled"
STATUS_ERROR = "Error"
STATUS_CANCELLING = "Cancelling..."

# Logs/messages templates
LOG_SESSION_FILE = "Session log file: {path}"
LOG_FETCHED_YT_INFO = "Fetched YouTube info: {title}"
LOG_YT_TOO_LONG = "Warning: YouTube video is longer than 4 hours."
LOG_ADDED_YT_TO_QUEUE = "Added YouTube URL to queue: {value}"
LOG_SELECTED_INPUT_FILE = "Selected input file: {path}"
LOG_ADDED_TO_QUEUE = "Added to queue: {path}"
LOG_QUEUE_UPDATED = "Queue updated. Added: {added}, skipped: {skipped}."
LOG_REMOVED_SELECTED = "Removed {count} selected file(s) from queue."
LOG_QUEUE_CLEARED = "Queue cleared."
LOG_MOVED_UP = "Moved selected item(s) up."
LOG_MOVED_DOWN = "Moved selected item(s) down."
LOG_RETRIED_FAILED = "Requeued failed items: {count}."
LOG_SELECTED_OUTPUT_FOLDER = "Selected output folder: {path}"
LOG_TRANSCRIPTION_STARTED = "Transcription started for {count} file(s)."
LOG_OPENED_CONTAINING_FOLDER = "Opened containing folder: {path}"
LOG_FAILED_OPEN_CONTAINING_FOLDER = "Failed to open containing folder: {error}"
LOG_OPENED_IN_NOTEPAD = "Opened in Notepad: {path}"
LOG_FAILED_OPEN_IN_NOTEPAD = "Failed to open in Notepad: {error}"
LOG_PROCESSING_ITEM = "Processing [{index}/{total}] {label}"
LOG_DONE_ITEM = "Done [{index}/{total}] {label} -> {output}"
LOG_FAILED_ITEM = "Failed [{index}/{total}] {label}: {error}"
LOG_BATCH_FINISHED = "Batch finished. Files processed: {count}."
LOG_BATCH_FINISHED_WITH_ERRORS = (
    "Batch finished with errors. Success: {success}, failed: {failed}."
)
LOG_CANCELLATION_REQUESTED = "Cancellation requested."
LOG_ERROR = "Error: {error}"
LOG_STOPPED_ON_FIRST_ERROR = "Run policy stop-on-first-error triggered; remaining queue items were not processed."

# Queue/status templates
QUEUE_STATUS_TEMPLATE = "{count} files queued"
STATUS_RUNNING_ITEM_TEMPLATE = "Running {index}/{total}"
QUEUE_FAILED_NOTE = "\nFailed files remain in queue."
QUEUE_STOPPED_NOTE = "\nRun stopped on first error; remaining files stay in queue."
YT_PREFIX = "[YT] "
YT_UNKNOWN_TITLE = "Unknown title"
YT_UNKNOWN_DURATION = "unknown duration"
MSG_TRANSCRIPTION_CANCELLED = "Transcription cancelled."
RUN_POLICY_CONTINUE = "Continue on errors"
RUN_POLICY_STOP = "Stop on first error"

# Config-backed UI option labels
COMPUTE_DEVICE_OPTIONS_UI = [
    ("Auto", "auto"),
    ("CPU", "cpu"),
    ("GPU", "gpu"),
]

LANGUAGE_OPTIONS_UI = [
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

INPUT_FILE_DIALOG_TYPES_UI = [
    ("Media files", "*.mp3 *.wav *.m4a *.flac *.ogg *.webm *.mp4 *.mkv *.mov *.avi"),
    ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
    ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
    ("All files", "*.*"),
]
