"""A/B t+1: motor ACTIVO congelado vs referencia espectral integrada.

Misma muestra OHLCV, cómputo y stops. Separa señales diarias de operaciones;
DD y racha son por ticker, nunca se presentan como cartera agregada.
"""
from __future__ import annotations
import argparse, json, csv, hashlib
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from actualizar import compute, read_catalog, last_complete_daily
from backtest import download, macro_history, close_time, simulate, metrics
from decision_engine import decide, audit_consistency, top_five_by_decision
from lectura_espectral import story, macro_wind, normalized_macro
import spectrum_config as cfg

TICKERS='AMZN,NVDA,MSFT,META,GOOGL,JPM,TGT,COPX,IREN,TQQQ'


def category(signal):
    if signal.startswith('COMPRA'):return 'compra'
    if signal.startswith('VIGILAR'):return 'vigilar'
    if signal.startswith('REDUCIR'):return 'reducir'
    if signal.startswith('SALIR'):return 'salir'
    if signal in ('SIN DATOS','NO OPERABLE','DATOS VIEJOS'):return 'sin_datos'
    return 'esperar'


def aggregate(rows):
    trades=[t for r in rows for t in r['trades']]
    return {'operaciones':len(trades),
            'acierto_pct':round(np.mean([t.net_return_pct>0 for t in trades])*100,3) if trades else None,
            'r_promedio':round(np.mean([t.net_r for t in trades]),4) if trades else None,
            'max_drawdown_peor_ticker_pct':min((r['metrics']['max_drawdown_pct'] for r in rows),default=None),
            'peor_racha_individual':max((r['metrics']['peor_racha_perdedora'] for r in rows),default=0)}


