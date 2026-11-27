import copy
import sys
import unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from paper_intraday import process,bars,summary,VERSION
from paper_sim import new_ledger,open_tranche
from test_unified_activation import asset


def frame(start='2026-11-27 09:30',n=5,price=100):
    return pd.DataFrame({'Open':price,'High':price+1,'Low':price-1,'Close':price,'Volume':10000},index=pd.date_range(start,periods=n,freq='15min',tz='America/New_York'))

def assets():
    a=asset('AAA',80);a['data']['date']='2026-11-25';return [a]


def run(s,now,f=None,a=None):
    f=f if f is not None else frame()
    return process(s,{'SPY':f,'AAA':f},assets() if a is None else a,'FAVORABLE',18,'2026-11-25',pd.Timestamp(now,tz='America/New_York'))


class IntradayTests(unittest.TestCase):
    def state(self):return new_ledger('2026-11-25','2026-11-25T22:00:00Z')

    def test_closed_bars_only_and_timezone(self):
        f=frame()
        self.assertEqual(len(bars(f,pd.Timestamp('2026-11-27 10:07',tz='America/New_York'))),2)
        bad=f.copy();bad.index=bad.index.tz_localize(None)
        with self.assertRaises(ValueError):bars(bad,pd.Timestamp('2026-11-27 16:00Z'))

    def test_migration_keeps_cash_history_and_never_backfills(self):
        s=self.state();s['cash']=1995;s['fills']=[{'id':1,'date':'2026-11-25'}]
        original=copy.deepcopy(s)
        x=run(s,'2026-11-27 10:07')
        self.assertEqual(s,original)
        self.assertEqual(x['cash'],1995);self.assertEqual(x['fills'],s['fills'])
        self.assertEqual(x['equity_history'][:len(s['equity_history'])],s['equity_history'])
        self.assertEqual(x['execution_mode'],VERSION)
        self.assertEqual(x['orders'][0]['issued_at'],'2026-11-27T15:07:00+00:00')

    def test_fill_only_after_observation_and_no_duplicate(self):
        x=run(self.state(),'2026-11-27 10:07')
        y=run(x,'2026-11-27 10:31')
        self.assertEqual(len(y['fills']),1)
        fill=y['fills'][0]
        self.assertGreater(pd.Timestamp(fill['timestamp']),pd.Timestamp(fill['signal_timestamp']))
        self.assertEqual(fill['timestamp'],'2026-11-27T15:15:00+00:00')
        self.assertEqual(len(run(y,'2026-11-27 10:31')['fills']),1)
        self.assertGreaterEqual(y['cash'],1400)
        self.assertEqual(y['positions']['AAA']['tranche_count'],1)

    def test_no_fill_from_incomplete_bar(self):
        x=run(self.state(),'2026-11-27 10:07')
        y=run(x,'2026-11-27 10:29')
        self.assertFalse(y['fills'])

    def test_gap_stop_and_no_same_day_churn(self):
        x=run(self.state(),'2026-11-27 10:07');y=run(x,'2026-11-27 10:31')
        f=frame(n=6);f.loc[f.index[4],['Open','High','Low','Close']]=[90,91,89,90]
        z=run(y,'2026-11-27 10:46',f)
        self.assertFalse(z['positions']);self.assertFalse(z['orders'])
        self.assertTrue(z['fills'][-1]['action'].startswith('STOP'))
        self.assertLess(z['fills'][-1]['price_usd'],90)
        self.assertEqual(z['fills'][-1]['timestamp_precision'],'bar_end')

    def test_missing_bar_blocks_later_fills(self):
        x=run(self.state(),'2026-11-27 10:07');f=frame();missing=f.drop(f.index[3])
        y=process(x,{'SPY':f,'AAA':missing},assets(),'FAVORABLE',18,'2026-11-25',pd.Timestamp('2026-11-27 10:46',tz='America/New_York'))
        self.assertFalse(y['fills']);self.assertIn('AAA',y['intraday_unpriced'])

    def test_market_closed_does_not_generate_orders(self):
        x=run(self.state(),'2026-11-28 10:07')
        self.assertFalse(x['orders']);self.assertFalse(x['fills'])
        self.assertIn('Sin velas',x['intraday_status'])

    def test_live_marks_and_summary_do_not_reset(self):
        x=run(self.state(),'2026-11-27 10:07');y=run(x,'2026-11-27 10:31')
        p=summary(y)
        self.assertEqual(p['execution_mode'],VERSION)
        self.assertTrue(p['intraday_equity']);self.assertIsNotNone(p['valued_at'])
        self.assertAlmostEqual(p['equity_usd'],y['cash']+y['positions']['AAA']['shares']*100,places=2)

    def test_no_reset_when_feed_missing(self):
        x=run(self.state(),'2026-11-27 10:07');y=run(x,'2026-11-27 10:31')
        z=process(y,{},assets(),'FAVORABLE',18,'2026-11-25',pd.Timestamp('2026-11-27 16:00Z'))
        self.assertEqual(z['cash'],y['cash']);self.assertEqual(z['fills'],y['fills'])
        self.assertIn('AAA',z['intraday_unpriced'])

    def test_previous_orders_restamped_at_migration(self):
        s=self.state();s['orders']=[{'side':'BUY','usa':'AAA','ticker':'AAA','sector':'Tech','tranche':1,'issued_day':'2026-11-25'}]
        x=run(s,'2026-11-27 10:07');self.assertFalse(x['fills'])
        self.assertEqual(x['orders'][0]['issued_at'],x['intraday_started_at'])

    def test_migration_rechecks_pending_buys(self):
        s=self.state();s['orders']=[{'side':'BUY','usa':'AAA','ticker':'AAA','sector':'Tech','tranche':1,'issued_day':'2026-11-25'}]
        a=assets();a[0]['data']['rank_score']=0;a[0]['score_decision']=0
        x=run(s,'2026-11-27 10:07',a=a)
        self.assertFalse(x['orders']);self.assertFalse(x['fills'])
        self.assertEqual(x['cash'],s['cash']);self.assertIn('migrar',x['cancelled'][0]['reason'])

    def test_old_timestamp_cannot_reprocess_ledger(self):
        x=run(self.state(),'2026-11-27 10:07');y=run(x,'2026-11-27 10:31')
        self.assertEqual(run(y,'2026-11-27 10:20'),y)

    def test_daily_signals_stay_daily_and_unknown_data_never_buys(self):
        a=assets();a[0]['data']['macd_hist_w']=None
        x=run(self.state(),'2026-11-27 10:07',a=a)
        self.assertFalse(x['orders'])
        a=assets();a[0]['data']['date']='2026-11-24'
        self.assertFalse(run(self.state(),'2026-11-27 10:07',a=a)['orders'])

    def test_gap_in_benchmark_cannot_hide_missing_stop_window(self):
        x=run(self.state(),'2026-11-27 10:07');f=frame();spy=f.drop(f.index[3])
        y=process(x,{'SPY':spy,'AAA':f},assets(),'FAVORABLE',18,'2026-11-25',pd.Timestamp('2026-11-27 10:46',tz='America/New_York'))
        self.assertFalse(y['fills']);self.assertIn('AAA',y['intraday_unpriced'])

    def test_expired_order_is_recorded_even_without_prices(self):
        x=run(self.state(),'2026-11-27 10:07')
        y=process(x,{},assets(),'FAVORABLE',18,'2026-11-25',pd.Timestamp('2026-11-28 16:00Z'))
        self.assertFalse(y['orders']);self.assertIn('vencida',y['cancelled'][-1]['reason'])

    def test_daily_history_keeps_one_point_per_session(self):
        x=run(self.state(),'2026-11-27 10:07');y=run(x,'2026-11-27 10:31')
        self.assertEqual([p['date'] for p in y['equity_history']],['2026-11-25','2026-11-27'])
        self.assertEqual(y['equity_history'][-1]['equity'],y['intraday_equity'][-1]['equity'])
        f=frame(start='2026-11-30 09:30')
        z=run(y,'2026-11-30 10:07',f,a=[])
        self.assertEqual(z['equity_history'][:2],y['equity_history'])
        self.assertEqual(z['equity_history'][-1]['date'],'2026-11-30')
