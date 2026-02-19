from __future__ import annotations

from dataclasses import asdict
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import (
    APP_TITLE,
    COMPUTE_DEVICE_OPTIONS,
    DEFAULT_COMPUTE_DEVICE,
    DEFAULT_INCLUDE_TIMESTAMPS,
    DEFAULT_INPUT_FORMAT,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_RUN_POLICY,
    DEFAULT_SEGMENT_SECONDS,
    DEFAULT_YT_DOWNLOAD_DIR,
    INPUT_FILE_DIALOG_TYPES,
    INPUT_FORMATS,
    LANGUAGE_OPTIONS,
    OUTPUT_FORMATS,
    WHISPER_MODELS,
)
from transcription_service import (
    TranscriptionCancelled,
    TranscriptionError,
    run_transcription,
)
from youtube_service import download_audio, fetch_video_info, get_cached_video_info, is_youtube_url
from app_controller import AppController
from job_runner import estimate_eta_seconds, format_eta, infer_stage_label
from logging_service import SessionLogger
from models import BatchRunSummary, ItemRunResult
from settings_service import load_app_settings, save_app_settings
import ui_strings as ui


class TranscriberApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("980x740")
        self.root.minsize(820, 620)

        self.ui_queue: queue.Queue[tuple] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.is_running = False
        self.app_controller = AppController()
        self.queue_service = self.app_controller.queue_service
        self.file_queue: list[str] = self.queue_service.items
        self.youtube_info_cache: dict[str, dict[str, object]] = {}
        self.active_queue_mode = False
        self.generated_output_paths: list[str] = []
        self.last_failed_items: list[str] = []
        self.run_policy_by_label = {
            ui.RUN_POLICY_CONTINUE: "continue",
            ui.RUN_POLICY_STOP: "stop",
        }
        self.label_by_run_policy = {
            "continue": ui.RUN_POLICY_CONTINUE,
            "stop": ui.RUN_POLICY_STOP,
        }

        self.language_by_label = {label: code for label, code in LANGUAGE_OPTIONS}
        self.label_by_language = {code: label for label, code in LANGUAGE_OPTIONS}
        self.device_by_label = {label: code for label, code in COMPUTE_DEVICE_OPTIONS}
        self.label_by_device = {code: label for label, code in COMPUTE_DEVICE_OPTIONS}

        self.yt_url_var = tk.StringVar()
        self.yt_info_var = tk.StringVar(value="")
        self.input_path_var = tk.StringVar()
        self.input_format_var = tk.StringVar(value=DEFAULT_INPUT_FORMAT)
        self.output_dir_var = tk.StringVar(
            value=str(Path(__file__).resolve().parent / DEFAULT_OUTPUT_DIR)
        )
        self.language_var = tk.StringVar(
            value=self.label_by_language.get(DEFAULT_LANGUAGE, LANGUAGE_OPTIONS[0][0])
        )
        self.output_format_var = tk.StringVar(value=DEFAULT_OUTPUT_FORMAT)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.compute_device_var = tk.StringVar(
            value=self.label_by_device.get(
                DEFAULT_COMPUTE_DEVICE, COMPUTE_DEVICE_OPTIONS[0][0]
            )
        )
        self.segment_seconds_var = tk.StringVar(value=str(DEFAULT_SEGMENT_SECONDS))
        self.include_timestamps_var = tk.BooleanVar(value=DEFAULT_INCLUDE_TIMESTAMPS)
        self.run_policy_var = tk.StringVar(
            value=self.label_by_run_policy.get(DEFAULT_RUN_POLICY, ui.RUN_POLICY_CONTINUE)
        )
        self.queue_status_var = tk.StringVar(
            value=ui.QUEUE_STATUS_TEMPLATE.format(count=0)
        )
        self.status_var = tk.StringVar(value=ui.STATUS_READY)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.session_logger = SessionLogger(self.output_dir_var.get())
        self._apply_saved_settings()

        self._build_ui()
        if self.session_logger.log_path is not None:
            self._log(ui.LOG_SESSION_FILE.format(path=self.session_logger.log_path))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(16, weight=1)

        ttk.Label(container, text=ui.LABEL_YOUTUBE_URL).grid(
            row=0, column=0, sticky=tk.W, pady=4
        )
        self.yt_entry = ttk.Entry(container, textvariable=self.yt_url_var)
        self.yt_entry.grid(row=0, column=1, sticky=tk.EW, padx=8, pady=4)
        self.fetch_yt_button = ttk.Button(
            container, text=ui.BUTTON_FETCH_INFO, command=self._fetch_youtube_info
        )
        self.fetch_yt_button.grid(row=0, column=2, sticky=tk.EW, pady=4)

        self.yt_info_label = ttk.Label(container, textvariable=self.yt_info_var)
        self.yt_info_label.grid(row=1, column=1, sticky=tk.W, padx=8, pady=(0, 4))
        self.add_yt_button = ttk.Button(
            container, text=ui.BUTTON_ADD_YT_TO_QUEUE, command=self._add_youtube_to_queue
        )
        self.add_yt_button.grid(row=1, column=2, sticky=tk.EW, pady=(0, 4))

        ttk.Label(container, text=ui.LABEL_INPUT_FILE).grid(
            row=2, column=0, sticky=tk.W, pady=4
        )
        self.input_entry = ttk.Entry(container, textvariable=self.input_path_var)
        self.input_entry.grid(row=2, column=1, sticky=tk.EW, padx=8, pady=4)
        self.browse_input_button = ttk.Button(
            container, text=ui.BUTTON_BROWSE, command=self._browse_input
        )
        self.browse_input_button.grid(row=2, column=2, sticky=tk.EW, pady=4)

        queue_tools = ttk.Frame(container)
        queue_tools.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=(0, 6))
        queue_tools.columnconfigure(7, weight=1)

        self.add_path_button = ttk.Button(
            queue_tools, text=ui.BUTTON_ADD_FROM_PATH, command=self._add_input_to_queue
        )
        self.add_path_button.grid(row=0, column=0, padx=(0, 6))

        self.add_many_button = ttk.Button(
            queue_tools, text=ui.BUTTON_ADD_MANY, command=self._add_many_to_queue
        )
        self.add_many_button.grid(row=0, column=1, padx=(0, 6))

        self.remove_queue_button = ttk.Button(
            queue_tools,
            text=ui.BUTTON_REMOVE_SELECTED,
            command=self._remove_selected_from_queue,
        )
        self.remove_queue_button.grid(row=0, column=2, padx=(0, 6))

        self.move_up_queue_button = ttk.Button(
            queue_tools,
            text=ui.BUTTON_MOVE_UP,
            command=self._move_selected_up,
        )
        self.move_up_queue_button.grid(row=0, column=3, padx=(0, 6))

        self.move_down_queue_button = ttk.Button(
            queue_tools,
            text=ui.BUTTON_MOVE_DOWN,
            command=self._move_selected_down,
        )
        self.move_down_queue_button.grid(row=0, column=4, padx=(0, 6))

        self.retry_failed_button = ttk.Button(
            queue_tools,
            text=ui.BUTTON_RETRY_FAILED,
            command=self._retry_failed_items,
        )
        self.retry_failed_button.grid(row=0, column=5, padx=(0, 6))

        self.clear_queue_button = ttk.Button(
            queue_tools, text=ui.BUTTON_CLEAR_QUEUE, command=self._clear_queue
        )
        self.clear_queue_button.grid(row=0, column=6, padx=(0, 6))

        ttk.Label(queue_tools, textvariable=self.queue_status_var).grid(
            row=0, column=7, sticky=tk.E
        )

        ttk.Label(container, text=ui.LABEL_QUEUE).grid(row=4, column=0, sticky=tk.W, pady=(0, 4))
        queue_frame = ttk.Frame(container)
        queue_frame.grid(row=4, column=1, columnspan=2, sticky=tk.NSEW, padx=8, pady=(0, 6))
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        self.queue_listbox = tk.Listbox(queue_frame, height=6, selectmode=tk.EXTENDED)
        self.queue_listbox.grid(row=0, column=0, sticky=tk.NSEW)

        queue_scroll = ttk.Scrollbar(
            queue_frame, orient=tk.VERTICAL, command=self.queue_listbox.yview
        )
        queue_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.queue_listbox.configure(yscrollcommand=queue_scroll.set)

        ttk.Label(container, text=ui.LABEL_RUN_POLICY).grid(
            row=5, column=0, sticky=tk.W, pady=4
        )
        self.run_policy_combo = ttk.Combobox(
            container,
            values=[ui.RUN_POLICY_CONTINUE, ui.RUN_POLICY_STOP],
            textvariable=self.run_policy_var,
            state="readonly",
        )
        self.run_policy_combo.grid(row=5, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_INPUT_FORMAT).grid(row=6, column=0, sticky=tk.W, pady=4)
        self.input_format_combo = ttk.Combobox(
            container,
            values=INPUT_FORMATS,
            textvariable=self.input_format_var,
            state="readonly",
        )
        self.input_format_combo.grid(row=6, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_OUTPUT_FOLDER).grid(row=7, column=0, sticky=tk.W, pady=4)
        self.output_entry = ttk.Entry(container, textvariable=self.output_dir_var)
        self.output_entry.grid(row=7, column=1, sticky=tk.EW, padx=8, pady=4)
        self.select_output_button = ttk.Button(
            container, text=ui.BUTTON_SELECT, command=self._browse_output_dir
        )
        self.select_output_button.grid(row=7, column=2, sticky=tk.EW, pady=4)

        ttk.Label(container, text=ui.LABEL_LANGUAGE).grid(row=8, column=0, sticky=tk.W, pady=4)
        language_labels = [label for label, _ in LANGUAGE_OPTIONS]
        self.language_combo = ttk.Combobox(
            container,
            values=language_labels,
            textvariable=self.language_var,
            state="readonly",
        )
        self.language_combo.grid(row=8, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_OUTPUT_FORMAT).grid(row=9, column=0, sticky=tk.W, pady=4)
        self.output_format_combo = ttk.Combobox(
            container,
            values=OUTPUT_FORMATS,
            textvariable=self.output_format_var,
            state="readonly",
        )
        self.output_format_combo.grid(row=9, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_WHISPER_MODEL).grid(row=10, column=0, sticky=tk.W, pady=4)
        self.model_combo = ttk.Combobox(
            container,
            values=WHISPER_MODELS,
            textvariable=self.model_var,
            state="readonly",
        )
        self.model_combo.grid(row=10, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_COMPUTE_DEVICE).grid(row=11, column=0, sticky=tk.W, pady=4)
        device_labels = [label for label, _ in COMPUTE_DEVICE_OPTIONS]
        self.compute_device_combo = ttk.Combobox(
            container,
            values=device_labels,
            textvariable=self.compute_device_var,
            state="readonly",
        )
        self.compute_device_combo.grid(row=11, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text=ui.LABEL_SEGMENT_LENGTH).grid(
            row=12, column=0, sticky=tk.W, pady=4
        )
        self.segment_entry = ttk.Entry(container, textvariable=self.segment_seconds_var)
        self.segment_entry.grid(row=12, column=1, sticky=tk.EW, padx=8, pady=4)
        self.include_timestamps_check = ttk.Checkbutton(
            container,
            text=ui.LABEL_INCLUDE_TIMESTAMPS,
            variable=self.include_timestamps_var,
        )
        self.include_timestamps_check.grid(row=12, column=2, sticky=tk.W, pady=4)

        buttons = ttk.Frame(container)
        buttons.grid(row=13, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4))
        buttons.columnconfigure(0, weight=0)
        buttons.columnconfigure(1, weight=0)
        buttons.columnconfigure(2, weight=0)
        buttons.columnconfigure(3, weight=0)
        buttons.columnconfigure(4, weight=1)

        self.start_button = ttk.Button(
            buttons, text=ui.BUTTON_START_TRANSCRIPTION, command=self._start_transcription
        )
        self.start_button.grid(row=0, column=0, padx=(0, 8))

        self.cancel_button = ttk.Button(
            buttons,
            text=ui.BUTTON_CANCEL,
            command=self._cancel_transcription,
            state=tk.DISABLED,
        )
        self.cancel_button.grid(row=0, column=1)

        self.open_containing_folder_button = ttk.Button(
            buttons,
            text=ui.BUTTON_OPEN_CONTAINING_FOLDER,
            command=self._open_containing_folder,
            state=tk.DISABLED,
        )
        self.open_containing_folder_button.grid(row=0, column=2, padx=(8, 0))

        self.edit_in_notepad_button = ttk.Button(
            buttons,
            text=ui.BUTTON_EDIT_IN_NOTEPAD,
            command=self._edit_in_notepad,
            state=tk.DISABLED,
        )
        self.edit_in_notepad_button.grid(row=0, column=3, padx=(8, 0))

        ttk.Label(buttons, textvariable=self.status_var).grid(
            row=0, column=4, sticky=tk.E, padx=(10, 0)
        )

        self.progress_bar = ttk.Progressbar(
            container,
            variable=self.progress_var,
            mode="determinate",
            maximum=100,
        )
        self.progress_bar.grid(row=14, column=0, columnspan=3, sticky=tk.EW, pady=(6, 10))

        log_header = ttk.Frame(container)
        log_header.grid(row=15, column=0, columnspan=3, sticky=tk.EW)
        ttk.Label(log_header, text=ui.LOG_PANEL_TITLE).pack(side=tk.LEFT)
        self.clear_log_button = ttk.Button(
            log_header, text=ui.BUTTON_CLEAR_LOG, command=self._clear_log
        )
        self.clear_log_button.pack(side=tk.RIGHT)

        self.log_text = tk.Text(container, height=13, state=tk.DISABLED, wrap="word")
        self.log_text.grid(row=16, column=0, columnspan=3, sticky=tk.NSEW)
        container.rowconfigure(16, weight=1)

        log_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=16, column=3, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _apply_saved_settings(self) -> None:
        defaults = {
            "input_format": DEFAULT_INPUT_FORMAT,
            "output_dir": self.output_dir_var.get(),
            "language": DEFAULT_LANGUAGE,
            "output_format": DEFAULT_OUTPUT_FORMAT,
            "model_name": DEFAULT_MODEL,
            "compute_device": DEFAULT_COMPUTE_DEVICE,
            "segment_seconds": DEFAULT_SEGMENT_SECONDS,
            "include_timestamps": DEFAULT_INCLUDE_TIMESTAMPS,
            "run_policy": DEFAULT_RUN_POLICY,
        }
        settings = load_app_settings(defaults=defaults)

        input_format = str(settings.get("input_format", DEFAULT_INPUT_FORMAT)).strip().lower()
        if input_format in INPUT_FORMATS:
            self.input_format_var.set(input_format)

        output_dir = str(settings.get("output_dir", self.output_dir_var.get())).strip()
        if output_dir:
            self.output_dir_var.set(output_dir)
            self.session_logger.set_output_dir(output_dir)

        language_code = str(settings.get("language", DEFAULT_LANGUAGE)).strip().lower()
        self.language_var.set(
            self.label_by_language.get(language_code, self.language_var.get())
        )

        output_format = str(settings.get("output_format", DEFAULT_OUTPUT_FORMAT)).strip().lower()
        if output_format in OUTPUT_FORMATS:
            self.output_format_var.set(output_format)

        model_name = str(settings.get("model_name", DEFAULT_MODEL)).strip()
        if model_name in WHISPER_MODELS:
            self.model_var.set(model_name)

        compute_device = str(settings.get("compute_device", DEFAULT_COMPUTE_DEVICE)).strip().lower()
        self.compute_device_var.set(
            self.label_by_device.get(compute_device, self.compute_device_var.get())
        )

        try:
            segment_seconds = int(settings.get("segment_seconds", DEFAULT_SEGMENT_SECONDS))
        except (TypeError, ValueError):
            segment_seconds = DEFAULT_SEGMENT_SECONDS
        self.segment_seconds_var.set(str(max(1, segment_seconds)))

        include_timestamps_raw = settings.get("include_timestamps", False)
        if isinstance(include_timestamps_raw, str):
            include_timestamps = include_timestamps_raw.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        else:
            include_timestamps = bool(include_timestamps_raw)
        self.include_timestamps_var.set(include_timestamps)
        run_policy_code = str(settings.get("run_policy", DEFAULT_RUN_POLICY)).strip().lower()
        self.run_policy_var.set(
            self.label_by_run_policy.get(run_policy_code, ui.RUN_POLICY_CONTINUE)
        )

    def _collect_settings_payload(self) -> dict[str, object]:
        language_label = self.language_var.get()
        language_code = self.language_by_label.get(language_label, DEFAULT_LANGUAGE)
        compute_label = self.compute_device_var.get()
        compute_code = self.device_by_label.get(compute_label, DEFAULT_COMPUTE_DEVICE)
        run_policy_label = self.run_policy_var.get()
        run_policy = self.run_policy_by_label.get(run_policy_label, DEFAULT_RUN_POLICY)
        try:
            segment_seconds = int(self.segment_seconds_var.get().strip())
        except (TypeError, ValueError):
            segment_seconds = DEFAULT_SEGMENT_SECONDS

        return {
            "input_format": self.input_format_var.get().strip().lower(),
            "output_dir": self.output_dir_var.get().strip(),
            "language": language_code,
            "output_format": self.output_format_var.get().strip().lower(),
            "model_name": self.model_var.get().strip(),
            "compute_device": compute_code,
            "segment_seconds": max(1, segment_seconds),
            "include_timestamps": bool(self.include_timestamps_var.get()),
            "run_policy": run_policy,
        }

    def _save_settings(self) -> None:
        save_app_settings(self._collect_settings_payload())

    def _get_file_dialog_types(self) -> list[tuple[str, str]]:
        selected_format = self.input_format_var.get().strip().lower()
        if selected_format and selected_format != "auto":
            return [
                (
                    ui.FILE_DIALOG_SELECTED_FORMAT_LABEL.format(
                        format=selected_format.upper(),
                    ),
                    ui.FILE_DIALOG_SELECTED_FORMAT_PATTERN.format(format=selected_format),
                ),
                (ui.FILE_DIALOG_ALL_FILES_LABEL, ui.FILE_DIALOG_ALL_FILES_PATTERN),
            ]
        return INPUT_FILE_DIALOG_TYPES

    def _is_youtube_item(self, item: str) -> bool:
        normalized = item.strip().lower()
        return normalized.startswith("http://") or normalized.startswith("https://")

    def _format_duration(self, seconds: int) -> str:
        if seconds <= 0:
            return ui.YT_UNKNOWN_DURATION
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _format_eta(self, seconds: float | None) -> str:
        return format_eta(seconds)

    def _infer_stage_label(self, message: str) -> str:
        return infer_stage_label(message)

    def _get_queue_display_text(self, item: str) -> str:
        if not self._is_youtube_item(item):
            return item
        info = self.youtube_info_cache.get(item)
        if isinstance(info, dict):
            title = str(info.get("title") or "").strip()
            if title:
                return f"{ui.YT_PREFIX}{title}"
        return f"{ui.YT_PREFIX}{item}"

    def _fetch_youtube_info(self, url: str | None = None) -> dict[str, object] | None:
        target_url = (url or self.yt_url_var.get()).strip()
        if not target_url:
            messagebox.showerror(ui.TITLE_MISSING_DATA, ui.MSG_ENTER_YOUTUBE_URL)
            return None
        if not is_youtube_url(target_url):
            messagebox.showerror(ui.TITLE_VALIDATION_ERROR, ui.MSG_ENTER_VALID_YOUTUBE_URL)
            return None
        try:
            cached_info = get_cached_video_info(target_url)
            info = cached_info if cached_info is not None else fetch_video_info(target_url)
        except (TranscriptionError, Exception) as exc:
            messagebox.showerror(ui.TITLE_YOUTUBE, str(exc))
            return None

        self.youtube_info_cache[target_url] = info
        title = str(info.get("title") or ui.YT_UNKNOWN_TITLE)
        raw_duration = info.get("duration_seconds")
        try:
            duration_seconds = int(raw_duration) if raw_duration is not None else 0
        except (TypeError, ValueError):
            duration_seconds = 0

        self.yt_info_var.set(f"{title} ({self._format_duration(duration_seconds)})")
        self._log(ui.LOG_FETCHED_YT_INFO.format(title=title))
        if duration_seconds > 4 * 3600:
            self._log(ui.LOG_YT_TOO_LONG)
        return info

    def _add_youtube_to_queue(self) -> None:
        url = self.yt_url_var.get().strip()
        if not url:
            messagebox.showerror(ui.TITLE_MISSING_DATA, ui.MSG_ENTER_YOUTUBE_URL)
            return
        if not is_youtube_url(url):
            messagebox.showerror(ui.TITLE_VALIDATION_ERROR, ui.MSG_ENTER_VALID_YOUTUBE_URL)
            return
        existing = {item.lower() for item in self.file_queue}
        if url.lower() in existing:
            messagebox.showinfo(ui.TITLE_QUEUE, ui.MSG_URL_ALREADY_QUEUED)
            return
        info = self._fetch_youtube_info(url=url)
        if info is None:
            return
        self.queue_service.append_unique(url)
        self._refresh_queue_view()
        self._log(ui.LOG_ADDED_YT_TO_QUEUE.format(value=info.get("title") or url))

    def _browse_input(self) -> None:
        chosen = filedialog.askopenfilename(
            title=ui.FILE_DIALOG_SELECT_INPUT,
            filetypes=self._get_file_dialog_types(),
        )
        if chosen:
            self.input_path_var.set(chosen)
            self._log(ui.LOG_SELECTED_INPUT_FILE.format(path=chosen))

    def _add_input_to_queue(self) -> None:
        candidate = self.input_path_var.get().strip()
        if not candidate:
            messagebox.showerror(ui.TITLE_MISSING_DATA, ui.MSG_SELECT_INPUT_FILE_FIRST)
            return
        added, skipped = self._enqueue_files([candidate])
        if added:
            self._log(ui.LOG_ADDED_TO_QUEUE.format(path=candidate))
        elif skipped:
            messagebox.showinfo(
                ui.TITLE_QUEUE,
                ui.MSG_FILE_NOT_ADDED,
            )

    def _add_many_to_queue(self) -> None:
        chosen = filedialog.askopenfilenames(
            title=ui.FILE_DIALOG_SELECT_QUEUE_FILES,
            filetypes=self._get_file_dialog_types(),
        )
        if not chosen:
            return
        added, skipped = self._enqueue_files(list(chosen))
        self._log(ui.LOG_QUEUE_UPDATED.format(added=added, skipped=skipped))

    def _remove_selected_from_queue(self) -> None:
        selected = sorted(self.queue_listbox.curselection(), reverse=True)
        if not selected:
            return
        removed_count = self.queue_service.remove_indices(selected)
        self._refresh_queue_view()
        self._log(ui.LOG_REMOVED_SELECTED.format(count=removed_count))

    def _move_selected_up(self) -> None:
        selected = list(self.queue_listbox.curselection())
        if not selected or selected[0] == 0:
            return

        new_selection = self.queue_service.move_up(selected)
        self._refresh_queue_view()
        for index in new_selection:
            self.queue_listbox.selection_set(index)
        self._log(ui.LOG_MOVED_UP)

    def _move_selected_down(self) -> None:
        selected = list(self.queue_listbox.curselection())
        if not selected or selected[-1] >= len(self.file_queue) - 1:
            return

        new_selection = self.queue_service.move_down(selected)
        self._refresh_queue_view()
        for index in new_selection:
            self.queue_listbox.selection_set(index)
        self._log(ui.LOG_MOVED_DOWN)

    def _retry_failed_items(self) -> None:
        if not self.last_failed_items:
            messagebox.showinfo(ui.TITLE_QUEUE, ui.MSG_NO_FAILED_ITEMS)
            return

        existing = {item.lower() for item in self.file_queue}
        added_count = 0
        for item in self.last_failed_items:
            candidate = item.strip()
            if not candidate:
                continue
            if self._is_youtube_item(candidate):
                normalized = candidate
            else:
                normalized = str(Path(candidate).expanduser().resolve())
                if not Path(normalized).is_file():
                    continue

            if normalized.lower() in existing:
                continue
            self.queue_service.append_unique(normalized)
            existing.add(normalized.lower())
            added_count += 1

        self._refresh_queue_view()
        if added_count <= 0:
            messagebox.showinfo(ui.TITLE_QUEUE, ui.MSG_NO_FAILED_ITEMS)
            return
        self._log(ui.LOG_RETRIED_FAILED.format(count=added_count))

    def _clear_queue(self) -> None:
        self.queue_service.clear()
        self.youtube_info_cache.clear()
        self.yt_url_var.set("")
        self.yt_info_var.set("")
        self.input_path_var.set("")
        self._refresh_queue_view()
        self._log(ui.LOG_QUEUE_CLEARED)

    def _enqueue_files(self, paths: list[str]) -> tuple[int, int]:
        added, skipped = self.queue_service.enqueue_local_paths(paths)
        self._refresh_queue_view()
        return added, skipped

    def _refresh_queue_view(self) -> None:
        self.queue_listbox.delete(0, tk.END)
        for item in self.file_queue:
            self.queue_listbox.insert(tk.END, self._get_queue_display_text(item))
        self.queue_status_var.set(ui.QUEUE_STATUS_TEMPLATE.format(count=len(self.file_queue)))

    def _get_transcription_targets(self) -> tuple[list[str], bool]:
        if self.file_queue:
            return list(self.file_queue), True
        single = self.input_path_var.get().strip()
        if single:
            return [single], False
        return [], False

    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title=ui.FILE_DIALOG_SELECT_OUTPUT_FOLDER,
            initialdir=self.output_dir_var.get() or str(Path.cwd()),
        )
        if chosen:
            self.output_dir_var.set(chosen)
            self.session_logger.set_output_dir(chosen)
            self._log(ui.LOG_SELECTED_OUTPUT_FOLDER.format(path=chosen))
            self._save_settings()

    def _start_transcription(self) -> None:
        if self.is_running:
            return

        input_files, queue_mode = self._get_transcription_targets()
        if not input_files:
            messagebox.showerror(
                ui.TITLE_MISSING_DATA,
                ui.MSG_SELECT_INPUT_OR_QUEUE,
            )
            return

        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showerror(ui.TITLE_MISSING_DATA, ui.MSG_SELECT_OUTPUT_FOLDER)
            return

        try:
            segment_seconds = int(self.segment_seconds_var.get().strip())
            if segment_seconds <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(ui.TITLE_VALIDATION_ERROR, ui.MSG_SEGMENT_LENGTH_POSITIVE)
            return

        self.active_queue_mode = queue_mode
        self.generated_output_paths.clear()
        self.last_failed_items.clear()
        self._update_output_action_buttons_state()
        self._save_settings()

        self.cancel_event.clear()
        self._drain_ui_events()
        self._set_running_state(True)
        self.progress_var.set(0.0)
        self.status_var.set(ui.STATUS_RUNNING)
        self._log(ui.LOG_TRANSCRIPTION_STARTED.format(count=len(input_files)))
        self.session_logger.set_output_dir(output_dir)

        language_label = self.language_var.get()
        language_code = self.language_by_label.get(language_label, "auto")
        device_label = self.compute_device_var.get()
        compute_device = self.device_by_label.get(device_label, "auto")
        run_policy_label = self.run_policy_var.get()
        run_policy = self.run_policy_by_label.get(run_policy_label, DEFAULT_RUN_POLICY)

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            kwargs={
                "input_files": input_files,
                "input_format": self.input_format_var.get(),
                "output_dir": output_dir,
                "language": language_code,
                "compute_device": compute_device,
                "output_format": self.output_format_var.get(),
                "model_name": self.model_var.get(),
                "segment_seconds": segment_seconds,
                "include_timestamps": bool(self.include_timestamps_var.get()),
                "run_policy": run_policy,
            },
            daemon=True,
        )
        self.worker_thread.start()
        self.root.after(120, self._process_queue)

    def _get_available_output_paths(self) -> list[str]:
        return [path for path in self.generated_output_paths if Path(path).is_file()]

    def _get_latest_output_path(self) -> str | None:
        available_paths = self._get_available_output_paths()
        if not available_paths:
            return None
        return available_paths[-1]

    def _update_output_action_buttons_state(self) -> None:
        if self.is_running:
            self.open_containing_folder_button.configure(state=tk.DISABLED)
            self.edit_in_notepad_button.configure(state=tk.DISABLED)
            return
        state = tk.NORMAL if self._get_available_output_paths() else tk.DISABLED
        self.open_containing_folder_button.configure(state=state)
        self.edit_in_notepad_button.configure(state=state)

    def _open_containing_folder(self) -> None:
        output_path = self._get_latest_output_path()
        if output_path is None:
            self._log(ui.MSG_NO_TRANSCRIPTION_FILE_AVAILABLE)
            messagebox.showerror(
                ui.TITLE_TRANSCRIPTION_FILE,
                ui.MSG_NO_TRANSCRIPTION_FILE_AVAILABLE,
            )
            self._update_output_action_buttons_state()
            return

        containing_folder = Path(output_path).parent
        try:
            if os.name == "nt":
                os.startfile(str(containing_folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(containing_folder)])
            self._log(ui.LOG_OPENED_CONTAINING_FOLDER.format(path=containing_folder))
        except OSError as exc:
            message = ui.LOG_FAILED_OPEN_CONTAINING_FOLDER.format(error=str(exc))
            self._log(message)
            messagebox.showerror(ui.TITLE_TRANSCRIPTION_FILE, message)

    def _edit_in_notepad(self) -> None:
        output_path = self._get_latest_output_path()
        if output_path is None:
            self._log(ui.MSG_NO_TRANSCRIPTION_FILE_AVAILABLE)
            messagebox.showerror(
                ui.TITLE_TRANSCRIPTION_FILE,
                ui.MSG_NO_TRANSCRIPTION_FILE_AVAILABLE,
            )
            self._update_output_action_buttons_state()
            return

        try:
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", output_path])
            else:
                subprocess.Popen(["xdg-open", output_path])
            self._log(ui.LOG_OPENED_IN_NOTEPAD.format(path=output_path))
        except OSError as exc:
            message = ui.LOG_FAILED_OPEN_IN_NOTEPAD.format(error=str(exc))
            self._log(message)
            messagebox.showerror(ui.TITLE_TRANSCRIPTION_FILE, message)

    def _run_worker(
        self,
        input_files: list[str],
        input_format: str,
        output_dir: str,
        language: str,
        compute_device: str,
        output_format: str,
        model_name: str,
        segment_seconds: int,
        include_timestamps: bool,
        run_policy: str,
    ) -> None:
        try:
            total_files = len(input_files)
            outputs: list[str] = []
            failures: list[tuple[str, str]] = []
            destination_dir = Path(output_dir).expanduser().resolve()
            batch_started_at = time.perf_counter()
            stopped_on_error = False
            pending_items: list[str] = []

            for index, queue_item in enumerate(input_files, start=1):
                if self.cancel_event.is_set():
                    raise TranscriptionCancelled(ui.MSG_TRANSCRIPTION_CANCELLED)

                self.ui_queue.put(("item_started", index, total_files, queue_item))

                normalized_item = queue_item.strip()
                is_yt_item = self._is_youtube_item(normalized_item)
                input_for_transcription = normalized_item
                selected_input_format = input_format
                item_label = self._get_queue_display_text(normalized_item)
                extra_metadata: dict[str, object] | None = None
                downloaded_audio_path: Path | None = None
                yt_download_dir: Path | None = None
                item_started_at = time.perf_counter()
                transcription_stage_metrics: dict[str, float] = {}
                item_result = ItemRunResult(
                    queue_index=index,
                    queue_total=total_files,
                    source_kind="youtube" if is_yt_item else "local",
                    source_path=normalized_item,
                    model_name=model_name,
                    compute_device=compute_device,
                    output_format=output_format,
                    run_policy=run_policy,
                )
                item_metrics = item_result.metrics

                if not is_yt_item:
                    item_label = Path(normalized_item).name

                def update_item_progress(message: str, progress: float) -> None:
                    bounded = max(0.0, min(100.0, progress))
                    global_progress = (((index - 1) * 100.0) + bounded) / total_files
                    stage_label = self._infer_stage_label(message)
                    item_elapsed = max(0.0, time.perf_counter() - item_started_at)
                    batch_elapsed = max(0.0, time.perf_counter() - batch_started_at)
                    item_eta = estimate_eta_seconds(item_elapsed, bounded)
                    batch_eta = estimate_eta_seconds(batch_elapsed, global_progress)
                    prefixed = (
                        f"[{index}/{total_files}] {item_label} [{stage_label}]: {message}"
                        f" | ETA item: {self._format_eta(item_eta)}"
                        f" | ETA total: {self._format_eta(batch_eta)}"
                    )
                    self._worker_progress(prefixed, global_progress)

                try:
                    if is_yt_item:
                        yt_url = normalized_item
                        metadata_started_at = time.perf_counter()
                        cached_yt_info = get_cached_video_info(yt_url)
                        item_metrics["yt_metadata_cache_hit"] = cached_yt_info is not None
                        yt_info = cached_yt_info if cached_yt_info is not None else fetch_video_info(yt_url)
                        item_metrics["yt_metadata_seconds"] = round(
                            max(0.0, time.perf_counter() - metadata_started_at),
                            4,
                        )
                        self.youtube_info_cache[yt_url] = yt_info

                        yt_title = str(yt_info.get("title") or yt_url)
                        raw_duration = yt_info.get("duration_seconds")
                        try:
                            duration_seconds = (
                                int(raw_duration) if raw_duration is not None else 0
                            )
                        except (TypeError, ValueError):
                            duration_seconds = 0

                        if duration_seconds > 4 * 3600:
                            update_item_progress(
                                ui.LOG_YT_TOO_LONG,
                                0.0,
                            )

                        item_label = f"{ui.YT_PREFIX}{yt_title}"
                        extra_metadata = {
                            "youtube": {
                                "url": yt_url,
                                "title": yt_title,
                                "duration_seconds": duration_seconds,
                            }
                        }
                        yt_download_dir = destination_dir / DEFAULT_YT_DOWNLOAD_DIR

                        def download_progress(message: str, progress: float) -> None:
                            scaled_progress = max(0.0, min(100.0, progress)) * 0.30
                            update_item_progress(message, scaled_progress)

                        download_started_at = time.perf_counter()
                        downloaded_audio_path = download_audio(
                            url=yt_url,
                            output_dir=yt_download_dir,
                            progress_callback=download_progress,
                            cancel_event=self.cancel_event,
                        )
                        item_metrics["yt_download_seconds"] = round(
                            max(0.0, time.perf_counter() - download_started_at),
                            4,
                        )
                        input_for_transcription = str(downloaded_audio_path)
                        selected_input_format = DEFAULT_INPUT_FORMAT

                        def item_progress(message: str, progress: float) -> None:
                            scaled_progress = 30.0 + max(0.0, min(100.0, progress)) * 0.70
                            update_item_progress(message, scaled_progress)
                    else:
                        item_progress = update_item_progress

                    transcription_started_at = time.perf_counter()
                    output_path = run_transcription(
                        input_path=input_for_transcription,
                        selected_input_format=selected_input_format,
                        output_dir=output_dir,
                        language=language,
                        compute_device=compute_device,
                        output_format=output_format,
                        model_name=model_name,
                        segment_time_sec=segment_seconds,
                        progress_callback=item_progress,
                        cancel_event=self.cancel_event,
                        extra_metadata=extra_metadata,
                        stage_metrics=transcription_stage_metrics,
                        include_timestamps=include_timestamps,
                    )
                    item_metrics["transcription_call_seconds"] = round(
                        max(0.0, time.perf_counter() - transcription_started_at),
                        4,
                    )
                    for metric_name, metric_value in transcription_stage_metrics.items():
                        item_metrics[f"stage_{metric_name}"] = metric_value
                    item_metrics["item_total_seconds"] = round(
                        max(0.0, time.perf_counter() - item_started_at),
                        4,
                    )
                    item_result.result = "success"
                    item_result.output_path = str(output_path)
                    outputs.append(str(output_path))
                    self.ui_queue.put(
                        (
                            "item_done",
                            index,
                            total_files,
                            queue_item,
                            str(output_path),
                            asdict(item_result),
                        )
                    )
                except TranscriptionCancelled:
                    raise
                except (TranscriptionError, Exception) as exc:
                    for metric_name, metric_value in transcription_stage_metrics.items():
                        item_metrics[f"stage_{metric_name}"] = metric_value
                    item_metrics["item_total_seconds"] = round(
                        max(0.0, time.perf_counter() - item_started_at),
                        4,
                    )
                    item_result.result = "error"
                    item_result.error = str(exc)
                    failures.append((queue_item, str(exc)))
                    self.ui_queue.put(
                        (
                            "item_error",
                            index,
                            total_files,
                            queue_item,
                            str(exc),
                            asdict(item_result),
                        )
                    )
                    if run_policy == "stop":
                        stopped_on_error = True
                        pending_items = list(input_files[index:])
                        self._worker_progress(
                            ui.LOG_STOPPED_ON_FIRST_ERROR,
                            (index / max(total_files, 1)) * 100.0,
                        )
                        break
                finally:
                    if downloaded_audio_path is not None and downloaded_audio_path.exists():
                        try:
                            downloaded_audio_path.unlink()
                        except OSError:
                            pass
                    if yt_download_dir is not None and yt_download_dir.exists():
                        try:
                            yt_download_dir.rmdir()
                        except OSError:
                            pass

            batch_summary = BatchRunSummary(
                total_items=total_files,
                success_items=len(outputs),
                failed_items=len(failures),
                run_policy=run_policy,
                stopped_on_error=stopped_on_error,
                pending_items=len(pending_items),
                total_seconds=round(
                    max(0.0, time.perf_counter() - batch_started_at),
                    4,
                ),
            )
            self.ui_queue.put(
                (
                    "batch_done",
                    outputs,
                    failures,
                    asdict(batch_summary),
                    pending_items,
                    stopped_on_error,
                )
            )
        except TranscriptionCancelled as exc:
            self.ui_queue.put(("cancelled", str(exc)))
        except (TranscriptionError, Exception) as exc:
            self.ui_queue.put(("error", str(exc)))

    def _worker_progress(self, message: str, progress: float) -> None:
        self.ui_queue.put(("progress", message, progress))

    def _process_queue(self) -> None:
        while True:
            try:
                event = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "progress":
                _, message, progress = event
                self.progress_var.set(progress)
                self.status_var.set(message)
                self._log(message)
            elif kind == "item_started":
                _, index, total, input_file = event
                self.status_var.set(ui.STATUS_RUNNING_ITEM_TEMPLATE.format(index=index, total=total))
                self._log(
                    ui.LOG_PROCESSING_ITEM.format(
                        index=index,
                        total=total,
                        label=self._get_queue_display_text(input_file),
                    )
                )
            elif kind == "item_done":
                _, index, total, input_file, output_path, item_metrics = event
                self.generated_output_paths.append(output_path)
                self._log(
                    ui.LOG_DONE_ITEM.format(
                        index=index,
                        total=total,
                        label=self._get_queue_display_text(input_file),
                        output=output_path,
                    ),
                    context=item_metrics,
                )
            elif kind == "item_error":
                _, index, total, input_file, error_text, item_metrics = event
                self._log(
                    ui.LOG_FAILED_ITEM.format(
                        index=index,
                        total=total,
                        label=self._get_queue_display_text(input_file),
                        error=error_text,
                    ),
                    context=item_metrics,
                )
            elif kind == "batch_done":
                _, outputs, failures, batch_metrics, pending_items, stopped_on_error = event
                self.progress_var.set(100.0)
                success_count = len(outputs)
                failure_count = len(failures)
                self.last_failed_items = [item[0] for item in failures]

                if self.active_queue_mode:
                    if stopped_on_error:
                        retained_paths = {
                            item[0].lower() for item in failures
                        } | {item.lower() for item in pending_items}
                    else:
                        retained_paths = {item[0].lower() for item in failures}
                    self.queue_service.retain_items(retained_paths)
                    self._refresh_queue_view()

                if stopped_on_error:
                    self._log(
                        ui.LOG_STOPPED_ON_FIRST_ERROR,
                        level="WARNING",
                        context=batch_metrics,
                    )

                if failure_count == 0:
                    self.status_var.set(ui.STATUS_FINISHED)
                    self._log(
                        ui.LOG_BATCH_FINISHED.format(count=success_count),
                        context=batch_metrics,
                    )
                    messagebox.showinfo(
                        ui.TITLE_DONE,
                        ui.MSG_PROCESSED_SUMMARY.format(success=success_count, failed=0),
                    )
                else:
                    if success_count == 0:
                        self.status_var.set(ui.STATUS_FAILED)
                    else:
                        self.status_var.set(ui.STATUS_FINISHED_WITH_ERRORS)
                    self._log(
                        ui.LOG_BATCH_FINISHED_WITH_ERRORS.format(
                            success=success_count,
                            failed=failure_count,
                        ),
                        context=batch_metrics,
                    )
                    queue_note = (
                        ui.QUEUE_FAILED_NOTE
                        if self.active_queue_mode
                        else ""
                    )
                    if stopped_on_error and self.active_queue_mode:
                        queue_note += ui.QUEUE_STOPPED_NOTE
                    messagebox.showwarning(
                        ui.TITLE_FINISHED_WITH_ERRORS,
                        (
                            ui.MSG_PROCESSED_SUMMARY.format(
                                success=success_count,
                                failed=failure_count,
                            )
                            + queue_note
                        ),
                    )

                self.active_queue_mode = False
                self._set_running_state(False)
            elif kind == "cancelled":
                reason = event[1]
                self.status_var.set(ui.STATUS_CANCELLED)
                self._log(reason)
                self.active_queue_mode = False
                self._set_running_state(False)
                messagebox.showwarning(ui.TITLE_CANCELLED, reason)
            elif kind == "error":
                error_text = event[1]
                self.status_var.set(ui.STATUS_ERROR)
                self._log(ui.LOG_ERROR.format(error=error_text))
                self.active_queue_mode = False
                self._set_running_state(False)
                messagebox.showerror(ui.TITLE_ERROR, error_text)

        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(120, self._process_queue)

    def _cancel_transcription(self) -> None:
        if not self.is_running:
            return
        self.cancel_event.set()
        self.status_var.set(ui.STATUS_CANCELLING)
        self._log(ui.LOG_CANCELLATION_REQUESTED)

    def _set_running_state(self, running: bool) -> None:
        self.is_running = running
        if running:
            self.start_button.configure(state=tk.DISABLED)
            self.cancel_button.configure(state=tk.NORMAL)
            self.yt_entry.configure(state=tk.DISABLED)
            self.fetch_yt_button.configure(state=tk.DISABLED)
            self.add_yt_button.configure(state=tk.DISABLED)
            self.input_entry.configure(state=tk.DISABLED)
            self.output_entry.configure(state=tk.DISABLED)
            self.segment_entry.configure(state=tk.DISABLED)
            self.browse_input_button.configure(state=tk.DISABLED)
            self.add_path_button.configure(state=tk.DISABLED)
            self.add_many_button.configure(state=tk.DISABLED)
            self.remove_queue_button.configure(state=tk.DISABLED)
            self.move_up_queue_button.configure(state=tk.DISABLED)
            self.move_down_queue_button.configure(state=tk.DISABLED)
            self.retry_failed_button.configure(state=tk.DISABLED)
            self.clear_queue_button.configure(state=tk.DISABLED)
            self.select_output_button.configure(state=tk.DISABLED)
            self.queue_listbox.configure(state=tk.DISABLED)
            self.input_format_combo.configure(state=tk.DISABLED)
            self.run_policy_combo.configure(state=tk.DISABLED)
            self.language_combo.configure(state=tk.DISABLED)
            self.output_format_combo.configure(state=tk.DISABLED)
            self.model_combo.configure(state=tk.DISABLED)
            self.compute_device_combo.configure(state=tk.DISABLED)
            self.include_timestamps_check.configure(state=tk.DISABLED)
            self.clear_log_button.configure(state=tk.DISABLED)
            self.open_containing_folder_button.configure(state=tk.DISABLED)
            self.edit_in_notepad_button.configure(state=tk.DISABLED)
        else:
            self.start_button.configure(state=tk.NORMAL)
            self.cancel_button.configure(state=tk.DISABLED)
            self.yt_entry.configure(state=tk.NORMAL)
            self.fetch_yt_button.configure(state=tk.NORMAL)
            self.add_yt_button.configure(state=tk.NORMAL)
            self.input_entry.configure(state=tk.NORMAL)
            self.output_entry.configure(state=tk.NORMAL)
            self.segment_entry.configure(state=tk.NORMAL)
            self.browse_input_button.configure(state=tk.NORMAL)
            self.add_path_button.configure(state=tk.NORMAL)
            self.add_many_button.configure(state=tk.NORMAL)
            self.remove_queue_button.configure(state=tk.NORMAL)
            self.move_up_queue_button.configure(state=tk.NORMAL)
            self.move_down_queue_button.configure(state=tk.NORMAL)
            self.retry_failed_button.configure(state=tk.NORMAL)
            self.clear_queue_button.configure(state=tk.NORMAL)
            self.select_output_button.configure(state=tk.NORMAL)
            self.queue_listbox.configure(state=tk.NORMAL)
            self.input_format_combo.configure(state="readonly")
            self.run_policy_combo.configure(state="readonly")
            self.language_combo.configure(state="readonly")
            self.output_format_combo.configure(state="readonly")
            self.model_combo.configure(state="readonly")
            self.compute_device_combo.configure(state="readonly")
            self.include_timestamps_check.configure(state=tk.NORMAL)
            self.clear_log_button.configure(state=tk.NORMAL)
            self._update_output_action_buttons_state()

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _log(
        self,
        message: str,
        level: str = "INFO",
        context: dict[str, object] | None = None,
    ) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        payload = {"status": self.status_var.get()}
        if context:
            payload.update(context)
        self.session_logger.log(
            level=level,
            message=message,
            context=payload,
        )

    def _drain_ui_events(self) -> None:
        while True:
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                break

    def _on_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            should_close = messagebox.askyesno(
                ui.TITLE_EXIT,
                ui.MSG_EXIT_WHILE_RUNNING,
            )
            if not should_close:
                return
            self.cancel_event.set()
        self._save_settings()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_app() -> None:
    app = TranscriberApp()
    app.run()


