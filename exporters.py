from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_txt(data: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(data.get("full_text", ""), encoding="utf-8")


def export_json(data: dict[str, Any], output_path: Path) -> None:
    metadata = data.get("metadata", {})
    payload = {
        "metadata": metadata,
        "segments": data.get("segments", []),
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
        data.get("full_text", ""),
    ]

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

    for segment in segments:
        lines.append(f"### Segment {segment.get('index', '?')}")
        lines.append(f"- File: `{segment.get('file_name', '')}`")
        lines.append("")
        lines.append(segment.get("text", ""))
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
