from __future__ import annotations

import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yt_dlp
from yt_dlp.utils import DownloadError

from config import YOUTUBE_INFO_CACHE_TTL_SECONDS, YOUTUBE_URL_PATTERNS
from transcription_service import TranscriptionCancelled, TranscriptionError

ProgressCallback = Callable[[str, float], None]
CANCEL_MESSAGE = "YouTube download was cancelled."
TRANSCRIPTION_CANCELLED_MESSAGE = "Transcription was cancelled."

MAX_DOWNLOAD_RETRIES_PER_STRATEGY = 2
MAX_METADATA_RETRIES_PER_CLIENT = 1
BACKOFF_BASE_SECONDS = 1.2
BACKOFF_MAX_SECONDS = 8.0

_METADATA_CACHE_LOCK = threading.Lock()
_METADATA_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_METADATA_CACHE_TTL_SECONDS = max(0, int(YOUTUBE_INFO_CACHE_TTL_SECONDS))


@dataclass(frozen=True)
class _ErrorClassification:
    category: str
    summary: str
    hint: str
    retry_same_strategy: bool
    try_next_strategy: bool


@dataclass(frozen=True)
class _FailureContext:
    operation: str
    strategy_label: str
    classification: _ErrorClassification
    raw_error: str


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
        raise _YoutubeDownloadCancelled(CANCEL_MESSAGE)


def _sleep_with_cancel(seconds: float, cancel_event: Any | None) -> None:
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while True:
        _check_cancel(cancel_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def _retry_delay_seconds(retry_index: int) -> float:
    return min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2**retry_index))


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(token in haystack for token in needles)


def _normalize_cache_key(url: str) -> str:
    return url.strip()


