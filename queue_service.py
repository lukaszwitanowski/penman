from __future__ import annotations

from pathlib import Path


class QueueService:
    def __init__(self) -> None:
        self._items: list[str] = []

    @property
    def items(self) -> list[str]:
        return self._items

    def clear(self) -> None:
        self._items.clear()

    def remove_indices(self, indices: list[int]) -> int:
        removed = 0
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self._items):
                del self._items[index]
                removed += 1
        return removed

    def enqueue_local_paths(self, paths: list[str]) -> tuple[int, int]:
        added = 0
        skipped = 0
        existing = {item.lower() for item in self._items}

        for raw_path in paths:
            if not raw_path:
                skipped += 1
                continue

            normalized = str(Path(raw_path).expanduser().resolve())
            if normalized.lower() in existing:
                skipped += 1
                continue
            if not Path(normalized).is_file():
                skipped += 1
                continue

            self._items.append(normalized)
            existing.add(normalized.lower())
            added += 1

        return added, skipped

    def append_unique(self, value: str) -> bool:
        normalized = value.strip()
        if not normalized:
            return False
        existing = {item.lower() for item in self._items}
        if normalized.lower() in existing:
            return False
        self._items.append(normalized)
        return True

    def move_up(self, indices: list[int]) -> list[int]:
        selected = sorted({idx for idx in indices if 0 <= idx < len(self._items)})
        if not selected or selected[0] == 0:
            return selected

        for index in selected:
            self._items[index - 1], self._items[index] = (
                self._items[index],
                self._items[index - 1],
            )
        return [index - 1 for index in selected]

    def move_down(self, indices: list[int]) -> list[int]:
        selected = sorted({idx for idx in indices if 0 <= idx < len(self._items)})
        if not selected or selected[-1] >= len(self._items) - 1:
            return selected

        for index in reversed(selected):
            self._items[index + 1], self._items[index] = (
                self._items[index],
                self._items[index + 1],
            )
        return [index + 1 for index in selected]

    def retain_items(self, allowed_lower_values: set[str]) -> None:
        self._items[:] = [
            item for item in self._items if item.lower() in allowed_lower_values
        ]
