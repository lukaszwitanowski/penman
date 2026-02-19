from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import transcription_service
import youtube_service
from transcription_service import run_transcription
from youtube_service import download_audio, fetch_video_info


class _FakeYoutubeDL:
    def __init__(self, opts: dict):
        self.opts = opts

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def _prepared_path(self) -> Path:
        template = str(self.opts.get("outtmpl", "out_%(id)s.%(ext)s"))
        resolved = template.replace("%(id)s", "abc123").replace("%(ext)s", "webm")
        return Path(resolved)

    def extract_info(self, url: str, download: bool = False):
        if not download:
            return {"id": "abc123", "title": "Fake title", "duration": 12}

        prepared = self._prepared_path()
        prepared.parent.mkdir(parents=True, exist_ok=True)
        wav_path = prepared.with_suffix(".wav")
        wav_path.write_bytes(b"RIFF")
        for hook in self.opts.get("progress_hooks", []):
            hook({"status": "finished", "filename": str(wav_path)})
        return {"id": "abc123", "title": "Fake title", "duration": 12}

    def prepare_filename(self, info: dict) -> str:
        return str(self._prepared_path())


class SmokeIntegrationTests(unittest.TestCase):
    def test_local_transcription_smoke_with_mocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            input_file = base / "in.wav"
            input_file.write_text("fake", encoding="utf-8")
            output_dir = base / "out"
            stage_metrics: dict[str, float] = {}

            def _fake_save_output(
                payload: dict,
                output_dir: Path,
                output_format: str,
                source_file: Path,
            ) -> Path:
                output_dir.mkdir(parents=True, exist_ok=True)
                target = output_dir / "smoke.txt"
                target.write_text(payload.get("full_text", ""), encoding="utf-8")
                return target

            with (
                patch("transcription_service.shutil.which", return_value="ffmpeg"),
                patch(
                    "transcription_service._validate_and_detect_input_format",
                    return_value="wav",
                ),
                patch(
                    "transcription_service._resolve_compute_device",
                    return_value=("cpu", False),
                ),
                patch(
                    "transcription_service._probe_media_duration_seconds",
                    return_value=60.0,
                ),
                patch(
                    "transcription_service._build_segmentation_plan",
                    return_value=transcription_service._SegmentationPlan(
                        should_segment=False,
                        effective_segment_seconds=300,
                        reason="short_input_skip_segmentation",
                    ),
                ),
                patch(
                    "transcription_service._get_or_load_model",
                    return_value=(object(), False),
                ),
                patch(
                    "transcription_service._transcribe_segments",
                    return_value={
                        "segments": [
                            {
                                "index": 1,
                                "file_name": "in.wav",
                                "text": "hello",
                                "error": None,
                                "detected_language": "en",
                                "start_seconds": 0.0,
                                "end_seconds": 1.0,
                            }
                        ],
                        "timeline_segments": [
                            {
                                "index": 1,
                                "segment_index": 1,
                                "start_seconds": 0.0,
                                "end_seconds": 1.0,
                                "text": "hello",
                            }
                        ],
                        "full_text": "hello",
                        "detected_languages": ["en"],
                    },
                ),
                patch("transcription_service._save_output", side_effect=_fake_save_output),
            ):
                output_path = run_transcription(
                    input_path=input_file,
                    output_dir=output_dir,
                    output_format="txt",
                    stage_metrics=stage_metrics,
                )

            self.assertTrue(output_path.exists())
            self.assertIn("total_pipeline_seconds", stage_metrics)

    def test_youtube_fetch_and_download_smoke_with_fake_ydl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with (
                patch("youtube_service.yt_dlp.YoutubeDL", _FakeYoutubeDL),
                patch("youtube_service.shutil.which", return_value="ffmpeg"),
            ):
                info = fetch_video_info("https://youtu.be/abc123")
                downloaded = download_audio(
                    url="https://youtu.be/abc123",
                    output_dir=base,
                )

            self.assertEqual("Fake title", info["title"])
            self.assertTrue(downloaded.exists())
            self.assertEqual(".wav", downloaded.suffix.lower())


if __name__ == "__main__":
    unittest.main()
