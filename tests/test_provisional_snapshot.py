import sys,unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from provisional_snapshot import closed_bars,partial_daily,snapshot
from test_lectura_espectral import build,FRESH

class ProvisionalTests(unittest.TestCase):
    def bars(self):
        return pd.DataFrame({'Open':[100,101,102], 'High':[102,103,104], 'Low':[99,100,101], 'Close':[101,102,103], 'Volume':[100,150,200]},index=pd.date_range('2026-11-20 09:30',periods=3,freq='h',tz='America/New_York'))
    def test_bar_must_be_closed(self):
        bars=closed_bars(self.bars(),pd.Timestamp('2026-11-20 11:00',tz='America/New_York'))
        self.assertEqual(len(bars),1)
    def test_gap_and_stale_rejected(self):
        f=build(FRESH)
        self.assertIsNone(partial_daily(f,self.bars().iloc[1:],pd.Timestamp('2026-11-20 13:00',tz='America/New_York')))
        self.assertIsNone(partial_daily(f,self.bars(),pd.Timestamp('2026-11-20 15:00',tz='America/New_York')))
    def test_future_daily_bar_ignored(self):
        f=build(FRESH);asof=pd.Timestamp('2026-11-20 11:00',tz='America/New_York')
        f.index=pd.bdate_range(end='2026-11-20',periods=len(f))
        g=f.copy();g.iloc[-1]=999999
        pd.testing.assert_frame_equal(partial_daily(f,self.bars(),asof),partial_daily(g,self.bars(),asof))
    def test_missing_quotes_never_reuse_closed_signal(self):
        base={'assets':[{'ticker':'A','usa':'A','data':{'price':100},'signal':'COMPRA CONDICIONAL'}],'sectors':[],'meta':{}}
        result=snapshot(base,{'A':build(FRESH)},{},pd.Timestamp('2026-11-20 11:00',tz='America/New_York'))
        self.assertEqual(result['top5'],[]);self.assertNotIn(result['assets'][0]['signal'],('COMPRA CONDICIONAL','COMPRA CON PRECAUCIÓN'))
        self.assertEqual(base['assets'][0]['signal'],'COMPRA CONDICIONAL')

if __name__=='__main__':unittest.main()
