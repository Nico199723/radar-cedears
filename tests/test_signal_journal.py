import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from signal_journal import update

class JournalTests(unittest.TestCase):
    def test_idempotent_and_no_invented_history(self):
        f=pd.DataFrame({'Open':100.,'High':101.,'Low':99.,'Close':100.,'Volume':1e6},index=pd.bdate_range('2026-01-01',periods=50))
        a={'usa':'A','signal':'COMPRA CONDICIONAL','data':{'date':str(f.index[25].date()),'price':100.,'atr14':2.}}
        snapshots={'espectral':{'assets':[a]}};now=datetime(2026,11,21,tzinfo=timezone.utc)
        state,public=update(None,snapshots,{'A':f,'SPY':f},now)
        again,other=update(state,snapshots,{'A':f,'SPY':f},now)
        self.assertEqual(len(again['events']),1);self.assertEqual(public,other)
        self.assertEqual(public['summaries']['espectral']['20']['matured'],1)
        self.assertFalse(public['summaries']['espectral']['20']['initial_sample'])
        a['data']['date']=str(f.index[-1].date())
        state,_=update(state,snapshots,{'A':f,'SPY':f},now)
        self.assertEqual(len(state['events']),1)
    def test_incompatible_cache_is_not_reset(self):
        with self.assertRaises(ValueError):update({'version':'old'},{},{},datetime.now(timezone.utc))

if __name__=='__main__':unittest.main()
