"""La papa está en el piso: radar EXPERIMENTAL contra-tendencia, NO órdenes.

Parámetros explícitos y auditables. No es señal de compra del motor de
tendencia ni alimenta ledger USD 2000. Histórico earnings carece de calendario.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import math
import numpy as np
import pandas as pd
from actualizar import rsi,macd_hist

RULES_VERSION="rebound-0.1-experimental"
PAPER_REBOUND=False       # Flag separado; el simulador vigente nunca lo importa.
HIGH_RISK_LABEL="ALTO RIESGO · CONTRA-TENDENCIA"
EXCLUDED_LEVERAGED_INVERSE={"TQQQ","SQQQ","SOXL","SOXS","SPXL","SPXS","UPRO",
    "SPXU","TNA","TZA","LABU","LABD","SRTY","SDS","QID","SH","PSQ"}

@dataclass(frozen=True)
class ReboundParams:
    rsi_max:float=30.0
    rsi_extreme:float=25.0
    bb_period:int=20
    bb_sd:float=2.0
    atr_period:int=14
    stretch_atr:float=2.5
    drawdown_from_high:float=.18
    lookback_high:int=60
    rvol_min:float=1.2
    dollar_volume_min:float=5_000_000
    reversal_close_location:float=2/3
    stop_atr:float=1.7
    stop_offset_atr:float=.08
    min_rr:float=2.0
    time_stop_sessions:int=7
    max_rows:int=8
    size_frac:float=.10        # 10% paper teórico, una sola entrada.
PARAMS=ReboundParams()


def indicators(f:pd.DataFrame,p:ReboundParams=PARAMS)->dict|None:
    f=f.copy().sort_index().dropna(subset=["Open","High","Low","Close","Volume"])
    if len(f)<max(p.lookback_high,p.bb_period,p.atr_period)+22:return None
    c=f["Close"].astype(float)
    hi=f["High"].astype(float)
    lo=f["Low"].astype(float)
    vol=f["Volume"].astype(float)
    if (c<=0).any() or (hi<lo).any() or (vol<0).any():return None
    prev=c.shift()
    tr=pd.concat([(hi-lo).abs(),(hi-prev).abs(),(lo-prev).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(p.atr_period,min_periods=p.atr_period).mean().iloc[-1])
    if not math.isfinite(atr) or atr<=0:return None
    ma21=float(c.tail(21).mean())
    ma10=float(c.tail(10).mean())
    ma200=float(c.tail(200).mean()) if len(c)>=200 else None
    mean=c.rolling(p.bb_period,min_periods=p.bb_period).mean()
    dev=c.rolling(p.bb_period,min_periods=p.bb_period).std(ddof=0)
    bb_lower=float((mean-p.bb_sd*dev).iloc[-1])
    r=rsi(c,14)
    macd=macd_hist(c)
    if not all(math.isfinite(float(x)) for x in
               (r.iloc[-1],r.iloc[-2],macd.iloc[-1],macd.iloc[-2],macd.iloc[-3])):
        return None
    high_recent=float(hi.iloc[-p.lookback_high:].max())
    low_recent=float(lo.iloc[-p.lookback_high:].min())
    day_high=float(hi.iloc[-1])
    day_low=float(lo.iloc[-1])
    day_close=float(c.iloc[-1])
    day_open=float(f["Open"].iloc[-1])
    position=(day_close-day_low)/max(.00001,day_high-day_low)
    vbase=float(vol.iloc[-21:-1].mean())
    rvol=float(vol.iloc[-1]/vbase) if vbase>0 else 0.
    climax=(max(vol.iloc[-4:-1])/max(vbase,1)>=1.8 and
            vol.iloc[-1]<vol.iloc[-2] and
            vol.iloc[-2]<max(vol.iloc[-4:-2]))
    div=False
    if len(c)>20:
        former=int(np.argmin(lo.iloc[-20:-5].to_numpy()))
        old_idx=len(c)-20+former
        div=(day_low<float(lo.iloc[old_idx]) and
             float(r.iloc[-1])>float(r.iloc[old_idx])+1.5)
    return {
        "day":str(f.index[-1].date()),"price":day_close,"open":day_open,
        "low":day_low,"high":day_high,"ma10":ma10,"ma21":ma21,
        "ma200":ma200,"atr":atr,"bb_lower":bb_lower,
        "rsi":float(r.iloc[-1]),"rsi_delta":float(r.iloc[-1]-r.iloc[-2]),
        "macd_hist":float(macd.iloc[-1]),
        "macd_improving":bool(macd.iloc[-1]>macd.iloc[-2]>macd.iloc[-3]),
        "drawdown_pct":100*(high_recent-day_close)/high_recent,
        "distance_atr":(day_close-ma21)/atr,
        "range_position":position,"green_body":day_close>day_open,
        "rvol":rvol,"climax_drying":bool(climax),
        "dollar_volume20":vbase*day_close,
        "recent_high":high_recent,"recent_low":low_recent,
        "divergence":bool(div)}


def proposed_trade(x:dict,p:ReboundParams=PARAMS)->dict|None:
    close=x["price"]
    stop=min(x["low"]-p.stop_offset_atr*x["atr"],
             close-p.stop_atr*x["atr"])
    risk=close-stop
    if risk<=0 or risk>2.7*x["atr"]:return None
    # Resistencias objetivas conocidas al cierre: SMA10/SMA21 y retrocesos
    # del rango reciente. No inventar target exacto si RR<2.
    span=x["recent_high"]-x["recent_low"]
    targets={"SMA10":x["ma10"],"SMA21":x["ma21"],
             "FIB 38.2":x["recent_low"]+.382*span,
             "FIB 50":x["recent_low"]+.5*span}
    candidates=sorted([(value,key) for key,value in targets.items()
                       if value>close and (value-close)/risk>=p.min_rr])
    if not candidates:return None
    target,kind=candidates[0]     # La primera resistencia con RR>=2.
    return {"entry_ref":round(close,3),"stop_usd":round(stop,3),
            "target_usd":round(target,3),"target_type":kind,
            "rr":round((target-close)/risk,2),
            "risk_usd_per_share":round(risk,3)}


def candidate(f:pd.Data,ticker:str,earnings:dict|None=None,
              p:ReboundParams=PARAMS)->dict|None:
    if ticker.upper() in EXCLUDED_LEVERAGED_INVERSE:return None
    x=indicators(f,p)
    if x is None:return None
    if x["rsi"]>p.rsi_max:return None
    extended=(x["price"]<=x["bb_lower"] or x["distance_atr"]<=-p.stretch_atr
              or x["drawdown_pct"]>=100*p.drawdown_from_high)
    if not extended:return None
    # No comprar cuchillos cayendo: AL MENOS estas tres pruebas de giro.
    if not(x["rsi_delta"]>0 and x["macd_improving"]
           and x["range_position"]>=p.reversal_close_location
           and x["green_body"]):return None
    if not(x["rvol"]>=p.rvol_min or x["climax_drying"]):return None
    if x["dollar_volume20"]<p.dollar_volume_min:return None
    days=(earnings or {}).get("days_until")
    if isinstance(days,(int,float)) and 0<=days<=7:return None
    trade=proposed_trade(x,p)
    if trade is None:return None
    stretched=max(0.,-x["distance_atr"]-1.5)
    oversold=max(0.,p.rsi_max-x["rsi"])
    # Score INDEPENDIENTE de Score Oportunidad de tendencia.
    score=min(100,25+min(22,oversold*2)+min(18,stretched*6)
                 +min(15,max(0.,x["drawdown_pct"]-12)*.9)
                 +min(10,x["rsi_delta"]*2)
                 +min(7,max(0,x["rvol"]-1)*5)
                 +(3 if x["divergence"] else 0))
    earnings_status=("SIN BALANCE CERCANO CONOCIDO · FECHA INDICATIVA"
                     if earnings is not None else
                     "FECHA DE BALANCE NO VERIFICADA")
    category=("CAPITULACIÓN · BAJO SMA200" if x["ma200"] is None or
              x["price"]<x["ma200"] else "PULLBACK PROFUNDO · SOBRE SMA200")
    return {"ticker":ticker,"signal_date":x["day"],
            "rebound_score":round(score,1),
            "price":round(x["price"],3),"drop_from_high_pct":round(x["drawdown_pct"],1),
            "rsi14":round(x["rsi"],1),"distance_atr":round(x["distance_atr"],2),
            "rvol20":round(x["rvol"],2),
            "turn_signal":("RSI ↑ / MACD 3 BARRAS ↑ / VELA REVERSIÓN "+
                           ("+ DIVERGENCIA" if x["divergence"] else "")),
            **trade,"earnings":earnings,"earnings_status":earnings_status,
            "risk_label":HIGH_RISK_LABEL,"structure":category,
            "time_stop_sessions":p.time_stop_sessions,
            "entry_tranches":[100],"paper_rebound":PAPER_REBOUND,
            "rules_version":RULES_VERSION}


def scan_rebounds(catalog:list[dict],frames:dict[str,pd.DataFrame],
                  earnings_dates:dict,now,p:ReboundParams=PARAMS,
                  technical:dict|None=None)->list[dict]:
    # Clasificación de acciones del catálogo, no ETFs, apalancados o inversos.
    from actualizar import last_complete_daily,SECTORS
    # Los subyacentes para la papa son sólo acciones, nunca fondos/ETF.
    etfs=set(SECTORS.values())|{"SPY","QQQ","GLD","SLV","IBIT","ETHA",
        "COPX","URA","URNM","ARKK","XBI","IBB","TAN","LIT","EEM",
        "EWZ","EWJ","IWM","DIA","TLT","HYG","BND","DBA","CORN"}
    chosen=[]
    seen=set()
    for item in catalog:
        if item.get("sector")=="Índices y ETFs":continue
        sym=item.get("subyacente_usa","").upper().strip()
        if not sym or sym in seen or sym in EXCLUDED_LEVERAGED_INVERSE or sym in etfs:continue
        if technical is not None and (technical.get(sym) or {}).get("asset_kind")!="ACCION":continue
        seen.add(sym)
        frame=frames.get(sym)
        if frame is None:continue
        try:
            trade=candidate(last_complete_daily(frame,now),sym,earnings_dates.get(sym),p)
        except (ValueError,KeyError,IndexError,TypeError,OverflowError):
            continue
        if trade:
            trade["cedear"]=item["cedear"]
            chosen.append(trade)
    chosen.sort(key=lambda x:(-x["rebound_score"],-x["rr"],x["ticker"]))
    return chosen[:p.max_rows]
