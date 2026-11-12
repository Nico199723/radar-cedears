"""UI: categoría HOLD/ESPERAR y chistes visibles, sin cambiar el motor de señales."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DOCS / "index.html").read_text(encoding="utf-8")
        cls.js = (DOCS / "app.js").read_text(encoding="utf-8")
        cls.css = (DOCS / "style.css").read_text(encoding="utf-8")

    def test_hold_esperar_filter_unifies_old_options(self):
        self.assertIn('<option value="esperar">HOLD / ESPERAR</option>', self.html)
        self.assertNotIn('<option value="mantener">', self.html)
        self.assertIn("if(s.includes('MANTENER'))return 'esperar'", self.js)

    def test_legacy_signal_labels_are_rendered_as_hold_esperar(self):
        self.assertIn("s==='MANTENER / ESPERAR'||s==='ESPERAR'", self.js)
        self.assertIn("s==='ESPERAR MACRO'", self.js)
        self.assertIn("signalLabel(s||'SIN DATOS')", self.js)

    def test_martin_has_visible_static_fallback_and_multiple_quotes(self):
        self.assertIn('<aside class="martin-card"', self.html)
        self.assertIn('id="martinQuote"', self.html)
        self.assertIn('id="martinNext"', self.html)
        self.assertIn('ASTS', self.html)
        self.assertIn('-40%', self.html)
        quotes = re.search(r'const martinQuotes=\[(.*?)\];', self.js, re.S)
        self.assertIsNotNone(quotes)
        self.assertGreaterEqual(quotes.group(1).count("\n  '"), 10)

    def test_rotation_respects_accessibility_and_visibility(self):
        self.assertIn('prefers-reduced-motion: reduce', self.js)
        self.assertIn('if(!document.hidden)', self.js)
        self.assertIn('12000', self.js)
        self.assertIn("martinNext').addEventListener('click'", self.js)
        self.assertIn('aria-live="off"', self.html)
        self.assertIn('.martin-card', self.css)

    @unittest.skipUnless(shutil.which("node"), "Node.js no disponible")
    def test_javascript_has_valid_syntax(self):
        subprocess.run(["node", "--check", str(DOCS / "app.js")],
                       check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
