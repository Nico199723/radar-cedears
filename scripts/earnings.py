"""Consulta acotada del calendario de balances: fuente gratuita y fecha NO confirmada.

Yahoo Finance / yfinance puede devolver estimaciones, fallar o rate-limitar.
No inventar fechas; nunca confundir "sin datos" con "sin balance".
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone, timedelta
import logging
import pandas as pd


def parse_earnings(calendar, today: date) -> dict | None:
    """Fecha futura más próxima de Yahoo; sin usar datos de precio."""
    raw=None
    if isinstance(calendar,dict):
        raw=calendar.get("Earnings Date")
    elif isinstance(calendar,pd.DataFrame):
        if "Earnings Date" in calendar.index:
            raw=calendar.loc["Earnings Date"].tolist()
        elif "Earnings Date" in calendar.columns:
            raw=calendar["Earnings Date"].tolist()
    if raw is None:
        return None
    values=raw if isinstance(raw,(list,tuple,pd.Series)) else [raw]
    dates=[]
    for item in values:
        try:
            d=pd.to_datetime(item,errors="coerce")
            if pd.isna(d): continue
            current=d.date()
            if today<=current<=today+timedelta(days=120):
                dates.append(current)
        except (TypeError,ValueError,OverflowError,AttributeError):
            continue
    if not dates: return None
    d=min(dates)
    return {"date":d.isoformat(), "days_until":(d-today).days,
            "source":"Yahoo Finance vía yfinance", "status":"FECHA INDICATIVA — confirmar en relaciones con inversores"}


def get_calendar(symbol: str, today: date) -> dict | None:
    import yfinance as yf
    try:
        return parse_earnings(yf.Ticker(symbol).calendar, today)
    except Exception as exc:
        logging.warning("Balance %s sin verificar: %s",symbol,str(exc)[:100])
        return None


def earnings_for_candidates(assets: list[dict], today: date, max_queries=55) -> tuple[dict,dict]:
    """Consulta sólo candidatos técnicos fuertes; cobertura explícita."""
    if max_queries<=0:
        return {}, {"consulted":0,"found":0,"eligible":0}
    pool={}
    for a in assets:
        d=a.get("data")
        sym=a.get("usa")
        if not d or not sym or not (d.get("score",0)>=65):
            continue
        if a.get("sector")=="Índices y ETFs":
            continue
        pool[sym]=max(pool.get(sym,-1),d["score"])
    eligible=len(pool)
    selection=[k for k,v in sorted(pool.items(),key=lambda item:item[1],reverse=True)[:max_queries]]
    result={}
    with ThreadPoolExecutor(max_workers=4) as ex:
        future={ex.submit(get_calendar,sym,today):sym for sym in selection}
        for f in as_completed(future):
            sym=future[f]
            try:
                result[sym]=f.result()
            except Exception:
                result[sym]=None
    return result,{"consulted":len(selection),"found":sum(v is not None for v in result.values()),"eligible":eligible}


def event_label(earnings: dict | None, checked: bool) -> str:
    if not checked:
        return "FECHA NO CONSULTADA"
    if not earnings:
        return "FECHA SIN VERIFICAR"
    days=earnings["days_until"]
    if days<=7:return "BALANCE <=7 DÍAS"
    if days<=14:return "BALANCE <=14 DÍAS"
    return "FECHA INDICATIVA"
