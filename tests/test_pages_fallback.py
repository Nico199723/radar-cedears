"""La publicación Jekyll de la rama no debe mostrar README en vez del radar."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PagesFallbackTest(unittest.TestCase):
    def test_root_index_redirects_to_real_dashboard(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('url=./docs/', index)
        self.assertIn('window.location.replace(', index)
        self.assertIn('href="./docs/"', index)
        self.assertTrue((ROOT / "docs" / "index.html").is_file())
        self.assertTrue((ROOT / "docs" / "app.js").is_file())

    def test_custom_workflow_still_deploys_docs_artifact(self):
        workflow = (ROOT / ".github" / "workflows" / "actualizar.yml").read_text(encoding="utf-8")
        self.assertIn("path: docs", workflow)
        self.assertIn("actions/deploy-pages@", workflow)


if __name__ == "__main__":
    unittest.main()
