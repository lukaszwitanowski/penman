from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from config import (
    DEFAULT_INPUT_FORMAT,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_SEGMENT_DIR,
    DEFAULT_SEGMENT_SECONDS,
    INPUT_FORMATS,
)
from exporters import export_json, export_md, export_txt

ProgressCallback = Callable[[str, float], None]


class TranscriptionError(Exception):
    pass


class TranscriptionCancelled(Exception):
    pass


def _report(callback: ProgressCallback | None, message: str, progress: float) -> None:
    if callback is not None:
        bounded = max(0.0, min(100.0, progress))
        callback(message, bounded)


def _check_cancel(cancel_event: Any | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TranscriptionCancelled("Transkrypcja zostala anulowana.")


def _resolve_compute_device(requested_device: str) -> tuple[str, bool]:
    normalized = requested_device.strip().lower()
    if normalized not in {"auto", "cpu", "gpu"}:
        raise TranscriptionError(
            f"Nieobslugiwane urzadzenie: {requested_device}. Obslugiwane: auto, cpu, gpu"
        )

    if normalized == "cpu":
        return "cpu", False

    try:
        import torch
    except Exception as exc:
        if normalized == "auto":
            return "cpu", False
        raise TranscriptionError(
            "Wybrano GPU, ale PyTorch nie jest dostepny lub nie dziala poprawnie."
        ) from exc

    cuda_available = torch.cuda.is_available()
    mps_backend = getattr(torch.backends, "mps", None)
    mps_available = bool(mps_backend is not None and mps_backend.is_available())

    if normalized == "gpu":
        if cuda_available:
            return "cuda", True
        if mps_available:
            return "mps", False
        raise TranscriptionError("Wybrano GPU, ale CUDA/MPS nie jest dostepne.")

    if cuda_available:
        return "cuda", True
    if mps_available:
        return "mps", False
    return "cpu", False


def _validate_and_detect_input_format(input_file: Path, selected_format: str) -> str:
    if not input_file.exists() or not input_file.is_file():
        raise TranscriptionError(f"Nie znaleziono pliku wejsciowego: {input_file}")

    extension = input_file.suffix.lower().lstrip(".")
    if not extension:
        raise TranscriptionError("Plik wejsciowy nie ma rozszerzenia.")

    if extension not in INPUT_FORMATS:
        supported = ", ".join(f for f in INPUT_FORMATS if f != DEFAULT_INPUT_FORMAT)
        raise TranscriptionError(
            f"Nieobslugiwany format wejsciowy: .{extension}. Obslugiwane: {supported}"
        )

    normalized = selected_format.strip().lower()
    if normalized != DEFAULT_INPUT_FORMAT and normalized != extension:
        raise TranscriptionError(
            f"Wybrany format wejsciowy '{normalized}' nie pasuje do pliku '.{extension}'."
        )

    return extension


def _extract_audio_and_split(
    input_file: Path,
    segment_dir: Path,
    segment_time_sec: int,
    cancel_event: Any | None = None,
) -> list[Path]:
    import ffmpeg

    _check_cancel(cancel_event)
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_pattern = str(segment_dir / "segment_%03d.wav")

    try:
        (
            ffmpeg.input(str(input_file))
            .output(
                segment_pattern,
                vn=None,
                acodec="pcm_s16le",
                ar="16000",
                ac=1,
                f="segment",
                segment_time=segment_time_sec,
                reset_timestamps=1,
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        details = ""
        if exc.stderr:
            details = exc.stderr.decode(errors="ignore").strip()
        raise TranscriptionError(f"Blad ffmpeg podczas segmentacji. {details}") from exc

    _check_cancel(cancel_event)
    segment_paths = sorted(segment_dir.glob("segment_*.wav"))
    if not segment_paths:
        raise TranscriptionError("Nie udalo sie wygenerowac segmentow audio.")
    return segment_paths


def _transcribe_segments(
    segment_paths: list[Path],
    model_name: str,
    language: str,
    compute_device: str,
    use_fp16: bool,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    import whisper

    _check_cancel(cancel_event)
    _report(
        progress_callback,
        f"Ladowanie modelu Whisper: {model_name} ({compute_device})",
        20,
    )

    model = whisper.load_model(model_name, device=compute_device)
    total_segments = len(segment_paths)
    full_text_parts: list[str] = []
    segment_items: list[dict[str, Any]] = []

    for idx, segment_file in enumerate(segment_paths, start=1):
        _check_cancel(cancel_event)
        start_progress = 20 + ((idx - 1) / max(total_segments, 1)) * 70
        _report(
            progress_callback,
            f"Transkrypcja segmentu {idx}/{total_segments}: {segment_file.name}",
            start_progress,
        )

        args: dict[str, Any] = {"fp16": use_fp16}
        if language != "auto":
            args["language"] = language

        try:
            result = model.transcribe(str(segment_file), **args)
            text = result.get("text", "").strip()
            detected_language = result.get("language")
        except Exception as exc:
            text = ""
            detected_language = None
            segment_items.append(
                {
                    "index": idx,
                    "file_name": segment_file.name,
                    "text": text,
                    "error": str(exc),
                    "detected_language": detected_language,
                }
            )
            full_text_parts.append(text)
            continue

        segment_items.append(
            {
                "index": idx,
                "file_name": segment_file.name,
                "text": text,
                "error": None,
                "detected_language": detected_language,
            }
        )
        full_text_parts.append(text)

    _check_cancel(cancel_event)
    full_text = "\n".join(full_text_parts).strip()
    detected_languages = sorted(
        {
            item["detected_language"]
            for item in segment_items
            if item.get("detected_language")
        }
    )

    return {
        "segments": segment_items,
        "full_text": full_text,
        "detected_languages": detected_languages,
    }


def _save_output(
    payload: dict[str, Any],
    output_dir: Path,
    output_format: str,
    source_file: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{source_file.stem}_transcript_{timestamp}"
    output_path = output_dir / f"{base_name}.{output_format}"

    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter:02d}.{output_format}"
        counter += 1

    if output_format == "txt":
        export_txt(payload, output_path)
    elif output_format == "json":
        export_json(payload, output_path)
    elif output_format == "md":
        export_md(payload, output_path)
    else:
        raise TranscriptionError(
            f"Nieobslugiwany format zapisu: {output_format}. Obslugiwane: txt, json, md"
        )

    return output_path


def run_transcription(
    input_path: str | Path,
    selected_input_format: str = DEFAULT_INPUT_FORMAT,
    output_dir: str | Path = ".",
    language: str = "auto",
    compute_device: str = "auto",
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    model_name: str = DEFAULT_MODEL,
    segment_time_sec: int = DEFAULT_SEGMENT_SECONDS,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
    keep_segments: bool = False,
) -> Path:
    if shutil.which("ffmpeg") is None:
        raise TranscriptionError(
            "Nie znaleziono programu ffmpeg w PATH. Zainstaluj ffmpeg i uruchom ponownie."
        )

    source_file = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    normalized_output_format = output_format.strip().lower()

    _report(progress_callback, "Walidacja ustawien...", 5)
    detected_input_format = _validate_and_detect_input_format(
        source_file, selected_input_format
    )
    resolved_device, use_fp16 = _resolve_compute_device(compute_device)
    _report(progress_callback, f"Urzadzenie obliczeniowe: {resolved_device}", 8)
    _check_cancel(cancel_event)

    temp_dir = destination / f"{DEFAULT_SEGMENT_DIR.name}_{uuid.uuid4().hex[:8]}"
    try:
        _report(progress_callback, "Segmentacja audio przez ffmpeg...", 10)
        segment_paths = _extract_audio_and_split(
            source_file,
            temp_dir,
            segment_time_sec=segment_time_sec,
            cancel_event=cancel_event,
        )

        transcribed = _transcribe_segments(
            segment_paths=segment_paths,
            model_name=model_name,
            language=language,
            compute_device=resolved_device,
            use_fp16=use_fp16,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        payload = {
            "metadata": {
                "source_file": str(source_file),
                "input_format": detected_input_format,
                "language": language,
                "model_name": model_name,
                "compute_device_requested": compute_device,
                "compute_device_used": resolved_device,
                "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "segments_count": len(transcribed["segments"]),
                "detected_languages": transcribed["detected_languages"],
            },
            "segments": transcribed["segments"],
            "full_text": transcribed["full_text"],
        }

        _check_cancel(cancel_event)
        _report(progress_callback, "Zapisywanie pliku wynikowego...", 95)
        output_path = _save_output(
            payload=payload,
            output_dir=destination,
            output_format=normalized_output_format,
            source_file=source_file,
        )
        _report(progress_callback, "Zakonczono.", 100)
        return output_path
    finally:
        if not keep_segments and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
