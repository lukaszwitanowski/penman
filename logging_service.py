from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionLogger:
    def __init__(self, output_dir: str | Path) -> None:
        self._lock = threading.Lock()
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path: Path | None = None
        self.set_output_dir(output_dir)

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    def set_output_dir(self, output_dir: str | Path) -> None:
        try:
            base_dir = Path(output_dir).expanduser().resolve()
            logs_dir = base_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = logs_dir / f"session_{self._session_id}.jsonl"
        except OSError:
            self._log_path = None

    def log(self, level: str, message: str, context: dict[str, Any] | None = None) -> None:
        if self._log_path is None:
            return

        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": level.upper(),
            "message": message,
            "context": context or {},
        }
        line = json.dumps(record, ensure_ascii=False)

        with self._lock:
            try:
                with self._log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                return
