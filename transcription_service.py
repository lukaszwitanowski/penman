from __future__ import annotations

import gc
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
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
from exporters import export_json, export_md, export_srt, export_txt, export_vtt

ProgressCallback = Callable[[str, float], None]


class TranscriptionError(Exception):
    pass


class TranscriptionCancelled(Exception):
    pass


_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE_KEY: tuple[str, str] | None = None
_MODEL_CACHE_INSTANCE: Any | None = None

ADAPTIVE_MIN_SEGMENT_SECONDS = 1
ADAPTIVE_MAX_SEGMENT_SECONDS = 600
ADAPTIVE_SKIP_SEGMENT_SECONDS = 15 * 60
ADAPTIVE_MEDIUM_AUDIO_SECONDS = 60 * 60
ADAPTIVE_LONG_AUDIO_SECONDS = 2 * 60 * 60


@dataclass(frozen=True)
class _SegmentationPlan:
    should_segment: bool
    effective_segment_seconds: int
    reason: str


def _release_compute_memory() -> None:
    gc.collect()
    try:
        import torch
    except Exception:
        return

    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    try:
        torch_mps = getattr(torch, "mps", None)
        if torch_mps is not None and hasattr(torch_mps, "empty_cache"):
            torch_mps.empty_cache()
    except Exception:
        pass


def _get_or_load_model(
    model_name: str,
    compute_device: str,
    reuse_model: bool = True,
) -> tuple[Any, bool]:
    import whisper

    global _MODEL_CACHE_KEY, _MODEL_CACHE_INSTANCE
    cache_key = (model_name, compute_device)

    with _MODEL_CACHE_LOCK:
        if (
            reuse_model
            and _MODEL_CACHE_INSTANCE is not None
            and _MODEL_CACHE_KEY == cache_key
        ):
            return _MODEL_CACHE_INSTANCE, True

        if reuse_model and _MODEL_CACHE_INSTANCE is not None:
            _MODEL_CACHE_INSTANCE = None
            _MODEL_CACHE_KEY = None
            _release_compute_memory()

        model = whisper.load_model(model_name, device=compute_device)
        if reuse_model:
            _MODEL_CACHE_INSTANCE = model
            _MODEL_CACHE_KEY = cache_key
        return model, False


def clear_model_cache() -> None:
    global _MODEL_CACHE_KEY, _MODEL_CACHE_INSTANCE

    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE_INSTANCE = None
        _MODEL_CACHE_KEY = None

    _release_compute_memory()


def _report(callback: ProgressCallback | None, message: str, progress: float) -> None:
    if callback is not None:
        bounded = max(0.0, min(100.0, progress))
        callback(message, bounded)


