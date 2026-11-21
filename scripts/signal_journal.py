"""Forward observation journal, independent of the trading ledger.

No historical signals are invented on first run. Cache loss is disclosed through
started_at, and the study restarts its count. Bars/earnings are never committed.
"""
import json
import math
from pathlib import Path
import numpy as np
from signal_study import observe
from risk_experiment import HORIZONS

VERSION='signal-observations-v1'


def update(state, snapshots, frames, now):
    if state is None:state={'version':VERSION,'started_at':now.isoformat(),'last':{},'events':[]}
    if state.get('version')!=VERSION:raise ValueError('Versión de estudio incompatible')
    for engine,snapshot in snapshots.items():
        for a in snapshot.get('assets',[]):
            d=a.get('data') or {};sym=a.get('usa');day=d.get('date')
            if not sym or not day or sym not in frames:continue
            key=engine+':'+sym;previous=state['last'].get(key,{})
            if previous.get('date','')>=day:continue
            # Unknown data must not manufacture a new regime when it returns.
            if a.get('signal') in ('SIN DATOS','DATOS VIEJOS','NO OPERABLE'):continue
            buy=str(a.get('signal','')).startswith('COMPRA')
            if buy and not previous.get('buy',False):
                atr=d.get('atr14');price=d.get('price')
                if all(isinstance(v,(float,int)) and math.isfinite(v) and v>0 for v in (atr,price)):
                    state['events'].append({'engine':engine,'ticker':sym,'date':day,'atr_fraction':atr/price,'observed_at':now.isoformat()})
            state['last'][key]={'date':day,'buy':buy}
    results=[];spy=frames.get('SPY')
    if spy is not None:
        for event in state['events']:
            f=frames.get(event['ticker'])
            if f is None or event['date'] not in f.index:continue
            # Use the same adjusted basis for signal ATR and future prices.
            atr=float(f.loc[event['date'],'Close'])*event['atr_fraction']
            row=observe(f,spy,event['date'],atr)
            if row:results.append({**event,**row})
    summaries={}
    for engine in snapshots:
        rows=[r for r in results if r['engine']==engine]
        summaries[engine]={}
        count=sum(e['engine']==engine for e in state['events'])
        for h in HORIZONS:
            mature=[r for r in rows if r.get(f'return_{h}') is not None]
            summaries[engine][str(h)]={'observed':count,'matured':len(mature),'pending':count-len(mature),
                'initial_sample':len(mature)>=30,
                **{k:float(np.mean([r[f'{k}_{h}'] for r in mature])) if mature else None for k in ('return','excess_spy','r')}}
    return state,{'version':VERSION,'started_at':state['started_at'],'generated_at':now.isoformat(),
                  'summaries':summaries,'events':results,
                  'note':'Señales nuevas observadas desde el inicio del registro. Retorno sin stop a 5/10/20 ruedas; R usa riesgo 2 ATR con costos. Señales correlacionadas: 30 no validan una estrategia. Caché independiente del ledger; si se pierde, se reinicia la fecha y el conteo.'}


def publish(snapshots,frames,now,cache_path,output_path):
    path=Path(cache_path)
    # Corrupt state is an error, never silently reset.
    state=json.loads(path.read_text()) if path.exists() else None
    state,public=update(state,snapshots,frames,now)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,allow_nan=False,ensure_ascii=False));temp.replace(path)
    Path(output_path).write_text(json.dumps(public,allow_nan=False,ensure_ascii=False),encoding='utf-8')
