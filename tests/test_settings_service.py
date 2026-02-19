from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import settings_service


class SettingsServiceTests(unittest.TestCase):
    def test_save_and_load_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            payload = {
                "output_dir": "C:/tmp/out",
                "model_name": "base",
                "include_timestamps": True,
            }
            with patch.object(settings_service, "get_settings_path", return_value=settings_path):
                self.assertTrue(settings_service.save_app_settings(payload))
                loaded = settings_service.load_app_settings(defaults={"model_name": "tiny"})
            self.assertEqual("C:/tmp/out", loaded["output_dir"])
            self.assertEqual("base", loaded["model_name"])
            self.assertTrue(loaded["include_timestamps"])


if __name__ == "__main__":
    unittest.main()