def _purge_expired_metadata_cache(now_monotonic: float | None = None) -> None:
    if _METADATA_CACHE_TTL_SECONDS <= 0:
        _METADATA_CACHE.clear()
        return

    now_value = time.monotonic() if now_monotonic is None else now_monotonic
    expired_keys = [
        key
        for key, (cached_at, _) in _METADATA_CACHE.items()
        if (now_value - cached_at) > _METADATA_CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        _METADATA_CACHE.pop(key, None)


def get_cached_video_info(url: str) -> dict[str, Any] | None:
    cache_key = _normalize_cache_key(url)
    if not cache_key:
        return None

    with _METADATA_CACHE_LOCK:
        _purge_expired_metadata_cache()
        cached_entry = _METADATA_CACHE.get(cache_key)
        if cached_entry is None:
            return None
        return dict(cached_entry[1])


def clear_video_info_cache() -> None:
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE.clear()


def _set_cached_video_info(url: str, info: dict[str, Any]) -> None:
    cache_key = _normalize_cache_key(url)
    if not cache_key:
        return
    if _METADATA_CACHE_TTL_SECONDS <= 0:
        return

    with _METADATA_CACHE_LOCK:
        _purge_expired_metadata_cache()
        _METADATA_CACHE[cache_key] = (time.monotonic(), dict(info))


def _classify_error(error_text: str) -> _ErrorClassification:
    lower = (error_text or "").lower()

    if _contains_any(
        lower,
        (
            "ffmpeg",
            "ffprobe",
            "postprocessing",
            "please install or provide the path",
            "unable to obtain file audio codec",
        ),
    ):
        return _ErrorClassification(
            category="configuration",
            summary="Local yt-dlp/ffmpeg setup is not ready.",
            hint="Verify ffmpeg/ffprobe in PATH and update yt-dlp.",
            retry_same_strategy=False,
            try_next_strategy=False,
        )

    if _contains_any(
        lower,
        (
            "sign in to confirm your age",
            "log in to confirm your age",
            "login required",
            "age-restricted",
            "age restricted",
            "members-only",
            "members only",
            "this video may be inappropriate",
        ),
    ):
        return _ErrorClassification(
            category="auth_or_age_restriction",
            summary="YouTube requires login or age verification.",
            hint="Use a public video or configure yt-dlp cookies.",
            retry_same_strategy=False,
            try_next_strategy=False,
        )

    if _contains_any(
        lower,
        (
            "not available in your country",
            "not available in your region",
            "geo-restricted",
            "geo restricted",
            "blocked in your country",
        ),
    ):
        return _ErrorClassification(
            category="geo_restricted",
            summary="Video is blocked in this region.",
            hint="Use a video available in your region.",
            retry_same_strategy=False,
            try_next_strategy=False,
        )

    if _contains_any(
        lower,
        (
            "private video",
            "this video is private",
            "video unavailable",
            "this video is unavailable",
            "has been removed",
            "video is no longer available",
            "copyright",
            "terminated",
        ),
    ):
        return _ErrorClassification(
            category="video_unavailable",
            summary="Video is unavailable, private, or removed.",
            hint="Verify the URL is public and playable in browser.",
            retry_same_strategy=False,
            try_next_strategy=False,
        )

    if _contains_any(
        lower,
        (
            "http error 429",
            "too many requests",
            "rate limit",
            "temporarily blocked",
            "quota exceeded",
        ),
    ):
        return _ErrorClassification(
            category="transient_rate_limit",
            summary="YouTube rate-limited this request.",
            hint="Retrying with backoff may succeed.",
            retry_same_strategy=True,
            try_next_strategy=True,
        )

    if _contains_any(
        lower,
        (
            "timed out",
            "timeout",
            "network is unreachable",
            "temporary failure in name resolution",
            "name or service not known",
            "connection reset",
            "connection aborted",
            "connection refused",
            "remote end closed connection",
            "http error 408",
            "proxy error",
        ),
    ):
        return _ErrorClassification(
            category="transient_network",
            summary="Temporary network/connectivity issue.",
            hint="Retrying with backoff may recover.",
            retry_same_strategy=True,
            try_next_strategy=True,
        )

    if _contains_any(
        lower,
        (
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
            "internal server error",
            "bad gateway",
            "service unavailable",
        ),
    ):
        return _ErrorClassification(
            category="transient_server",
            summary="Temporary YouTube/server-side problem.",
            hint="Retrying with backoff may recover.",
            retry_same_strategy=True,
            try_next_strategy=True,
        )

    if _contains_any(
        lower,
        (
            "drm",
            "requested format is not available",
            "requested format not available",
            "no video formats",
            "no formats found",
            "only images are available",
            "no longer supported",
            "configuration error",
            "nsig extraction failed",
            "signature extraction failed",
        ),
    ):
        return _ErrorClassification(
            category="strategy_or_format",
            summary="Current format/client strategy is incompatible.",
            hint="Trying a different strategy may work.",
            retry_same_strategy=False,
            try_next_strategy=True,
        )

    if "http error 403" in lower or "forbidden" in lower:
        return _ErrorClassification(
            category="access_denied",
            summary="Access denied for current strategy.",
            hint="A different strategy may work; otherwise verify video access.",
            retry_same_strategy=False,
            try_next_strategy=True,
        )

    return _ErrorClassification(
        category="unknown",
        summary="Unclassified yt-dlp error.",
        hint="Will try next strategy when available.",
        retry_same_strategy=False,
        try_next_strategy=True,
    )


def _format_terminal_error(
    operation: str,
    strategy_label: str,
    classification: _ErrorClassification,
    raw_error: str,
) -> str:
    return (
        f"Failed to {operation}. Category: {classification.category}. "
        f"{classification.summary} Strategy: {strategy_label}. "
        f"Hint: {classification.hint} "
        f"Details: {raw_error}"
    )


def _format_exhausted_error(last_failure: _FailureContext) -> str:
    return (
        f"Failed to {last_failure.operation} after all retry strategies. "
        f"Last category: {last_failure.classification.category}. "
        f"{last_failure.classification.summary} "
        f"Last strategy: {last_failure.strategy_label}. "
        f"Hint: {last_failure.classification.hint} "
        f"Details: {last_failure.raw_error}"
    )


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
        raise TranscriptionError("Invalid YouTube URL.")
    cache_key = _normalize_cache_key(url)
    cached_info = get_cached_video_info(cache_key)
    if cached_info is not None:
        return cached_info

    client_strategies: list[tuple[str, dict[str, Any] | None]] = [
        ("android client", {"youtube": {"player_client": ["android"]}}),
        ("web/mweb client", {"youtube": {"player_client": ["web", "mweb"]}}),
        ("default client", None),
    ]

    info: dict[str, Any] | None = None
    last_failure: _FailureContext | None = None

    for client_label, extractor_args in client_strategies:
        for retry_idx in range(MAX_METADATA_RETRIES_PER_CLIENT + 1):
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
                    extracted = ydl.extract_info(url, download=False)
                if isinstance(extracted, dict):
                    info = extracted
                    break

                classification = _classify_error("empty metadata response")
                last_failure = _FailureContext(
                    operation="fetch YouTube metadata",
                    strategy_label=client_label,
                    classification=classification,
                    raw_error="Empty metadata response.",
                )
                break
            except DownloadError as exc:
                classification = _classify_error(str(exc))
                last_failure = _FailureContext(
                    operation="fetch YouTube metadata",
                    strategy_label=client_label,
                    classification=classification,
                    raw_error=str(exc),
                )

                if (
                    classification.retry_same_strategy
                    and retry_idx < MAX_METADATA_RETRIES_PER_CLIENT
                ):
                    time.sleep(_retry_delay_seconds(retry_idx))
                    continue

                if classification.try_next_strategy:
                    break

                raise TranscriptionError(
                    _format_terminal_error(
                        "fetch YouTube metadata",
                        client_label,
                        classification,
                        str(exc),
                    )
                ) from exc
            except Exception as exc:
                classification = _classify_error(str(exc))
                last_failure = _FailureContext(
                    operation="fetch YouTube metadata",
                    strategy_label=client_label,
                    classification=classification,
                    raw_error=str(exc),
                )

                if (
                    classification.retry_same_strategy
                    and retry_idx < MAX_METADATA_RETRIES_PER_CLIENT
                ):
                    time.sleep(_retry_delay_seconds(retry_idx))
                    continue

                if classification.try_next_strategy:
                    break

                raise TranscriptionError(
                    _format_terminal_error(
                        "fetch YouTube metadata",
                        client_label,
                        classification,
                        str(exc),
                    )
                ) from exc

        if isinstance(info, dict):
            break

    if not isinstance(info, dict):
        if last_failure is not None:
            raise TranscriptionError(_format_exhausted_error(last_failure))
        raise TranscriptionError("Failed to fetch YouTube metadata.")

    title = str(info.get("title") or "Unknown title")
    duration_raw = info.get("duration")
    try:
        duration_seconds = int(duration_raw) if duration_raw is not None else 0
    except (TypeError, ValueError):
        duration_seconds = 0

    result = {
        "title": title,
        "duration_seconds": duration_seconds,
        "url": url,
    }
    _set_cached_video_info(cache_key, result)
    return dict(result)


def download_audio(
    url: str,
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Any | None = None,
) -> Path:
    if not is_youtube_url(url):
        raise TranscriptionError("Invalid YouTube URL.")
    if shutil.which("ffmpeg") is None:
        raise TranscriptionError(
            "ffmpeg was not found in PATH. Install ffmpeg and retry."
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
            _report(progress_callback, "Downloading audio from YouTube...", percentage)
        elif status == "finished":
            filename = data.get("filename")
            if filename:
                last_downloaded_file = Path(filename)
            _report(
                progress_callback,
                "Download finished. Converting audio...",
                95.0,
            )

    postprocessors = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }
    ]

    download_strategies: list[dict[str, Any]] = [
        {
            "label": "android / bestaudio",
            "format": "bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
        {
            "label": "android / format18 fallback",
            "format": "18/bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
        {
            "label": "web+mweb / bestaudio",
            "format": "bestaudio/best",
            "extractor_args": {"youtube": {"player_client": ["web", "mweb"]}},
        },
        {
            "label": "default / bestaudio",
            "format": "bestaudio/best",
        },
        {
            "label": "android / relaxed format",
            "format": "worstaudio/worst/best",
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        },
    ]

    info: dict[str, Any] | None = None
    prepared_path: Path | None = None
    last_failure: _FailureContext | None = None
    total_strategies = len(download_strategies)
    success = False

    for strategy_idx, strategy in enumerate(download_strategies, start=1):
        strategy_label = str(strategy["label"])
        for retry_idx in range(MAX_DOWNLOAD_RETRIES_PER_STRATEGY + 1):
            _check_cancel(cancel_event)
            _report(
                progress_callback,
                (
                    f"Download attempt {strategy_idx}/{total_strategies} "
                    f"({strategy_label}, try {retry_idx + 1})..."
                ),
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
                "postprocessors": postprocessors,
                "postprocessor_args": ["-ar", "16000", "-ac", "1"],
                "format": strategy["format"],
            }
            if "extractor_args" in strategy:
                ydl_opts["extractor_args"] = strategy["extractor_args"]

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    extracted = ydl.extract_info(url, download=True)
                    prepared_path = Path(ydl.prepare_filename(extracted))
                if isinstance(extracted, dict):
                    info = extracted
                success = True
                break
            except _YoutubeDownloadCancelled as exc:
                raise TranscriptionCancelled(TRANSCRIPTION_CANCELLED_MESSAGE) from exc
            except DownloadError as exc:
                if CANCEL_MESSAGE in str(exc):
                    raise TranscriptionCancelled(TRANSCRIPTION_CANCELLED_MESSAGE) from exc

                classification = _classify_error(str(exc))
                last_failure = _FailureContext(
                    operation="download audio from YouTube",
                    strategy_label=strategy_label,
                    classification=classification,
                    raw_error=str(exc),
                )

                if (
                    classification.retry_same_strategy
                    and retry_idx < MAX_DOWNLOAD_RETRIES_PER_STRATEGY
                ):
                    wait_seconds = _retry_delay_seconds(retry_idx)
                    _report(
                        progress_callback,
                        (
                            f"{classification.summary} "
                            f"Retrying in {wait_seconds:.1f}s..."
                        ),
                        5.0,
                    )
                    try:
                        _sleep_with_cancel(wait_seconds, cancel_event)
                    except _YoutubeDownloadCancelled as cancel_exc:
                        raise TranscriptionCancelled(
                            TRANSCRIPTION_CANCELLED_MESSAGE
                        ) from cancel_exc
                    continue

                if classification.try_next_strategy:
                    if strategy_idx < total_strategies:
                        _report(
                            progress_callback,
                            f"{classification.summary} Trying next strategy...",
                            5.0,
                        )
                    break

                raise TranscriptionError(
                    _format_terminal_error(
                        "download audio from YouTube",
                        strategy_label,
                        classification,
                        str(exc),
                    )
                ) from exc
            except Exception as exc:
                classification = _classify_error(str(exc))
                last_failure = _FailureContext(
                    operation="download audio from YouTube",
                    strategy_label=strategy_label,
                    classification=classification,
                    raw_error=str(exc),
                )

                if (
                    classification.retry_same_strategy
                    and retry_idx < MAX_DOWNLOAD_RETRIES_PER_STRATEGY
                ):
                    wait_seconds = _retry_delay_seconds(retry_idx)
                    _report(
                        progress_callback,
                        (
                            f"{classification.summary} "
                            f"Retrying in {wait_seconds:.1f}s..."
                        ),
                        5.0,
                    )
                    try:
                        _sleep_with_cancel(wait_seconds, cancel_event)
                    except _YoutubeDownloadCancelled as cancel_exc:
                        raise TranscriptionCancelled(
                            TRANSCRIPTION_CANCELLED_MESSAGE
                        ) from cancel_exc
                    continue

                if classification.try_next_strategy:
                    if strategy_idx < total_strategies:
                        _report(
                            progress_callback,
                            f"{classification.summary} Trying next strategy...",
                            5.0,
                        )
                    break

                raise TranscriptionError(
                    _format_terminal_error(
                        "download audio from YouTube",
                        strategy_label,
                        classification,
                        str(exc),
                    )
                ) from exc

        if success:
            break

    if not success:
        if last_failure is not None:
            raise TranscriptionError(_format_exhausted_error(last_failure))
        raise TranscriptionError("Failed to download audio from YouTube.")

    _check_cancel(cancel_event)
    _report(progress_callback, "Finalizing downloaded audio...", 100.0)

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

    existing_candidates = [
        path for path in candidate_paths if path.exists() and path.is_file()
    ]
    if existing_candidates:
        return existing_candidates[0].resolve()

    latest_wav = sorted(
        output_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if latest_wav:
        return latest_wav[0].resolve()

    raise TranscriptionError(
        "Download finished, but no audio file was found for transcription."
    )
