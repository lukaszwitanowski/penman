from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_runtime_paths() -> None:
    if not getattr(sys, "frozen", False):
        return

    base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    ffmpeg_candidates = [
        base_dir / "ffmpeg" / "bin",
        base_dir / "bin",
        base_dir,
    ]

    for candidate in ffmpeg_candidates:
        ffmpeg_exe = candidate / "ffmpeg.exe"
        if ffmpeg_exe.exists():
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{candidate}{os.pathsep}{current_path}"
            break
