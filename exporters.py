from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_txt(data: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(data.get("full_text", ""), encoding="utf-8")


def export_json(data: dict[str, Any], output_path: Path) -> None:
    payload = {
        "metadata": data.get("metadata", {}),
        "segments": data.get("segments", []),
        "full_text": data.get("full_text", ""),
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_md(data: dict[str, Any], output_path: Path) -> None:
    metadata = data.get("metadata", {})
    segments = data.get("segments", [])

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
        "",
        "## Segments",
        "",
    ]

    for segment in segments:
        lines.append(f"### Segment {segment.get('index', '?')}")
        lines.append(f"- File: `{segment.get('file_name', '')}`")
        lines.append("")
        lines.append(segment.get("text", ""))
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