def _check_cancel(cancel_event: Any | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TranscriptionCancelled("Transcription was cancelled.")


def _resolve_compute_device(requested_device: str) -> tuple[str, bool]:
    normalized = requested_device.strip().lower()
    if normalized not in {"auto", "cpu", "gpu"}:
        raise TranscriptionError(
            f"Unsupported compute device: {requested_device}. Supported: auto, cpu, gpu."
        )

    if normalized == "cpu":
        return "cpu", False

    try:
        import torch
    except Exception as exc:
        if normalized == "auto":
            return "cpu", False
        raise TranscriptionError(
            "GPU was selected, but PyTorch is unavailable or misconfigured."
        ) from exc

    cuda_available = torch.cuda.is_available()
    mps_backend = getattr(torch.backends, "mps", None)
    mps_available = bool(mps_backend is not None and mps_backend.is_available())

    if normalized == "gpu":
        if cuda_available:
            return "cuda", True
        if mps_available:
            return "mps", False
        raise TranscriptionError("GPU was selected, but CUDA/MPS is not available.")

    if cuda_available:
        return "cuda", True
    if mps_available:
        return "mps", False
    return "cpu", False


def _validate_and_detect_input_format(input_file: Path, selected_format: str) -> str:
    if not input_file.exists() or not input_file.is_file():
        raise TranscriptionError(f"Input file was not found: {input_file}")

    extension = input_file.suffix.lower().lstrip(".")
    if not extension:
        raise TranscriptionError("Input file has no extension.")

    if extension not in INPUT_FORMATS:
        supported = ", ".join(f for f in INPUT_FORMATS if f != DEFAULT_INPUT_FORMAT)
        raise TranscriptionError(
            f"Unsupported input format: .{extension}. Supported: {supported}"
        )

    normalized = selected_format.strip().lower()
    if normalized != DEFAULT_INPUT_FORMAT and normalized != extension:
        raise TranscriptionError(
            f"Selected input format '{normalized}' does not match file extension '.{extension}'."
        )

    return extension


def _clamp_segment_seconds(value: int) -> int:
    return max(ADAPTIVE_MIN_SEGMENT_SECONDS, min(ADAPTIVE_MAX_SEGMENT_SECONDS, value))


def _probe_media_duration_seconds(input_file: Path) -> float | None:
    try:
        import ffmpeg
    except Exception:
        return None

    try:
        probe_data = ffmpeg.probe(str(input_file))
    except Exception:
        return None

    format_info = probe_data.get("format", {})
    duration_raw = format_info.get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return duration


def _build_segmentation_plan(
    source_duration_seconds: float | None,
    requested_segment_seconds: int,
    compute_device: str,
) -> _SegmentationPlan:
    requested = _clamp_segment_seconds(requested_segment_seconds)

    if source_duration_seconds is None:
        return _SegmentationPlan(
            should_segment=True,
            effective_segment_seconds=requested,
            reason="duration_unknown",
        )

    if source_duration_seconds <= ADAPTIVE_SKIP_SEGMENT_SECONDS:
        return _SegmentationPlan(
            should_segment=False,
            effective_segment_seconds=requested,
            reason="short_input_skip_segmentation",
        )

    effective = requested
    if compute_device == "cpu":
        if source_duration_seconds >= ADAPTIVE_LONG_AUDIO_SECONDS:
            effective = min(requested, 90)
        elif source_duration_seconds >= ADAPTIVE_MEDIUM_AUDIO_SECONDS:
            effective = min(requested, 120)
    else:
        if source_duration_seconds >= ADAPTIVE_LONG_AUDIO_SECONDS:
            effective = max(requested, 240)
        elif source_duration_seconds >= ADAPTIVE_MEDIUM_AUDIO_SECONDS:
            effective = max(requested, 180)

    effective = _clamp_segment_seconds(effective)
    if effective != requested:
        return _SegmentationPlan(
            should_segment=True,
            effective_segment_seconds=effective,
            reason="adaptive_segment_length_adjusted",
        )
    return _SegmentationPlan(
        should_segment=True,
        effective_segment_seconds=effective,
        reason="requested_segment_length",
    )


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
        raise TranscriptionError(f"ffmpeg failed during segmentation. {details}") from exc

    _check_cancel(cancel_event)
    segment_paths = sorted(segment_dir.glob("segment_*.wav"))
    if not segment_paths:
        raise TranscriptionError("Failed to generate audio segments.")
    return segment_paths


def _transcribe_segments(
    segment_paths: list[Path],
    model: Any,
    language: str,
    use_fp16: bool,
    segment_offset_seconds: float = 0.0,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    _check_cancel(cancel_event)
    total_segments = len(segment_paths)
    full_text_parts: list[str] = []
    segment_items: list[dict[str, Any]] = []
    timeline_items: list[dict[str, Any]] = []

    for idx, segment_file in enumerate(segment_paths, start=1):
        _check_cancel(cancel_event)
        start_progress = 24 + ((idx - 1) / max(total_segments, 1)) * 66
        _report(
            progress_callback,
            f"Transcribing segment {idx}/{total_segments}: {segment_file.name}",
            start_progress,
        )

        args: dict[str, Any] = {"fp16": use_fp16}
        if language != "auto":
            args["language"] = language

        offset_seconds = max(0.0, float(segment_offset_seconds)) * (idx - 1)

        try:
            result = model.transcribe(str(segment_file), **args)
            text = result.get("text", "").strip()
            detected_language = result.get("language")
            raw_segments = result.get("segments")
            chunk_start_seconds: float | None = None
            chunk_end_seconds: float | None = None

            if isinstance(raw_segments, list):
                for raw_segment in raw_segments:
                    if not isinstance(raw_segment, dict):
                        continue
                    segment_text = str(raw_segment.get("text", "")).strip()
                    if not segment_text:
                        continue
                    try:
                        local_start = float(raw_segment.get("start", 0.0))
                    except (TypeError, ValueError):
                        local_start = 0.0
                    try:
                        local_end = float(raw_segment.get("end", local_start))
                    except (TypeError, ValueError):
                        local_end = local_start

                    global_start = max(0.0, offset_seconds + local_start)
                    global_end = max(global_start + 0.01, offset_seconds + local_end)
                    timeline_items.append(
                        {
                            "index": len(timeline_items) + 1,
                            "segment_index": idx,
                            "start_seconds": round(global_start, 3),
                            "end_seconds": round(global_end, 3),
                            "text": segment_text,
                        }
                    )
                    if chunk_start_seconds is None:
                        chunk_start_seconds = global_start
                    chunk_end_seconds = global_end

            if text and chunk_start_seconds is None:
                fallback_duration = max(1.0, min(8.0, len(text) / 12.0))
                chunk_start_seconds = offset_seconds
                chunk_end_seconds = offset_seconds + fallback_duration
                timeline_items.append(
                    {
                        "index": len(timeline_items) + 1,
                        "segment_index": idx,
                        "start_seconds": round(chunk_start_seconds, 3),
                        "end_seconds": round(chunk_end_seconds, 3),
                        "text": text,
                    }
                )
        except Exception as exc:
            text = ""
            detected_language = None
            chunk_start_seconds = None
            chunk_end_seconds = None
            segment_items.append(
                {
                    "index": idx,
                    "file_name": segment_file.name,
                    "text": text,
                    "error": str(exc),
                    "detected_language": detected_language,
                    "start_seconds": chunk_start_seconds,
                    "end_seconds": chunk_end_seconds,
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
                "start_seconds": (
                    round(chunk_start_seconds, 3)
                    if chunk_start_seconds is not None
                    else None
                ),
                "end_seconds": (
                    round(chunk_end_seconds, 3)
                    if chunk_end_seconds is not None
                    else None
                ),
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
        "timeline_segments": timeline_items,
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
    elif output_format == "srt":
        export_srt(payload, output_path)
    elif output_format == "vtt":
        export_vtt(payload, output_path)
    else:
        raise TranscriptionError(
            "Unsupported output format: "
            f"{output_format}. Supported: txt, json, md, srt, vtt."
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
    extra_metadata: dict[str, Any] | None = None,
    reuse_model: bool = True,
    stage_metrics: dict[str, float] | None = None,
    include_timestamps: bool = False,
) -> Path:
    metrics: dict[str, float] = {}
    started_total = time.perf_counter()

    def _record_metric(name: str, started_at: float) -> None:
        elapsed = max(0.0, time.perf_counter() - started_at)
        metrics[name] = round(elapsed, 4)

    source_file = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    normalized_output_format = output_format.strip().lower()

    temp_dir = destination / f"{DEFAULT_SEGMENT_DIR.name}_{uuid.uuid4().hex[:8]}"
    output_path: Path | None = None
    try:
        if shutil.which("ffmpeg") is None:
            raise TranscriptionError(
                "ffmpeg was not found in PATH. Install ffmpeg and retry."
            )

        started_stage = time.perf_counter()
        _report(progress_callback, "Validating settings...", 5)
        detected_input_format = _validate_and_detect_input_format(
            source_file, selected_input_format
        )
        resolved_device, use_fp16 = _resolve_compute_device(compute_device)
        _report(progress_callback, f"Compute device: {resolved_device}", 8)
        _check_cancel(cancel_event)
        _record_metric("validate_settings_seconds", started_stage)

        started_stage = time.perf_counter()
        source_duration_seconds = _probe_media_duration_seconds(source_file)
        segmentation_plan = _build_segmentation_plan(
            source_duration_seconds=source_duration_seconds,
            requested_segment_seconds=segment_time_sec,
            compute_device=resolved_device,
        )
        _record_metric("analyze_input_seconds", started_stage)

        if not segmentation_plan.should_segment:
            _report(
                progress_callback,
                "Adaptive segmentation: short input detected, skipping ffmpeg split.",
                10,
            )
            segment_paths = [source_file]
            metrics["segment_audio_seconds"] = 0.0
        else:
            if (
                segmentation_plan.effective_segment_seconds
                != _clamp_segment_seconds(segment_time_sec)
            ):
                _report(
                    progress_callback,
                    (
                        "Adaptive segmentation: using "
                        f"{segmentation_plan.effective_segment_seconds}s chunks "
                        f"(requested {segment_time_sec}s)."
                    ),
                    10,
                )
            else:
                _report(progress_callback, "Segmenting audio with ffmpeg...", 10)
            started_stage = time.perf_counter()
            segment_paths = _extract_audio_and_split(
                source_file,
                temp_dir,
                segment_time_sec=segmentation_plan.effective_segment_seconds,
                cancel_event=cancel_event,
            )
            _record_metric("segment_audio_seconds", started_stage)

        _check_cancel(cancel_event)
        started_stage = time.perf_counter()
        model, reused_model = _get_or_load_model(
            model_name=model_name,
            compute_device=resolved_device,
            reuse_model=reuse_model,
        )
        _record_metric("model_ready_seconds", started_stage)
        if reused_model:
            _report(
                progress_callback,
                f"Reusing Whisper model: {model_name} ({resolved_device})",
                20,
            )
        else:
            _report(
                progress_callback,
                f"Loading Whisper model: {model_name} ({resolved_device})",
                20,
            )

        started_stage = time.perf_counter()
        transcribed = _transcribe_segments(
            segment_paths=segment_paths,
            model=model,
            language=language,
            use_fp16=use_fp16,
            segment_offset_seconds=(
                0.0
                if not segmentation_plan.should_segment
                else float(segmentation_plan.effective_segment_seconds)
            ),
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        _record_metric("transcribe_segments_seconds", started_stage)

        metadata = {
            "source_file": str(source_file),
            "input_format": detected_input_format,
            "language": language,
            "model_name": model_name,
            "model_reused": reused_model,
            "include_timestamps": bool(include_timestamps),
            "source_duration_seconds": (
                int(round(source_duration_seconds))
                if source_duration_seconds is not None
                else None
            ),
            "segment_time_requested_sec": int(segment_time_sec),
            "segment_time_effective_sec": (
                None
                if not segmentation_plan.should_segment
                else segmentation_plan.effective_segment_seconds
            ),
            "segmentation_skipped": not segmentation_plan.should_segment,
            "segmentation_reason": segmentation_plan.reason,
            "compute_device_requested": compute_device,
            "compute_device_used": resolved_device,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "segments_count": len(transcribed["segments"]),
            "detected_languages": transcribed["detected_languages"],
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        payload = {
            "metadata": metadata,
            "segments": transcribed["segments"],
            "timeline_segments": transcribed.get("timeline_segments", []),
            "full_text": transcribed["full_text"],
        }

        _check_cancel(cancel_event)
        _report(progress_callback, "Saving output file...", 95)
        started_stage = time.perf_counter()
        output_path = _save_output(
            payload=payload,
            output_dir=destination,
            output_format=normalized_output_format,
            source_file=source_file,
        )
        _record_metric("export_output_seconds", started_stage)
        _report(progress_callback, "Completed.", 100)
        return output_path
    finally:
        metrics["total_pipeline_seconds"] = round(
            max(0.0, time.perf_counter() - started_total),
            4,
        )
        if stage_metrics is not None:
            stage_metrics.clear()
            stage_metrics.update(metrics)

        if not keep_segments and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
