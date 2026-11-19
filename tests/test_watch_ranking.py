import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from watch_ranking import ranked_watchlist

class WatchRankingTests(unittest.TestCase):
    def assets(self):
        return [dict(ticker=str(i),usa=str(i),sector=str(i%3),signal='REDUCIR / EVITAR',
                     data=dict(rank_score=60-i,price=10,dollar_volume20=2_000_000)) for i in range(8)]
    def test_fills_without_buys_and_preserves_signal(self):
        a=self.assets();r=ranked_watchlist(a)
        self.assertEqual(len(r),5)
        self.assertEqual([x['rank_score'] for x in r],[60,59,58,57,56])
        self.assertTrue(all(x['signal']=='REDUCIR / EVITAR' and x['ranking_only'] for x in r))
    def test_sector_cap_is_soft(self):
        a=self.assets()
        for x in a:x['sector']='one'
        self.assertEqual(len(ranked_watchlist(a)),5)
    def test_excludes_bad_data_and_illiquid(self):
        a=self.assets();a[0]['signal']='DATOS VIEJOS';a[1]['data']['rank_score']=float('nan');a[2]['data']['dollar_volume20']=999999
        self.assertEqual([x['ticker'] for x in ranked_watchlist(a)],['3','4','5','6','7'])
