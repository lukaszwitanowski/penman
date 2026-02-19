from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from queue_service import QueueService


class QueueServiceTests(unittest.TestCase):
    def test_enqueue_local_paths_skips_duplicates_and_invalid(self) -> None:
        service = QueueService()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            file_a = base / "a.wav"
            file_b = base / "b.wav"
            file_a.write_text("x", encoding="utf-8")
            file_b.write_text("y", encoding="utf-8")

            added, skipped = service.enqueue_local_paths(
                [str(file_a), str(file_b), str(file_a), str(base / "missing.wav")]
            )

            self.assertEqual(2, added)
            self.assertEqual(2, skipped)
            self.assertEqual(2, len(service.items))

    def test_move_up_and_down(self) -> None:
        service = QueueService()
        service.items.extend(["a", "b", "c", "d"])

        new_selection = service.move_up([2])
        self.assertEqual([1], new_selection)
        self.assertEqual(["a", "c", "b", "d"], service.items)

        new_selection = service.move_down([1])
        self.assertEqual([2], new_selection)
        self.assertEqual(["a", "b", "c", "d"], service.items)

    def test_retain_items(self) -> None:
        service = QueueService()
        service.items.extend(["A", "B", "C"])
        service.retain_items({"a", "c"})
        self.assertEqual(["A", "C"], service.items)


if __name__ == "__main__":
    unittest.main()
