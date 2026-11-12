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


def ranking_score(row: dict) -> int | None:
    """85% técnico tradicional + 15% confirmación volumen (0..100)."""
    b,v=row.get("score"),row.get("volume_score")
    if b is None or v is None:
        return None
    return round(cap(.85*float(b) + 1.5*float(v),0,100))


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
        priority = rank + (5 if d.get("near20") else 0) + (6 if d.get("breakout") else 0)
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
        tag="GATILLO DE ENTRADA" if (d.get("breakout") or d.get("near20")) else "ESPERAR GATILLO"
        if market!="FAVORABLE":
            tag += " · RIESGO MACRO"
        if event_days is not None and 0<=event_days<=7:
            tag += " · BALANCE PRÓXIMO"
        selection.append({
            "ticker":a["ticker"], "usa":a["usa"],"sector":sector,
            "rank_score":d["rank_score"],"score":d["score"],
            "price":d["price"],"ma20":d["ma20"],"invalid_usd":d.get("invalid_usd"),
            "target_2r":d.get("target_2r"),
            "relative_spy20":relative,"rvol20":d.get("rvol20"),
            "dollar_volume20":d.get("dollar_volume20"),"signal":a["signal"],"tag":tag,
            "earnings":e,"date":d.get("date"),
        })
        if len(selection)>=limit:break
    return selection
