from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable

import yt_dlp
from yt_dlp.utils import DownloadError

from config import YOUTUBE_URL_PATTERNS
from transcription_service import TranscriptionCancelled, TranscriptionError

ProgressCallback = Callable[[str, float], None]


class _YoutubeDownloadCancelled(Exception):
    pass


def _report(
    callback: ProgressCallback | None,
    message: str,
    progress: float,
) -> None:
    if callback is None:
        return
    bounded = max(0.0, min(100.0, progress))
    callback(message, bounded)


def _check_cancel(cancel_event: Any | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _YoutubeDownloadCancelled("Pobieranie YouTube zostalo anulowane.")


def is_youtube_url(url: str) -> bool:
    candidate = url.strip()
    if not candidate:
        return False
    return any(
        re.search(pattern, candidate, flags=re.IGNORECASE)
        for pattern in YOUTUBE_URL_PATTERNS
    )


def fetch_video_info(url: str) -> dict[str, Any]:
    if not is_youtube_url(url):
        raise TranscriptionError("Nieprawidlowy URL YouTube.")

    _clients_to_try = [
        {"youtube": {"player_client": ["android"]}},
        {"youtube": {"player_client": ["web", "mweb"]}},
        None,  # default
    ]

    info = None
    for extractor_args in _clients_to_try:
        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }
        if extractor_args is not None:
            ydl_opts["extractor_args"] = extractor_args
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except Exception:
            continue

    if not isinstance(info, dict):
        raise TranscriptionError("Nie udalo sie pobrac metadanych YouTube.")

    if not isinstance(info, dict):
        raise TranscriptionError("Nie udalo sie odczytac informacji o wideo YouTube.")

    title = str(info.get("title") or "Unknown title")
    duration_raw = info.get("duration")
    try:
        duration_seconds = int(duration_raw) if duration_raw is not None else 0
    except (TypeError, ValueError):
        duration_seconds = 0

    return {
        "title": title,
        "duration_seconds": duration_seconds,
        "url": url,
    }


def download_audio(
    url: str,
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
) -> Path:
    if not is_youtube_url(url):
        raise TranscriptionError("Nieprawidlowy URL YouTube.")
    if shutil.which("ffmpeg") is None:
        raise TranscriptionError(
            "Nie znaleziono programu ffmpeg w PATH. Zainstaluj ffmpeg i uruchom ponownie."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    download_template = output_dir / "%(id)s.%(ext)s"
    last_downloaded_file: Path | None = None

    def _progress_hook(data: dict[str, Any]) -> None:
        nonlocal last_downloaded_file
        _check_cancel(cancel_event)
        status = data.get("status")
        if status == "downloading":
            total_bytes = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded_bytes = data.get("downloaded_bytes", 0)
            if total_bytes:
                percentage = float(downloaded_bytes) / float(total_bytes) * 100.0
            else:
                percentage = 0.0
            _report(progress_callback, "Pobieranie audio z YouTube...", percentage)
        elif status == "finished":
            filename = data.get("filename")
            if filename:
                last_downloaded_file = Path(filename)
            _report(
                progress_callback,
                "Pobieranie zakonczone. Konwersja audio...",
                95.0,
            )

    _postprocessors = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }
    ]

    # Each attempt uses a different player-client + format combo to work
    # around YouTube DRM on certain innertube clients (tv/TVHTML5).
    _download_strategies: list[dict[str, Any]] = [
        # 1) Android client — most reliable, no DRM for audio
        {
            "format": "bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
        # 2) Android with explicit format 18 (mp4 360p with audio)
        {
            "format": "18/bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
        # 3) Web + mweb clients
        {
            "format": "bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["web", "mweb"]}},
        },
        # 4) Default clients, standard format
        {
            "format": "bestaudio/best",
        },
        # 5) Last resort: any format, android
        {
            "format": "worstaudio/worst/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
    ]

    info = None
    prepared_path = None
    last_error = None

    for attempt_idx, strategy in enumerate(_download_strategies, start=1):
        _check_cancel(cancel_event)
        _report(
            progress_callback,
            f"Proba pobierania ({attempt_idx}/{len(_download_strategies)})...",
            2.0,
        )

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "outtmpl": str(download_template),
            "restrictfilenames": True,
            "prefer_ffmpeg": True,
            "progress_hooks": [_progress_hook],
            "postprocessors": _postprocessors,
            "postprocessor_args": ["-ar", "16000", "-ac", "1"],
            "format": strategy["format"],
        }
        if "extractor_args" in strategy:
            ydl_opts["extractor_args"] = strategy["extractor_args"]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared_path = Path(ydl.prepare_filename(info))
            last_error = None
            break
        except _YoutubeDownloadCancelled as exc:
            raise TranscriptionCancelled("Transkrypcja zostala anulowana.") from exc
        except DownloadError as exc:
            if "Pobieranie YouTube zostalo anulowane." in str(exc):
                raise TranscriptionCancelled("Transkrypcja zostala anulowana.") from exc
            last_error = exc
            error_msg = str(exc).lower()
            retryable = (
                "drm" in error_msg
                or "unavailable" in error_msg
                or "not available" in error_msg
                or "no video formats" in error_msg
                or "requested format" in error_msg
                or "configuration error" in error_msg
                or "no longer supported" in error_msg
                or "only images" in error_msg
                or "403" in error_msg
            )
            if retryable:
                _report(
                    progress_callback,
                    f"Strategia {attempt_idx} nieudana, kolejna proba...",
                    5.0,
                )
                continue
            raise TranscriptionError(f"Nie udalo sie pobrac audio z YouTube: {exc}") from exc
        except Exception as exc:
            raise TranscriptionError(f"Blad podczas pobierania audio z YouTube: {exc}") from exc

    if last_error is not None:
        raise TranscriptionError(
            f"Nie udalo sie pobrac audio z YouTube — wszystkie strategie zawiodly "
            f"(wideo moze byc chronione DRM): {last_error}"
        ) from last_error

    _check_cancel(cancel_event)
    _report(progress_callback, "Finalizacja pobranego audio...", 100.0)

    candidate_paths: list[Path] = []
    if prepared_path is not None:
        candidate_paths.append(prepared_path.with_suffix(".wav"))
    if last_downloaded_file is not None:
        candidate_paths.append(last_downloaded_file)
        candidate_paths.append(last_downloaded_file.with_suffix(".wav"))

    if isinstance(info, dict):
        video_id = info.get("id")
        if video_id:
            candidate_paths.extend(sorted(output_dir.glob(f"*_{video_id}.wav")))

    existing_candidates = [path for path in candidate_paths if path.exists() and path.is_file()]
    if existing_candidates:
        return existing_candidates[0].resolve()

    latest_wav = sorted(output_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if latest_wav:
        return latest_wav[0].resolve()

    raise TranscriptionError("Pobrano material, ale nie znaleziono pliku audio do transkrypcji.")
