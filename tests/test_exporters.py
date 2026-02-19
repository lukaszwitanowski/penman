from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from exporters import export_md, export_srt, export_txt, export_vtt


class ExportersTests(unittest.TestCase):
    def _sample_payload(self) -> dict:
        return {
            "metadata": {
                "source_file": "sample.wav",
                "include_timestamps": True,
            },
            "segments": [
                {"index": 1, "file_name": "seg_001.wav", "text": "hello world"},
            ],
            "timeline_segments": [
                {"start_seconds": 0.0, "end_seconds": 1.0, "text": "hello"},
                {"start_seconds": 1.0, "end_seconds": 2.0, "text": "world"},
            ],
            "full_text": "hello world",
        }

    def test_srt_and_vtt_export(self) -> None:
        payload = self._sample_payload()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            srt_path = base / "out.srt"
            vtt_path = base / "out.vtt"
            export_srt(payload, srt_path)
            export_vtt(payload, vtt_path)
            srt_text = srt_path.read_text(encoding="utf-8")
            vtt_text = vtt_path.read_text(encoding="utf-8")
            self.assertIn("1", srt_text)
            self.assertIn("-->", srt_text)
            self.assertTrue(vtt_text.startswith("WEBVTT"))

    def test_txt_and_md_with_timestamps(self) -> None:
        payload = self._sample_payload()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            txt_path = base / "out.txt"
            md_path = base / "out.md"
            export_txt(payload, txt_path)
            export_md(payload, md_path)
            txt_text = txt_path.read_text(encoding="utf-8")
            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("[00:00:00]", txt_text)
            self.assertIn("## Timeline", md_text)


if __name__ == "__main__":
    unittest.main()
