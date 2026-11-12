"""Volumen, entradas prudentes y ranking informativo de subyacentes USA.

NO accede a cuentas/brokers ni convierte precios CEDEAR. Las reglas nuevas deben
compararse en backtest antes de entrar en producción como señales operativas.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def cap(x, a, b):
    return min(b, max(a, x))


def relative_strength(close: pd.Series, spy: pd.Series | None,
                      qqq: pd.Series | None, period: int = 20) -> dict:
    """Exceso de retorno de 20 ruedas sobre SPY/QQQ con fechas comunes.

    Sólo hay RS verificada si los tres activos tienen cierre en la fecha t.
    Se usan t y t-20 de la intersección pasada; nunca precios posteriores.
    """
    empty={"rs_spy20":None,"rs_qqq20":None,"rs_score":None,
           "rs_verified":False}
    if spy is None or qqq is None or close is None:
        return empty
    frames=[]
    for series in (close,spy,qqq):
        s=pd.to_numeric(series,errors="coerce").copy()
        s.index=pd.to_datetime(s.index)
        if s.index.tz is not None:
            s.index=s.index.tz_convert("America/New_York").tz_localize(None)
        s.index=s.index.normalize()
        s=s[~s.index.duplicated(keep="last")].sort_index()
        frames.append(s)
    current=frames[0].index[-1] if len(frames[0]) else None
    if current is None:return empty
    common=pd.concat(frames,axis=1,join="inner",keys=["asset","spy","qqq"]).dropna()
    common=common.loc[:current]
    if len(common)<period+1 or common.index[-1]!=current:
        return empty
    for col in common.columns:
        if not (common[col].iloc[-1]>0 and common[col].iloc[-period-1]>0):
            return empty
    rets=(common.iloc[-1]/common.iloc[-period-1]-1)*100
    excess_spy=float(rets.iloc[0]-rets.iloc[1])
    excess_qqq=float(rets.iloc[0]-rets.iloc[2])
    avg=(excess_spy+excess_qqq)/2
    # 50 = rendimiento similar a índices, ventaja sostenida suma puntos.
    # Superar SPY pero rezagar mucho a QQQ no se considera liderazgo pleno.
    score=cap(50+3*avg+max(-20,min(20,1.5*min(excess_spy,excess_qqq))),0,100)
    return {"rs_spy20":round(excess_spy,2),"rs_qqq20":round(excess_qqq,2),
            "rs_score":round(score,2),"rs_verified":True}


def volume_profile(frame: pd.DataFrame) -> dict:
    """Indicadores al cierre t. RVOL usa las 20 sesiones ANTERIORES."""
    v = frame["Volume"].astype(float)
    c = frame["Close"].astype(float)
    h, l = frame["High"].astype(float), frame["Low"].astype(float)
    if len(frame) < 40 or v.iloc[-21:].isna().any() or not (v.iloc[-21:] >= 0).all():
        return {"rvol20": None, "dollar_volume20": None, "obv_up10": None,
                "atr14": None, "stretch_atr20": None, "volume_score": None, "volume_confirm_score": None}
    base = float(v.iloc[-21:-1].mean())
    rvol = float(v.iloc[-1] / base) if base > 0 else None
    dv = float((c.tail(20) * v.tail(20)).mean())
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    obv_up = bool(obv.iloc[-1] > obv.iloc[-11])
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()],axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1])
    ma20 = float(c.tail(20).mean())
    extension = (float(c.iloc[-1])-ma20)/atr if atr>0 else None
    volume_score = cap(5 + cap((rvol - 1) * 5, -3, 3) + (2 if obv_up else -2), 0, 10) if rvol is not None else None
    # Volumen atípico sólo es alcista si confirma precio y OBV.
    price_up=bool(c.iloc[-1]>=c.iloc[-2])
    if rvol is None:
        volume_confirm=None
    else:
        impact=cap((rvol-.8)*30,0,35)
        volume_confirm=cap(45+(15 if obv_up else -15)
                           +(impact if price_up and obv_up else -impact)
                           +(5 if price_up else -8),0,100)
    return {
        "rvol20": round(rvol, 2) if rvol is not None else None,
        "dollar_volume20": round(dv, 0),
        "obv_up10": obv_up,
        "atr14": round(atr, 4),
        "stretch_atr20": round(extension, 2) if extension is not None else None,
        "volume_score": round(volume_score, 2) if volume_score is not None else None,
        "volume_confirm_score": round(volume_confirm,2) if volume_confirm is not None else None,
    }


def sma21_priority(close: pd.Series, rsi_values: pd.Series | None = None,
                   macd_values: pd.Series | None = None,
                   atr: float | None = None) -> dict:
    """Espectro SMA21: cruce reciente > tendencia madura; pierde fuerza al aplanarse.

    Usa únicamente cierres hasta t. La edad es el número de cierres consecutivos
    por encima de la SMA21, no días calendario. RSI/MACD restan al inclinarse,
    aunque todavía estén en zona positiva: *no* esperan al cruce bajista.
    """
    no_data={"ma21":None,"ma21_prev":None,"cross_up21":False,
             "cross_down21":False,"sma21_state":"SIN HISTÓRICO",
             "sma21_component":None,"sma21_age":None,"sma21_slope_pct3":None,
             "sma21_distance_atr":None,"rsi_delta1":None,"rsi_delta3":None,
             "macd_delta1_pct":None,"macd_delta3_pct":None,
             "indicator_slope_penalty":0,"indicator_slope_reasons":[]}
    if len(close)<25:return no_data
    c=close.astype(float)
    ma=c.rolling(21,min_periods=21).mean()
    price,prev=float(c.iloc[-1]),float(c.iloc[-2])
    ma21,previous_ma21=float(ma.iloc[-1]),float(ma.iloc[-2])
    if not all(math.isfinite(x) for x in (price,prev,ma21,previous_ma21)) or ma21<=0:
        return no_data
    above=bool(price>ma21)
    up=bool(prev<=previous_ma21 and above)
    down=bool(prev>=previous_ma21 and price<ma21)
    age=0
    if above:
        for p,m in zip(reversed(c.to_numpy()),reversed(ma.to_numpy())):
            if not np.isfinite(m) or p<=m:break
            age+=1
    slope3=(ma21/float(ma.iloc[-4])-1)*100
    # Primera vela sobre SMA21 tiene prima; después se agota por maduración.
    # No equivale a comprar cualquier cruce: la distancia en ATR evita perseguir.
    if down:
        base,state=7,"CRUCE BAJISTA"
    elif not above:
        base,state=22,"BAJO SMA21"
    elif age==1:
        base,state=94,"CRUCE ALCISTA"
    elif age<=3:
        base,state=88,"CRUCE RECIENTE · "+str(age)+" RUEDAS"
    elif age<=6:
        base,state=79,"SOBRE SMA21 · "+str(age)+" RUEDAS"
    elif age<=9:
        base,state=70,"SOBRE SMA21 · "+str(age)+" RUEDAS"
    elif age<=14:
        base,state=58,"TENDENCIA MADURA · "+str(age)+" RUEDAS"
    else:
        base,state=46,"TENDENCIA EXTENDIDA · "+str(age)+" RUEDAS"
    # La inclinación de la SMA cuenta, sin bonus automático por sobrecompra.
    if slope3>=.45:
        base+=7
    elif slope3>0:
        base+=3
    elif slope3<-.45:
        base-=11
    elif slope3<0:
        base-=6
    # Un cruce muy estirado no tiene ventaja simplemente por ser reciente.
    distance_atr=None
    if atr is not None and math.isfinite(float(atr)) and float(atr)>0:
        distance_atr=(price-ma21)/float(atr)
        if distance_atr>2.0:base-=20
        elif distance_atr>1.4:base-=11
        elif up and distance_atr>=.2:base+=4
    # Vigilar cambios de pendiente *antes* de un cruce bajista formal.
    penalty,reasons=0,[]
    delta1=delta3=macd1=macd3=None
    if rsi_values is not None and len(rsi_values)>=4:
        r=rsi_values.astype(float)
        if all(math.isfinite(float(x)) for x in (r.iloc[-1],r.iloc[-2],r.iloc[-4])):
            delta1=float(r.iloc[-1]-r.iloc[-2])
            delta3=float(r.iloc[-1]-r.iloc[-4])
            # Caída leve ya resta; una caída pronunciada de 3 ruedas resta más.
            loss=min(12,(2 if delta1<0 else 0)+min(10,round(max(0,-delta3)*1.2)))
            if loss:
                penalty+=loss
                reasons.append(f"RSI diario pierde pendiente (1r {delta1:+.1f}, 3r {delta3:+.1f}): -{loss}")
    if macd_values is not None and len(macd_values)>=4 and price>0:
        m=macd_values.astype(float)
        if all(math.isfinite(float(x)) for x in (m.iloc[-1],m.iloc[-2],m.iloc[-4])):
            macd1=float((m.iloc[-1]-m.iloc[-2])/price*100)
            macd3=float((m.iloc[-1]-m.iloc[-4])/price*100)
            loss=min(12,(2 if macd1<0 else 0)+min(10,round(max(0,-macd3)*70)))
            if loss:
                penalty+=loss
                reasons.append(f"Histograma MACD pierde pendiente (1r {macd1:+.3f}%, 3r {macd3:+.3f}%): -{loss}")
    return {"ma21":round(ma21,3),"ma21_prev":round(previous_ma21,3),
            "cross_up21":up,"cross_down21":down,"sma21_state":state,
            "sma21_component":round(cap(base,0,100),2),
            "sma21_age":age,"sma21_slope_pct3":round(slope3,3),
            "sma21_distance_atr":round(distance_atr,2) if distance_atr is not None else None,
            "rsi_delta1":round(delta1,2) if delta1 is not None else None,
            "rsi_delta3":round(delta3,2) if delta3 is not None else None,
            "macd_delta1_pct":round(macd1,4) if macd1 is not None else None,
            "macd_delta3_pct":round(macd3,4) if macd3 is not None else None,
            "indicator_slope_penalty":penalty,
            "indicator_slope_reasons":reasons}



def score_penalties(row: dict) -> tuple[int,list[str]]:
    """Deducciones transparentes por extremos de RSI y ruptura SMA200."""
    penalty=int(row.get("indicator_slope_penalty") or 0)
    reasons=list(row.get("indicator_slope_reasons") or [])
    daily=row.get("rsi14d")
    if daily is not None:
        if daily>=80: x=30
        elif daily>=75: x=22
        elif daily>=70: x=12
        elif daily>=67: x=5
        elif daily<=25: x=24
        elif daily<=30: x=17
        elif daily<=35: x=10
        elif daily<=40: x=5
        else:x=0
        if x:
            penalty+=x
            reasons.append(f"RSI14 diario {daily:.1f}: -{x}")
    weekly=row.get("rsi21w")
    if weekly is not None and (weekly>=75 or weekly<=30):
        penalty+=8
        reasons.append("RSI21 semanal extremo: -8")
    monthly=row.get("rsi21m")
    if monthly is not None and (monthly>=75 or monthly<=25):
        penalty+=8
        reasons.append("RSI21 mensual extremo: -8")
    price,ma200=row.get("price"),row.get("ma200")
    if price is not None and ma200 is not None and ma200>0 and price<ma200:
        below=(1-price/ma200)*100
        x=min(30,20+int(below//2))
        penalty+=x
        reasons.append(f"Bajo SMA200 ({below:.1f}%): -{x}")
    return penalty,reasons


def opportunity_score(row: dict, is_stock: bool=True) -> int | None:
    """Ranking 0..100. RS30%, volumen20%, SMA21 20%/15%, base30%/35%.

    No sustituye score histórico de las reglas principales. Si no se pueden
    verificar ambos benchmarks, se marca como NO VERIFICADO y descuenta 12 pts.
    """
    components=(row.get("score"),row.get("sma21_component"),row.get("volume_confirm_score"))
    if any(x is None for x in components):
        return None
    base,sma21,volume=(float(x) for x in components)
    rs=row.get("rs_score")
    verified=bool(row.get("rs_verified")) and rs is not None
    strength=float(rs) if verified else 50.
    wb,wm=(.30,.20) if is_stock else (.35,.15)
    pre=wb*base+wm*sma21+.30*strength+.20*volume
    penalty,notes=score_penalties(row)
    if not verified:
        penalty+=12
        notes.append("Fuerza relativa SPY/QQQ no verificada: -12")
    row["rank_penalty"]=penalty
    row["rank_penalty_reasons"]=notes
    row["rank_components"]={
        "technical":round(wb*base,2),"sma21":round(wm*sma21,2),
        "rs_spy_qqq":round(.30*strength,2),
        "volume":round(.20*volume,2),
        "penalty":-penalty,
    }
    return round(cap(pre-penalty,0,100))


def ranking_stock_21(row: dict) -> int | None:
    return opportunity_score(row,True)


def ranking_score(row: dict) -> int | None:
    return opportunity_score(row,False)


def cautious_signal(row: dict | None, market: str, vix: float | None,
                    fresh: bool, base_signal: str) -> tuple[str, str, str | None]:
    """Candidato muy exigente fuera del régimen FAVORABLE; sin órdenes.

    Respeta las salidas existentes. No genera compras si macro no verificado,
    VIX alto, o volumen/serie semanal incompletos. Este método es una propuesta:
    no usar como decisión final hasta comparación histórica IS/OOS.
    """
    if not row or not fresh or market in ("FAVORABLE", "NO VERIFICADO"):
        return base_signal, "neutral", None
    if base_signal.startswith(("SALIR", "REDUCIR")):
        return base_signal, "neutral", None
    p, m20, m50, m200 = (row.get(k) for k in ("price","ma20","ma50","ma200"))
    if any(x is None for x in (p,m20,m50,m200)):
        return base_signal, "neutral", None
    trend = p > m50 > m200
    sc = row.get("score", 0)
    rsi = row.get("rsi14d")
    weekly = row.get("rsi21w")
    macd = row.get("macd_hist_d")
    histw = row.get("macd_hist_w")
    rvol = row.get("rvol20")
    usdvol = row.get("dollar_volume20")
    obv = row.get("obv_up10")
    stretch = row.get("stretch_atr20")
    gate = (
        vix is not None and vix < 25 and trend and sc >= 76
        and rsi is not None and 46 <= rsi <= 70
        and weekly is not None and weekly >= 52
        and macd is not None and macd > 0
        and histw is not None and histw > 0
        and rvol is not None and usdvol is not None
        and usdvol >= 5_000_000 and obv is True
        and stretch is not None and stretch <= 1.8
    )
    if not gate:
        if trend and sc >= 73 and macd is not None and macd > 0 and vix is not None and vix < 25:
            return "VIGILAR COMPRA · MACRO", "wait", "Fortaleza individual, pero falta confirmación de volumen/semanal o el gatillo; sin compra automática"
        return base_signal, "neutral", None
    pullback = bool(row.get("near20") and rvol >= 0.70)
    breakout = bool(row.get("breakout") and rvol >= 1.20)
    if pullback or breakout:
        return "COMPRA CON PRECAUCIÓN", "wait", (
            "Mercado mixto/defensivo: señal condicionada a volumen y semanal; "
            "evaluar sólo primer tramo reducido (20-30% de la posición prevista), "
            "riesgo 0,5% del capital, invalidación técnica y sin perseguir precio"
        )
    return "VIGILAR COMPRA · MACRO", "wait", "Liderazgo relativo y volumen aceptables; esperar pullback o ruptura válida"


def top_five(assets: list[dict], spy: dict | None, market: str, limit: int = 5) -> list[dict]:
    """Top para estudio, NO cinco compras forzadas. Diversifica sectores."""
    candidates=[]
    spy_roc=spy.get("roc20") if spy else None
    for a in assets:
        d=a.get("data")
        if not d or not a.get("usa"):
            continue
        rank=d.get("rank_score")
        dollar=d.get("dollar_volume20")
        if rank is None or rank<58 or not d.get("rs_verified") or dollar is None or dollar<5_000_000:
            continue
        if d.get("score",0)<65 or d.get("price",0)<=d.get("ma200",float("inf")):
            continue
        if d.get("rsi14d") is None or not(35<d["rsi14d"]<75):
            continue
        if d.get("macd_hist_d",0)<0:
            continue
        if a.get("signal","").startswith(("REDUCIR","SALIR","DATOS","SIN")):
            continue
        relative=d.get("rs_spy20")
        # Regla de desempate declarada. Divergencia vs SPY en 20 ruedas, no
        # una estimación de alpha futura.
        priority = rank + (7 if d.get("cross_up21") else 0) + (5 if d.get("near20") else 0) + (6 if d.get("breakout") else 0)
        priority += cap((relative or 0)/3, -4, 4)
        priority += cap((d.get("rs_qqq20") or 0)/3, -4, 4)
        if d.get("stretch_atr20") is not None and d["stretch_atr20"]>2:
            priority -= 6
        if d.get("rvol20") is not None and d["rvol20"]<0.65:
            priority -= 3
        candidates.append((priority,a,relative))
    candidates.sort(key=lambda v:(v[0],v[1]["data"]["rank_score"]),reverse=True)
    selection=[]
    counts={}
    for pr,a,relative in candidates:
        sector=a["sector"]
        if counts.get(sector,0)>=2:
            continue
        counts[sector]=counts.get(sector,0)+1
        d=a["data"]
        e=a.get("earnings") or {}
        event_days=e.get("days_until")
        tag="CRUCE ALCISTA SMA21 · CONFIRMAR" if d.get("cross_up21") else ("GATILLO DE ENTRADA" if (d.get("breakout") or d.get("near20")) else "ESPERAR GATILLO")
        if market!="FAVORABLE":
            tag += " · RIESGO MACRO"
        if event_days is not None and 0<=event_days<=7:
            tag += " · BALANCE PRÓXIMO"
        selection.append({
            "ticker":a["ticker"], "usa":a["usa"],"sector":sector,
            "rank_score":d["rank_score"],"score":d["score"],
            "price":d["price"],"ma20":d["ma20"],"invalid_usd":d.get("invalid_usd"),
            "target_2r":d.get("target_2r"),
            "relative_spy20":relative,"relative_qqq20":d.get("rs_qqq20"),
            "rs_score":d.get("rs_score"),"volume_confirm_score":d.get("volume_confirm_score"),
            "rank_penalty":d.get("rank_penalty"),"rank_penalty_reasons":d.get("rank_penalty_reasons"),
            "rvol20":d.get("rvol20"),"ma21":d.get("ma21"),"sma21_state":d.get("sma21_state"),
            "dollar_volume20":d.get("dollar_volume20"),"signal":a["signal"],"tag":tag,
            "earnings":e,"date":d.get("date"),
        })
        if len(selection)>=limit:break
    return selection
