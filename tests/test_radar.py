import csv
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import actualizar as r

class RadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        idx = pd.bdate_range("2023-01-02", periods=790)
        prices = 100 * np.exp(np.cumsum(np.full(len(idx), 0.001) + np.sin(np.arange(len(idx)) / 13) * 0.003))
        cls.frame = pd.DataFrame({"Open": prices, "High": prices*1.015, "Low": prices*0.985, "Close": prices, "Volume": np.full(len(idx), 1000000)}, index=idx)

    def test_catalog_curated_is_unique(self):
        d=r.read_catalog()
        self.assertEqual(len(d), 271)
        self.assertEqual(len(set(x['cedear'] for x in d)),len(d))
        self.assertTrue(any(x['subyacente_usa'] == '' for x in d))

    def test_score_range(self):
        d=r.compute(self.frame, datetime(2026,11,12,21,0,tzinfo=timezone.utc))
        self.assertIsNotNone(d)
        self.assertGreaterEqual(d['score'],0)
        self.assertLessEqual(d['score'],100)
        self.assertIsNotNone(d['rsi14d'])
        self.assertIsNotNone(d['macd_hist_d'])

    def test_no_buy_if_macro_unverified(self):
        d=r.compute(self.frame, datetime(2026,11,12,21,0,tzinfo=timezone.utc))
        for macro in ('DEFENSIVO','NO VERIFICADO','MIXTO'):
            signal,_,_=r.get_signal(d,macro,True)
            self.assertNotEqual(signal,'COMPRA CONDICIONAL')

    def test_stale_blocks_signal(self):
        d=r.compute(self.frame, datetime(2026,11,12,21,0,tzinfo=timezone.utc))
        signal,_,_=r.get_signal(d,'FAVORABLE',False)
        self.assertEqual(signal,'DATOS VIEJOS')

    def test_discard_open_us_session(self):
        idx=pd.to_datetime(['2026-11-10','2026-11-11','2026-11-12'])
        s=pd.DataFrame({'Close':[100.,101.,102.]}, index=idx)
        from zoneinfo import ZoneInfo
        early=datetime(2026,11,12,11,0,tzinfo=ZoneInfo('America/New_York'))
        truncated=r.last_complete_daily(s,early)
        self.assertEqual(str(truncated.index[-1].date()),'2026-11-11')

if __name__ == '__main__':
    unittest.main()
