import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from chart_data import chart_series, chart_filename, publish_charts


class ChartDataTests(unittest.TestCase):
    def frame(self, count=260):
        return pd.DataFrame({'Close': np.arange(1., count+1)},
                            index=pd.bdate_range(end='2026-11-25', periods=count))

    def test_averages_use_full_history_before_last_90(self):
        series=chart_series(self.frame())
        self.assertEqual(set(series), {'d','c','m21','m50','m200'})
        self.assertEqual(len(series['d']),90)
        self.assertEqual(series['c'][0],171.)
        self.assertEqual(series['m21'][-1],250.)
        self.assertEqual(series['m50'][-1],235.5)
        self.assertEqual(series['m200'][-1],160.5)
        self.assertIsNone(series['m200'][0])

    def test_json_is_finite_rounded_and_null_for_unavailable(self):
        f=self.frame(3);f['Close']=[1.23456,np.nan,np.inf]
        series=chart_series(f)
        encoded=json.dumps(series,allow_nan=False)
        self.assertNotIn('NaN',encoded)
        self.assertNotIn('Infinity',encoded)
        self.assertEqual(series['c'],[1.23,None,None])
        self.assertEqual(series['m21'],[None]*3)

    def test_safe_filename_and_index_exclusion(self):
        for symbol,expected in [('BRK-B','BRK-B.json'),('BRK.B','BRK.B.json'),
                                ('../a/b','.._a_b.json'),('A B=F','A_B_F.json')]:
            self.assertEqual(chart_filename(symbol),expected)
        self.assertIsNone(chart_filename('^VIX'))
        self.assertIsNone(chart_filename(''))

    def test_complete_candles_and_per_symbol_failure(self):
        now=datetime(2026,11,25,18,tzinfo=timezone.utc) # before NY close
        with tempfile.TemporaryDirectory() as d:
            Path(d,'BAD.json').write_text('old')
            meta=publish_charts({'OK':self.frame(),'^VIX':self.frame(),
                                 'BAD':pd.DataFrame({'Wrong':[1]})},now,d)
            self.assertEqual(meta,{'path':'./charts/','bars':90,'count':1})
            series=json.loads(Path(d,'OK.json').read_text())
            self.assertEqual(series['d'][-1],'2026-11-24')
            self.assertFalse(Path(d,'BAD.json').exists())
            self.assertFalse(Path(d,'_VIX.json').exists())

    def test_input_not_mutated(self):
        f=self.frame();before=f.copy(deep=True)
        chart_series(f)
        pd.testing.assert_frame_equal(f,before)

    def test_rules_are_the_existing_engine_constants(self):
        from actualizar import presentation_rules
        from radar_features import MIN_OPTION_SCORE, risk_policy
        from decision_engine import BUY_FLOOR, PRIORITY_FLOOR
        rules=presentation_rules()
        self.assertEqual(rules['thresholds'], {'watch': MIN_OPTION_SCORE,
            'buy': BUY_FLOOR, 'priority': PRIORITY_FLOOR})
        self.assertEqual(rules['policy_normal'],risk_policy('FAVORABLE',0))
        self.assertEqual(rules['policy_prudent'],risk_policy('DEFENSIVO',0))
