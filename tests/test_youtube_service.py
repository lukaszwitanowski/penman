from __future__ import annotations

import unittest

from youtube_service import (
    _classify_error,
    _set_cached_video_info,
    clear_video_info_cache,
    get_cached_video_info,
)


class YouTubeServiceTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_video_info_cache()

    def test_error_classification(self) -> None:
        self.assertEqual(
            "transient_rate_limit",
            _classify_error("HTTP Error 429: Too Many Requests").category,
        )
        self.assertEqual(
            "video_unavailable",
            _classify_error("This video is private").category,
        )
        self.assertEqual(
            "strategy_or_format",
            _classify_error("Requested format is not available").category,
        )

    def test_metadata_cache_set_get(self) -> None:
        clear_video_info_cache()
        url = "https://youtu.be/abc123"
        self.assertIsNone(get_cached_video_info(url))
        _set_cached_video_info(
            url,
            {"title": "Test", "duration_seconds": 7, "url": url},
        )
        cached = get_cached_video_info(url)
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual("Test", cached["title"])


if __name__ == "__main__":
    unittest.main()
