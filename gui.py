from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import (
    APP_TITLE,
    COMPUTE_DEVICE_OPTIONS,
    DEFAULT_COMPUTE_DEVICE,
    DEFAULT_INPUT_FORMAT,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FORMAT,
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
from youtube_service import download_audio, fetch_video_info, is_youtube_url


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
        self.file_queue: list[str] = []
        self.youtube_info_cache: dict[str, dict[str, object]] = {}
        self.active_queue_mode = False

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
        self.queue_status_var = tk.StringVar(value="0 files queued")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(16, weight=1)

        ttk.Label(container, text="YouTube URL").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.yt_entry = ttk.Entry(container, textvariable=self.yt_url_var)
        self.yt_entry.grid(row=0, column=1, sticky=tk.EW, padx=8, pady=4)
        self.fetch_yt_button = ttk.Button(
            container, text="Fetch info", command=self._fetch_youtube_info
        )
        self.fetch_yt_button.grid(row=0, column=2, sticky=tk.EW, pady=4)

        self.yt_info_label = ttk.Label(container, textvariable=self.yt_info_var)
        self.yt_info_label.grid(row=1, column=1, sticky=tk.W, padx=8, pady=(0, 4))
        self.add_yt_button = ttk.Button(
            container, text="Add YT to queue", command=self._add_youtube_to_queue
        )
        self.add_yt_button.grid(row=1, column=2, sticky=tk.EW, pady=(0, 4))

        ttk.Label(container, text="Input file").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.input_entry = ttk.Entry(container, textvariable=self.input_path_var)
        self.input_entry.grid(row=2, column=1, sticky=tk.EW, padx=8, pady=4)
        self.browse_input_button = ttk.Button(
            container, text="Browse...", command=self._browse_input
        )
        self.browse_input_button.grid(row=2, column=2, sticky=tk.EW, pady=4)

        queue_tools = ttk.Frame(container)
        queue_tools.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=(0, 6))
        queue_tools.columnconfigure(4, weight=1)

        self.add_path_button = ttk.Button(
            queue_tools, text="Add from path", command=self._add_input_to_queue
        )
        self.add_path_button.grid(row=0, column=0, padx=(0, 6))

        self.add_many_button = ttk.Button(
            queue_tools, text="Add many...", command=self._add_many_to_queue
        )
        self.add_many_button.grid(row=0, column=1, padx=(0, 6))

        self.remove_queue_button = ttk.Button(
            queue_tools, text="Remove selected", command=self._remove_selected_from_queue
        )
        self.remove_queue_button.grid(row=0, column=2, padx=(0, 6))

        self.clear_queue_button = ttk.Button(
            queue_tools, text="Clear queue", command=self._clear_queue
        )
        self.clear_queue_button.grid(row=0, column=3, padx=(0, 6))

        ttk.Label(queue_tools, textvariable=self.queue_status_var).grid(
            row=0, column=4, sticky=tk.E
        )

        ttk.Label(container, text="Queue").grid(row=4, column=0, sticky=tk.W, pady=(0, 4))
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

        ttk.Label(container, text="Input format").grid(row=6, column=0, sticky=tk.W, pady=4)
        self.input_format_combo = ttk.Combobox(
            container,
            values=INPUT_FORMATS,
            textvariable=self.input_format_var,
            state="readonly",
        )
        self.input_format_combo.grid(row=6, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text="Output folder").grid(row=7, column=0, sticky=tk.W, pady=4)
        self.output_entry = ttk.Entry(container, textvariable=self.output_dir_var)
        self.output_entry.grid(row=7, column=1, sticky=tk.EW, padx=8, pady=4)
        self.select_output_button = ttk.Button(
            container, text="Select...", command=self._browse_output_dir
        )
        self.select_output_button.grid(row=7, column=2, sticky=tk.EW, pady=4)

        ttk.Label(container, text="Language").grid(row=8, column=0, sticky=tk.W, pady=4)
        language_labels = [label for label, _ in LANGUAGE_OPTIONS]
        self.language_combo = ttk.Combobox(
            container,
            values=language_labels,
            textvariable=self.language_var,
            state="readonly",
        )
        self.language_combo.grid(row=8, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text="Output format").grid(row=9, column=0, sticky=tk.W, pady=4)
        self.output_format_combo = ttk.Combobox(
            container,
            values=OUTPUT_FORMATS,
            textvariable=self.output_format_var,
            state="readonly",
        )
        self.output_format_combo.grid(row=9, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text="Whisper model").grid(row=10, column=0, sticky=tk.W, pady=4)
        self.model_combo = ttk.Combobox(
            container,
            values=WHISPER_MODELS,
            textvariable=self.model_var,
            state="readonly",
        )
        self.model_combo.grid(row=10, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text="Compute device").grid(row=11, column=0, sticky=tk.W, pady=4)
        device_labels = [label for label, _ in COMPUTE_DEVICE_OPTIONS]
        self.compute_device_combo = ttk.Combobox(
            container,
            values=device_labels,
            textvariable=self.compute_device_var,
            state="readonly",
        )
        self.compute_device_combo.grid(row=11, column=1, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(container, text="Segment length (s)").grid(
            row=12, column=0, sticky=tk.W, pady=4
        )
        self.segment_entry = ttk.Entry(container, textvariable=self.segment_seconds_var)
        self.segment_entry.grid(row=12, column=1, sticky=tk.EW, padx=8, pady=4)

        buttons = ttk.Frame(container)
        buttons.grid(row=13, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4))
        buttons.columnconfigure(0, weight=0)
        buttons.columnconfigure(1, weight=0)
        buttons.columnconfigure(2, weight=1)

        self.start_button = ttk.Button(
            buttons, text="Start transcription", command=self._start_transcription
        )
        self.start_button.grid(row=0, column=0, padx=(0, 8))

        self.cancel_button = ttk.Button(
            buttons,
            text="Cancel",
            command=self._cancel_transcription,
            state=tk.DISABLED,
        )
        self.cancel_button.grid(row=0, column=1)

        ttk.Label(buttons, textvariable=self.status_var).grid(
            row=0, column=2, sticky=tk.E, padx=(10, 0)
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
        ttk.Label(log_header, text="Log").pack(side=tk.LEFT)
        self.clear_log_button = ttk.Button(
            log_header, text="Clear log", command=self._clear_log
        )
        self.clear_log_button.pack(side=tk.RIGHT)

        self.log_text = tk.Text(container, height=13, state=tk.DISABLED, wrap="word")
        self.log_text.grid(row=16, column=0, columnspan=3, sticky=tk.NSEW)
        container.rowconfigure(16, weight=1)

        log_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=16, column=3, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _get_file_dialog_types(self) -> list[tuple[str, str]]:
        selected_format = self.input_format_var.get().strip().lower()
        if selected_format and selected_format != "auto":
            return [
                (f"{selected_format.upper()} files", f"*.{selected_format}"),
                ("All files", "*.*"),
            ]
        return INPUT_FILE_DIALOG_TYPES

    def _is_youtube_item(self, item: str) -> bool:
        normalized = item.strip().lower()
        return normalized.startswith("http://") or normalized.startswith("https://")

    def _format_duration(self, seconds: int) -> str:
        if seconds <= 0:
            return "unknown duration"
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _get_queue_display_text(self, item: str) -> str:
        if not self._is_youtube_item(item):
            return item
        info = self.youtube_info_cache.get(item)
        if isinstance(info, dict):
            title = str(info.get("title") or "").strip()
            if title:
                return f"[YT] {title}"
        return f"[YT] {item}"

    def _fetch_youtube_info(self) -> dict[str, object] | None:
        url = self.yt_url_var.get().strip()
        if not url:
            messagebox.showerror("Missing data", "Enter YouTube URL first.")
            return None
        if not is_youtube_url(url):
            messagebox.showerror("Validation error", "Enter a valid YouTube URL.")
            return None
        try:
            info = fetch_video_info(url)
        except (TranscriptionError, Exception) as exc:
            messagebox.showerror("YouTube", str(exc))
            return None

        self.youtube_info_cache[url] = info
        title = str(info.get("title") or "Unknown title")
        raw_duration = info.get("duration_seconds")
        try:
            duration_seconds = int(raw_duration) if raw_duration is not None else 0
        except (TypeError, ValueError):
            duration_seconds = 0

        self.yt_info_var.set(f"{title} ({self._format_duration(duration_seconds)})")
        self._log(f"Fetched YouTube info: {title}")
        if duration_seconds > 4 * 3600:
            self._log("Warning: YouTube video is longer than 4 hours.")
        return info

    def _add_youtube_to_queue(self) -> None:
        url = self.yt_url_var.get().strip()
        if not url:
            messagebox.showerror("Missing data", "Enter YouTube URL first.")
            return
        if not is_youtube_url(url):
            messagebox.showerror("Validation error", "Enter a valid YouTube URL.")
            return
        existing = {item.lower() for item in self.file_queue}
        if url.lower() in existing:
            messagebox.showinfo("Queue", "URL was not added (already queued).")
            return
        info = self.youtube_info_cache.get(url) or self._fetch_youtube_info()
        if info is None:
            return
        self.file_queue.append(url)
        self._refresh_queue_view()
        self._log(f"Added YouTube URL to queue: {info.get('title') or url}")

    def _browse_input(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select input audio/video file",
            filetypes=self._get_file_dialog_types(),
        )
        if chosen:
            self.input_path_var.set(chosen)
            self._log(f"Selected input file: {chosen}")

    def _add_input_to_queue(self) -> None:
        candidate = self.input_path_var.get().strip()
        if not candidate:
            messagebox.showerror("Missing data", "Select an input file first.")
            return
        added, skipped = self._enqueue_files([candidate])
        if added:
            self._log(f"Added to queue: {candidate}")
        elif skipped:
            messagebox.showinfo(
                "Queue",
                "File was not added (already queued or path is invalid).",
            )

    def _add_many_to_queue(self) -> None:
        chosen = filedialog.askopenfilenames(
            title="Select files for queue",
            filetypes=self._get_file_dialog_types(),
        )
        if not chosen:
            return
        added, skipped = self._enqueue_files(list(chosen))
        self._log(f"Queue updated. Added: {added}, skipped: {skipped}.")

    def _remove_selected_from_queue(self) -> None:
        selected = sorted(self.queue_listbox.curselection(), reverse=True)
        if not selected:
            return
        for index in selected:
            del self.file_queue[index]
        self._refresh_queue_view()
        self._log(f"Removed {len(selected)} selected file(s) from queue.")

    def _clear_queue(self) -> None:
        self.file_queue.clear()
        self.youtube_info_cache.clear()
        self.yt_url_var.set("")
        self.yt_info_var.set("")
        self.input_path_var.set("")
        self._refresh_queue_view()
        self._log("Queue cleared.")

    def _enqueue_files(self, paths: list[str]) -> tuple[int, int]:
        added = 0
        skipped = 0
        existing = {item.lower() for item in self.file_queue}
        for raw_path in paths:
            if not raw_path:
                skipped += 1
                continue
            normalized = str(Path(raw_path).expanduser().resolve())
            if normalized.lower() in existing:
                skipped += 1
                continue
            if not Path(normalized).is_file():
                skipped += 1
                continue
            self.file_queue.append(normalized)
            existing.add(normalized.lower())
            added += 1
        self._refresh_queue_view()
        return added, skipped

    def _refresh_queue_view(self) -> None:
        self.queue_listbox.delete(0, tk.END)
        for item in self.file_queue:
            self.queue_listbox.insert(tk.END, self._get_queue_display_text(item))
        self.queue_status_var.set(f"{len(self.file_queue)} files queued")

    def _get_transcription_targets(self) -> tuple[list[str], bool]:
        if self.file_queue:
            return list(self.file_queue), True
        single = self.input_path_var.get().strip()
        if single:
            return [single], False
        return [], False

    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select output folder",
            initialdir=self.output_dir_var.get() or str(Path.cwd()),
        )
        if chosen:
            self.output_dir_var.set(chosen)
            self._log(f"Selected output folder: {chosen}")

    def _start_transcription(self) -> None:
        if self.is_running:
            return

        input_files, queue_mode = self._get_transcription_targets()
        if not input_files:
            messagebox.showerror(
                "Missing data",
                "Select an input file or add files to the queue first.",
            )
            return

        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showerror("Missing data", "Select an output folder.")
            return

        try:
            segment_seconds = int(self.segment_seconds_var.get().strip())
            if segment_seconds <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation error", "Segment length must be a positive integer.")
            return

        self.active_queue_mode = queue_mode

        self.cancel_event.clear()
        self._drain_ui_events()
        self._set_running_state(True)
        self.progress_var.set(0.0)
        self.status_var.set("Running")
        self._log(f"Transcription started for {len(input_files)} file(s).")

        language_label = self.language_var.get()
        language_code = self.language_by_label.get(language_label, "auto")
        device_label = self.compute_device_var.get()
        compute_device = self.device_by_label.get(device_label, "auto")

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
            },
            daemon=True,
        )
        self.worker_thread.start()
        self.root.after(120, self._process_queue)

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
    ) -> None:
        try:
            total_files = len(input_files)
            outputs: list[str] = []
            failures: list[tuple[str, str]] = []
            destination_dir = Path(output_dir).expanduser().resolve()

            for index, queue_item in enumerate(input_files, start=1):
                if self.cancel_event.is_set():
                    raise TranscriptionCancelled("Transcription cancelled.")

                self.ui_queue.put(("item_started", index, total_files, queue_item))

                normalized_item = queue_item.strip()
                is_yt_item = self._is_youtube_item(normalized_item)
                input_for_transcription = normalized_item
                selected_input_format = input_format
                item_label = self._get_queue_display_text(normalized_item)
                extra_metadata: dict[str, object] | None = None
                downloaded_audio_path: Path | None = None
                yt_download_dir: Path | None = None

                if not is_yt_item:
                    item_label = Path(normalized_item).name

                def update_item_progress(message: str, progress: float) -> None:
                    bounded = max(0.0, min(100.0, progress))
                    global_progress = (((index - 1) * 100.0) + bounded) / total_files
                    prefixed = f"[{index}/{total_files}] {item_label}: {message}"
                    self._worker_progress(prefixed, global_progress)

                try:
                    if is_yt_item:
                        yt_url = normalized_item
                        yt_info = self.youtube_info_cache.get(yt_url)
                        if yt_info is None:
                            yt_info = fetch_video_info(yt_url)
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
                                "Warning: YouTube video is longer than 4 hours.",
                                0.0,
                            )

                        item_label = f"[YT] {yt_title}"
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

                        downloaded_audio_path = download_audio(
                            url=yt_url,
                            output_dir=yt_download_dir,
                            progress_callback=download_progress,
                            cancel_event=self.cancel_event,
                        )
                        input_for_transcription = str(downloaded_audio_path)
                        selected_input_format = DEFAULT_INPUT_FORMAT

                        def item_progress(message: str, progress: float) -> None:
                            scaled_progress = 30.0 + max(0.0, min(100.0, progress)) * 0.70
                            update_item_progress(message, scaled_progress)
                    else:
                        item_progress = update_item_progress

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
                    )
                    outputs.append(str(output_path))
                    self.ui_queue.put(("item_done", index, total_files, queue_item, str(output_path)))
                except TranscriptionCancelled:
                    raise
                except (TranscriptionError, Exception) as exc:
                    failures.append((queue_item, str(exc)))
                    self.ui_queue.put(("item_error", index, total_files, queue_item, str(exc)))
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

            self.ui_queue.put(("batch_done", outputs, failures))
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
                self.status_var.set(f"Running {index}/{total}")
                self._log(f"Processing [{index}/{total}] {self._get_queue_display_text(input_file)}")
            elif kind == "item_done":
                _, index, total, input_file, output_path = event
                self._log(f"Done [{index}/{total}] {self._get_queue_display_text(input_file)} -> {output_path}")
            elif kind == "item_error":
                _, index, total, input_file, error_text = event
                self._log(f"Failed [{index}/{total}] {self._get_queue_display_text(input_file)}: {error_text}")
            elif kind == "batch_done":
                _, outputs, failures = event
                self.progress_var.set(100.0)
                success_count = len(outputs)
                failure_count = len(failures)

                if self.active_queue_mode:
                    failed_paths = {item[0] for item in failures}
                    self.file_queue = [item for item in self.file_queue if item in failed_paths]
                    self._refresh_queue_view()

                if failure_count == 0:
                    self.status_var.set("Finished")
                    self._log(f"Batch finished. Files processed: {success_count}.")
                    messagebox.showinfo(
                        "Done",
                        f"Processed files: {success_count}\nFailed files: 0",
                    )
                else:
                    if success_count == 0:
                        self.status_var.set("Failed")
                    else:
                        self.status_var.set("Finished with errors")
                    self._log(
                        f"Batch finished with errors. Success: {success_count}, failed: {failure_count}."
                    )
                    queue_note = (
                        "\nFailed files remain in queue."
                        if self.active_queue_mode
                        else ""
                    )
                    messagebox.showwarning(
                        "Finished with errors",
                        f"Processed files: {success_count}\nFailed files: {failure_count}{queue_note}",
                    )

                self.active_queue_mode = False
                self._set_running_state(False)
            elif kind == "cancelled":
                reason = event[1]
                self.status_var.set("Cancelled")
                self._log(reason)
                self.active_queue_mode = False
                self._set_running_state(False)
                messagebox.showwarning("Cancelled", reason)
            elif kind == "error":
                error_text = event[1]
                self.status_var.set("Error")
                self._log(f"Error: {error_text}")
                self.active_queue_mode = False
                self._set_running_state(False)
                messagebox.showerror("Error", error_text)

        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(120, self._process_queue)

    def _cancel_transcription(self) -> None:
        if not self.is_running:
            return
        self.cancel_event.set()
        self.status_var.set("Cancelling...")
        self._log("Cancellation requested.")

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
            self.clear_queue_button.configure(state=tk.DISABLED)
            self.select_output_button.configure(state=tk.DISABLED)
            self.queue_listbox.configure(state=tk.DISABLED)
            self.input_format_combo.configure(state=tk.DISABLED)
            self.language_combo.configure(state=tk.DISABLED)
            self.output_format_combo.configure(state=tk.DISABLED)
            self.model_combo.configure(state=tk.DISABLED)
            self.compute_device_combo.configure(state=tk.DISABLED)
            self.clear_log_button.configure(state=tk.DISABLED)
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
            self.clear_queue_button.configure(state=tk.NORMAL)
            self.select_output_button.configure(state=tk.NORMAL)
            self.queue_listbox.configure(state=tk.NORMAL)
            self.input_format_combo.configure(state="readonly")
            self.language_combo.configure(state="readonly")
            self.output_format_combo.configure(state="readonly")
            self.model_combo.configure(state="readonly")
            self.compute_device_combo.configure(state="readonly")
            self.clear_log_button.configure(state=tk.NORMAL)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _drain_ui_events(self) -> None:
        while True:
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                break

    def _on_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            should_close = messagebox.askyesno(
                "Exit",
                "Transcription is still running. Exit and cancel the task?",
            )
            if not should_close:
                return
            self.cancel_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_app() -> None:
    app = TranscriberApp()
    app.run()
