import sys,json,tempfile,unittest,urllib.error,subprocess
from pathlib import Path
from datetime import date
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import earnings_calendar as ec
from test_earnings_calendar import asset, payload

class EarningsResilienceTests(unittest.TestCase):
    def run_cached(self, yahoo):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'cache.json'
            ec.save_cache(cache,{'AAA':{'date':'2026-11-23','source':'Nasdaq','fetched_at':'2026-11-01'}})
            result,cov=ec.earnings_for_universe([asset('AAA')],date(2026,11,18),cache,
                fetch_nasdaq=lambda d:payload(),fetch_yahoo_fn=yahoo,days_ahead=1,pause=0,sleep=lambda _:None)
            stored=ec.load_cache(cache)
            self.assertEqual(result['AAA']['date'],'2026-11-23')
            self.assertEqual(stored['AAA']['fetched_at'],'2026-11-01')
            self.assertEqual(cov['from_cache'],1)
            self.assertTrue(result['AAA']['stale'])

    def test_empty_response_cannot_erase_good_date(self):
        self.run_cached(lambda s,d:None)

    def test_past_response_cannot_erase_good_date(self):
        self.run_cached(lambda s,d:{'date':'2026-10-01'})

    def test_malformed_nasdaq_degrades_to_yahoo(self):
        r,c=ec.earnings_for_universe([asset('AAA')],date(2026,11,18),
            fetch_nasdaq=lambda d:{'data':{'rows':42}},fetch_yahoo_fn=lambda s,d:{'date':'2026-12-10'},
            days_ahead=8,pause=0,sleep=lambda _:None)
        self.assertTrue(c['nasdaq_aborted']);self.assertEqual(c['from_yahoo'],1)
        self.assertEqual(c['nasdaq_days_attempted'],4)
        self.assertEqual(r['AAA']['date'],'2026-12-10')

    def test_http_block_is_distinguished_from_timeout(self):
        for exc,blocked in [(urllib.error.HTTPError('url',403,'denied',None,None),4),(TimeoutError('timeout'),0)]:
            def fetch(d):raise exc
            _,c=ec.collect_nasdaq(date(2026,11,18),8,fetch,0,lambda _:None)
            self.assertEqual(c['nasdaq_blocked_responses'],blocked)
            self.assertTrue(c['nasdaq_aborted'])

    def test_yfinance_swallowed_error_is_not_no_date(self):
        fake=MagicMock();fake.Ticker.return_value.calendar={}
        with patch.dict(sys.modules,{'yfinance':fake}):
            with self.assertRaises(RuntimeError):ec.fetch_yahoo('AAA',date(2026,11,18))

    def test_invalid_cache_entry_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'c.json';p.write_text(json.dumps({'version':1,'entries':{'AAA':42,'BBB':None}}))
            self.assertEqual(ec.load_cache(p),{})

    def test_etf_without_price_history_not_queried(self):
        a=asset('COPX','Materiales y minería');a['data']=None;a['earnings_is_etf']=True
        r,c=ec.earnings_for_universe([a],date(2026,11,18),days_ahead=0,
            fetch_yahoo_fn=lambda s,d:self.fail('ETF consultado'))
        self.assertEqual(c['etfs'],1);self.assertEqual(r,{})

    def test_sources_and_missing_states_render(self):
        root=Path(__file__).resolve().parents[1]
        js=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const ctx={document:{getElementById:()=>({})}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync('docs/app.js','utf8').split('function openDetails')[0],ctx);
const render=x=>{ctx.x=x;return vm.runInContext('eventHtml(x)',ctx)};
assert(render({earnings:{date:'2099-01-01',days_until:90,source:'Nasdaq <x>'}}).includes('2099'));
assert(!render({earnings:{date:'2099-01-01',days_until:90,source:'Nasdaq <x>'}}).includes('<x>'));
assert(!render({earnings:{date:'2001-01-01',days_until:1}}).includes('2001'));
assert(render({earnings_status:'ETF · SIN BALANCES'}).includes('>ETF<'));
assert(render({earnings_status:'SIN FECHA PUBLICADA'}).includes('>s/f<'));
assert(render({earnings_status:'FECHA NO CONSULTADA'}).includes('no consultada'));
'''
        subprocess.run(['node','-e',js],cwd=root,check=True,capture_output=True,text=True)
