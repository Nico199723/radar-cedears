#!/usr/bin/env python3
"""Radar CEDEARs: señales exclusivamente sobre subyacentes USD en EE.UU.

Fuente gratuita experimental: Yahoo Finance via yfinance (uso personal, datos no garantizados).
Sin credenciales ni datos privados de cartera. Ejecutar: python scripts/actualizar.py
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from radar_features import volume_profile, ranking_score, cautious_signal, top_five, sma21_priority, ranking_stock_21
from earnings import earnings_for_candidates, event_label

# Se activa sólo tras contrastar baseline y candidato en datos fuera de muestra.
ENABLE_CAUTION_ENTRIES = False

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "universo.csv"
OUT = ROOT / "docs" / "data.json"
NY_TZ = ZoneInfo("America/New_York")
AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SOURCE = "Yahoo Finance (yfinance), precios ajustados, USD del mercado estadounidense"

SECTORS = {
    "Aeroespacial y defensa": "ITA", "Agro": "DBA", "Bancos": "KBE",
    "Consumo básico": "XLP", "Consumo discrecional": "XLY",
    "Cripto y activos digitales": "IBIT", "Energía": "XLE",
    "Finanzas y pagos": "XLF", "Índices y ETFs": "SPY",
    "Industriales": "XLI", "Materiales y minería": "XLB",
    "Salud y biotecnología": "XLV", "Semiconductores": "SMH",
    "Software y cloud": "IGV", "Tecnología e internet": "XLK",
    "Telecomunicaciones": "IYZ", "Turismo y viajes": "JETS",
}


def number(v, nd=3):
    try:
        x = float(v)
        return round(x, nd) if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(down.ne(0), 100).where((down.ne(0) | up.ne(0)), 50)


def macd_hist(close: pd.Series, short=12, long=26, signal=9) -> pd.Series:
    macd = close.ewm(span=short, adjust=False).mean() - close.ewm(span=long, adjust=False).mean()
    return macd - macd.ewm(span=signal, adjust=False).mean()


def adx(df: pd.DataFrame, n=14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    up, down = h.diff(), -l.diff()
    pos_dm = pd.Series(np.where((up > down) & (up > 0), up, 0), index=h.index)
    neg_dm = pd.Series(np.where((down > up) & (down > 0), down, 0), index=h.index)
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    pos_di = 100 * pos_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr.replace(0,np.nan)
    neg_di = 100 * neg_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr.replace(0,np.nan)
    dx = 100 * (pos_di-neg_di).abs() / (pos_di+neg_di).replace(0,np.nan)
    return dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean()


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def read_catalog() -> list[dict]:
    with CATALOG.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 200, "Faltan instrumentos en el catálogo"
    assert len({x['cedear'] for x in rows}) == len(rows), "CEDEAR duplicado"
    return rows


def last_complete_daily(df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Durante rueda descarta la vela diaria de hoy, que sería parcial.
    Fuera de rueda puede usar el cierre diario publicado; mostrar siempre fecha.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_convert(NY_TZ).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Close"])
    ny = now.astimezone(NY_TZ)
    # 9:30-16:00 NY. No tratar la vela actual todavía incompleta como cierre.
    before_close = (ny.hour < 16)
    if before_close and not df.empty and df.index[-1].date() >= ny.date():
        df = df[df.index.date < ny.date()]
    return df


def compute(df: pd.DataFrame, now: datetime, is_stock: bool = False) -> dict | None:
    df = last_complete_daily(df, now)
    if len(df) < 240:
        return None
    c = df["Close"].astype(float)
    if not math.isfinite(float(c.iloc[-1])) or float(c.iloc[-1]) <= 0:
        return None
    date = df.index[-1].date()
    price = float(c.iloc[-1])
    ma20 = float(c.tail(20).mean())
    ma50 = float(c.tail(50).mean())
    ma200 = float(c.tail(200).mean())
    rsiD = float(rsi(c, 14).iloc[-1])
    histD = float(macd_hist(c).iloc[-1])
    roc20 = float((price / c.iloc[-21] - 1) * 100)
    vol = float(c.pct_change().tail(20).std() * np.sqrt(252) * 100)
    # Semana completa: sólo viernes cerrado, evita RSI semanal parcial.
    weekly = c.resample("W-FRI").last().dropna()
    weekly = weekly[weekly.index.date <= date]
    rsiW = number(rsi(weekly, 21).iloc[-1], 2) if len(weekly) > 24 else None
    histW = number(macd_hist(weekly, 6, 13, 5).iloc[-1], 4) if len(weekly) > 24 else None
    # Mensual: usar último mes totalmente finalizado.
    monthly = c.resample("ME").last().dropna()
    monthly = monthly[monthly.index.to_period("M") < pd.Period(date, freq="M")]
    rsiM = number(rsi(monthly, 21).iloc[-1], 2) if len(monthly)>24 else None
    histM = number(macd_hist(monthly, 6, 13, 5).iloc[-1], 4) if len(monthly)>24 else None
    adxD = number(adx(df).iloc[-1],2) if {"High", "Low", "Close"} <= set(df.columns) else None
    # Score replica conceptualmente los pesos documentados en Sheets (0-100).
    macd_pct = histD / price * 100
    histW_pct = ((histW or 0) / price) * 100
    score = (
        clamp(10 + 10 * (price / ma200 - 1) / .12, 0, 20)
        + clamp(7.5 + 7.5 * (price / ma50 - 1) / .08, 0, 15)
        + clamp(15 - abs(rsiD - 56) * .55, 0, 15)
        + clamp(7.5 + macd_pct * 18, 0, 15)
        + clamp(7.5 + roc20 * .55, 0, 15)
        + clamp(10 - vol * 10 / 90, 0, 10)
        + clamp(5 - abs((rsiW if rsiW is not None else 50) - 55) * .16, 0, 5)
        + clamp(2.5 + histW_pct * 15, 0, 5)
    )
    slope50 = float(c.tail(50).mean() - c.iloc[-55:-5].mean())
    if price > ma50 > ma200 and slope50 > 0:
        trend = "ALCISTA"
    elif price < ma50 < ma200 and slope50 < 0:
        trend = "BAJISTA"
    elif price > ma200 and price < ma50 or (price < ma200 and price > ma50):
        trend = "EN TRANSICIÓN"
    else:
        trend = "LATERAL"
    high20 = number(df["High"].iloc[-21:-1].max()) if "High" in df else None
    low20 = number(df["Low"].tail(20).min()) if "Low" in df else None
    avg_volume20 = number(df["Volume"].tail(20).mean(), 0) if "Volume" in df else None
    curr_volume = number(df["Volume"].iloc[-1], 0) if "Volume" in df else None
    prev = float(c.iloc[-2])
    near20 = -.01 <= price / ma20 - 1 <= .03 and price > prev
    breakout = high20 is not None and price > high20 and curr_volume is not None and avg_volume20 and curr_volume >= avg_volume20 * 1.1
    # No es stop de opción ni nivel ejecutivo: invalidación de referencia swing.
    invalid = number(min(ma50, low20) if low20 and trend != 'BAJISTA' else ma50, 2)
    risk = (price - invalid) if invalid is not None else None
    if risk and risk > 0 and price / invalid < 1.6:
        obj1 = round(price + 2 * risk, 2)
        obj2 = round(price + 3 * risk, 2)
    else:
        obj1 = obj2 = None
    volumes = volume_profile(df) if {"Volume", "High", "Low"} <= set(df.columns) else {}
    sma21 = sma21_priority(c)
    result = {
        "date":date.isoformat(), "price":number(price,3), "ma20":number(ma20,3),
        "ma50":number(ma50,3), "ma200":number(ma200,3),
        "rsi14d":number(rsiD,2), "rsi21w":rsiW, "rsi21m":rsiM,
        "macd_hist_d":number(histD,4), "macd_hist_w":histW, "macd_hist_m":histM,
        "roc20":number(roc20,2),"vol20":number(vol,2),"adx14":adxD,
        "score":int(round(score)),"trend":trend,
        "high20":high20,"low20":low20,"near20":near20,"breakout":bool(breakout),
        "invalid_usd":invalid,"target_2r":obj1,"target_3r":obj2,
    }
    result.update(volumes)
    result.update(sma21)
    result["rank_score"] = ranking_stock_21(result) if is_stock else ranking_score(result)
    result["asset_kind"] = "ACCION" if is_stock else "ETF / INDICE / NO CLASIFICADO"
    return result


def get_signal(row: dict | None, macro: str, fresh: bool) -> tuple[str,str,list[str]]:
    if row is None:
        return "SIN DATOS", "neutral", ["Cotización del subyacente USD no disponible o histórico insuficiente"]
    if not fresh:
        return "DATOS VIEJOS", "neutral", ["Último cierre demasiado antiguo; no tomar señal"]
    p, m20, m50, m200 = row["price"],row["ma20"],row["ma50"],row["ma200"]
    sc,rsiD,macdD=row["score"],row["rsi14d"],row["macd_hist_d"]
    reasons = [f"Tendencia {row['trend'].lower()}; score técnico {sc}/100", f"RSI14 diario {rsiD:.1f}, MACD diario {'positivo' if macdD>0 else 'negativo'}"]
    if row.get("cross_up21"):
        reasons.append("Cruce alcista confirmado del cierre diario sobre SMA21: priorizar vigilancia, no implica compra aislada")
    elif row.get("cross_down21"):
        reasons.append("Cruce bajista del cierre diario bajo SMA21: revisar estructura y proteger riesgo")
    bearish = p < m200 and macdD < 0 and rsiD < 40
    reduced = ((p < m50 and macdD < 0 and rsiD < 48) or sc < 30)
    bull = sc >= 73 and p > m50 > m200 and 46 <= rsiD <= 70 and macdD > 0
    entry = bool(row["near20"] or row["breakout"])
    if bearish:
        return "SALIR / EVITAR", "down", reasons+["Bajo SMA200 con RSI débil y MACD negativo; revisar tesis antes de mantener"]
    if reduced:
        return "REDUCIR / EVITAR", "down", reasons+["Debilidad de estructura; priorizar riesgo y esperar recuperación"]
    if macro != "FAVORABLE":
        if bull:
            return "ESPERAR MACRO", "wait", reasons+["Contexto SPY/QQQ/VIX no habilita nueva entrada"]
        return "ESPERAR", "wait", reasons+["Contexto de mercado no habilita compras agresivas"]
    if bull and entry:
        gate = "Ruptura de máximo 20 ruedas con volumen" if row["breakout"] else "Zona de SMA20 con reacción positiva"
        return "COMPRA CONDICIONAL", "up", reasons+[gate,"Confirmar entrada en diario/4H y ejecutar 2–3 tramos; sin orden automática"]
    if bull:
        return "VIGILAR COMPRA", "up", reasons+["Tendencia favorable, pero falta gatillo de entrada; no perseguir precio"]
    if sc>=54 and p>=m200:
        return "MANTENER / ESPERAR", "hold", reasons+["Estructura no rota; esperar señal nueva para ampliar"]
    return "ESPERAR", "wait", reasons+["No hay confluencia suficiente para entrada"]


def get_prices(symbols: list[str], now:datetime) -> dict[str,pd.DataFrame]:
    import yfinance as yf
    out = {}
    for off in range(0,len(symbols),18):
        subset=symbols[off:off+18]
        for retry in range(2):
            try:
                data=yf.download(subset,period="3y",interval="1d",group_by="ticker",auto_adjust=True,threads=6,progress=False,timeout=25,repair=False)
                if data is None or data.empty:
                    raise ValueError("Lote vacío")
                for sym in subset:
                    try:
                        d=data[sym].copy() if isinstance(data.columns,pd.MultiIndex) else data.copy()
                        if "Close" in d and d["Close"].notna().sum() >= 240:
                            out[sym] = d
                    except (KeyError, TypeError):
                        continue
                break
            except Exception as exc:
                logging.warning("Lote %d, intento %d: %s",off//18+1,retry+1,exc)
                time.sleep(3 * (retry+1))
        logging.info("Descargados %s/%s símbolos",len(out),len(symbols))
        time.sleep(.7)
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true",help="Validar catálogo y cálculos con series artificiales, sin generar cotizaciones")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    catalog=read_catalog()
    if args.check:
        rng=np.random.default_rng(3)
        idx=pd.bdate_range('2022-01-03',periods=860)
        c=pd.Series(100*np.exp(np.cumsum(rng.normal(.00045,.013,len(idx)))),index=idx)
        t=pd.DataFrame({'Close':c,'High':c*1.01,'Low':c*.99,'Open':c,'Volume':1_000_000},index=idx)
        sample=compute(t,datetime(2026,11,12,20,0,tzinfo=timezone.utc))
        assert sample and 0<=sample['score']<=100
        logging.info("CHECK OK: %d CEDEARs, %d mapeos USA; score ejemplo %s",len(catalog),sum(bool(x['subyacente_usa']) for x in catalog),sample['score'])
        return
    now=datetime.now(timezone.utc)
    symbols=sorted({x['subyacente_usa'] for x in catalog if x['subyacente_usa']} | set(SECTORS.values()) | {'SPY','QQQ','^VIX'})
    frames=get_prices(symbols,now)
    # Catálogo curado: excluimos ETFs y proxies frecuentes de la ponderación accionaria.
    # La clasificación es orientativa; no sustituye confirmación del tipo de instrumento.
    etfs=set(SECTORS.values()) | {
        "SPY","QQQ","TQQQ","SQQQ","SPXL","SOXL","SOXS","ARKK","IBB","XBI",
        "COPX","URA","URNM","GLD","GDX","GDXJ","SLV","USO","UNG","DBA",
        "CORN","SOYB","IBIT","ETHA","EEM","EWZ","EWJ","EFA","IWM","DIA",
        "TLT","IEF","HYG","BND","TAN","LIT","KWEB","FXI","BITO","XOP",
    }
    nonstocks={x["subyacente_usa"] for x in catalog if x["sector"]=="Índices y ETFs"}
    technical={}
    for sym,frame in frames.items():
        try:
            v=compute(frame,now,is_stock=(sym not in etfs and sym not in nonstocks))
            if v:technical[sym]=v
        except Exception as exc:
            logging.warning("Error de cálculo %s: %s",sym,exc)
    healthy=sum(sym in technical for sym in symbols if sym not in {'^VIX'})
    coverage=healthy/max(1,len(symbols)-1)
    if coverage < .60:
        raise SystemExit(f"Datos incompletos: cobertura {coverage:.0%}; no publicar snapshot nuevo. Se conserva la última publicación.")
    spy,qqq,vix = (technical.get(s) for s in ('SPY','QQQ','^VIX'))
    vixvalue=vix['price'] if vix else None
    macro = "NO VERIFICADO"
    if spy and qqq and vixvalue is not None:
        spy_ok = spy['price'] >= spy['ma50']
        qqq_ok = qqq['price'] >= qqq['ma50']
        if spy_ok and qqq_ok and vixvalue < 25:
            macro='FAVORABLE'
        elif (not spy_ok and not qqq_ok) or vixvalue>=30:
            macro='DEFENSIVO'
        else:
            macro='MIXTO'
    def is_fresh(v):
        if not v:return False
        d=datetime.fromisoformat(v['date']).date()
        # 5 días calendario admite finde largo, sin dar por fresco histórico antiguo.
        return 0 <= (now.astimezone(NY_TZ).date()-d).days <= 5
    if not all(is_fresh(v) for v in (spy,qqq,vix)):
        macro='NO VERIFICADO'
    assets=[]
    for item in catalog:
        us=item['subyacente_usa'].strip()
        val=technical.get(us) if us else None
        fresh=is_fresh(val)
        signal,tone,why = get_signal(val,macro,fresh)
        if ENABLE_CAUTION_ENTRIES and val:
            candidate, candidate_tone, note = cautious_signal(val,macro,vixvalue,fresh,signal)
            if candidate != signal:
                signal,tone=candidate,candidate_tone
                if note:why=why+[note]
        if not us:
            signal,tone,why='SIN SUBYACENTE USA','neutral',['No existe mapeo USD estadounidense confiable; no usar ticker homónimo']
        assets.append({
            'ticker':item['cedear'], 'usa':us or None, 'sector':item['sector'],
            'cedear_verificado':False, # Catálogo curado NO sustituye PDF oficial BYMA
            'estado_instrumento':'PENDIENTE VALIDAR RATIO Y LISTADO BYMA',
            'signal':signal,'tone':tone,'reasons':why,'data':val,
            'verificacion':item['observacion']
        })
    # Calendario opcional y parcial: no afirmar "sin balance" cuando falla Yahoo.
    earnings_dates, earnings_coverage = earnings_for_candidates(assets,now.astimezone(NY_TZ).date())
    for a in assets:
        sym=a["usa"]
        checked=bool(sym and sym in earnings_dates)
        a["earnings"]=earnings_dates.get(sym) if checked else None
        a["earnings_status"]=event_label(a["earnings"],checked)
    selection=top_five(assets,spy,macro)
    sectors=[]
    for sector,proxy in SECTORS.items():
        val=technical.get(proxy)
        signal,tone,why=get_signal(val,macro,is_fresh(val))
        sectors.append({'sector':sector,'proxy':proxy,'signal':signal,'tone':tone,'reasons':why,'data':val})
    result={
        'meta':{'generated_at_utc':now.isoformat(timespec='seconds'), 'generated_at_ar':now.astimezone(AR_TZ).isoformat(timespec='seconds'),
          'source':SOURCE,'universe_size':len(catalog),'mapped_us':sum(bool(x['subyacente_usa']) for x in catalog),
          'download_coverage':round(coverage*100,1), 'period':'3y / 1d',
          'rules_version':'1.1-sma21-rank-stock-v1-base-signals-unchanged',
          'earnings_coverage':earnings_coverage,
          'note':'SMA21 para acciones: 65% score anterior, 15% volumen, 20% SMA21. ETFs mantienen 85/15. Cruces son informativos, no compras nuevas. CEDEAR BYMA/ratio/spread sin validar.'},
        'macro':{'state':macro,'spy':spy,'qqq':qqq,'vix':vixvalue,
                 'reason':'Filtro SPY y QQQ vs SMA50, VIX <25 como habilitación inicial. Validar FED/BOJ/GEX antes de operar.'},
        'assets':assets,'sectors':sectors,'top5':selection
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    tmp.replace(OUT)
    logging.info('Escrito %s (%d activos, %d sectores, cobertura %.0f%%)',OUT,len(assets),len(sectors),coverage*100)

if __name__=='__main__':
    main()
