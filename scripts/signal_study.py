"""Point-in-time signal study. t+1 open; fixed horizons; risk-sized, separate from paper ledger.

Forward returns ignore stops (signal quality). Executable 20-session trades include
stops, adverse gaps, fees/slippage and one concurrent position per instrument.
Drawdown is worst individual sleeve, NOT portfolio drawdown. No production switch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from lectura_espectral import signal_for
from risk_experiment import ATR_MULTIPLE, RISK_FRACTION, CAPITAL, FEE_BPS, SLIPPAGE_BPS, HORIZONS, position_plan


def atr_series(frame):
    prev=frame.Close.shift()
    tr=pd.concat([frame.High-frame.Low,(frame.High-prev).abs(),(frame.Low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()


def observe(frame, spy, signal_day, atr, stop_kind='atr', capital=CAPITAL):
    """ATR from signal close only; quantity calculated at next open including slip."""
    pos=frame.index.searchsorted(pd.Timestamp(signal_day),side='right')
    if pos>=len(frame):return None
    entry_day=frame.index[pos]
    if entry_day not in spy.index:return None
    entry=float(frame.Open.iloc[pos])*(1+SLIPPAGE_BPS/10000)
    plan=position_plan(entry,atr,capital,stop_kind)
    if plan is None:return None
    record={'signal_date':str(pd.Timestamp(signal_day).date()),'entry_date':str(entry_day.date()),**plan}
    spy_entry=float(spy.loc[entry_day,'Open'])*(1+SLIPPAGE_BPS/10000)
    for horizon in HORIZONS:
        end=pos+horizon-1
        if end>=len(frame) or frame.index[end] not in spy.index:
            record[f'return_{horizon}']=record[f'excess_spy_{horizon}']=record[f'r_{horizon}']=None
            continue
        exit_price=float(frame.Close.iloc[end])*(1-SLIPPAGE_BPS/10000)
        ret=(exit_price*(1-FEE_BPS/10000)/(entry*(1+FEE_BPS/10000))-1)*100
        benchmark=(float(spy.loc[frame.index[end],'Close'])*(1-SLIPPAGE_BPS/10000)*(1-FEE_BPS/10000)/(spy_entry*(1+FEE_BPS/10000))-1)*100
        record.update({f'return_{horizon}':ret,f'excess_spy_{horizon}':ret-benchmark,
                       f'r_{horizon}':(exit_price-entry-(entry+exit_price)*FEE_BPS/10000)/plan['risk_per_share']})
    # Require the complete 20-session window, even if a stop happened early:
    # avoids counting early losers while winners remain censored.
    if pos+max(HORIZONS)>len(frame):return record
    exit_pos=pos+max(HORIZONS)-1;raw_exit=float(frame.Close.iloc[exit_pos]);reason='20 ruedas'
    for j in range(pos,exit_pos+1):
        if float(frame.Low.iloc[j])<=plan['stop']:
            exit_pos=j;raw_exit=min(float(frame.Open.iloc[j]),plan['stop']);reason='STOP / GAP';break
    exit_price=raw_exit*(1-SLIPPAGE_BPS/10000)
    pnl=(exit_price-entry-(entry+exit_price)*FEE_BPS/10000)*plan['shares']
    record.update(exit_date=str(frame.index[exit_pos].date()),pnl=pnl,
                  trade_r=pnl/plan['risk_usd'],exit_reason=reason)
    return record


def evaluate(readings, frames, spy, kind):
    rows=[];trades=[]
    for ticker, group in readings.groupby('ticker'):
        frame=frames[ticker];atrs=atr_series(frame);was_buy=False;available='';equity=CAPITAL;peak=equity;dd=0.;streak=worst=0
        for item in group.sort_values('date').itertuples():
            buy=(item.signal if hasattr(item,'signal') else signal_for(item.score,item.deterioration)).startswith('COMPRA')
            new=buy and not was_buy;was_buy=buy
            if not new or pd.Timestamp(item.date) not in atrs.index:continue
            row=observe(frame,spy,item.date,float(atrs.loc[item.date]),kind)
            if row is None:continue
            row['ticker']=ticker;rows.append(row)
            if row['entry_date']<=available or 'trade_r' not in row:continue
            trade=observe(frame,spy,item.date,float(atrs.loc[item.date]),kind,equity)
            # Daily close mark-to-market, with actual proceeds on the exit day.
            path=frame.loc[trade['entry_date']:trade['exit_date']]
            cash=equity-trade['shares']*trade['entry']*(1+FEE_BPS/10000)
            for day,bar in path.iterrows():
                mark=equity+trade['pnl'] if str(day.date())==trade['exit_date'] else cash+trade['shares']*float(bar.Close)
                peak=max(peak,mark);dd=min(dd,(mark/peak-1)*100)
            equity+=trade['pnl']
            streak=streak+1 if trade['pnl']<0 else 0;worst=max(worst,streak);available=trade['exit_date']
            trades.append({**trade,'ticker':ticker,'equity':equity,'drawdown':dd,'worst_streak':worst})
    forward={}
    for h in HORIZONS:
        complete=[r for r in rows if r[f'return_{h}'] is not None]
        forward[str(h)]={'matured':len(complete),'pending':len(rows)-len(complete),
          **{k:float(np.mean([r[f'{k}_{h}'] for r in complete])) if complete else None for k in ('return','excess_spy','r')},
          'win_pct':float(np.mean([r[f'return_{h}']>0 for r in complete])*100) if complete else None}
    return {'signals':len(rows),'forward':forward,'trades':len(trades),
            'win_pct':float(np.mean([t['pnl']>0 for t in trades])*100) if trades else None,
            'mean_r':float(np.mean([t['trade_r'] for t in trades])) if trades else None,
            'worst_ticker_dd':min((t['drawdown'] for t in trades),default=0),
            'worst_ticker_streak':max((t['worst_streak'] for t in trades),default=0)},rows,trades


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--readings',required=True);parser.add_argument('--market',required=True);parser.add_argument('--out',required=True);a=parser.parse_args()
    readings=pd.read_csv(a.readings);frames={k:pd.read_csv(Path(a.market)/(k+'.csv'),index_col=0,parse_dates=True) for k in sorted(set(readings.ticker)|{'SPY'})}
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);report={'production_activated':False,'study':'entry-onset ATR vs fixed 6% / 8%', 'engine':'active' if 'signal' in readings else 'spectral',
    'risk_fraction':RISK_FRACTION,'atr_multiple':ATR_MULTIPLE,'horizons':HORIZONS,'fee_bps':FEE_BPS,'slippage_bps':SLIPPAGE_BPS,
    'last_data':str(min(f.index[-1] for f in frames.values()).date()),
    'input_sha256':hashlib.sha256(Path(a.readings).read_bytes()).hexdigest(),'results':{}}
    lines=['# Señales '+report['engine']+': riesgo ATR vs stops fijos','', 'Entradas nuevas al open siguiente; 0,5% de riesgo máximo, sin solapamiento por ticker en el ensayo de operaciones. Retornos forward sí pueden solaparse.','', '| Stop | Operaciones | Acierto | R medio | Peor DD individual | Peor racha |','|---|---:|---:|---:|---:|---:|']
    for kind in ('fixed6','fixed8','atr'):
        stats,rows,trades=evaluate(readings,frames,frames['SPY'],kind);report['results'][kind]=stats
        pd.DataFrame(rows).to_csv(out/f'{kind}-signals.csv',index=False);pd.DataFrame(trades).to_csv(out/f'{kind}-trades.csv',index=False)
        lines.append(f"| {kind} | {stats['trades']} | {stats['win_pct']:.2f}% | {stats['mean_r']:.3f} | {stats['worst_ticker_dd']:.2f}% | {stats['worst_ticker_streak']} |")
    lines+=['','## Señal sin stop: retorno al cierre de cada horizonte (costos incluidos)','','| Ruedas | Señales maduras | Pendientes | Retorno medio | Exceso vs SPY | R medio ATR |','|---|---:|---:|---:|---:|---:|']
    for h,v in report['results']['atr']['forward'].items():lines.append(f"| {h} | {v['matured']} | {v['pending']} | {v['return']:.2f}% | {v['excess_spy']:.2f} pp | {v['r']:.3f} |")
    lines+=['','Muestra de conveniencia de 10 activos, incluye apalancados, sesgo de supervivencia y señales correlacionadas. No hay calendario histórico de balances. Parámetros iniciales, sin calibración OOS. 30 señales permiten una primera descripción, no validan una estrategia. El DD usa marcas a cierre diario y corresponde a carteras individuales, no a una cartera conjunta. Riesgo máximo nominal: los gaps pueden superarlo. No activa el motor ni modifica el ledger.']
    (out/'study.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False));(out/'study.md').write_text('\n'.join(lines))
    print('\n'.join(lines))

if __name__=='__main__':main()
