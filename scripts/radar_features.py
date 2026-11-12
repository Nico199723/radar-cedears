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
    # Confirmación como espectro: magnitud de pendiente OBV, precio y RVOL.
    # Un cierre 0,01% en rojo no debe restar de golpe 30 puntos de volumen.
    obv_delta=(float(obv.iloc[-1])-float(obv.iloc[-11]))/(max(base,1.)*10)
    obv_slope=math.tanh(obv_delta/.35)
    price_impulse=(float(c.iloc[-1])-float(c.iloc[-2]))/max(atr,.001)
    price_slope=math.tanh(price_impulse/.9)
    if rvol is None:
        volume_confirm=None
    else:
        atypical=math.tanh((rvol-1)/.8)
        confirmation=.65*obv_slope+.35*price_slope
        volume_confirm=cap(50+17*obv_slope+12*price_slope
                           +20*atypical*confirmation,0,100)
    return {
        "rvol20": round(rvol, 2) if rvol is not None else None,
        "dollar_volume20": round(dv, 0),
        "obv_up10": obv_up,
        "atr14": round(atr, 4),
        "stretch_atr20": round(extension, 2) if extension is not None else None,
        "volume_score": round(volume_score, 2) if volume_score is not None else None,
        "volume_confirm_score": round(volume_confirm,2) if volume_confirm is not None else None,
        "obv_impulse10":round(obv_delta,3),"price_impulse_atr":round(price_impulse,3),
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
    # Espectro continuo: distancia normalizada por ATR, edad y pendiente.
    # Sin escalones de 94 a 88 o de 79 a 70 por una sola rueda.
    distance_atr=None
    effective_atr=(float(atr) if atr is not None and math.isfinite(float(atr))
                   and float(atr)>0 else max(.01,price*.02))
    distance_atr=(price-ma21)/effective_atr
    recency=math.exp(-max(0,age-1)/7.0) if above else 0.
    # En el cruce: transición suave y control de distancia. 1.5 ATR es fuerte.
    location=50+40*math.tanh(distance_atr/.55)
    age_drag=27*(1-math.exp(-max(0,age-1)/7.5)) if above else 0.
    fresh_bonus=8*recency*cap(distance_atr/.6,0,1)
    slope_effect=8*math.tanh(slope3/.5)
    extension_cost=20*(1-math.exp(-max(0.,distance_atr-1.15)/.65))
    base=location-age_drag+fresh_bonus+slope_effect-extension_cost
    if up:state="CRUCE ALCISTA · 1 RUEDA"
    elif down:state="CRUCE BAJISTA"
    elif not above:state="BAJO SMA21"
    elif age<=3:state=f"CRUCE RECIENTE · {age} RUEDAS"
    elif age<=9:state=f"SOBRE SMA21 · {age} RUEDAS"
    elif age<=14:state=f"TENDENCIA MADURA · {age} RUEDAS"
    else:state=f"TENDENCIA EXTENDIDA · {age} RUEDAS"
    # Vigilar cambios de pendiente *antes* de un cruce bajista formal.
    penalty,reasons=0,[]
    delta1=delta3=macd1=macd3=None
    if rsi_values is not None and len(rsi_values)>=4:
        r=rsi_values.astype(float)
        if all(math.isfinite(float(x)) for x in (r.iloc[-1],r.iloc[-2],r.iloc[-4])):
            delta1=float(r.iloc[-1]-r.iloc[-2])
            delta3=float(r.iloc[-1]-r.iloc[-4])
            # Caída leve ya resta; una caída pronunciada de 3 ruedas resta más.
            loss=min(12.,2.2*max(0.,-delta1)+.95*max(0.,-delta3))
            if loss:
                penalty+=loss
                reasons.append(f"RSI diario pierde pendiente (1r {delta1:+.1f}, 3r {delta3:+.1f}): -{loss}")
    if macd_values is not None and len(macd_values)>=4 and price>0:
        m=macd_values.astype(float)
        if all(math.isfinite(float(x)) for x in (m.iloc[-1],m.iloc[-2],m.iloc[-4])):
            macd1=float((m.iloc[-1]-m.iloc[-2])/price*100)
            macd3=float((m.iloc[-1]-m.iloc[-4])/price*100)
            loss=min(12.,28*max(0.,-macd1)+44*max(0.,-macd3))
            if loss:
                penalty+=loss
                reasons.append(f"Histograma MACD pierde pendiente (1r {macd1:+.3f}%, 3r {macd3:+.3f}%): -{loss}")
    penalty=round(penalty,2)
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



def score_penalties(row: dict) -> tuple[float,list[str]]:
    """Descuentos graduales sin saltos por RSI 69.9/70 ni SMA200 0.01%.

    RSI14 diario: curva continua, con castigo de 30 puntos en 80.
    SMA200: castigo creciente según distancia porcentual bajo media.
    Pérdida de pendiente RSI/MACD resta antes del cruce, proporcional al giro.
    """
    penalty=float(row.get("indicator_slope_penalty") or 0)
    reasons=list(row.get("indicator_slope_reasons") or [])
    daily=row.get("rsi14d")
    if daily is not None and math.isfinite(float(daily)):
        points=[(0,28),(25,24),(30,17),(35,10),(40,5),(44,0),
                (64,0),(67,4),(70,12),(75,22),(80,30),(90,37),(100,42)]
        x=float(np.interp(float(daily),[p[0] for p in points],[p[1] for p in points]))
        if x>=.05:
            penalty+=x
            reasons.append(f"RSI14 diario {float(daily):.1f}: -{x:.1f}")
    weekly=row.get("rsi21w")
    if weekly is not None and math.isfinite(float(weekly)):
        w=cap((float(weekly)-65)*.8,0,10)+cap((35-float(weekly))*.8,0,10)
        if w>=.05:
            penalty+=w
            reasons.append(f"RSI21 semanal en extremo: -{w:.1f}")
    monthly=row.get("rsi21m")
    if monthly is not None and math.isfinite(float(monthly)):
        m=cap((float(monthly)-68)*.8,0,10)+cap((32-float(monthly))*.8,0,10)
        if m>=.05:
            penalty+=m
            reasons.append(f"RSI21 mensual en extremo: -{m:.1f}")
    price,ma200=row.get("price"),row.get("ma200")
    if price is not None and ma200 is not None and float(ma200)>0 and float(price)<float(ma200):
        below=(1-float(price)/float(ma200))*100
        x=26*(1-math.exp(-below/3.6))
        penalty+=x
        reasons.append(f"Bajo SMA200 ({below:.1f}%): -{x:.1f}")
    return round(penalty,2),reasons


def legacy_entry_rank(close: pd.Series, rsi_values: pd.Series,
                      macd_values: pd.Series, row: dict, is_stock: bool) -> tuple[int|None,int]:
    """Congelar la escala de decisión pre-v1.6 hasta tener backtest OOS.

    El Score Oportunidad puede volverse más suave para ranking/vigilancia,
    pero las compras prudentes no deben cambiar ocultamente por eso.
    """
    if any(row.get(k) is None for k in ("score","volume_score","rvol20","sma21_age",
                                        "sma21_slope_pct3","ma21","price")):
        return None,0
    price=float(row["price"])
    age=int(row["sma21_age"])
    slope=float(row["sma21_slope_pct3"])
    dist=row.get("sma21_distance_atr")
    if row.get("cross_down21"):sma=7
    elif price<=row["ma21"]:sma=22
    elif age==1:sma=94
    elif age<=3:sma=88
    elif age<=6:sma=79
    elif age<=9:sma=70
    elif age<=14:sma=58
    else:sma=46
    sma+=7 if slope>=.45 else 3 if slope>0 else -11 if slope<-.45 else -6 if slope<0 else 0
    if dist is not None:
        if dist>2:sma-=20
        elif dist>1.4:sma-=11
        elif row.get("cross_up21") and dist>=.2:sma+=4
    sma=cap(sma,0,100)
    rvol=float(row["rvol20"])
    obv_up=row.get("obv_up10") is True
    up=bool(float(close.iloc[-1])>=float(close.iloc[-2]))
    impact=cap((rvol-.8)*30,0,35)
    vol=cap(45+(15 if obv_up else -15)
            +(impact if up and obv_up else -impact)+(5 if up else -8),0,100)
    loss=0
    if len(rsi_values)>=4:
        r=rsi_values.astype(float)
        d1=float(r.iloc[-1]-r.iloc[-2]);d3=float(r.iloc[-1]-r.iloc[-4])
        if math.isfinite(d1) and math.isfinite(d3):
            loss+=min(12,(2 if d1<0 else 0)+min(10,round(max(0,-d3)*1.2)))
    if len(macd_values)>=4:
        m=macd_values.astype(float)
        d1=float((m.iloc[-1]-m.iloc[-2])/price*100)
        d3=float((m.iloc[-1]-m.iloc[-4])/price*100)
        if math.isfinite(d1) and math.isfinite(d3):
            loss+=min(12,(2 if d1<0 else 0)+min(10,round(max(0,-d3)*70)))
    daily=row.get("rsi14d")
    if daily is not None:
        if daily>=80:loss+=30
        elif daily>=75:loss+=22
        elif daily>=70:loss+=12
        elif daily>=67:loss+=5
        elif daily<=25:loss+=24
        elif daily<=30:loss+=17
        elif daily<=35:loss+=10
        elif daily<=40:loss+=5
    weekly=row.get("rsi21w")
    monthly=row.get("rsi21m")
    if weekly is not None and (weekly>=75 or weekly<=30):loss+=8
    if monthly is not None and (monthly>=75 or monthly<=25):loss+=8
    ma200=row.get("ma200")
    if ma200 and price<ma200:
        loss+=min(30,20+int(((1-price/ma200)*100)//2))
    rs=row.get("rs_score")
    verified=bool(row.get("rs_verified")) and rs is not None
    wb,wm=(.30,.20) if is_stock else (.35,.15)
    gross=wb*float(row["score"])+wm*sma+.30*(float(rs) if verified else 50.)+.20*vol
    if not verified:loss+=12
    return round(cap(gross-loss,0,100)),int(loss)


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
    final=round(cap(pre-penalty,0,100),1)
    row["rank_raw"]=round(pre,2)
    row["rank_level"]=("PRIORIDAD PARA ESTUDIAR" if final>=78 else
                       "CANDIDATA PARA VIGILAR" if final>=62 else
                       "FUERA DE RANGO DE COMPRA")
    return final


def ranking_stock_21(row: dict) -> int | None:
    return opportunity_score(row,True)


def ranking_score(row: dict) -> int | None:
    return opportunity_score(row,False)


def risk_policy(market: str, vix: float | None) -> dict:
    """El macro MODULA riesgo; sólo datos no verificables/estrés extremo bloquean.

    Los porcentajes corresponden al simulador ficticio de USD 2000; el radar
    no coloca órdenes ni determina tamaños para las cuentas reales.
    """
    if market not in ("FAVORABLE", "MIXTO", "DEFENSIVO") or vix is None or not math.isfinite(float(vix)) or vix>=30:
        return {"mode":"SIN NUEVAS ENTRADAS","max_position_usd":0,
                "reserve_usd":2000,"reserve_pct":100,"stop_pct":None,
                "max_positions":0,"max_per_sector":0}
    if market!="FAVORABLE":
        return {"mode":"PRUDENTE","max_position_usd":120,
                "reserve_usd":1400,"reserve_pct":70,"stop_pct":6,
                "max_positions":2,"max_per_sector":1}
    return {"mode":"NORMAL","max_position_usd":250,
            "reserve_usd":1000,"reserve_pct":50,"stop_pct":8,
            "max_positions":4,"max_per_sector":2}


def reconcile_buy_label(row: dict | None, signal: str, tone: str,
                        reasons: list[str], fresh: bool,
                        candidate: dict | None = None) -> tuple[str,str,list[str]]:
    """Señal visible y elegibilidad: compra REAL requiere Score O >=70.

    Separar 3 preguntas distintas:
    - ¿Score suficiente para entrada?
    - ¿Hay setup técnico completo?
    - ¿Es sólo una oportunidad a vigilar?
    No convertir un 90/100 automáticamente en entrada ni ocultarlo en HOLD.
    """
    if not fresh or row is None:
        if signal in ("COMPRA CONDICIONAL","COMPRA CON PRECAUCIÓN"):
            return "DATOS VIEJOS","neutral",reasons+["No habilitar compra sin datos actuales"]
        return signal,tone,reasons
    if signal.startswith(("SALIR","REDUCIR","DATOS","SIN")):
        return signal,tone,reasons
    rank=row.get("rank_score")
    if rank is None or not math.isfinite(float(rank)):
        if signal in ("COMPRA CONDICIONAL","COMPRA CON PRECAUCIÓN"):
            return "ESPERAR","wait",reasons+["Compra bloqueada: Score Oportunidad sin verificar"]
        return signal,tone,reasons
    rank=float(rank)
    is_buy=signal in ("COMPRA CONDICIONAL","COMPRA CON PRECAUCIÓN")
    if is_buy and rank<MIN_BUY_SCORE:
        explanation=(f"Compra NO habilitada: Score Oportunidad {rank:.1f}/100, "
                     f"mínimo de entrada {MIN_BUY_SCORE:.0f}/100")
        if rank>=MIN_OPTION_SCORE:
            return "VIGILAR COMPRA · SCORE","watch",reasons+[explanation]
        return "ESPERAR","wait",reasons+[explanation]
    is_hold=signal in ("ESPERAR","ESPERAR MACRO","MANTENER / ESPERAR")
    if is_hold and rank>=MIN_BUY_SCORE:
        blocked=list((candidate or {}).get("blockers") or [])
        if (candidate or {}).get("eligible"):
            return ("VIGILAR COMPRA · SCORE","watch",reasons+
                    [f"Score Oportunidad {rank:.1f}/100 >=70, "
                     "pero aún falta un gatillo técnico para entrar"]+
                    blocked)
        return ("VIGILAR SETUP · SCORE","watch",reasons+
                [f"Score Oportunidad {rank:.1f}/100 >=70, "
                 "pero NO cumple el setup para comprar"]+
                blocked)
    if signal.startswith("VIGILAR"):
        return signal,"watch",reasons
    return signal,tone,reasons


def cautious_signal(row: dict | None, market: str, vix: float | None,
                    fresh: bool, base_signal: str) -> tuple[str, str, str | None]:
    """Entrada condicional en acciones Y ETFs pese a SPY/QQQ bajo SMA50.

    Usar los subyacentes USA/USD, a cierre. No inventar 5 compras si ningún
    activo confirma. VIX <30, dato fresco, precio sobre SMA21/50/200,
    RSI y semanal no quebrados, RS relativo y volumen de calidad. Cada
    señal con régimen defensivo se acompaña de menor tamaño y stop en paper.
    """
    if row is None or not fresh or market=="FAVORABLE":
        return base_signal,"neutral",None
    if base_signal.startswith(("SALIR","REDUCIR","DATOS","SIN")):
        return base_signal,"neutral",None
    policy=risk_policy(market,vix)
    if policy["mode"]=="SIN NUEVAS ENTRADAS":
        return base_signal,"neutral",None

    def val(k):
        x=row.get(k)
        try:
            x=float(x)
            return x if math.isfinite(x) else None
        except (TypeError,ValueError):
            return None

    p,ma21,ma50,ma200=(val(k) for k in ("price","ma21","ma50","ma200"))
    if any(x is None or x<=0 for x in (p,ma21,ma50,ma200)):
        return base_signal,"neutral",None
    if not (p>ma21 and p>ma50 and p>ma200):
        return base_signal,"neutral",None

    score,rsi,weekly=(val(k) for k in ("score","rsi14d","rsi21w"))
    rank=val("rank_score_signal") if row.get("rank_score_signal") is not None else val("rank_score")
    macd,macd_w=(val(k) for k in ("macd_hist_d","macd_hist_w"))
    rvol,dollar,stretch=(val(k) for k in ("rvol20","dollar_volume20","stretch_atr20"))
    rs_spy,rs_qqq,rs_score=(val(k) for k in ("rs_spy20","rs_qqq20","rs_score"))
    volume_confirm=val("volume_confirm_score")
    if any(x is None for x in (score,rank,rsi,weekly,macd,macd_w,
                                rvol,dollar,stretch,rs_spy,rs_qqq,rs_score,
                                volume_confirm)):
        return base_signal,"neutral",None

    structure=(score>=67 and rank>=58 and 43<=rsi<70
               and weekly>=45 and macd>0 and macd_w>=0
               and row.get("rank_penalty_signal",row.get("rank_penalty",0))<24)
    leadership=(row.get("rs_verified") is True and rs_score>=43
                and (rs_spy+rs_qqq)/2>=-3.5)
    liquidity=(dollar>=5_000_000 and rvol>=.75
               and volume_confirm>=50 and row.get("obv_up10") is True)
    not_chasing=(-.8<=stretch<=1.6)
    if not (structure and leadership and liquidity and not_chasing):
        # Separar la vigilancia del rechazo absoluto del índice.
        if score>=65 and macd>0 and 40<=rsi<74 and rank>=53:
            return "VIGILAR COMPRA · MACRO", "wait", (
                "SPY/QQQ débiles: vigilar fuerza propia, pero aún falta "
                "confirmación de impulso, volumen, semanal o distancia ATR")
        return base_signal,"neutral",None

    # No exigir que el cruce ocurra justamente hoy; un pullback sano,
    # ruptura con volumen o continuación próxima a SMA20 también valen.
    pullback=bool(row.get("near20"))
    cross=bool(row.get("cross_up21")) and rvol>=.85
    breakout=bool(row.get("breakout")) and rvol>=1.15
    continuation=(0<=stretch<=1.0 and rvol>=.90
                  and rsi<=64 and rank>=62
                  and row.get("sma21_age") is not None
                  and row["sma21_age"]<=14)
    if not (pullback or cross or breakout or continuation):
        return "VIGILAR COMPRA · MACRO", "wait", (
            "No bloquea SPY/QQQ: falta cruce SMA21, pullback, ruptura o "
            "continuación próxima a la media sin perseguir precio")

    return "COMPRA CON PRECAUCIÓN", "caution", (
        "Setup individual confirmado con SPY/QQQ débiles. Plan SIMULADO: "
        "hasta USD 120 por posición, 70% de reserva y stop de referencia 6%; "
        "compras 40/35/25. Los gaps pueden provocar pérdidas mayores.")



MIN_BUY_SCORE=70.0
MIN_OPTION_SCORE=62.0
PRIORITY_OPTION_SCORE=75.0


def buy_candidate(row: dict | None, signal: str, fresh: bool) -> dict:
    """Semáforo de ESTUDIO, distinto de señal operable.

    Un score alto no da una orden. La ausencia de entrada indica exactamente
    cuál confirmación falta. No modifica los stops ni el paper track record.
    """
    out={"eligible":False,"min_score":MIN_OPTION_SCORE,
         "priority_score":PRIORITY_OPTION_SCORE,"level":"SIN CANDIDATURA",
         "blockers":[]}
    if not fresh or not row or signal.startswith(("SALIR","REDUCIR","SIN","DATOS")):
        out["blockers"]=["Datos sin vigencia o salida activa"];return out
    rank=row.get("rank_score")
    if rank is None:
        out["blockers"]=["Score Oportunidad sin calcular"];return out
    if rank<MIN_OPTION_SCORE:
        out["blockers"]=[f"Score {rank:.1f} por debajo del mínimo {MIN_OPTION_SCORE:.0f}"];return out
    p,ma21,ma200=(row.get(k) for k in ("price","ma21","ma200"))
    rsi=row.get("rsi14d")
    macd=row.get("macd_hist_d")
    blockers=[]
    if not row.get("rs_verified"):blockers.append("RS frente a SPY/QQQ no verificada")
    if p is None or ma200 is None or p<=ma200:blockers.append("Precio bajo SMA200")
    if p is None or ma21 is None or p<=ma21:blockers.append("Aún bajo SMA21 diaria")
    if rsi is None or not 35<rsi<75:blockers.append("RSI en extremo de riesgo")
    if macd is None or macd<=0:blockers.append("MACD diario sin impulso positivo")
    if row.get("dollar_volume20") is None or row["dollar_volume20"]<5_000_000:
        blockers.append("Volumen USD promedio insuficiente")
    out["blockers"]=blockers
    out["eligible"]=not blockers
    if not blockers:
        out["level"]=("PRIORIDAD DE COMPRA · A CONFIRMAR" if rank>=PRIORITY_OPTION_SCORE
                      else "CANDIDATA · A CONFIRMAR")
        if not (row.get("near20") or row.get("breakout") or row.get("cross_up21")):
            out["blockers"]=["Score favorable; falta gatillo o continuación validada"]
    else:
        out["level"]="SCORE ALTO · ESTRUCTURA POR CONFIRMAR"
    return out


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
        if rank is None or rank<MIN_OPTION_SCORE or not d.get("rs_verified") or dollar is None or dollar<5_000_000:
            continue
        if d.get("price",0)<=d.get("ma200",float("inf")):
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
        priority = rank + 3.0*(d.get("sma21_component") or 0)/100 + 2.5*min(1.,max(0.,(d.get("rvol20") or 0)-.6))
        priority += cap((relative or 0)/3, -4, 4)
        priority += cap((d.get("rs_qqq20") or 0)/3, -4, 4)
        if d.get("stretch_atr20") is not None:
            priority -= 8*(1-math.exp(-max(0.,d["stretch_atr20"]-1.2)))
        if d.get("rvol20") is not None and d["rvol20"]<0.65:
            priority -= 3*(1-d["rvol20"]/.65)
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
        if a.get("signal") in ("VIGILAR COMPRA · SCORE","VIGILAR COMPRA · MACRO"):
            tag="SCORE PARA ESTUDIAR · FALTA CONFIRMACIÓN"
        if market!="FAVORABLE":
            tag += " · RIESGO MACRO"
        if event_days is not None and 0<=event_days<=7:
            tag += " · BALANCE PRÓXIMO"
        selection.append({
            "ticker":a["ticker"], "usa":a["usa"],"sector":sector,
            "rank_score":d["rank_score"],"score":d["score"],
            "candidate":a.get("candidate"),"rank_level":d.get("rank_level"),
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
