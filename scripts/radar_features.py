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


def volume_profile(frame: pd.DataFrame) -> dict:
    """Indicadores al cierre t. RVOL usa las 20 sesiones ANTERIORES."""
    v = frame["Volume"].astype(float)
    c = frame["Close"].astype(float)
    h, l = frame["High"].astype(float), frame["Low"].astype(float)
    if len(frame) < 40 or v.iloc[-21:].isna().any() or not (v.iloc[-21:] >= 0).all():
        return {"rvol20": None, "dollar_volume20": None, "obv_up10": None,
                "atr14": None, "stretch_atr20": None, "volume_score": None}
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
    return {
        "rvol20": round(rvol, 2) if rvol is not None else None,
        "dollar_volume20": round(dv, 0),
        "obv_up10": obv_up,
        "atr14": round(atr, 4),
        "stretch_atr20": round(extension, 2) if extension is not None else None,
        "volume_score": round(volume_score, 2) if volume_score is not None else None,
    }


def sma21_priority(close: pd.Series) -> dict:
    """Cruce de cierre contra SMA21: sin mirar la vela futura.

    Puntaje 0..100 es calidad de la relación con SMA21, NO rendimiento esperado.
    El cruce tiene más peso que simplemente operar arriba de la media.
    """
    if len(close) < 23:
        return {"ma21": None, "ma21_prev": None, "cross_up21": False,
                "cross_down21": False, "sma21_state": "SIN HISTÓRICO",
                "sma21_component": None}
    c = close.astype(float)
    price,prev=float(c.iloc[-1]),float(c.iloc[-2])
    ma21=float(c.iloc[-21:].mean())
    previous_ma21=float(c.iloc[-22:-1].mean())
    up=prev<=previous_ma21 and price>ma21
    down=prev>=previous_ma21 and price<ma21
    if up:rating,state=100,"CRUCE ALCISTA"
    elif down:rating,state=0,"CRUCE BAJISTA"
    elif price>ma21 and ma21>previous_ma21:rating,state=80,"SOBRE SMA21 · SUBIENDO"
    elif price>ma21:rating,state=65,"SOBRE SMA21"
    elif ma21>previous_ma21:rating,state=35,"BAJO SMA21 · MEDIA SUBIENDO"
    else:rating,state=15,"BAJO SMA21"
    return {"ma21":round(ma21,3),"ma21_prev":round(previous_ma21,3),
            "cross_up21":up,"cross_down21":down,"sma21_state":state,
            "sma21_component":rating}


def ranking_stock_21(row: dict) -> int | None:
    """Acciones individuales: 65% base, 15% volumen, 20% SMA21 diaria."""
    sc,vol,m21=row.get("score"),row.get("volume_score"),row.get("sma21_component")
    if any(v is None for v in (sc,vol,m21)):
        return None
    return round(cap(.65*float(sc) + 1.5*float(vol) + .20*float(m21),0,100))


def ranking_score(row: dict) -> int | None:
    """85% técnico tradicional + 15% confirmación volumen (0..100)."""
    b,v=row.get("score"),row.get("volume_score")
    if b is None or v is None:
        return None
    return round(cap(.85*float(b) + 1.5*float(v),0,100))


