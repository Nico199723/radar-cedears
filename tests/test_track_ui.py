"""Tests de presencia y límites del track record, sin navegar ni llamar a brokers."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class TrackUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/"docs/index.html").read_text(encoding="utf-8")
        cls.js=(ROOT/"docs/app.js").read_text(encoding="utf-8")
        cls.workflow=(ROOT/".github/workflows/actualizar.yml").read_text(encoding="utf-8")
        cls.server=(ROOT/"scripts/actualizar.py").read_text(encoding="utf-8")

    def test_tab_and_four_activity_sections(self):
        self.assertIn('data-tab="simulador"',self.html)
        self.assertIn('id="pageSimulador"',self.html)
        for marker in ("paperPositions","paperClosed","paperFills","paperPending"):
            self.assertIn('id="'+marker+'"',self.html)
        self.assertIn("['simulador','pageSimulador']",self.js)

    def test_dollars_are_fictitious_and_no_orders_sent(self):
        self.assertIn("Capital inicial US$ 2.000",self.html)
        self.assertIn("simul",self.html.lower())
        self.assertIn("Sin operaciones",self.html)
        self.assertIn("'./paper.json?refresh='",self.js)
        self.assertIn("j.is_simulated!==true",self.js)

    def test_state_is_in_action_artifacts_without_commits(self):
        self.assertIn("actions: read",self.workflow)
        self.assertIn("name: radar-paper-ledger-v1",self.workflow)
        self.assertIn("retention-days: 90",self.workflow)
        self.assertIn("GH_ACTIONS_TOKEN:",self.workflow)
        self.assertIn("actions/upload-artifact@",self.workflow)
        self.assertIn("path: docs",self.workflow)
        self.assertIn("process_ledger(state,paper_frames",self.server)
        self.assertNotIn("git push",self.workflow)

if __name__=="__main__":
    unittest.main()
