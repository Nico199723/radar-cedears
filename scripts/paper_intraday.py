"""One existing ledger, daily eligibility, forward execution on closed 15m bars.

No intraday score and no retrospective signals. Daily closes are not reprocessed
once migrated. Missing feeds never turn into fictitious fills or cash resets.
"""
from copy import deepcopy
import logging
import math
import pandas as pd
from decision_engine import BUY_SIGNALS, RULES_VERSION, decide
from paper_sim import (check_ledger, open_tranche, close_position, sell_fraction,
                       mark_stop, public_summary, MAX_SESSION_HOLD)
from radar_features import risk_policy

VERSION='paper-15m-v1'
NY='America/New_York'
STEP=pd.Timedelta(minutes=15)
MAX_AGE=pd.Timedelta(minutes=40)


def utc(value):
    t=pd.Timestamp(value)
    if t.tzinfo is None:raise ValueError('Timestamp sin zona horaria')
    return t.tz_convert('UTC')


def bars(frame, now):
    if frame is None or frame.empty:return pd.DataFrame()
    f=frame.copy()
    if f.index.tz is None:raise ValueError('Velas sin zona horaria')
    f.index=f.index.tz_convert('UTC')
    f=f[~f.index.duplicated(keep='last')].sort_index()
    local=f.index.tz_convert(NY);minute=local.hour*60+local.minute
    mask=(minute>=570)&(minute<960)&(local.minute%15==0)&(local.dayofweek<5)&(f.index+STEP<=utc(now))
    f=f.loc[mask]
    f=f[['Open','High','Low','Close','Volume']].apply(pd.to_numeric,errors='coerce')
    good=f.notna().all(axis=1)&f.map(lambda v:math.isfinite(v)).all(axis=1)
    good &= (f[['Open','High','Low','Close']]>0).all(axis=1)&(f.Volume>=0)
    good &= (f.High>=f[['Open','Close','Low']].max(axis=1))&(f.Low<=f[['Open','Close','High']].min(axis=1))
    return f.loc[good]


def download(symbols):
    import yfinance as yf
    result={}
    for off in range(0,len(symbols),15):
        subset=symbols[off:off+15]
        try:
            raw=yf.download(subset,period='5d',interval='15m',group_by='ticker',auto_adjust=True,
                            prepost=False,threads=4,progress=False,timeout=20)
            if raw is None or raw.empty:continue
            for sym in subset:
                try:result[sym]=raw[sym].copy() if isinstance(raw.columns,pd.MultiIndex) else raw.copy()
                except KeyError:continue
        except Exception as exc:logging.warning('Datos 15m no disponibles: %s',exc)
    return result


def symbols_for(state,assets):
    eligible=sorted((a for a in assets if a.get('usa') and a.get('signal') in BUY_SIGNALS),
                    key=lambda a:-(a.get('score_decision') or 0))[:20]
    return sorted({'SPY'}|set(state['positions'])|{o['usa'] for o in state['orders']}|{a['usa'] for a in eligible})


def migrate(state,now):
    s=deepcopy(state);check_ledger(s)
    if s.get('execution_mode')==VERSION:return s
    if s.get('execution_mode'):raise ValueError('Modo de ejecución incompatible; no reiniciar')
    stamp=utc(now).isoformat()
    s.update(execution_mode=VERSION,intraday_started_at=stamp,last_observed_at=stamp,
             bar_cursors={},intraday_equity=[],intraday_peak=max([2000]+[x['equity'] for x in s['equity_history']]),intraday_dd=0,
             last_daily_session=s['last_session'])
    for o in s['orders']:o.update(issued_at=stamp,decision_rules_version=RULES_VERSION)
    return s


