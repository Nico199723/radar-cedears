"""Reconstruct frozen active-engine decisions on a supplied point-in-time sample."""
import argparse
from pathlib import Path
import pandas as pd
import presentation
presentation.price_history=lambda _:[]
from actualizar import compute,read_catalog
from backtest import macro_history,close_time
from decision_engine import decide
parser=argparse.ArgumentParser();parser.add_argument('--readings',required=True);parser.add_argument('--market',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
readings=pd.read_csv(args.readings)
frames={p.stem:pd.read_csv(p,index_col=0,parse_dates=True) for p in Path(args.market).glob('*.csv')}
frames['^VIX']=frames['_IDX_VIX']
macro=macro_history(frames['SPY'],frames['QQQ'],frames['^VIX'])
catalog={r['subyacente_usa']:r for r in read_catalog()}
rows=[]
for ticker,g in readings.groupby('ticker'):
 for item in g.itertuples():
  day=pd.Timestamp(item.date);hist=frames[ticker].loc[:day]
  row=compute(hist,close_time(day),is_stock=ticker not in ('COPX','TQQQ') and catalog[ticker]['sector']!='Índices y ETFs',spy_close=frames['SPY'].loc[:day,'Close'],qqq_close=frames['QQQ'].loc[:day,'Close'])
  decision=decide(row,macro[day],float(frames['^VIX'].loc[day,'Close']),True,mode='unified')
  rows.append({'date':item.date,'ticker':ticker,'signal':decision.signal})
 print(ticker,flush=True)
pd.DataFrame(rows).to_csv(args.out,index=False)
