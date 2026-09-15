import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import sync_live


class SyncLiveTests(unittest.TestCase):
    def test_read_events_uses_already_filtered_view_verbatim(self):
        raw = "日付,会場,詳細,フライヤー\n2026/09/19,Venue,Detail,\n"
        self.assertEqual(sync_live.read_events(raw)[0]["venue"], "Venue")

    def test_mirror_only_future_rows_with_flyer_url(self):
        png = b"\x89PNG\r\n\x1a\nreal-image"
        events = [
            {"date": "2026-01-01", "venue": "Past", "detail": "", "flyerUrl": "https://example/past"},
            {"date": "2026-12-01", "venue": "No image", "detail": "", "flyerUrl": ""},
            {"date": "2026-12-02", "venue": "Future", "detail": "", "flyerUrl": "https://example/future"},
        ]
        with tempfile.TemporaryDirectory() as directory, patch.object(sync_live, "FLYER_DIR", Path(directory)), patch.object(sync_live, "ROOT", Path(directory)), patch.object(sync_live, "curl", return_value=png) as fetch:
            mirrored = sync_live.mirror_future_flyers(events, today="2026-06-01")
            self.assertEqual(mirrored, {"2026-12-02": "flyer_20261202.png"})
            self.assertEqual(fetch.call_count, 1)

    def test_media_is_sorted_real_assets_and_never_nowprinting(self):
        png = b"\x89PNG\r\n\x1a\nreal-image"
        events = [{"date": "2026-06-28", "venue": "V", "detail": "", "flyerUrl": "source"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            flyers = root / "img" / "flyer"
            flyers.mkdir(parents=True)
            (flyers / "flyer_20260628.png").write_bytes(png)
            (flyers / "flyer_20250504.jpg").write_bytes(b"\xff\xd8\xffreal")
            (flyers / "nowprinting.png").write_bytes(png)
            with patch.object(sync_live, "ROOT", root), patch.object(sync_live, "FLYER_DIR", flyers):
                payload = sync_live.media_payload(events)
            self.assertEqual([item["date"] for item in payload["media"]], ["2025-05-04", "2026-06-28"])
            self.assertEqual(payload["media"][1]["purposes"], ["archive", "current_event_match"])
            self.assertNotIn("nowprinting", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
