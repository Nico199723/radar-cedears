import sys,unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from signal_study import observe,atr_series
from risk_experiment import position_plan
from presentation import price_history,methodology

class RiskStudyTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({'Open':100.,'High':102.,'Low':99.,'Close':101.,'Volume':1e6},index=pd.bdate_range('2025-01-01',periods=260))
    def test_risk_bounded_and_atr_quantity(self):
        p=position_plan(100,2);q=position_plan(100,4)
        self.assertLess(q['shares'],p['shares']);self.assertAlmostEqual(p['risk_usd'],10)
        self.assertLessEqual(position_plan(100,.01)['risk_usd'],10)
        self.assertIsNone(position_plan(100,60));self.assertIsNone(position_plan(100,float('nan')))
    def test_entry_next_open_and_gap_can_exceed_one_r(self):
        f=self.frame();day=f.index[235];f.loc[f.index[237],['Open','High','Low','Close']]=[80,82,79,81]
        r=observe(f,self.frame(),day,2)
        self.assertEqual(r['entry_date'],str(f.index[236].date()));self.assertLess(r['trade_r'],-1)
    def test_censored_windows_not_zero_or_early_losers(self):
        f=self.frame();r=observe(f,f,f.index[-5],2)
        self.assertIsNone(r['return_5']);self.assertNotIn('trade_r',r)
    def test_no_forward_lookahead_in_sizing(self):
        f=self.frame();day=f.index[235];a=float(atr_series(f.loc[:day]).iloc[-1]);r=observe(f,f,day,a)
        f.loc[f.index[240]:,'Close']=200
        other=observe(f,f,day,a)
        for key in ('shares','stop','risk_usd','entry'):self.assertEqual(r[key],other[key])
    def test_chart_rolling_averages_use_full_history(self):
        f=self.frame();f['Close']=range(1,261);points=price_history(f)
        self.assertEqual(len(points),90);self.assertEqual(points[-1]['sma200'],160.5)
        self.assertEqual(points[0]['sma200'],None)
    def test_metadata_from_constants(self):
        from decision_engine import BUY_FLOOR
        from spectrum_config import BAND_BUY
        self.assertEqual(methodology()['buy'],BUY_FLOOR);self.assertEqual(methodology(True)['buy'],BAND_BUY)

if __name__=='__main__':unittest.main()
