from __future__ import annotations


def infer_stage_label(message: str) -> str:
    lower = message.strip().lower()
    if "download" in lower or "youtube" in lower:
        return "Download"
    if "transcrib" in lower or "whisper" in lower:
        return "Transcribe"
    if "segment" in lower or "ffmpeg" in lower:
        return "Preprocess"
    if "saving output" in lower or "completed" in lower:
        return "Export"
    return "Run"


def estimate_eta_seconds(elapsed_seconds: float, progress_percent: float) -> float | None:
    bounded_progress = max(0.0, min(100.0, progress_percent))
    if bounded_progress <= 0:
        return None
    return (elapsed_seconds / bounded_progress) * (100.0 - bounded_progress)


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    bounded = max(0, int(round(seconds)))
    hours, remainder = divmod(bounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