def run(frames,tickers,start,end,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frames={k:v.loc[:end] for k,v in frames.items()}
    if any(k not in frames or frames[k].empty for k in tickers+['SPY','QQQ','^VIX']):
        raise ValueError('Muestra incompleta: no producir comparación parcial silenciosa')
    macros=macro_history(frames['SPY'],frames['QQQ'],frames['^VIX'])
    days=sorted(d for d in macros if str(d.date())>=start)
    winds={d:normalized_macro(macro_wind(frames['SPY'].loc[:d],frames['QQQ'].loc[:d],frames['^VIX'].loc[:d,'Close'])) for d in days}
    vix=frames['^VIX']['Close'].to_dict()
    catalog={r['subyacente_usa']:r for r in read_catalog()}
    outputs={v:[] for v in ('actual','espectral')}; daily=defaultdict(lambda:defaultdict(Counter)); pools=defaultdict(list)
    calibration=[]
    for ticker in tickers:
        f=frames[ticker]; dec={v:{} for v in outputs}; cat=catalog[ticker]
        for pos in range(240,len(f)):
            day=f.index[pos]
            if day not in winds:continue
            hist=f.iloc[:pos+1]
            row=compute(hist,close_time(day),is_stock=(ticker not in ('COPX','TQQQ') and cat['sector']!='Índices y ETFs'),
                        spy_close=frames['SPY'].loc[:day,'Close'],qqq_close=frames['QQQ'].loc[:day,'Close'])
            if row is None:continue
            a=decide(row,macros[day],vix.get(day),True,mode='unified').public()
            row['_spectrum_story']=story(hist,frames['SPY'].loc[:day,'Close'])
            b=decide(row,macros[day],vix.get(day),True,mode='spectrum',wind=winds[day]).public()
            asset={'ticker':cat['cedear'],'usa':ticker,'sector':cat['sector'],'data':row,**b}
            errors=audit_consistency([asset],mode='spectrum')
            if errors:raise ValueError(errors)
            pools[day].append(asset)
            for name,result in [('actual',a),('espectral',b)]:
                dec[name][day]={'signal':result['signal'],'stop':row['invalid_usd']}
                daily[day][name][category(result['signal'])]+=1
            calibration.append({'date':str(day.date()),'ticker':ticker,'score':b['score_decision'],
                                'deterioration':b['deterioration'],'size_mult':b['size_mult'],
                                'stop':row['invalid_usd']})
        valid=f.loc[start:end]
        for name in outputs:
            trades,curve=simulate(valid,dec[name],ticker)
            split=valid.index[int(len(valid)*.6)]
            oos=[t for t in trades if t.entry_date>=str(split.date())]
            outputs[name].append({'ticker':ticker,'metrics':metrics(trades,curve),'trades':trades,
                'oos_trades':oos})
            pd.DataFrame([asdict(t) for t in trades]).to_csv(out/f'{name}-{ticker}-trades.csv',index=False)
        print(ticker, {k:outputs[k][-1]['metrics']['n_senales_ejecutadas'] for k in outputs},flush=True)
    daily_rows=[]
    for day in sorted(daily):
        top=top_five_by_decision(pools[day],mode='spectrum')
        r={'date':str(day.date()),'universo':len(pools[day]),'top5':len(top),
           'sobre_precaucion':sum(x['data']['rank_score'] is not None and x['data']['rank_score']>=cfg.BAND_CAUTION for x in pools[day]),
           'top5_fallback':sum(x['fallback'] for x in top)}
        for name in outputs:
            for c in ('compra','vigilar','esperar','reducir','salir','sin_datos'):r[f'{name}_{c}']=daily[day][name][c]
        daily_rows.append(r)
    pd.DataFrame(daily_rows).to_csv(out/'distribucion-diaria.csv',index=False)
    pd.DataFrame(calibration).to_csv(out/'lecturas-diarias.csv',index=False)
    report={'rules_version':cfg.RULES_VERSION,'source':'Yahoo Finance/yfinance OHLCV ajustado USD',
        'generated_at':datetime.now(timezone.utc).isoformat(),'start':start,'end':end,'tickers':tickers,
        'sessions':len(daily),'fee_bps_per_side':5,'slippage_bps_per_side':10,
        'data_sha256':{k:hashlib.sha256(v.to_csv().encode()).hexdigest() for k,v in frames.items()},
        'production_activated':False,'results':{},
        'top5_full_sessions':sum(r['top5']==5 for r in daily_rows),
        'top5_eligible_sessions':sum(r['universo']>=5 for r in daily_rows),
        'latest_distribution':daily_rows[-1] if daily_rows else None}
    for name,rows in outputs.items():
        report['results'][name]={**aggregate(rows),
            'senales_compra_por_dia':round(np.mean([r[f'{name}_compra'] for r in daily_rows]),3),
            'distribucion_promedio':{c:round(np.mean([r[f'{name}_{c}'] for r in daily_rows]),3) for c in ('compra','vigilar','esperar','reducir','salir')},
            'oos':{k:v for k,v in aggregate([{**r,'trades':r['oos_trades']} for r in rows]).items() if k in ('operaciones','acierto_pct','r_promedio')},
            'por_ticker':[{k:v for k,v in r.items() if k not in ('trades','oos_trades')} for r in rows]}
    report['limitations']=['Muestra actual de 10 instrumentos: sesgo de supervivencia.',
        'DD y racha: peor ticker individual; NO cartera agregada.',
        'Mismo simulador original: posición completa por ticker, sin tramos ni tamaños espectrales; compara señales.',
        'Calendario histórico de balances ausente: fricción de earnings no evaluada.',
        'Sin CCL, ratio BYMA ni spread local; subyacentes USA en USD.',
        'Split cronológico 60/40 por entrada; no equivale a validación walk-forward.',
        'No activar en producción sólo por llenar el ranking.']
    (out/'comparacion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    lines=['# A/B motor vigente vs espectral — candidato sin activar','',f"Muestra: {start} a {end}; {len(daily)} ruedas, {len(tickers)} instrumentos.",'',
        '| Métrica | Actual | Espectral |','|---|---:|---:|']
    for key in ('senales_compra_por_dia','operaciones','acierto_pct','r_promedio','max_drawdown_peor_ticker_pct','peor_racha_individual'):
        lines.append(f"| {key} | {report['results']['actual'][key]} | {report['results']['espectral'][key]} |")
    lines+=['',f"Top 5 completo: {report['top5_full_sessions']}/{report['top5_eligible_sessions']} ruedas con al menos 5 activos evaluados.",'',
            '## Distribución diaria promedio','', '| Señal | Actual | Espectral |','|---|---:|---:|']
    for c in ('compra','vigilar','esperar','reducir','salir'):
        lines.append(f"| {c} | {report['results']['actual']['distribucion_promedio'][c]} | {report['results']['espectral']['distribucion_promedio'][c]} |")
    lines+=['','## Límites','']+['- '+v for v in report['limitations']]
    (out/'comparacion.md').write_text('\n'.join(lines))
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',default='backtest-out/market');p.add_argument('--out',default='backtest-out/spectrum')
    p.add_argument('--tickers',default=TICKERS);p.add_argument('--end',default=None);p.add_argument('--years',type=int,default=5)
    a=p.parse_args();tickers=a.tickers.split(',');frames=download(sorted(set(tickers+['SPY','QQQ','^VIX'])),a.years,a.cache)
    now=datetime.now(timezone.utc); frames={k:last_complete_daily(v,now) for k,v in frames.items()}
    if not frames:raise SystemExit('Descarga sin datos; A/B NO ejecutado')
    end=a.end or str(min(v.index[-1] for v in frames.values()).date())
    start=str((pd.Timestamp(end)-pd.DateOffset(years=a.years)).date())
    run(frames,tickers,start,end,a.out)

if __name__=='__main__':main()
