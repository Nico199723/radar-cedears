"""Sensibilidad de bandas sobre entrenamiento; OOS cronológico separado, sin activación.

No optimiza pesos ni tamaños sin modelo de cartera. Elige sólo con R medio IS.
Cada ventana arranca sin posiciones y liquida al final para evitar arrastres IS/OOS.
"""
import argparse,json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import lectura_espectral as sp
from backtest import simulate
from backtest_spectrum import aggregate


def evaluate(readings,frames,bands,start,end):
    rows=[]
    with patch.multiple(sp,BAND_WATCH=bands[0],BAND_CAUTION=bands[1],BAND_BUY=bands[2]):
        for ticker,part in readings.groupby('ticker'):
            decisions={pd.Timestamp(r.date):{'signal':sp.signal_for(r.score,r.deterioration),'stop':r.stop}
                       for r in part.itertuples() if start<=r.date<=end and pd.notna(r.score)}
            f=frames[ticker].loc[start:end]
            trades,curve=simulate(f,decisions,ticker)
            from backtest import metrics
            rows.append({'trades':trades,'metrics':metrics(trades,curve)})
    return aggregate(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);r=json.loads((out/'comparacion.json').read_text());df=pd.read_csv(out/'lecturas-diarias.csv')
    dates=sorted(df.date.unique());split=dates[int(len(dates)*.6)]
    frames={t:pd.read_csv(Path(a.cache)/(t+'.csv'),index_col=0,parse_dates=True) for t in r['tickers']}
    candidates=[(42,52,63),(45,55,66),(48,58,69)]
    rows=[]
    for bands in candidates:
        rows.append({'bands':bands,'is':evaluate(df,frames,bands,dates[0],dates[int(len(dates)*.6)-1]),
                     'oos':evaluate(df,frames,bands,split,dates[-1])})
    selected=max(rows,key=lambda x:x['is']['r_promedio'] if x['is']['r_promedio'] is not None else -float('inf'))
    result={'split':split,'selected_using':'R promedio entrenamiento exclusivamente',
            'selected_bands':selected['bands'],'production_activated':False,'candidates':rows,
            'limitation':'Sensibilidad exploratoria; pesos y tamaños no calibrados. Requiere muestra ampliada y walk-forward antes de promoción.'}
    (out/'calibracion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['\n## Sensibilidad de bandas (vigilar / precaución / compra)','',f'Separación IS/OOS: {split}. Selección sólo por R IS; ventanas sin posiciones arrastradas.','',
           '| Bandas | Trades IS | R IS | Trades OOS | R OOS |','|---|---:|---:|---:|---:|']
    for row in rows:lines.append(f"| {row['bands']} | {row['is']['operaciones']} | {row['is']['r_promedio']} | {row['oos']['operaciones']} | {row['oos']['r_promedio']} |")
    lines+=['',f"Mejor IS: {selected['bands']}. No se cambia configuración ni se activa producción.",result['limitation']]
    with (out/'comparacion.md').open('a') as f:f.write('\n'.join(lines))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
