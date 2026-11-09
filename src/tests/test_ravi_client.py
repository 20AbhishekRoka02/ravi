import os
import sys
import types
import unittest

PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if PATH not in sys.path:
    sys.path.append(PATH)

from classes.ravi_client import RaviCaptionService, RaviClient, _first_caption_text


class RaviClientTests(unittest.TestCase):
    def test_normalize_base_url_handles_missing_scheme(self):
        self.assertEqual(RaviClient("https://api.example.com/").base_url, "https://api.example.com")
        self.assertEqual(RaviClient("api.example.com").base_url, "https://api.example.com")

    def test_first_caption_text_skips_vtt_timestamps(self):
        text = """WEBVTT\n\n00:00:00.000 --> 00:00:02.500\nHello world\n\n00:00:02.500 --> 00:00:04.000\nSecond line\n"""
        self.assertEqual(_first_caption_text(text), "Hello world")

    def test_clip_trim_window_uses_clip_trim_range(self):
        service = RaviCaptionService()
        clip = types.SimpleNamespace(data={"start": 5.5, "end": 9.5})
        self.assertEqual(service._clip_trim_window(clip), (5.5, 9.5))

    def test_clip_reader_path_uses_reader_metadata(self):
        service = RaviCaptionService()
        clip = types.SimpleNamespace(data={"reader": {"path": "/tmp/source.mov"}})
        self.assertEqual(service._clip_reader_path(clip), "/tmp/source.mov")


if __name__ == "__main__":
    unittest.main()
