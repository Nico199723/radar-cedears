"""Motor de señal único CANDIDATO. No se activa en main sin backtest A/B.

Score visible=rank_score: los score técnico y heredado son diagnósticos.
El riesgo del mercado decide size; nunca descalifica sólo por SPY/QQQ<SMA50.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from collections import Counter

RULES_VERSION="2.0-unified-decision-active"
BUY_FLOOR=70.0
PRIORITY_FLOOR=75.0
REDUCE_FLOOR=35.0
EXIT_FLOOR=18.0
MIN_DOLLAR_VOLUME=5_000_000.0
VIX_STRESS_LIMIT=30.0

BUY_SIGNALS={"COMPRA CONDICIONAL","COMPRA CON PRECAUCIÓN"}
WATCH_SIGNALS={"VIGILAR COMPRA · SCORE","VIGILAR COMPRA · GATILLO"}
OPPORTUNITY_SIGNALS=BUY_SIGNALS|WATCH_SIGNALS


def is_opportunity(signal:str)->bool:
    # Capturar también VIGILAR COMPRA legado, no sólo etiquetas nuevas.
    return signal in BUY_SIGNALS or signal.startswith("VIGILAR COMPRA")


@dataclass(frozen=True)
class Decision:
    signal:str
    tone:str
    score_decision:float|None
    vetoes:tuple[str,...]
    gate:str
    macro:str
    reasons:tuple[str,...]
    rules_version:str=RULES_VERSION

    def public(self)->dict:
        return {"signal":self.signal,"tone":self.tone,
                "score_decision":self.score_decision,
                "vetoes":list(self.vetoes),"gate":self.gate,
                "macro":self.macro,"reasons":list(self.reasons),
                "rules_version":self.rules_version}


def numeric(row:dict, field:str)->float|None:
    try:
        number=float(row.get(field))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def hard_vetoes(row:dict, macro:str, vix:float|None,
                fresh:bool, earnings:dict|None=None)->tuple[str,...]:
    veto=[]
    if not fresh:veto.append("CIERRE SIN VIGENCIA")
    p,ma200,ma21=(numeric(row,k) for k in ("price","ma200","ma21"))
    if p is None or ma200 is None or p<=ma200:
        veto.append("PRECIO BAJO SMA200")
    if p is None or ma21 is None or p<=ma21:
        veto.append("PRECIO BAJO SMA21")
    macd=numeric(row,"macd_hist_d")
    if macd is None or macd<=0:veto.append("MACD DIARIO NO POSITIVO")
    if (numeric(row,"dollar_volume20") or 0)<MIN_DOLLAR_VOLUME:
        veto.append("LIQUIDEZ USD INSUFICIENTE")
    rsi=numeric(row,"rsi14d")
    if rsi is None or rsi<=35 or rsi>=75:
        veto.append("RSI DIARIO EXTREMO")
    if not row.get("rs_verified"):
        veto.append("RS SPY/QQQ SIN VERIFICAR")
    week=numeric(row,"macd_hist_w")
    if week is None or week<0:
        veto.append("MACD SEMANAL NO CONFIRMADO")
    if row.get("obv_up10") is not True:
        veto.append("OBV SIN CONFIRMAR")
    if macro not in ("FAVORABLE","MIXTO","DEFENSIVO"):
        veto.append("MACRO SIN VERIFICAR")
    if vix is None or not math.isfinite(float(vix)) or float(vix)>=VIX_STRESS_LIMIT:
        veto.append("VIX NO VERIFICADO O >=30")
    days=(earnings or {}).get("days_until")
    if isinstance(days,(int,float)) and 0<=days<=7:
        veto.append("BALANCE EN 7 DIAS")
    # No añadir un veto por SPY/QQQ bajo SMA50: se reduce el tamaño.
    return tuple(veto)


def decide(row:dict|None, macro:str, vix:float|None,
           fresh:bool, earnings:dict|None=None)->Decision:
    if row is None:
        return Decision("SIN DATOS","neutral",None,("SIN HISTÓRICO",),"",macro,("Falta histórico",))
    score=numeric(row,"rank_score")
    if score is not None:
        # El umbral usa el valor exacto, no redondear 69.99 a 70.
        score=max(0,min(100,score))
    veto=hard_vetoes(row,macro,vix,fresh,earnings)
    if not fresh:
        return Decision("DATOS VIEJOS","neutral",score,veto,"",macro,("Último cierre no vigente",))
    if score is None:
        return Decision("SIN DATOS","neutral",None,veto,"",macro,("Score de decisión no calculable",))
    p,m50,m200=(numeric(row,k) for k in ("price","ma50","ma200"))
    macd=numeric(row,"macd_hist_d")
    rsi=numeric(row,"rsi14d")
    # Riesgo de tenencia prevalece sobre el score: los vetos sólo bloquean nuevas compras.
    if (score<=EXIT_FLOOR or
        (p is not None and m200 is not None and p<m200 and
         macd is not None and macd<0 and rsi is not None and rsi<40)):
        return Decision("SALIR / EVITAR","down",score,veto,"",macro,("Invalidación estructural o score crítico",))
    if (score<=REDUCE_FLOOR or
        (p is not None and m50 is not None and p<m50 and
         macd is not None and macd<0 and rsi is not None and rsi<48)):
        return Decision("REDUCIR / EVITAR","down",score,veto,"",macro,("Deterioro técnico; priorizar reducción",))
    if veto:
        signal="SCORE ALTO · VETADO" if score>=BUY_FLOOR else "HOLD / ESPERAR"
        return Decision(signal,"hold",score,veto,"",macro,
                        ("Score alto no habilita compra frente a veto: "+", ".join(veto),))
    if score<BUY_FLOOR:
        return Decision("HOLD / ESPERAR","hold",score,(),"",macro,
                        (f"Score {score:.1f} < mínimo {BUY_FLOOR:g}",))
    # Gatillos son puertas de ejecución, separadas del puntaje.
    trigger=("CRUCE SMA21" if row.get("cross_up21") else
             "RETROCESO SMA20" if row.get("near20") else
             "RUPTURA CON VOLUMEN" if row.get("breakout") else "")
    if not trigger and score<PRIORITY_FLOOR:
        return Decision("VIGILAR COMPRA · GATILLO","watch",score,(),"PENDIENTE",macro,
                        ("Score suficiente; esperar gatillo concreto",))
    if not trigger and score>=PRIORITY_FLOOR:
        trigger="PRIORIDAD >=75 / CONTINUACIÓN CONTROLADA"
    if macro=="FAVORABLE" and score<PRIORITY_FLOOR and trigger:
        return Decision("COMPRA CONDICIONAL","up",score,(),trigger,macro,
                        ("Entrada condicionada con macro favorable; no orden real",))
    # Si el setup es sólo por score elevado o la macro es defensiva,
    # se permite exclusivamente en tamaño reducido.
    return Decision("COMPRA CON PRECAUCIÓN","caution",score,(),trigger,macro,
                    ("Capital reducido; stop condicionado y ejecución t+1",))


def audit_consistency(assets:list[dict], *, require_score:bool=True)->list[dict]:
    """Un solo origen de verdad. Fallar cerrado si hay compras incoherentes.

    Se aplica a la variante A/B antes de tocar producción. La ficha
    debe declarar los vetoes que justifican una ausencia de entrada.
    """
    violations=[]
    for a in assets:
        ticker=a.get("ticker") or a.get("usa") or "?"
        signal=a.get("signal","")
        data=a.get("data") or {}
        score=a.get("score_decision",data.get("rank_score"))
        vetoes=tuple(a.get("vetoes") or ())
        if require_score and score is None and is_opportunity(signal):
            violations.append({"ticker":ticker,"reason":"opportunity_without_score"})
            continue
        if is_opportunity(signal) and score is not None and score<BUY_FLOOR:
            violations.append({"ticker":ticker,"reason":"opportunity_below_floor",
                               "score":score})
        if is_opportunity(signal) and vetoes:
            violations.append({"ticker":ticker,"reason":"opportunity_with_hard_veto",
                               "vetoes":list(vetoes)})
        if score is not None and score>=BUY_FLOOR and vetoes and is_opportunity(signal):
            violations.append({"ticker":ticker,"reason":"high_score_veto_marked_opportunity"})
        if signal=="SCORE ALTO · VETADO" and not vetoes:
            violations.append({"ticker":ticker,"reason":"veto_label_without_veto"})
        expected=data.get("rank_score")
        if score is not None and expected is not None and abs(float(score)-float(expected))>.011:
            violations.append({"ticker":ticker,"reason":"display_vs_decision_mismatch"})
        # El score técnico o el heredado NO pueden reemplazar rank_score.
    return violations


def top_five_by_decision(assets:list[dict],limit:int=5)->list[dict]:
    """Top5 ordenado estrictamente por el mismo score que decide."""
    pool=[x for x in assets if x.get("signal") in OPPORTUNITY_SIGNALS
          and not x.get("vetoes") and x.get("score_decision") is not None
          and x["score_decision"]>=BUY_FLOOR]
    pool.sort(key=lambda x:(-float(x["score_decision"]),x.get("ticker","")))
    return [{"ticker":x.get("ticker"),"usa":x.get("usa"),
             "score_decision":x["score_decision"],"signal":x["signal"]}
            for x in pool[:limit]]
