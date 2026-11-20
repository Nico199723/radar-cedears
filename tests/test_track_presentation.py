import shutil, subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TrackPresentation(unittest.TestCase):
    def test_quantity_headers_and_order(self):
        html=(ROOT/'docs/index.html').read_text().split('<section id="pageSimulador"',1)[1].split('</section>',1)[0]
        self.assertNotIn('Tramos',html)
        self.assertEqual(html.count('>Cantidad</th>'),3)
        ids=['paperPending','paperPositions','paperClosed','paperFills']
        self.assertEqual(sorted(ids,key=html.index),ids)
        self.assertIn('<details class="paper-rules">',html)
        self.assertEqual(html.count('class="paper-stat"'),6)
    @unittest.skipUnless(shutil.which('node'),'Node no disponible')
    def test_real_js_render(self):
        subprocess.run(['node','tests/track_presentation.cjs'],cwd=ROOT,check=True,capture_output=True,text=True)
