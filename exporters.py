from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_clock(seconds: float, millisecond_separator: str = ",") -> str:
    bounded = max(0.0, seconds)
    total_millis = int(round(bounded * 1000))
    hours = total_millis // 3_600_000
    minutes = (total_millis % 3_600_000) // 60_000
    secs = (total_millis % 60_000) // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{millisecond_separator}{millis:03d}"


def _format_short_clock(seconds: float) -> str:
    bounded = int(max(0.0, seconds))
    hours = bounded // 3600
    minutes = (bounded % 3600) // 60
    secs = bounded % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _normalize_timeline_item(raw_item: dict[str, Any]) -> dict[str, Any] | None:
    text = str(raw_item.get("text", "")).strip()
    if not text:
        return None

    start_seconds = _to_float(raw_item.get("start_seconds"), 0.0)
    end_seconds = _to_float(raw_item.get("end_seconds"), start_seconds)
    if end_seconds <= start_seconds:
        end_seconds = start_seconds + 1.0

    return {
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "text": text,
    }


def _build_fallback_timeline(data: dict[str, Any]) -> list[dict[str, Any]]:
    segments = data.get("segments", [])
    if not isinstance(segments, list):
        segments = []

    timeline: list[dict[str, Any]] = []
    cursor_seconds = 0.0

    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        # Fallback duration heuristic: 12 chars/second, bounded 1-8 seconds.
        duration_seconds = max(1.0, min(8.0, len(text) / 12.0))
        timeline.append(
            {
                "start_seconds": cursor_seconds,
                "end_seconds": cursor_seconds + duration_seconds,
                "text": text,
            }
        )
        cursor_seconds += duration_seconds

    if timeline:
        return timeline

    full_text = str(data.get("full_text", "")).strip()
    if not full_text:
        return []
    return [
        {
            "start_seconds": 0.0,
            "end_seconds": max(1.0, len(full_text) / 15.0),
            "text": full_text,
        }
    ]


def _get_timeline(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_timeline = data.get("timeline_segments", [])
    timeline: list[dict[str, Any]] = []

    if isinstance(raw_timeline, list):
        for raw_item in raw_timeline:
            if not isinstance(raw_item, dict):
                continue
            normalized = _normalize_timeline_item(raw_item)
            if normalized is not None:
                timeline.append(normalized)

    if timeline:
        timeline.sort(key=lambda item: (item["start_seconds"], item["end_seconds"]))
        return timeline

    return _build_fallback_timeline(data)


def export_txt(data: dict[str, Any], output_path: Path) -> None:
    metadata = data.get("metadata", {})
    include_timestamps = bool(
        isinstance(metadata, dict) and metadata.get("include_timestamps", False)
    )

    if include_timestamps:
        timeline = _get_timeline(data)
        lines = [
            f"[{_format_short_clock(item['start_seconds'])}] {item['text']}"
            for item in timeline
        ]
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return

    output_path.write_text(str(data.get("full_text", "")), encoding="utf-8")


def export_json(data: dict[str, Any], output_path: Path) -> None:
    metadata = data.get("metadata", {})
    payload = {
        "metadata": metadata,
        "segments": data.get("segments", []),
        "timeline_segments": _get_timeline(data),
        "full_text": data.get("full_text", ""),
    }
    youtube_metadata = metadata.get("youtube") if isinstance(metadata, dict) else None
    if isinstance(youtube_metadata, dict):
        payload["youtube"] = youtube_metadata

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_md(data: dict[str, Any], output_path: Path) -> None:
    metadata = data.get("metadata", {})
    segments = data.get("segments", [])
    youtube = metadata.get("youtube") if isinstance(metadata, dict) else None
    include_timestamps = bool(
        isinstance(metadata, dict) and metadata.get("include_timestamps", False)
    )

    lines: list[str] = [
        "# Transcription",
        "",
        f"- Source file: `{metadata.get('source_file', '')}`",
        f"- Input format: `{metadata.get('input_format', '')}`",
        f"- Language: `{metadata.get('language', 'auto')}`",
        f"- Model: `{metadata.get('model_name', '')}`",
        f"- Created at: `{metadata.get('created_at', '')}`",
        "",
        "## Full Text",
        "",
        str(data.get("full_text", "")),
    ]

    if include_timestamps:
        timeline = _get_timeline(data)
        lines.extend(
            [
                "",
                "## Timeline",
                "",
            ]
        )
        for item in timeline:
            lines.append(
                f"- `{_format_short_clock(item['start_seconds'])}` {item['text']}"
            )

    if isinstance(youtube, dict) and youtube:
        lines.extend(
            [
                "",
                "## YouTube",
                "",
                f"- URL: `{youtube.get('url', '')}`",
                f"- Title: `{youtube.get('title', '')}`",
                f"- Duration (s): `{youtube.get('duration_seconds', '')}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Segments",
            "",
        ]
    )

    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            lines.append(f"### Segment {segment.get('index', '?')}")
            lines.append(f"- File: `{segment.get('file_name', '')}`")
            lines.append("")
            lines.append(str(segment.get("text", "")))
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def export_srt(data: dict[str, Any], output_path: Path) -> None:
    timeline = _get_timeline(data)
    blocks: list[str] = []
    for index, item in enumerate(timeline, start=1):
        start = _format_clock(item["start_seconds"], millisecond_separator=",")
        end = _format_clock(item["end_seconds"], millisecond_separator=",")
        blocks.append(f"{index}\n{start} --> {end}\n{item['text']}\n")
    output_path.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")


def export_vtt(data: dict[str, Any], output_path: Path) -> None:
    timeline = _get_timeline(data)
    lines: list[str] = ["WEBVTT", ""]
    for item in timeline:
        start = _format_clock(item["start_seconds"], millisecond_separator=".")
        end = _format_clock(item["end_seconds"], millisecond_separator=".")
        lines.append(f"{start} --> {end}")
        lines.append(item["text"])
        lines.append("")
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
