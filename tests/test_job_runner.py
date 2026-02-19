from __future__ import annotations

import unittest

from job_runner import estimate_eta_seconds, format_eta, infer_stage_label


class JobRunnerTests(unittest.TestCase):
    def test_estimate_eta(self) -> None:
        self.assertIsNone(estimate_eta_seconds(10.0, 0.0))
        self.assertAlmostEqual(10.0, estimate_eta_seconds(10.0, 50.0))

    def test_format_eta(self) -> None:
        self.assertEqual("--:--", format_eta(None))
        self.assertEqual("01:05", format_eta(65))
        self.assertEqual("1:01:01", format_eta(3661))

    def test_infer_stage_label(self) -> None:
        self.assertEqual("Download", infer_stage_label("Downloading audio from YouTube..."))
        self.assertEqual("Preprocess", infer_stage_label("Segmenting audio with ffmpeg..."))
        self.assertEqual("Transcribe", infer_stage_label("Transcribing segment 1/3"))
        self.assertEqual("Export", infer_stage_label("Saving output file..."))


if __name__ == "__main__":
    unittest.main()
