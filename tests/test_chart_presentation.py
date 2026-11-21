import shutil,subprocess,unittest
from pathlib import Path
class ChartTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node unavailable')
    def test_real_svg(self):
        subprocess.run(['node','tests/chart_presentation.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)
