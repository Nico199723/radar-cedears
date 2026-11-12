#!/usr/bin/env python3
"""Backtest exploratorio de las reglas DE PRODUCCIÓN, sin modificar señales.

La señal se calcula al cierre de t con actualizar.compute/get_signal.
Una compra o salida confirmada al cierre se ejecuta al OPEN de t+1.
Stop en la sesión siguiente o posterior, con gap adverso a precio de apertura.
Datos: OHLCV ajustados de EE. UU. en USD (Yahoo/yfinance), nunca CEDEAR ARS.

Limitaciones: universo superviviente actual, sin historial de earnings, sin órdenes
parciales, ni spreads BYMA/CCL; no usar el resultado como expectativa garantizada.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar import compute, get_signal, read_catalog
from radar_features import cautious_signal

NY = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[1]
EXIT_SIGNALS = {"SALIR / EVITAR", "REDUCIR / EVITAR"}


@dataclass
class Trade:
    ticker: str
    signal_date: str
    entry_date: str
    exit_date: str
    entry: float
    stop: float
    exit: float
    exit_reason: str
    net_return_pct: float
    net_r: float


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Ordenar velas diarias; rechazar OHLC defectuosos (sin completar con futuro)."""
    f = df.copy()
    f.index = pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index = f.index.tz_convert(NY).tz_localize(None)
    f.index = f.index.normalize()
    f = f[~f.index.duplicated(keep="last")].sort_index()
    needed = ("Open", "High", "Low", "Close", "Volume")
    if not set(needed).issubset(f.columns):
        raise ValueError("Faltan columnas OHLCV: " + str(set(needed) - set(f.columns)))
    f = f[list(needed)].apply(pd.to_numeric, errors="coerce").dropna(subset=list(needed))
    f = f[(f["Open"] > 0) & (f["Close"] > 0) & (f["High"] >= f["Low"])]
    return f


def close_time(index: pd.Timestamp) -> datetime:
    return datetime.combine(index.date(), time(16, 15), tzinfo=NY)


def macro_history(spy: pd.DataFrame, qqq: pd.DataFrame, vix: pd.DataFrame) -> dict:
    """Sólo información observable al cierre de la misma fecha."""
    spy, qqq, vix = normalize(spy), normalize(qqq), normalize(vix)
    out = {}
    dates = spy.index.intersection(qqq.index).intersection(vix.index)
    for day in dates:
        s, q = spy.loc[:day, "Close"], qqq.loc[:day, "Close"]
        if len(s) < 200 or len(q) < 200:
            continue
        vv = float(vix.loc[day, "Close"])
        if s.iloc[-1] > s.tail(50).mean() and q.iloc[-1] > q.tail(50).mean() and vv < 25:
            state = "FAVORABLE"
        elif (s.iloc[-1] < s.tail(50).mean() and q.iloc[-1] < q.tail(50).mean()) or vv >= 30:
            state = "DEFENSIVO"
        else:
            state = "MIXTO"
        out[day] = state
    return out


def historical_decisions(frame: pd.DataFrame, macros: dict, start_date: str,
                         variant: str = 'baseline', vix_by_day: dict | None = None) -> dict:
    """Reutilizar EXACTAMENTE compute/get_signal de producción, con serie truncada en t."""
    frame = normalize(frame)
    decisions = {}
    for pos in range(240, len(frame)):
        day = frame.index[pos]
        if day.strftime("%Y-%m-%d") < start_date:
            continue
        if day not in macros:
            continue
        row = compute(frame.iloc[:pos + 1], close_time(day))
        if row is None:
            continue
        signal, _, _ = get_signal(row, macros[day], True)
        if variant == "prudente":
            candidate, _, _ = cautious_signal(row,macros[day],
                                    (vix_by_day or {}).get(day),True,signal)
            if candidate == "COMPRA CON PRECAUCIÓN":
                signal = candidate
        decisions[day] = {"signal": signal, "stop": row["invalid_usd"]}
    return decisions


