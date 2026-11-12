"""Validar integración de alertas, volumen y ranking sin datos de red."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from actualizar import ENABLE_CAUTION_ENTRIES


class UIUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/"docs/index.html").read_text(encoding="utf-8")
        cls.js=(ROOT/"docs/app.js").read_text(encoding="utf-8")
        cls.css=(ROOT/"docs/style.css").read_text(encoding="utf-8")
        cls.updater=(ROOT/"scripts/actualizar.py").read_text(encoding="utf-8")

    def test_top_five_is_visible_and_clickable(self):
        self.assertIn('id="top5Cards"',self.html)
        self.assertIn("function renderTop5()",self.js)
        self.assertIn('openDetails(\'asset\',el.dataset.top5)',self.js)
        self.assertIn("renderHeader();renderTop5();renderAssets();",self.js)

    def test_balance_alerts_are_conspicuous_but_not_fabricated(self):
        self.assertIn("<th>Balance</th>",self.html)
        self.assertIn('eventHtml(x)',self.js)
        self.assertIn("Fecha no verificada",self.js)
        self.assertIn("Fuente: Yahoo Finance",self.js)
        self.assertIn(".balance-alert.urgent",self.css)

    def test_stale_data_blocks_top5_too(self):
        self.assertIn("j.top5=[];",self.js)
        self.assertIn("const batchStale=",self.js)

    def test_rule_change_gated_pending_backtest(self):
        self.assertTrue(ENABLE_CAUTION_ENTRIES)
        self.assertIn("if ENABLE_CAUTION_ENTRIES and val:",self.updater)
        self.assertIn("cautious_signal",self.updater)

    def test_volume_rank_not_replaces_legacy_signal_score(self):
        self.assertIn('result["rank_score"] = ranking_stock_21(result) if is_stock else ranking_score(result)',self.updater)
        self.assertIn('sc,rsiD,macdD=row["score"]',self.updater)


if __name__=="__main__":
    unittest.main()