def process(state,frames,assets,macro,vix,latest_day,now,daily_frames=None):
    first=not state.get('execution_mode')
    now=utc(now);s=migrate(state,now)
    if first:
        current={a.get('usa'):a for a in assets}
        retained=[]
        for o in s['orders']:
            a=current.get(o['usa'],{});d=a.get('data') or {}
            valid=d.get('date')==latest_day and decide(d,macro,vix,True,a.get('earnings')).signal in BUY_SIGNALS
            if o['side']=='BUY' and not valid:
                s['cancelled'].append({'date':str(now.date()),'usa':o['usa'],'reason':'Compra pendiente sin señal vigente al migrar'})
            else:retained.append(o)
        s['orders']=retained
    if now<utc(s['last_observed_at']):return s
    prepared={}
    for sym,frame in frames.items():
        try:prepared[sym]=bars(frame,now)
        except (ValueError,KeyError,TypeError):continue
    spy=prepared.get('SPY',pd.DataFrame())
    today=str(now.tz_convert(NY).date())
    fresh_market=not spy.empty and str(spy.index[-1].tz_convert(NY).date())==today and now-(spy.index[-1]+STEP)<=MAX_AGE
    held=set(s['positions'])|{o['usa'] for o in s['orders']}
    blocked=set();events=[]
    for sym in held:
        f=prepared.get(sym,pd.DataFrame());cursor=utc(s['bar_cursors'].get(sym,s['intraday_started_at']))
        if spy.empty:blocked.add(sym);continue
        expected=[]
        for session,group in spy.groupby(spy.index.tz_convert(NY).date):
            opening=pd.Timestamp(str(session)+' 09:30',tz=NY).tz_convert('UTC')
            expected.extend(ts for ts in pd.date_range(opening,group.index[-1],freq='15min') if ts>cursor)
        # A cursor older than the download window cannot be recovered safely.
        if not spy.empty and cursor<spy.index[0]-pd.Timedelta(days=4):blocked.add(sym);continue
        for ts in expected:
            if ts not in spy.index or ts not in f.index:blocked.add(sym);break
            events.append((ts,sym,f.loc[ts]))
    for ts,sym,bar in sorted(events,key=lambda e:(e[0],0 if any(o['usa']==e[1] and o['side']=='SELL' for o in s['orders']) else 1,e[1])):
        day=str(ts.tz_convert(NY).date());end=ts+STEP
        # Apply only prior completed daily closes before testing this bar's low.
        p=s['positions'].get(sym);daily=(daily_frames or {}).get(sym)
        if p and daily is not None:
            from paper_sim import session_frame
            closes=session_frame(daily)['Close'].dropna()
            closes=closes.loc[(closes.index.date<pd.Timestamp(day).date()) & (closes.index.date>=pd.Timestamp(p['entry_date']).date())]
            since=p.get('last_trailing_session',s['last_daily_session'])
            for when,price in closes.items():
                session=str(when.date())
                if session>since:
                    mark_stop(p,float(price));p['last_trailing_session']=session
        for order in list(s['orders']):
            if order['usa']!=sym or ts<=utc(order['issued_at']):continue
            s['orders'].remove(order)
            if order['side']=='BUY' and ts-utc(order['issued_at'])>pd.Timedelta(hours=24):
                s['cancelled'].append({'date':day,'usa':sym,'reason':'Orden 15m vencida'});continue
            n=len(s['fills'])
            if order['side']=='BUY':
                ok=open_tranche(s,order,day,float(bar.Open))
                if not ok:s['cancelled'].append({'date':day,'usa':sym,'reason':'Límites de efectivo, tramos o concentración'})
            elif sym in s['positions']:
                p=s['positions'][sym];gap=float(bar.Open)<=p['stop_usd']
                sell_fraction(s,sym,day,float(bar.Open),'STOP / GAP' if gap else order['reason'],1. if gap else order.get('fraction',1.))
            for fill in s['fills'][n:]:fill.update(timestamp=ts.isoformat(),signal_timestamp=order['issued_at'],execution_version=VERSION,decision_rules_version=order.get('decision_rules_version'))
        if sym in s['positions']:
            p=s['positions'][sym]
            if p.get('counted_intraday_session')!=day:
                p['sessions_held']+=1;p['counted_intraday_session']=day
            if float(bar.Low)<=p['stop_usd']:
                n=len(s['fills']);close_position(s,sym,day,min(float(bar.Open),p['stop_usd']),'STOP LOSS / VELA 15m')
                for fill in s['fills'][n:]:fill.update(timestamp=end.isoformat(),execution_window_start=ts.isoformat(),timestamp_precision='bar_end',execution_version=VERSION)
            else:
                p.update(last_mark=float(bar.Close),last_mark_day=day,last_mark_at=end.isoformat())
                # Preserve the daily trailing rule: intraday low tests the last known stop.
        s['bar_cursors'][sym]=ts.isoformat()
    # Daily trailing update only after a complete daily close, never from its prior intraday lows.
    if latest_day>s.get('last_daily_session',''):
        for a in assets:
            p=s['positions'].get(a.get('usa'));d=a.get('data') or {}
            if p and d.get('date')==latest_day and d.get('price'):
                mark_stop(p,float(d['price']));p['last_trailing_session']=latest_day
        s['last_daily_session']=latest_day
    # Discard expired buys even when their symbol has no new quotes.
    retained=[]
    for o in s['orders']:
        if o['side']=='BUY' and now-utc(o['issued_at'])>pd.Timedelta(hours=24):
            s['cancelled'].append({'date':today,'usa':o['usa'],'reason':'Orden 15m vencida sin ejecución'})
        else:retained.append(o)
    s['orders']=retained
    policy=risk_policy(macro,vix)
    snapshot_ok=latest_day>=s.get('last_daily_session','') and 0<=(now.tz_convert(NY).date()-pd.Timestamp(latest_day).date()).days<=5
    if fresh_market and snapshot_ok:
        pending={o['usa'] for o in s['orders']}
        for a in sorted(assets,key=lambda a:-(a.get('score_decision') or 0)):
            sym=a.get('usa');d=a.get('data') or {};f=prepared.get(sym,pd.DataFrame())
            if not sym or sym in pending or sym in blocked or f.empty or d.get('date')!=latest_day:continue
            if f.index[-1]!=spy.index[-1]:continue
            p=s['positions'].get(sym);px=float(f.Close.iloc[-1]);decision=decide(d,macro,vix,True,a.get('earnings'))
            base={'usa':sym,'ticker':a['ticker'],'sector':a.get('sector',''), 'issued_day':today,
                  'issued_at':now.isoformat(),'decision_rules_version':RULES_VERSION}
            reason=None;fraction=1.
            if p:
                avg=p['spent']/p['shares']
                down2=False
                daily=(daily_frames or {}).get(sym)
                if daily is not None:
                    from paper_sim import session_frame
                    c=session_frame(daily).loc[:latest_day,'Close']
                    down2=len(c)>=23 and c.iloc[-1]<d.get('ma21',0) and c.iloc[-2]<float(c.iloc[-22:-1].mean()) and (d.get('macd_hist_d') or 0)<0
                if decision.signal.startswith('SALIR'):reason='SALIR TOTAL: RUPTURA ESTRUCTURAL'
                elif decision.signal.startswith('REDUCIR') and not p.get('reduction_taken'):reason='REDUCIR 50% POR DETERIORO TÉCNICO';fraction=.5
                elif down2 and not p.get('reduction_taken'):reason='DEBILIDAD: 2 CIERRES BAJO SMA21 Y MACD NEGATIVO';fraction=.5
                elif not p.get('profit_taken') and px>=avg*(1+2*p['stop_pct']):reason='OBJETIVO 2R: TOMAR GANANCIA EN 50%';fraction=.5
                elif p['sessions_held']>=MAX_SESSION_HOLD and px<avg*1.03:reason='SALIR TOTAL POR TIEMPO'
            if reason:
                s['orders'].append({**base,'side':'SELL','fraction':fraction,'reason':reason});pending.add(sym);continue
            if decision.signal not in BUY_SIGNALS or policy['max_position_usd']<=0:continue
            # Keep three tranches and at most one purchase per symbol per session.
            if p and (p.get('exit_started') or p['tranche_count']>=3 or p['last_fill_day']==today):continue
            # Don't churn back into a position stopped out earlier in this session.
            if not p and any(t['usa']==sym and t['exit_date']==today for t in s['closed_trades']):continue
            stage=p['tranche_count']+1 if p else 1
            if p and not (px>d.get('ma21',math.inf) and (d.get('macd_hist_d') or 0)>0 and ((stage==2 and (d.get('rvol20') or 0)>=.75) or (stage==3 and px>avg*1.02 and d.get('obv_up10') is True))):continue
            caution=decision.signal=='COMPRA CON PRECAUCIÓN';prudent=caution or policy['mode']=='PRUDENTE'
            leveraged=sym in {'TQQQ','SQQQ','SPXL','SOXL','SOXS','UPRO','SPXU'}
            budget=min(policy['max_position_usd'],60 if prudent else 120) if leveraged else min(policy['max_position_usd'],120) if prudent else policy['max_position_usd']
            reserve=max(policy['reserve_usd'],1600 if prudent else 1200) if leveraged else max(policy['reserve_usd'],1400) if prudent else policy['reserve_usd']
            slots=min(policy['max_positions'],2) if caution else policy['max_positions']
            sector_limit=min(policy['max_per_sector'],1) if caution else policy['max_per_sector']
            exposure=list(s['positions'].values())+[o for o in s['orders'] if o['side']=='BUY' and o['usa'] not in s['positions']]
            if not p and (len(exposure)>=slots or sum(x.get('sector')==a.get('sector') for x in exposure)>=sector_limit):continue
            if s['cash']-reserve<10:continue
            if not p:s['bar_cursors'][sym]=now.isoformat()
            s['orders'].append({**base,'side':'BUY','tranche':stage,'budget':p['budget'] if p else budget,
                'reserve_usd':reserve,'stop_pct':(.05 if prudent else .06) if leveraged else (.06 if prudent else policy['stop_pct']/100),
                'max_positions':slots,'max_per_sector':sector_limit,'risk_mode':'PRUDENTE' if prudent else policy['mode'],
                'reason':'SEÑAL DIARIA VIGENTE / EJECUCIÓN 15m · '+decision.signal})
            pending.add(sym)
    if not spy.empty:
        s['last_session']=max(s['last_session'],str(spy.index[-1].tz_convert(NY).date()))
    s['last_observed_at']=now.isoformat()
    s['intraday_status']='Velas recientes disponibles' if fresh_market else 'Sin velas recientes de la rueda: no se generan entradas'
    s['intraday_unpriced']=sorted(blocked|{sym for sym,p in s['positions'].items() if not p.get('last_mark_at') or now-utc(p['last_mark_at'])>MAX_AGE})
    equity=s['cash']+sum(p['shares']*p.get('last_mark',p['spent']/p['shares']) for p in s['positions'].values())
    peak=max(float(s.get('intraday_peak') or 2000),equity);s['intraday_peak']=peak
    s['intraday_dd']=min(s.get('intraday_dd',0),(equity/peak-1)*100)
    if fresh_market and not s['intraday_unpriced']:
        stamp=max(spy.index[-1]+STEP,utc(s['intraday_started_at'])).isoformat()
        point={'date':stamp,'equity':round(equity,2),'cash':round(s['cash'],2)}
        if s['intraday_equity'] and s['intraday_equity'][-1]['date']==stamp:s['intraday_equity'][-1]=point
        elif not s['intraday_equity'] or stamp>s['intraday_equity'][-1]['date']:s['intraday_equity'].append(point)
        s['intraday_equity']=s['intraday_equity'][-500:]
    check_ledger(s)
    return s


def summary(state):
    result=public_summary(state,{})
    result.update(execution_mode=VERSION,observed_at=state['last_observed_at'],
                  valued_at=state['intraday_equity'][-1]['date'] if state['intraday_equity'] else None,
                  intraday_status=state['intraday_status'],intraday_started_at=state['intraday_started_at'],
                  intraday_equity=state['intraday_equity'],unpriced_symbols=state['intraday_unpriced'])
    result['equity_history']=state['equity_history']+state['intraday_equity']
    result['max_drawdown_pct']=min(result['max_drawdown_pct'],round(state['intraday_dd'],2))
    result['assumptions']['entry_rule']='Elegibilidad diaria del motor único; apertura de vela 15m posterior a la observación'
    return result