def simulate(frame: pd.DataFrame, decisions: dict, ticker: str,
             fee_bps: float = 5.0, slippage_bps: float = 10.0) -> tuple[list[Trade], pd.Series]:
    """Una única posición larga; sin lookahead, sin apalancamiento y costo de ambos lados."""
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("Comisiones/slippage no pueden ser negativos")
    frame = normalize(frame)
    cash, shares, opened, basis = 1.0, 0.0, None, None
    fee, slip = fee_bps / 10000, slippage_bps / 10000
    trades, curve = [], {}

    def sell(day, execution, reason):
        nonlocal cash, shares, opened, basis
        effective = execution * (1 - slip)
        cash = shares * effective * (1 - fee)
        net_profit = cash - basis["spent"]
        at_risk = shares * (basis["entry"] - basis["stop"])
        trades.append(Trade(
            ticker=ticker, signal_date=basis["signal_date"],
            entry_date=basis["entry_date"], exit_date=day.strftime("%Y-%m-%d"),
            entry=round(basis["entry"], 5), stop=round(basis["stop"], 5),
            exit=round(effective, 5), exit_reason=reason,
            net_return_pct=round((cash / basis["spent"] - 1) * 100, 5),
            net_r=round(net_profit / at_risk, 5) if at_risk > 0 else float("nan"),
        ))
        shares, opened, basis = 0.0, None, None

    for i, day in enumerate(frame.index):
        bar = frame.iloc[i]
        if i:
            yesterday = frame.index[i - 1]
            decision = decisions.get(yesterday, {})
            sig = decision.get("signal")
            if shares and sig in EXIT_SIGNALS:
                sell(day, float(bar["Open"]), "SEÑAL AL CIERRE PREVIO")
            elif not shares and sig in ("COMPRA CONDICIONAL","COMPRA CON PRECAUCIÓN"):
                stop = decision.get("stop")
                entry = float(bar["Open"]) * (1 + slip)
                if stop is not None and math.isfinite(float(stop)) and 0 < float(stop) < entry:
                    spent = cash
                    shares = cash / (entry * (1 + fee))
                    cash = 0.0
                    opened, basis = day, {
                        "spent": spent, "entry": entry, "stop": float(stop),
                        "signal_date": yesterday.strftime("%Y-%m-%d"),
                        "entry_date": day.strftime("%Y-%m-%d")
                    }
        if shares and float(bar["Low"]) <= basis["stop"]:
            # Gap abajo del stop: no asumir ejecución milagrosa al nivel de stop.
            sell(day, min(float(bar["Open"]), basis["stop"]), "STOP/GAP")
        curve[day] = cash + shares * float(bar["Close"])

    # Liquidación de posición abierta al último cierre; explícita en la salida.
    if shares:
        last = frame.index[-1]
        sell(last, float(frame.iloc[-1]["Close"]), "CIERRE DE MUESTRA")
        curve[last] = cash
    return trades, pd.Series(curve, dtype=float)


def max_drawdown(curve: pd.Series) -> float:
    return float((curve / curve.cummax() - 1).min() * 100) if len(curve) else 0.0


def metrics(trades: list[Trade], curve: pd.Series) -> dict:
    rr = [x.net_r for x in trades if math.isfinite(x.net_r)]
    return {
        "n_senales_ejecutadas": len(trades),
        "win_rate_pct": round(sum(x.net_return_pct > 0 for x in trades) / len(trades) * 100, 2) if trades else None,
        "r_promedio": round(float(np.mean(rr)), 4) if rr else None,
        "expectancy_r": round(float(np.mean(rr)), 4) if rr else None,
        "max_drawdown_pct": round(max_drawdown(curve), 2),
        "retorno_neto_pct": round((float(curve.iloc[-1]) - 1) * 100, 2) if len(curve) else None,
    }


def benchmark(benchmark_frame: pd.DataFrame, index: pd.DatetimeIndex,
              fee_bps=5.0, slippage_bps=10.0) -> dict:
    f = normalize(benchmark_frame).reindex(index).dropna(subset=["Open", "Close"])
    if len(f) < 2:
        return {"retorno_neto_pct": None, "max_drawdown_pct": None}
    fee, slip = fee_bps / 10000, slippage_bps / 10000
    entry = float(f.iloc[0]["Open"]) * (1 + slip) * (1 + fee)
    eq = f["Close"] / entry
    eq.iloc[-1] *= (1 - slip) * (1 - fee)
    return {"retorno_neto_pct": round((float(eq.iloc[-1]) - 1) * 100, 2),
            "max_drawdown_pct": round(max_drawdown(eq), 2)}


