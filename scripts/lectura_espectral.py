"""Lectura espectral de un activo (módulo de referencia: lectura_espectral.py).

Idea central: en vez de una checklist de vetos blanco/negro, cada activo se lee como una
historia: qué pasó con las medias, hace cuántas ruedas, cuánto subió, qué tan lejos está y
hacia dónde giran RSI y MACD. Todo es continuo (0..1) y se combina en un score 0..100.

Sólo hay dos frenos duros, y son de integridad de datos (no de opinión técnica):
  - histórico insuficiente o precio inválido  -> SIN DATOS
  - liquidez inoperable (< USD 1 M diarios)   -> NO OPERABLE
Todo lo demás (macro, balances, liquidez baja, sobrecompra, MACD semanal negativo...)
son FRICCIONES: restan puntos o reducen el tamaño sugerido, pero nunca vetan.

Módulo de referencia: sólo depende de pandas/numpy. Los umbrales de bandas son iniciales y
deben calibrarse con el backtest A/B del repo antes de gobernar señales reales.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from spectrum_config import *  # Única configuración de la variante espectral.

# ----------------------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------------------
def _lg(x: float) -> float:
    x = max(-30.0, min(30.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _runs(mask: np.ndarray) -> list[list]:
    """Codificación por rachas de un array booleano: [[valor, largo], ...] de viejo a nuevo."""
    out: list[list] = []
    for v in mask:
        v = bool(v)
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def _finite(*vals) -> bool:
    return all(v is not None and math.isfinite(float(v)) for v in vals)


# ----------------------------------------------------------------------------------------
# indicadores
# ----------------------------------------------------------------------------------------
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi_wilder(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return (100 - 100 / (1 + au / ad)).where(ad.ne(0), 100).where(au.ne(0) | ad.ne(0), 50)


def macd_hist(c: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    line = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    return line - line.ewm(span=sig, adjust=False).mean()


# ----------------------------------------------------------------------------------------
# 1) La historia del activo: hechos medibles, sin juicios
# ----------------------------------------------------------------------------------------
def story(df: pd.DataFrame, bench: pd.Series | None = None) -> dict | None:
    """Hechos del activo con su contexto temporal. df: Open/High/Low/Close/Volume diarios."""
    if df is None or len(df) < MIN_BARS:
        return None
    c = df["Close"].astype(float)
    h, l = df["High"].astype(float), df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df else pd.Series(np.nan, index=df.index)
    ma21, ma50, ma200 = (c.rolling(n).mean() for n in (21, 50, 200))
    a = float(atr(df).iloc[-1])
    price = float(c.iloc[-1])
    if not _finite(price, a, ma21.iloc[-1], ma50.iloc[-1], ma200.iloc[-1]) or a <= 0 or price <= 0:
        return None

    # --- cuánto hace que está arriba/abajo de la SMA21, y qué había antes
    mask = (c > ma21).values[-160:]
    runs = _runs(mask)
    cur_above, cur_len = runs[-1]
    prev_len = runs[-2][1] if len(runs) >= 2 else 0
    age_above = cur_len if cur_above else 0
    age_below = 0 if cur_above else cur_len
    prior_below = prev_len if cur_above else 0          # ruedas abajo antes de recuperar
    prior_above = 0 if cur_above else prev_len          # ruedas arriba antes de perderla
    gain_atr = 0.0
    if cur_above and len(c) > age_above:
        ref = float(c.iloc[-(age_above + 1)])
        gain_atr = (price - ref) / a

    # --- piso en la SMA200 (toque y rebote)
    w = 40
    ratio = (l.iloc[-w:] / ma200.iloc[-w:] - 1.0)
    i_min = int(np.argmin(ratio.values))
    touch_depth = float(ratio.iloc[i_min])               # <=0.04: llegó a 4% de la SMA200 o menos
    low_at_touch = float(l.iloc[-w:].iloc[i_min])
    f = {
        "price": price,
        "atr14": a,
        "ma21": float(ma21.iloc[-1]), "ma50": float(ma50.iloc[-1]), "ma200": float(ma200.iloc[-1]),
        "d21_atr": (price - float(ma21.iloc[-1])) / a,
        "d50_atr": (price - float(ma50.iloc[-1])) / a,
        "d200_pct": price / float(ma200.iloc[-1]) - 1.0,
        "above21": bool(cur_above),
        "age_above21": age_above, "age_below21": age_below,
        "prior_below21": prior_below, "prior_above21": prior_above,
        "gain_since_cross_atr": gain_atr,
        "run_up20_pct": price / float(c.iloc[-21]) - 1.0,
        "slope21_atr": (float(ma21.iloc[-1]) - float(ma21.iloc[-6])) / a,
        "slope50_atr": (float(ma50.iloc[-1]) - float(ma50.iloc[-11])) / a,
        "slope200_pct20": (float(ma200.iloc[-1]) / float(ma200.iloc[-21]) - 1.0) * 100.0,
        "touched200": bool(touch_depth <= TOUCH200_TOLERANCE),
        "bars_since_touch200": int(w - 1 - i_min),
        "touch200_depth": touch_depth,
        "rebound_from_low_atr": (price - low_at_touch) / a,
    }

    # --- indicadores con perspectiva (nivel + dirección)
    r = rsi_wilder(c)
    f["rsi14"] = float(r.iloc[-1])
    f["rsi_slope3"] = float(r.iloc[-1] - r.iloc[-4])
    hist = macd_hist(c, 12, 26, 9)
    f["macd_hist_atr"] = float(hist.iloc[-1]) / a
    f["macd_slope3_atr"] = float(hist.iloc[-1] - hist.iloc[-4]) / a
    f["macd_rising_bars"] = int(next((i for i, x in enumerate(np.diff(hist.values)[::-1]) if x <= 0), 10))
    f["macd_hist_w_n"] = f["macd_slope_w_n"] = None
    if isinstance(c.index, pd.DatetimeIndex):
        wc = c.resample("W-FRI").last().dropna()
        wc = wc[wc.index <= c.index[-1]]  # Sólo semanas cerradas, igual que compute().
        if len(wc) >= 40:
            hw = macd_hist(wc, 6, 13, 5)
            wr = float(wc.diff().abs().rolling(14).mean().iloc[-1])
            if _finite(wr) and wr > 0:
                f["macd_hist_w_n"] = float(hw.iloc[-1]) / wr
                f["macd_slope_w_n"] = float(hw.iloc[-1] - hw.iloc[-2]) / wr

    # --- flujo y fuerza relativa (opcionales: si faltan, quedan neutros)
    f["obv_slope10"] = f["rvol"] = f["rs20"] = f["dollar_volume20"] = None
    if v.notna().sum() > 40:
        obv = (np.sign(c.diff().fillna(0)) * v.fillna(0)).cumsum()
        avg = float(v.rolling(20).mean().iloc[-1])
        if avg > 0:
            f["obv_slope10"] = float(obv.iloc[-1] - obv.iloc[-11]) / (avg * 10)
            f["rvol"] = float(v.iloc[-1]) / float(v.iloc[-21:-1].mean())
        f["dollar_volume20"] = float((c * v).rolling(20).mean().iloc[-1])
    if bench is not None and len(bench):
        b = bench.reindex(c.index).ffill()
        rs = c / b
        if _finite(rs.iloc[-1], rs.iloc[-21]) and float(rs.iloc[-21]) != 0:
            f["rs20"] = float(rs.iloc[-1] / rs.iloc[-21] - 1.0)
    optional = ('obv_slope10','rvol','rs20','dollar_volume20','macd_hist_w_n','macd_slope_w_n')
    for key in optional:
        if f[key] is not None and not _finite(f[key]): f[key] = None
    if not all(_finite(value) for key,value in f.items() if key not in optional):
        return None
    return f


# ----------------------------------------------------------------------------------------
# 2) Macro como viento (modula; no veta)
# ----------------------------------------------------------------------------------------
def macro_wind(spy: pd.DataFrame | None, qqq: pd.DataFrame | None,
               vix: pd.Series | None = None) -> dict:
    """Viento macro en [-1, +1]. SPY/QQQ bajo sus medias o VIX alto empujan en contra, pero
    sólo cambian unos puntos del score y el tamaño sugerido. Dato faltante = neutral."""
    comps = []
    for df in (spy, qqq):
        if df is None or len(df) < MACRO_MIN_BARS:
            continue
        c = df["Close"].astype(float)
        a = float(atr(df).iloc[-1])
        p = float(c.iloc[-1])
        if not _finite(a, p) or a <= 0:
            continue
        d21 = (p - float(c.rolling(21).mean().iloc[-1])) / a
        d50 = (p - float(c.rolling(50).mean().iloc[-1])) / a
        comps.append(0.5 * _lg(d21 / MACRO_DISTANCE_SCALES[0]) + 0.5 * _lg(d50 / MACRO_DISTANCE_SCALES[1]))
    idx = float(np.mean(comps)) if comps else 0.5
    vix_comp, vix_last = 0.5, None
    if vix is not None and len(vix) >= 6 and _finite(vix.iloc[-1], vix.iloc[-6]):
        vix_last = float(vix.iloc[-1])
        level = _lg((VIX_CENTER - vix_last) / VIX_LEVEL_SCALE)
        trend = _lg(-(vix_last - float(vix.iloc[-6])) / VIX_TREND_SCALE)   # VIX bajando = alivio
        vix_comp = VIX_LEVEL_WEIGHT * level + (1-VIX_LEVEL_WEIGHT) * trend
    wind = 2.0 * (INDEX_WEIGHT * idx + (1-INDEX_WEIGHT) * vix_comp) - 1.0
    size = MACRO_MIN_SIZE + (1-MACRO_MIN_SIZE) * (wind + 1.0) / 2.0                       # 0.50 (peor) .. 1.00 (mejor)
    label = "A FAVOR" if wind > MACRO_LABEL_CUT else "EN CONTRA" if wind < -MACRO_LABEL_CUT else "NEUTRAL"
    return {"wind": round(wind, 3), "size_mult": round(size, 3), "label": label,
            "vix": vix_last, "verified": len(comps) == 2 and vix_last is not None}


# ----------------------------------------------------------------------------------------
# 3) Componentes continuos
# ----------------------------------------------------------------------------------------
def _freshness(n: int) -> float:
    """Valor del evento según su edad: 1-3 ruedas = pleno; decae a 0.45 en 10 y 0.25 en 20."""
    if n <= FRESH_FULL:
        return 1.0
    if n <= FRESH_MID:
        return 1.0 - (n - FRESH_FULL) * ((1 - FRESH_MID_VALUE) / (FRESH_MID - FRESH_FULL))
    if n <= FRESH_OLD:
        return FRESH_MID_VALUE - (n - FRESH_MID) * ((FRESH_MID_VALUE - FRESH_OLD_VALUE) / (FRESH_OLD - FRESH_MID))
    return FRESH_FLOOR


def _runway(d21: float, gain_atr: float) -> float:
    """Recorrido que queda: cuanto más lejos de la media y más subió desde el cruce, menos."""
    r1 = _lg(-(d21 - RUNWAY_DISTANCE) / RUNWAY_DISTANCE_SCALE)
    r2 = _lg(-(gain_atr - RUNWAY_GAIN) / RUNWAY_GAIN_SCALE)
    return math.sqrt(r1 * r2)


def _structure(f: dict) -> float:
    p200 = _lg(f["d200_pct"] / STRUCTURE_SCALES[0])           # sobre/bajo SMA200 sin corte duro
    p50 = _lg(f["d50_atr"] / STRUCTURE_SCALES[1])
    s50 = _lg(f["slope50_atr"] / STRUCTURE_SCALES[2])
    s200 = _lg(f["slope200_pct20"] / STRUCTURE_SCALES[3])
    return sum(w*v for w,v in zip(STRUCTURE_WEIGHTS,(p200,p50,s50,s200)))


def _is_rebound_from_200(f: dict) -> bool:
    # Rebote "de verdad": tocó la zona de la SMA200, sigue cerca de ella (no se fue +12%),
    # no está extendido sobre la SMA21 y la SMA200 no cae con fuerza (evita el rebote de gato muerto).
    return (f["touched200"] and REBOUND_MIN_AGE <= f["bars_since_touch200"] <= REBOUND_MAX_AGE
            and f["rebound_from_low_atr"] >= REBOUND_MIN_ATR and f["slope200_pct20"] > REBOUND_MIN_SLOPE
            and f["d200_pct"] < REBOUND_MAX_DISTANCE and f["d21_atr"] < REBOUND_MAX_EXTENSION
            and (f["rsi_slope3"] > 0 or f["above21"]))


def _timing_above(f: dict) -> tuple[str, float]:
    d21, g = f["d21_atr"], f["gain_since_cross_atr"]
    run = _runway(d21, g)
    bonus = PRIOR_BASE + (1-PRIOR_BASE) * _clip(f["prior_below21"] / PRIOR_WINDOW)   # recuperar tras mucho tiempo abajo vale más
    t = _freshness(f["age_above21"]) * run * bonus
    if f["age_above21"] > FRESH_MID:
        t = max(t, MATURE_FLOOR * run)                               # tendencia sana madura: no es cero
    if d21 >= EXTENDED_DISTANCE or g >= EXTENDED_GAIN:
        stage = "EXTENDIDA"
    elif f["age_above21"] <= FRESH_FULL:
        stage = "RECUPERACIÓN FRESCA"
    elif f["age_above21"] <= FRESH_MID:
        stage = "TENDENCIA JOVEN"
    else:
        stage = "TENDENCIA MADURA"
    if _is_rebound_from_200(f):
        stage = "REBOTE DESDE SMA200"
        t = max(t, REBOUND_ABOVE_BASE + REBOUND_BONUS * _clip((f["rebound_from_low_atr"] - REBOUND_MIN_ATR) / REBOUND_SCALE))
    return stage, _clip(t)


def _timing_below(f: dict) -> tuple[str, float]:
    if _is_rebound_from_200(f):
        return "REBOTE DESDE SMA200", _clip(REBOUND_BELOW_BASE + REBOUND_BONUS * _clip((f["rebound_from_low_atr"] - REBOUND_MIN_ATR) / REBOUND_SCALE))
    pullback = (f["d50_atr"] > 0 and f["slope50_atr"] > 0 and f["age_below21"] <= PULLBACK_MAX_AGE and f["d21_atr"] > PULLBACK_MAX_DEPTH)
    if pullback:
        return "RETROCESO EN TENDENCIA", PULLBACK_TIMING
    if f["age_below21"] <= FRESH_FULL:
        return "RECIÉN PERDIDA SMA21", LOST_TIMING
    if f["age_below21"] <= WEAK_MAX_AGE:
        return "DEBILITADA", WEAK_TIMING
    return "BAJO SMA21 PROLONGADO", PROLONGED_TIMING





def _timing(f: dict) -> tuple[str, float]:
    """Momento del activo. Cruzar la SMA21 es un evento, pero a centímetros de la media no
    puede haber un salto de golpe: ahí se mezclan la lectura 'arriba' y la lectura 'abajo'."""
    d21 = f["d21_atr"]
    if abs(d21) >= NEAR_MA_ATR:
        return _timing_above(f) if f["above21"] else _timing_below(f)
    if f["above21"]:
        up = (_timing_above(f))
        dn = _timing_below({**f, "above21": False, "age_below21": 1, "prior_above21": f["age_above21"]})
    else:
        up = _timing_above({**f, "above21": True, "age_above21": 1, "prior_below21": f["age_below21"]})
        dn = _timing_below(f)
    w = _lg(d21 / NEAR_MA_BLEND_SCALE)                                   # 0.5 justo sobre la media
    stage = up[0] if w >= 0.5 else dn[0]
    return stage, _clip(w * up[1] + (1 - w) * dn[1])


_RSI_PTS = RSI_PTS


def _momentum(f: dict) -> float:
    base = float(np.interp(f["rsi14"], *_RSI_PTS))
    lift = _lg(f["rsi_slope3"] / RSI_SLOPE_SCALE)
    rsi_c = RSI_LEVEL_WEIGHT * base + (1-RSI_LEVEL_WEIGHT) * lift
    macd_d = 0.5 * _lg(f["macd_hist_atr"] / MACD_D_LEVEL_SCALE) + 0.5 * _lg(f["macd_slope3_atr"] / MACD_D_SLOPE_SCALE)
    if f["macd_hist_w_n"] is None:
        macd_w = 0.5
    else:
        macd_w = 0.5 * _lg(f["macd_hist_w_n"] / MACD_W_LEVEL_SCALE) + 0.5 * _lg((f["macd_slope_w_n"] or 0.0) / MACD_W_SLOPE_SCALE)
    return sum(w*v for w,v in zip(MOMENTUM_WEIGHTS,(rsi_c,macd_d,macd_w)))


def _flow(f: dict) -> float:
    rs = 0.5 if f["rs20"] is None else _lg(f["rs20"] / RS_SCALE)
    obv = 0.5 if f["obv_slope10"] is None else _lg(f["obv_slope10"] / OBV_SCALE)
    rvol = 0.5 if f["rvol"] is None else _lg((f["rvol"] - 1.0) / RVOL_SCALE)
    return sum(w*v for w,v in zip(FLOW_WEIGHTS,(rs,obv,rvol)))


def _deterioration(f: dict, struct: float, mom: float) -> float:
    pressure = 0.5 * _lg(-f["d50_atr"] / STRUCTURE_SCALES[1]) + 0.5 * _lg(-f["slope50_atr"] / STRUCTURE_SCALES[2])
    fresh_loss = 0.0
    if not f["above21"] and f["prior_above21"] >= LOSS_PRIOR_MIN:
        fresh_loss = _freshness(f["age_below21"]) * LOSS_RECENCY_WEIGHT       # perder la 21 tras una racha larga pesa más
    det = sum(w*v for w,v in zip(DETERIORATION_WEIGHTS,(1-struct,1-mom,pressure,fresh_loss)))
    return 100.0 * _clip(det)


# ----------------------------------------------------------------------------------------
# 4) Lectura completa
# ----------------------------------------------------------------------------------------
@dataclass
class Reading:
    signal: str
    score: float | None
    stage: str
    conviction: str
    size_mult: float
    deterioration: float | None
    components: dict
    frictions: list[str] = field(default_factory=list)
    narrative: list[str] = field(default_factory=list)
    macro: dict = field(default_factory=dict)
    rules_version: str = RULES_VERSION

    def public(self) -> dict:
        return {"signal": self.signal, "score_decision": self.score, "stage": self.stage,
                "conviction": self.conviction, "size_mult": self.size_mult,
                "deterioration": self.deterioration, "components": self.components,
                "frictions": self.frictions, "narrative": self.narrative,
                "macro": self.macro, "rules_version": self.rules_version}


def _narrative(f: dict, stage: str, mom_note: list[str]) -> list[str]:
    out = []
    if f["above21"]:
        out.append(f"Sobre la SMA21 hace {f['age_above21']} ruedas"
                   + (f" (venía {f['prior_below21']} ruedas abajo)" if f["prior_below21"] >= 5 else "")
                   + f", a {f['d21_atr']:+.1f} ATR de la media y {f['gain_since_cross_atr']:+.1f} ATR desde el cruce.")
    else:
        out.append(f"Bajo la SMA21 hace {f['age_below21']} ruedas, a {f['d21_atr']:+.1f} ATR de la media.")
    if f["touched200"] and f["bars_since_touch200"] <= 30:
        out.append(f"Tocó la zona de la SMA200 hace {f['bars_since_touch200']} ruedas y rebotó "
                   f"{f['rebound_from_low_atr']:.1f} ATR desde el mínimo.")
    out.append(f"{f['d200_pct']:+.1%} frente a la SMA200; SMA50 {'subiendo' if f['slope50_atr'] > 0 else 'bajando'}.")
    out.extend(mom_note)
    return out


def read(df: pd.DataFrame, bench: pd.Series | None = None, macro: dict | None = None,
         earnings_days: int | None = None, fresh: bool = True) -> Reading:
    return read_story(story(df, bench), macro, earnings_days, fresh)


def signal_for(score: float, deterioration: float) -> str:
    """La señal usa EXACTAMENTE el score publicado, con deterioro explícito para salidas."""
    if deterioration >= DETERIORATION_EXIT:
        return "SALIR / EVITAR"
    if deterioration >= DETERIORATION_REDUCE and score < BAND_CAUTION:
        return "REDUCIR / EVITAR"
    if score >= BAND_BUY:
        return "COMPRA CONDICIONAL"
    if score >= BAND_CAUTION:
        return "COMPRA CON PRECAUCIÓN"
    if score >= BAND_WATCH:
        return "VIGILAR COMPRA · SCORE"
    return "HOLD / ESPERAR"


def read_story(f: dict | None, macro: dict | None = None,
               earnings_days: int | None = None, fresh: bool = True) -> Reading:
    if f is None or not fresh:
        return Reading("SIN DATOS" if f is None else "DATOS VIEJOS", None, "SIN DATOS", "—", 0.0,
                       None, {}, ["Histórico insuficiente o cierre sin vigencia"])
    dv = f["dollar_volume20"]
    if dv is not None and dv < HARD_MIN_DOLLAR_VOLUME:
        return Reading("NO OPERABLE", None, "ILÍQUIDO", "—", 0.0, None, {},
                       [f"Liquidez inoperable (USD {dv:,.0f} diarios)"])

    stage, timing = _timing(f)
    struct, mom, flow = _structure(f), _momentum(f), _flow(f)
    comps = {"estructura": struct, "momento": timing, "impulso": mom, "flujo": flow}
    raw = 100.0 * sum(WEIGHTS[k] * comps[k] for k in WEIGHTS)

    macro = normalized_macro(macro)
    score = max(0.0, min(100.0, raw + MACRO_SCORE_SWING * macro["wind"]))
    score = round(score, SCORE_DECIMALS)
    det = round(_deterioration(f, struct, mom), SCORE_DECIMALS)

    # ---- fricciones: restan tamaño, nunca vetan
    size, frictions = macro["size_mult"], []
    if macro["label"] == "EN CONTRA":
        frictions.append(f"Macro en contra (viento {macro['wind']:+.2f}): tamaño ×{macro['size_mult']:.2f}")
    if not macro.get("verified"):
        frictions.append("Macro sin verificar: neutral, tamaño reducido")
    elif macro.get("vix") is not None and macro["vix"] >= VIX_STRESS:
        frictions.append("VIX alto: neutral, tamaño reducido")
    if dv is None:
        size *= LOW_LIQUIDITY_SIZE
        frictions.append("Liquidez sin verificar: tamaño reducido")
    if dv is not None and dv < SOFT_MIN_DOLLAR_VOLUME:
        size *= LOW_LIQUIDITY_SIZE
        frictions.append(f"Liquidez baja: tamaño ×{LOW_LIQUIDITY_SIZE:.2f}")
    if earnings_days is not None and 0 <= earnings_days <= EARNINGS_WINDOW:
        k = EARNINGS_IMMINENT_SIZE if earnings_days <= EARNINGS_IMMINENT else EARNINGS_SIZE
        size *= k
        frictions.append(f"Balance en {earnings_days} días: tamaño ×{k:.2f}")
    if f["rsi14"] >= OVERBOUGHT_RSI:
        size *= OVERBOUGHT_SIZE
        frictions.append(f"RSI {f['rsi14']:.0f} sobrecomprado: tamaño ×{OVERBOUGHT_SIZE:.2f}")
    if f["macd_hist_w_n"] is not None and f["macd_hist_w_n"] < 0:
        frictions.append("MACD semanal aún negativo (ya descontado en el score)")
    size = round(_clip(size, 0.0, 1.0), 2)

    mom_note = []
    mom_note.append(f"RSI {f['rsi14']:.0f} y {'subiendo' if f['rsi_slope3'] > 0 else 'bajando'} (3 ruedas).")
    sign = "positivo" if f["macd_hist_atr"] > 0 else "negativo"
    way = "girando al alza" if f["macd_slope3_atr"] > 0 else "perdiendo fuerza"
    mom_note.append(f"MACD diario {sign} y {way}.")
    mom_note.append(f"Macro {macro['label'].lower()}: tamaño sugerido ×{size:.2f} del tramo normal.")

    signal = signal_for(score, det)

    spread = max(comps.values()) - min(comps.values())
    conviction = ("ALTA" if score >= CONVICTION_HIGH and spread < CONVICTION_SPREAD else
                  "MEDIA" if score >= BAND_CAUTION else "BAJA")
    return Reading(signal, round(score, 1), stage, conviction, size, round(det, 1),
                   {k: round(v, 3) for k, v in comps.items()}, frictions,
                   _narrative(f, stage, mom_note), macro)


def normalized_macro(macro: dict | None) -> dict:
    m = dict(macro or {})
    vix = m.get("vix")
    if not m.get("verified") or not _finite(vix):
        return {**m, "wind": 0.0, "size_mult": UNVERIFIED_SIZE,
                "label": "NEUTRAL", "verified": False, "vix": None}
    if vix >= VIX_STRESS:
        return {**m, "wind": 0.0, "size_mult": STRESS_SIZE, "label": "NEUTRAL"}
    return {**m, "wind": _clip(m.get("wind", 0), -1, 1),
            "size_mult": _clip(m.get("size_mult", UNVERIFIED_SIZE))}