def cautious_signal(row: dict | None, market: str, vix: float | None,
                    fresh: bool, base_signal: str) -> tuple[str, str, str | None]:
    """Excepción macro *condicional*; no compra por score ni por mercado solo.

    Activar sólo con precio sobre SMA21/SMA50/SMA200, semanal firme, RSI/MACD,
    volumen y gatillo diario. Un VIX >=25 o macro desconocido sigue bloqueando.
    La contraprestación por mercado débil es menor size/stop en paper (no cambiar
    el precio ni ocultar el riesgo de gaps); jamás sustituye backtest OOS.
    """
    if not row or not fresh or market in ("FAVORABLE", "NO VERIFICADO"):
        return base_signal, "neutral", None
    if base_signal.startswith(("SALIR", "REDUCIR","DATOS","SIN")):
        return base_signal, "neutral", None
    if vix is None or vix >= 25 or vix < 0:
        return base_signal, "neutral", None
    keys=("price","ma21","ma50","ma200")
    vals=[row.get(k) for k in keys]
    if any(x is None or not math.isfinite(float(x)) or float(x)<=0 for x in vals):
        return base_signal, "neutral", None
    p,ma21,m50,m200=vals
    if not (p>ma21 and p>m50>m200):
        return base_signal, "neutral", None
    strong=(
        row.get("score",0)>=70
        and row.get("rsi14d") is not None and 46<=row["rsi14d"]<=70
        and row.get("rsi21w") is not None and row["rsi21w"]>=48
        and row.get("macd_hist_d") is not None and row["macd_hist_d"]>0
        and row.get("macd_hist_w") is not None and row["macd_hist_w"]>=0
        and row.get("dollar_volume20") is not None and row["dollar_volume20"]>=5_000_000
        and row.get("rvol20") is not None and row["rvol20"]>=.85
        and row.get("obv_up10") is True
        and row.get("stretch_atr20") is not None and -.75<=row["stretch_atr20"]<=1.8
    )
    if not strong:
        if row.get("score",0)>=70 and (row.get("macd_hist_d") or 0)>0:
            return "VIGILAR COMPRA · MACRO", "wait", (
                "Fortaleza individual por encima de SMA21/50/200, pero faltan "
                "confirmaciones para asumir riesgo en mercado adverso")
        return base_signal, "neutral", None
    gate=bool(row.get("cross_up21") or row.get("near20") or row.get("breakout"))
    if not gate:
        return "VIGILAR COMPRA · MACRO", "wait", (
            "Hay fuerza, volumen y estructura semanal, pero falta cruce/retroceso/ruptura de entrada")
    return "COMPRA CON PRECAUCIÓN", "wait", (
        "SPY/QQQ débiles NO bloquean la excepción: confirmar gatillo SMA21/volumen "
        "y asumir riesgo acotado en 40/35/25 con tope simulado USD 120, reserva >=70%, stop "
        "de referencia 6% (los gaps pueden superar el stop); sin orden automática")



def top_five(assets: list[dict], spy: dict | None, market: str, limit: int = 5) -> list[dict]:
    """Top para estudio, NO cinco compras forzadas. Diversifica sectores."""
    candidates=[]
    spy_roc=spy.get("roc20") if spy else None
    for a in assets:
        d=a.get("data")
        if not d or not a.get("usa") or a.get("sector")=="Índices y ETFs":
            continue
        rank=d.get("rank_score")
        dollar=d.get("dollar_volume20")
        if rank is None or dollar is None or dollar<5_000_000:
            continue
        if d.get("score",0)<65 or d.get("price",0)<=d.get("ma200",float("inf")):
            continue
        if d.get("rsi14d") is None or d["rsi14d"]>74:
            continue
        if d.get("macd_hist_d",0)<0:
            continue
        if a.get("signal","").startswith(("REDUCIR","SALIR","DATOS","SIN")):
            continue
        relative=round(d["roc20"]-spy_roc,2) if spy_roc is not None and d.get("roc20") is not None else None
        # Regla de desempate declarada. Divergencia vs SPY en 20 ruedas, no
        # una estimación de alpha futura.
        priority = rank + (7 if d.get("cross_up21") else 0) + (5 if d.get("near20") else 0) + (6 if d.get("breakout") else 0)
        priority += cap((relative or 0)/3, -4, 4)
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
            "relative_spy20":relative,"rvol20":d.get("rvol20"),"ma21":d.get("ma21"),"sma21_state":d.get("sma21_state"),
            "dollar_volume20":d.get("dollar_volume20"),"signal":a["signal"],"tag":tag,
            "earnings":e,"date":d.get("date"),
        })
        if len(selection)>=limit:break
    return selection