def download(symbols: list[str], years: int, cache_dir: str | None = None) -> dict[str, pd.DataFrame]:
    """Una única descarga y caché INMUTABLE compartida por ambas variantes del test.

    El manifest se escribe al final. Si existe, jamás se reconsulta Yahoo para
    evitar diferencias temporales y universos inconsistentes entre ejecuciones.
    """
    cache=Path(cache_dir) if cache_dir else None
    if cache and (cache/"manifest.json").exists():
        manifest=json.loads((cache/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("symbols")!=symbols or manifest.get("years")!=years:
            raise ValueError("Caché corresponde a otros parámetros/universo")
        out={}
        for ticker in manifest["downloaded"]:
            fname=cache/(ticker.replace("^","_IDX_")+".csv")
            out[ticker]=normalize(pd.read_csv(fname,index_col=0,parse_dates=True))
        return out
    import yfinance as yf
    start=(datetime.now(NY).date()-timedelta(days=int(years*365.25)+550)).isoformat()
    downloaded={}
    for off in range(0,len(symbols),12):
        batch=symbols[off:off+12]
        # Yahoo puede fallar para un ticker concreto: los faltantes se registran,
        # y no deben reaparecer solamente en la segunda estrategia.
        data=yf.download(batch,start=start,interval="1d",group_by="ticker",
                         auto_adjust=True,threads=2,progress=False,timeout=30)
        for ticker in batch:
            try:
                f=data[ticker].copy() if isinstance(data.columns,pd.MultiIndex) else data.copy()
                if len(f.dropna(subset=["Close"]))>=240:
                    downloaded[ticker]=normalize(f)
            except (KeyError,TypeError,ValueError):
                pass
    if cache:
        cache.mkdir(parents=True,exist_ok=True)
        for ticker,frame in downloaded.items():
            frame.to_csv(cache/(ticker.replace("^","_IDX_")+".csv"))
        (cache/"manifest.json").write_text(json.dumps({
            "symbols":symbols,"years":years,"downloaded":list(downloaded),
            "missing":[s for s in symbols if s not in downloaded],
            "downloaded_at":datetime.now(NY).isoformat()
        },indent=2),encoding="utf-8")
    return downloaded


def main():
    p = argparse.ArgumentParser(description="Backtest BASELINE: señales actuales, sin cambiar reglas")
    p.add_argument("--tickers", default="AMZN,NVDA,MSFT,META,GOOGL,JPM,TGT,COPX,IREN,TQQQ",
                   help="Subyacentes USA USD separados por coma; no símbolos CEDEAR locales")
    p.add_argument("--years", type=int, choices=range(5, 11), metavar="[5..10]", default=10)
    p.add_argument("--variant", choices=("baseline","prudente"), default="baseline")
    p.add_argument("--fee-bps", type=float, default=5.0)
    p.add_argument("--slippage-bps", type=float, default=10.0)
    p.add_argument("--out", default="backtest-out", help="Carpeta fuera de docs/")
    p.add_argument("--data-cache", default=None, help="Directorio de OHLCV compartido")
    args = p.parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    if any(t not in {x["subyacente_usa"] for x in read_catalog()} for t in tickers):
        p.error("Usar sólo símbolos de subyacentes USA incluidos en config/universo.csv")
    frames = download(sorted(set(tickers + ["SPY", "QQQ", "^VIX"])), args.years,args.data_cache)
    required = ("SPY", "QQQ", "^VIX")
    if any(x not in frames for x in required):
        raise SystemExit("No hay macro completa SPY/QQQ/VIX; NO ejecutar señales de compra")
    macro = macro_history(*(frames[t] for t in required))
    vix_by_day = normalize(frames["^VIX"])["Close"].to_dict()
    start_date = (datetime.now(NY).date() - timedelta(days=int(args.years * 365.25))).isoformat()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    totals = []
    for symbol in tickers:
        if symbol not in frames:
            totals.append({"ticker": symbol, "estado": "SIN HISTÓRICO"})
            continue
        f = frames[symbol]
        decisions = historical_decisions(f, macro, start_date,variant=args.variant,vix_by_day=vix_by_day)
        valid = f.loc[f.index >= pd.Timestamp(start_date)]
        trades, curve = simulate(valid, decisions, symbol, args.fee_bps, args.slippage_bps)
        row = {"ticker": symbol, "estado": "OK", "inicio":str(curve.index[0].date()),
               "fin":str(curve.index[-1].date()), **metrics(trades, curve),
               "SPY_buy_hold": benchmark(frames["SPY"], curve.index, args.fee_bps, args.slippage_bps),
               "QQQ_buy_hold": benchmark(frames["QQQ"], curve.index, args.fee_bps, args.slippage_bps)}
        # Split temporal 60/40: trades etiquetados por fecha de entrada (sin optimizar).
        split = curve.index[int(len(curve) * .6)]
        for label, selection in (("in_sample", [x for x in trades if x.entry_date < split.strftime("%Y-%m-%d")]),
                                 ("out_of_sample", [x for x in trades if x.entry_date >= split.strftime("%Y-%m-%d")])):
            vals = [x.net_r for x in selection if math.isfinite(x.net_r)]
            row[label] = {"operaciones": len(selection),
                          "expectancy_r": round(float(np.mean(vals)),4) if vals else None,
                          "acierto_pct": round(sum(x.net_return_pct>0 for x in selection)/len(selection)*100,2) if selection else None}
        totals.append(row)
        with (output / f"{symbol.replace('^','')}-trades.csv").open("w",encoding="utf-8", newline="") as fh:
            w=csv.DictWriter(fh, fieldnames=list(Trade.__dataclass_fields__))
            w.writeheader()
            for trade in trades:
                w.writerow(asdict(trade))
        print(f"{symbol}: {row['n_senales_ejecutadas']} trades, R medio {row['r_promedio']}, DD {row['max_drawdown_pct']}%")
    report={"version":"macro-"+args.variant+"-comparacion-2026-11-12",
            "as_of":datetime.now(NY).isoformat(),
            "source":"Yahoo Finance/yfinance OHLC ajustado USD; datos sujetos a revisión",
            "variant":args.variant,"years_requested":args.years,"fee_bps_per_side":args.fee_bps,
            "slippage_bps_per_side":args.slippage_bps,
            "limitations":["sesgo supervivencia (universo actual)", "earnings NO aplicado en código actual",
                "sin tramos 40/35/25", "sin CEDEAR ARS/CCL", "sin validación de Koncorde",
                "cierre semanal parcial replicado desde producción", "sin sensibilidad de umbrales todavía"],
            "results":totals}
    (output / "resumen.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Reporte: "+str(output / "resumen.json"))


if __name__ == "__main__":
    main()
