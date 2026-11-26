"""Offline, identical point-in-time features for both decision versions."""
import argparse
import concurrent.futures
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from actualizar import compute
from backtest import macro_history,close_time
from decision_engine import decide as gradual
from reference_decision_v2 import decide as baseline
from entry_study import evaluate


def worker(args):
    ticker,market,out=args
    frames={s:pd.read_csv(Path(market)/(s+'.csv'),index_col=0,parse_dates=True) for s in [ticker,'SPY','QQQ','_IDX_VIX']}
    macro=macro_history(frames['SPY'],frames['QQQ'],frames['_IDX_VIX'])
    f=frames[ticker];rows=[]
    for day in f.index:
        if str(day.date())<'2021-11-17' or day not in macro:continue
        row=compute(f.loc[:day],close_time(day),is_stock=ticker not in ('COPX','TQQQ'),spy_close=frames['SPY'].loc[:day,'Close'],qqq_close=frames['QQQ'].loc[:day,'Close'])
        if row is None:continue
        vix=float(frames['_IDX_VIX'].loc[day,'Close'])
        record={'date':str(day.date()),'ticker':ticker,'baseline':baseline(row,macro[day],vix,True).signal,'gradual':gradual(row,macro[day],vix,True).signal}
        rows.append(record)
    pd.DataFrame(rows).to_csv(Path(out)/(ticker+'-decisions.csv'),index=False)
    return ticker,len(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--market',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    tickers=['AMZN','COPX','GOOGL','IREN','JPM','META','MSFT','NVDA','TGT','TQQQ']
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(worker,[(t,a.market,a.out) for t in tickers]):print(result,flush=True)
    readings=pd.concat([pd.read_csv(out/(t+'-decisions.csv')) for t in tickers])
    frames={s:pd.read_csv(Path(a.market)/(s+'.csv'),index_col=0,parse_dates=True) for s in tickers+['SPY']}
    report={'market_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(Path(a.market).glob('*.csv'))},'protocol_sha256':hashlib.sha256((ROOT/'research/gradual-filter-protocol.md').read_bytes()).hexdigest(),'first_date':str(readings.date.min()),'last_date':str(readings.date.max()),'results':{}}
    for label in ['baseline','gradual']:
        sample=readings[['date','ticker',label]].rename(columns={label:'signal'})
        stats,events,trades=evaluate(sample,frames,frames['SPY'],'atr')
        report['results'][label]=stats
        pd.DataFrame(trades).to_csv(out/(label+'-trades.csv'),index=False)
    (out/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
