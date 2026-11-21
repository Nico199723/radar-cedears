"""Hourly observations, explicitly provisional. Never writes the paper ledger."""
from copy import deepcopy
import json, logging
import pandas as pd
from lectura_espectral import story, macro_wind, normalized_macro
from decision_engine import decide, audit_consistency, top_five_by_decision
from presentation import methodology
from risk_experiment import position_plan
NY='America/New_York'
MAX_AGE_MINUTES=75

def utc(t):
    t = pd.Timestamp(t)
    if t.tzinfo is None:
        raise ValueError('Timestamp sin zona horaria')
    return t.tz_convert('UTC')


def closed_bars(frame, asof):
    if frame is None or frame.empty:
        return pd.DataFrame()
    f = frame.copy()
    if f.index.tz is None:
        raise ValueError('Barras intradiarias sin zona horaria')
    f.index = f.index.tz_convert('UTC')
    f = f[~f.index.duplicated(keep='last')].sort_index()
    local = f.index.tz_convert(NY)
    minutes = local.hour*60+local.minute
    # Yahoo 1h: barras 09:30..15:30; última barra regular dura 30 minutos.
    ends = f.index + pd.to_timedelta([30 if m == 930 else 60 for m in minutes], unit='m')
    mask = (minutes >= 570) & (minutes <= 930) & (local.minute == 30) & (local.dayofweek < 5) & (ends <= utc(asof))
    f = f.loc[mask].copy()
    f['bar_end'] = ends[mask]
    valid = f[['Open','High','Low','Close','Volume']].apply(pd.to_numeric,errors='coerce')
    mask = valid.notna().all(axis=1) & (valid[['Open','High','Low','Close']]>0).all(axis=1) & (valid.Volume>=0)
    mask &= (valid.High >= valid[['Open','Close','Low']].max(axis=1)) & (valid.Low <= valid[['Open','Close','High']].min(axis=1))
    return f.loc[mask]


def partial_daily(daily, hourly, asof):
    """Jamás usa OHLC diario del día observado ni datos posteriores."""
    now = utc(asof)
    today = now.tz_convert(NY).date()
    f = daily.copy()
    if f.index.tz is not None:
        f.index = f.index.tz_convert(NY).tz_localize(None)
    f = f.loc[f.index.date < today]
    if f.empty or (today-f.index[-1].date()).days>5:return None
    bars = closed_bars(hourly, now)
    bars = bars.loc[bars.index.tz_convert(NY).date == today] if not bars.empty else bars
    if bars.empty or now-bars.bar_end.iloc[-1] > pd.Timedelta(minutes=MAX_AGE_MINUTES):
        return None
    # Exigir apertura y secuencia completa; un hueco no equivale a volumen cero.
    start = pd.Timestamp(str(today)+' 09:30',tz=NY).tz_convert('UTC')
    expected = pd.date_range(start,bars.index[-1],freq='h')
    if not bars.index.equals(expected):
        return None
    f.loc[pd.Timestamp(today), ['Open','High','Low','Close','Volume']] = [
        bars.Open.iloc[0],bars.High.max(),bars.Low.min(),bars.Close.iloc[-1],bars.Volume.sum()]
    return f



def snapshot(base, daily, hourly, asof):
    from actualizar import compute, ETF_SYMBOLS
    now=utc(asof);frames={}
    for sym,frame in daily.items():
        partial=partial_daily(frame,hourly.get(sym),now)
        if partial is not None:frames[sym]=partial
    s,q,v=(frames.get(k) for k in ('SPY','QQQ','^VIX'))
    wind=normalized_macro(macro_wind(s,q,v.Close) if all(f is not None for f in (s,q,v)) else None)
    bench=s.Close if s is not None else None
    result=deepcopy(base)
    for collection in ('assets','sectors'):
        for asset in result.get(collection,[]):
            sym=asset.get('usa',asset.get('proxy'));f=frames.get(sym)
            row=compute(f,now.to_pydatetime(),is_stock=sym not in ETF_SYMBOLS,
                        spy_close=bench,qqq_close=None if q is None else q.Close,provisional=True) if f is not None else None
            facts=story(f,bench)
            # A Friday in progress must not enter the weekly indicator.
            if facts is not None and now.tz_convert(NY).hour<16:
                closed=story(f.iloc[:-1],bench)
                for key in ('macd_hist_w_n','macd_slope_w_n'):facts[key]=closed[key] if closed else None
            row=row or {};row['_spectrum_story']=facts
            decision=decide(row,'',None,f is not None,asset.get('earnings'),mode='spectrum',wind=wind).public()
            asset.update(decision,data=row,provisional=True,observed_at=now.isoformat(),
                         quote_at=closed_bars(hourly[sym],now).bar_end.iloc[-1].isoformat() if f is not None else None,
                         candidate={'level':decision.get('stage'),'blockers':[]},risk_plan_paper=None,decision_v2_preview=None)
            if facts:row['atr_risk_preview']=position_plan(facts['price'],facts['atr14'])
    errors=audit_consistency(result['assets']+result.get('sectors',[]),mode='spectrum')
    if errors:raise ValueError(errors)
    result['top5']=top_five_by_decision(result['assets'],mode='spectrum')
    result['rebounds']=[]
    result['macro']={'state':wind['label'],'vix':wind.get('vix'),'spectrum':wind}
    result['meta'].update(methodology=methodology(True),provisional=True,
        generated_at_utc=now.isoformat(),generated_at_ar=now.tz_convert('America/Argentina/Buenos_Aires').isoformat(),
        observed_at=now.isoformat(),rules_version='3.0-spectrum-intraday-candidate',
        volume_basis='Volumen acumulado real, sin extrapolar',intraday_coverage=len(frames),
        note='Última barra horaria cerrada; vela diaria en formación. No opera el simulador.')
    return result


def publish_provisional(base,daily,now,path):
    local=utc(now).tz_convert(NY)
    unavailable={'meta':{'provisional':True,'unavailable':True,'generated_at_utc':utc(now).isoformat()},'assets':[],'sectors':[],'top5':[]}
    # No fake intraday observations outside regular hours; preserve daily view.
    result=unavailable
    if local.dayofweek<5 and 10*60+30<=local.hour*60+local.minute<=16*60+15:
        try:
            import yfinance as yf
            symbols=sorted(daily);hourly={}
            for start in range(0,len(symbols),25):
                batch=symbols[start:start+25]
                data=yf.download(batch,period='5d',interval='1h',group_by='ticker',auto_adjust=True,threads=4,progress=False,timeout=15)
                for sym in batch:
                    if isinstance(data.columns,pd.MultiIndex) and sym in data.columns.get_level_values(0):hourly[sym]=data[sym].dropna()
            result=snapshot(base,daily,hourly,now)
        except Exception as exc:
            logging.warning('Vista provisional no disponible: %s',exc)
    path.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
