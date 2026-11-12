"""Comprobar que GitHub Pages incluya el favicon solicitado en la pestaña."""
import struct
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class BrowserFaviconTest(unittest.TestCase):
    def test_png_valid_48x48_and_used_by_browser(self):
        html=(ROOT/"docs/index.html").read_text(encoding="utf-8")
        png=(ROOT/"docs/favicon.png").read_bytes()
        self.assertIn('<link rel="icon" type="image/png"',html)
        self.assertIn('href="favicon.png?v=20261112"',html)
        self.assertEqual(png[:8],bytes.fromhex("89504e470d0a1a0a"))
        self.assertGreater(len(png),500)
        self.assertEqual(struct.unpack(">II",png[16:24]),(48,48))

if __name__=="__main__":
    unittest.main()
