"""Cartera simulada FORWARD sobre acciones USA en USD, nunca CEDEAR ARS.

Capital propio ficticio USD 2.000. No transmite órdenes. Stop móvil 8% sobre
promedio pagado/close máximo registrado, se ejecuta conservadoramente con gap.
Señal al cierre t -> orden a apertura de siguiente rueda completada.
Los datos del ledger se archivan fuera del código en artefactos de Actions.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any

import pandas as pd

VERSION="paper-sma21-v1"
INITIAL=2000.0
RESERVE=1000.0
MAX_POSITION=250.0
MAX_SLOTS=4
MAX_SECTOR_SLOTS=2
STOP_PCT=.08
FEE_BPS=5
SLIP_BPS=10
TRANCHES=(.40,.35,.25)
MAX_SESSION_HOLD=25
PRUDENT_BUDGET=120.0
PRUDENT_RESERVE=1400.0
PRUDENT_STOP_PCT=.06
PRUDENT_SLOTS=2
PRUDENT_SECTOR_SLOTS=1


def allocation_for(macro:str)->dict:
    if macro in ('DEFENSIVO','MIXTO'):
        return {'risk_mode':'PRUDENTE','budget':PRUDENT_BUDGET,'reserve':PRUDENT_RESERVE,
                'stop_pct':PRUDENT_STOP_PCT,'max_slots':PRUDENT_SLOTS,
                'max_sector_slots':PRUDENT_SECTOR_SLOTS}
    if macro=='FAVORABLE':
        return {'risk_mode':'NORMAL','budget':MAX_POSITION,'reserve':RESERVE,
                'stop_pct':STOP_PCT,'max_slots':MAX_SLOTS,
                'max_sector_slots':MAX_SECTOR_SLOTS}
    raise ValueError('Macro sin verificar: nuevas compras bloqueadas')


def new_ledger(last_session: str, generated_at: str) -> dict:
    """Sin operaciones inventadas al iniciar: fecha de corte es referencia."""
    return {
        "version":VERSION,"initial_capital":INITIAL,
        "created_at":generated_at,"last_session":last_session,
        "last_signal_session":last_session,"cash":INITIAL,
        "positions":{},"orders":[],"fills":[],"closed_trades":[],
        "cancelled":[],"equity_history":[{"date":last_session,"equity":INITIAL,"cash":INITIAL}],
        "note":"Inicio forward sin trades históricos; órdenes desde cierres futuros observados."
    }


def check_ledger(s: dict) -> None:
    if s.get("version")!=VERSION or s.get("initial_capital")!=INITIAL:
        raise ValueError("Versión/capital del track record incompatibles; no reiniciar")
    if not isinstance(s.get("positions"),dict) or not isinstance(s.get("closed_trades"),list):
        raise ValueError("Ledger incompleto; no reiniciar ni continuar ciegamente")
    if not 0<=float(s["cash"])<=1000000:
        raise ValueError("Saldo simulado inválido")


def number(v, n=2):
    return round(float(v),n)


def session_frame(df: pd.DataFrame) -> pd.DataFrame:
    f=df.copy()
    f.index=pd.to_datetime(f.index)
    if f.index.tz is not None:
        f.index=f.index.tz_convert("America/New_York").tz_localize(None)
    f.index=f.index.normalize()
    return f[~f.index.duplicated(keep="last")].sort_index()


def add_fill(s:dict, day:str, usa:str, price:float, qty:float, action:str,
             reason:str, total_usd:float) -> None:
    s["fills"].append({"id":len(s["fills"])+1,"date":day,"usa":usa,
                       "action":action,"price_usd":number(price,4),
                       "shares":number(qty,7),"amount_usd":number(total_usd,2),
                       "reason":reason})


def mark_stop(p:dict, close:float) -> None:
    """Trailing anclado SOLO al cierre conocido, vigente desde próxima rueda."""
    p["peak_close"]=max(float(p.get("peak_close",0)),close)
    p["stop_usd"]=number(max(p["stop_usd"],p["peak_close"]*(1-p.get("stop_pct",STOP_PCT))),4)


def close_position(s:dict, usa:str, day:str, price:float, reason:str) -> None:
    p=s["positions"].pop(usa)
    price_exec=price*(1-SLIP_BPS/10000)
    gross=p["shares"]*price_exec
    proceeds=gross*(1-FEE_BPS/10000)
    s["cash"]+=proceeds
    pnl=proceeds-p["spent"]
    n_sessions=int(p.get("sessions_held",0))
    s["closed_trades"].append({
        "usa":usa,"ticker":p["ticker"],"sector":p["sector"],
        "entry_signal_date":p["signal_day"],"entry_date":p["entry_date"],
        "exit_date":day,"holding_sessions":n_sessions,
        "calendar_days":(date.fromisoformat(day)-date.fromisoformat(p["entry_date"])).days,
        "shares":number(p["shares"],7),"tranches":p["tranche_count"],
        "avg_cost_usd":number(p["spent"]/p["shares"],4),
        "exit_usd":number(price_exec,4),"cost_usd":number(p["spent"],2),
        "proceeds_usd":number(proceeds,2),"pnl_usd":number(pnl,2),
        "return_pct":number(100*pnl/p["spent"],2),"reason":reason,
        "rules_version":VERSION
    })
    add_fill(s,day,usa,price_exec,p["shares"],"VENTA" if not reason.startswith("STOP") else "STOP LOSS",
             reason,proceeds)
    s["orders"]=[o for o in s["orders"] if o["usa"]!=usa]


def open_tranche(s:dict, order:dict, day:str, open_price:float) -> bool:
    usa=order["usa"]
    p=s["positions"].get(usa)
    stage=int(order["tranche"])
    if p is None:
        if stage!=1 or len(s["positions"])>=int(order.get("max_slots",MAX_SLOTS)):
            return False
        sector_count=sum(1 for x in s["positions"].values() if x["sector"]==order["sector"])
        if sector_count>=int(order.get("max_sector_slots",MAX_SECTOR_SLOTS)):return False
        p={"usa":usa,"ticker":order["ticker"],"sector":order["sector"],
           "entry_date":day,"signal_day":order["issued_day"],
           "budget":min(float(order.get("budget",MAX_POSITION)),MAX_POSITION),
           "risk_mode":order.get("risk_mode","NORMAL"),
           "reserve_usd":float(order.get("reserve_usd",RESERVE)),
           "stop_pct":float(order.get("stop_pct",STOP_PCT)),
           "shares":0.0,"spent":0.0,"tranche_count":0,"last_fill_day":"",
           "stop_usd":0.0,"peak_close":0.0,"sessions_held":0}
    if stage!=p["tranche_count"]+1 or day==p["last_fill_day"]:
        return False
    # Retiene USD 1000 siempre, con USD 20 máximo de pérdida teórica al stop.
    remaining=min(p["budget"]*TRANCHES[stage-1],
                  max(0,s["cash"]-max(p["reserve_usd"],float(order.get("reserve_usd",p["reserve_usd"])))))
    if remaining<10:return False
    effective=open_price*(1+SLIP_BPS/10000)
    qty=remaining/(effective*(1+FEE_BPS/10000))
    if qty<=0:return False
    cost=qty*effective*(1+FEE_BPS/10000)
    p["shares"]+=qty
    p["spent"]+=cost
    p["tranche_count"]=stage
    p["last_fill_day"]=day
    p["stop_usd"]=number(max(p["stop_usd"],(p["spent"]/p["shares"])*(1-p["stop_pct"])),4)
    s["cash"]-=cost
    s["positions"][usa]=p
    add_fill(s,day,usa,effective,qty,f"COMPRA {stage}/3",order.get("reason","SMA21"),cost)
    return True


def evaluate_entry(a:dict, market:str, vix:float|None) -> tuple[bool,str]:
    """Variante experimental EXCLUSIVA del papel simulado, no modifica señales web."""
    d=a.get("data")
    if not d or d.get("asset_kind")!="ACCION" or not a.get("usa"):
        return False,""
    if market=="NO VERIFICADO" or vix is None or vix>=25:
        return False,""
    e=a.get("earnings") or {}
    if e.get("days_until") is not None and 0<=e["days_until"]<=7:
        return False,"BALANCE EN 7 DÍAS"
    if a.get("signal","").startswith(("SALIR","REDUCIR","DATOS","SIN")):
        return False,""
    p,ma21,ma200=(d.get(k) for k in ("price","ma21","ma200"))
    if not all(x is not None and x>0 for x in (p,ma21,ma200)):
        return False,""
    if not(p>ma21 and p>ma200):return False,""
    score,rank=d.get("score",0),d.get("rank_score",0)
    rsi,macd=d.get("rsi14d"),d.get("macd_hist_d")
    if score<65 or rank<68 or rsi is None or not(46<=rsi<=70) or macd is None or macd<=0:
        return False,""
    if d.get("dollar_volume20") is None or d["dollar_volume20"]<5_000_000:
        return False,""
    if d.get("rvol20") is None or d["rvol20"]<.80 or d.get("obv_up10") is not True:
        return False,""
    if d.get("stretch_atr20") is None or d["stretch_atr20"]>1.8:
        return False,""
    trigger=bool(d.get("cross_up21")) or a.get("signal")=="COMPRA CONDICIONAL"
    if not trigger:return False,""
    if market!="FAVORABLE":
        if score<76 or d.get("rsi21w") is None or d["rsi21w"]<52 or (
           d.get("macd_hist_w") is None or d["macd_hist_w"]<=0):
            return False,""
    return True,("CRUCE ALCISTA SMA21" if d.get("cross_up21") else "COMPRA CONDICIONAL") + (
        " · MACRO EN PRECAUCIÓN" if market!="FAVORABLE" else "")


def equity_at(s:dict, frames:dict, day:str)->tuple[float,list[str]]:
    pending=[]
    eq=s["cash"]
    for usa,p in s["positions"].items():
        f=frames.get(usa)
        if f is not None:
            f=session_frame(f)
            hist=f.loc[:day,"Close"].dropna()
        else:
            hist=pd.Series(dtype=float)
        if len(hist):
            px=float(hist.iloc[-1])
            p["last_mark"]=px
            p["last_mark_day"]=str(hist.index[-1].date())
        else:
            px=p.get("last_mark")
        if px is None:
            pending.append(usa)
        else:
            eq+=p["shares"]*float(px)
            if p.get("last_mark_day")!=day:pending.append(usa)
    return eq,pending


def process_ledger(s:dict, frames:dict[str,pd.DataFrame], assets:list[dict],
                   macro:str, vix:float|None, latest_day:str)->dict:
    """Procesa sólo ruedas completas nuevas; no reconstruye operaciones del pasado."""
    check_ledger(s)
    spy=frames.get("SPY")
    if spy is None:raise ValueError("No hay SPY para calendario de sesiones")
    days=[str(x.date()) for x in session_frame(spy).index
          if s["last_session"] < str(x.date()) <= latest_day]
    for day in days:
        # Las órdenes se crean al cierre anterior; por eso corren al primer OPEN posterior.
        next_orders=[]
        for o in s["orders"]:
            usa=o["usa"]
            frame=frames.get(usa)
            bar=None
            if frame is not None:
                daily=session_frame(frame)
                at=daily.loc[day:day]
                if len(at):bar=at.iloc[0]
            if o["issued_day"]>=day:
                next_orders.append(o);continue
            if bar is None or pd.isna(bar.get("Open")) or float(bar["Open"])<=0:
                if (date.fromisoformat(day)-date.fromisoformat(o["issued_day"])).days<=7:
                    next_orders.append(o)
                else:
                    s["cancelled"].append({"date":day,"usa":usa,"reason":"No hubo OPEN confirmado"})
                continue
            if o["side"]=="BUY":
                if not open_tranche(s,o,day,float(bar["Open"])):
                    s["cancelled"].append({"date":day,"usa":usa,"reason":"Límite de efectivo, sectores o tramos"})
            elif o["side"]=="SELL" and usa in s["positions"]:
                close_position(s,usa,day,float(bar["Open"]),o["reason"])
        # close_position cancela pedidos del símbolo: normalizar usando posiciones nuevas.
        s["orders"]=[o for o in next_orders if o["side"]!="BUY" or o["tranche"]>1 or o["usa"] not in s["positions"] or o["issued_day"]==day]
        for usa in list(s["positions"]):
            p=s["positions"][usa]
            f=frames.get(usa)
            if f is None:continue
            at=session_frame(f).loc[day:day]
            if at.empty:continue
            row=at.iloc[0]
            open_px,low_px,close_px=(float(row[k]) for k in ("Open","Low","Close"))
            if not all(math.isfinite(x) and x>0 for x in (open_px,low_px,close_px)):
                continue
            p["sessions_held"]+=1
            if low_px<=p["stop_usd"]:
                stop_fill=min(open_px,p["stop_usd"])
                close_position(s,usa,day,stop_fill,"STOP LOSS -8% / TRAILING (gap contemplado)")
                continue
            mark_stop(p,close_px)
        value,missing=equity_at(s,frames,day)
        s["equity_history"].append({"date":day,"equity":number(value,2),
                                     "cash":number(s["cash"],2),
                                     "unpriced":missing})
        s["last_session"]=day

    # Solo el cierre más reciente que realmente fue procesado puede generar órdenes.
    # En el arranque el último día ya figura como procesado: NO inventar fills previos.
    if s["last_session"]==latest_day and s["last_signal_session"]<latest_day:
        today_assets={a["usa"]:a for a in assets if a.get("usa") and (a.get("data") or {}).get("date")==latest_day}
        for usa,p in list(s["positions"].items()):
            a=today_assets.get(usa)
            if not a:continue
            d=a["data"]
            avg=p["spent"]/p["shares"]
            down2=False
            f=frames.get(usa)
            if f is not None:
                c=session_frame(f).loc[:latest_day,"Close"]
                if len(c)>=23:
                    from radar_features import sma21_priority
                    prev_21=float(c.iloc[-22:-1].mean())
                    down2=bool(c.iloc[-1]<d.get("ma21",0) and c.iloc[-2]<prev_21)
            reason=None
            if a["signal"].startswith(("SALIR","REDUCIR")):
                reason="VENTA POR SEÑAL TÉCNICA"
            elif down2 and (d.get("macd_hist_d") or 0)<0:
                reason="VENTA: DOS CIERRES BAJO SMA21 Y MACD NEGATIVO"
            elif d["price"]>=avg*(1+2*p.get("stop_pct",STOP_PCT)):
                reason="VENTA: OBJETIVO +16% APROX. (2R)"
            elif p["sessions_held"]>=MAX_SESSION_HOLD and d["price"]<avg*1.03:
                reason="VENTA POR TIEMPO: 25 RUEDAS SIN AVANCE"
            if reason:
                s["orders"].append({"side":"SELL","usa":usa,"ticker":p["ticker"],
                                    "issued_day":latest_day,"reason":reason})
                continue
            stage=p["tranche_count"]+1
            if stage<=3 and p["last_fill_day"]<latest_day and not any(o["usa"]==usa for o in s["orders"]):
                if d["price"]>d["ma21"] and (d.get("macd_hist_d") or 0)>0 and (
                    (stage==2 and (d.get("rvol20") or 0)>=.75) or (
                        stage==3 and d["price"]>avg*1.02 and d.get("obv_up10") is True)):
                    s["orders"].append({"side":"BUY","usa":usa,"ticker":p["ticker"],
                                        "sector":p["sector"],"tranche":stage,"issued_day":latest_day,
                                        "reason":"AGREGAR TRAMO TRAS CONFIRMACIÓN SMA21",
                                        "reserve_usd":max(p["reserve_usd"],allocation_for(macro)["reserve"]) if macro!="NO VERIFICADO" else p["reserve_usd"]})
        # Nuevas entradas: máximo 4 posiciones, concentración sectorial <=2.
        candidates=[]
        for a in assets:
            d=a.get("data") or {}
            if d.get("date")!=latest_day:continue
            allowed,reason=evaluate_entry(a,macro,vix)
            if allowed:
                candidates.append((d.get("rank_score",0),d.get("cross_up21",False),a,reason))
        candidates.sort(key=lambda x:(x[1],x[0]),reverse=True)
        policy=allocation_for(macro) if macro!="NO VERIFICADO" else None
        open_syms=set(s["positions"])|{o["usa"] for o in s["orders"]}
        sector_slots={}
        for p in s["positions"].values():
            sector_slots[p["sector"]]=sector_slots.get(p["sector"],0)+1
        for _,_,a,reason in candidates:
            usa=a["usa"]
            if policy is None or usa in open_syms or len(open_syms)>=policy["max_slots"] or s["cash"]<=policy["reserve"]+policy["budget"]*TRANCHES[0]:
                continue
            sector=a["sector"]
            if sector_slots.get(sector,0)>=policy["max_sector_slots"]:continue
            if s["cash"]<=policy["reserve"]+10:break
            s["orders"].append({"side":"BUY","usa":usa,"ticker":a["ticker"],
                                "sector":sector,"tranche":1,"issued_day":latest_day,
                                "budget":policy["budget"],"reserve_usd":policy["reserve"],
                                "stop_pct":policy["stop_pct"],"max_slots":policy["max_slots"],
                                "max_sector_slots":policy["max_sector_slots"],
                                "risk_mode":policy["risk_mode"],"reason":reason})
            open_syms.add(usa)
            sector_slots[sector]=sector_slots.get(sector,0)+1
        s["last_signal_session"]=latest_day
    return s


def public_summary(s:dict,frames:dict[str,pd.DataFrame])->dict:
    check_ledger(s)
    equity,missing=equity_at(s,frames,s["last_session"])
    closed=s["closed_trades"]
    gains=[t for t in closed if t["pnl_usd"]>0]
    peak=max([INITIAL]+[q["equity"] for q in s["equity_history"]]+[equity])
    dd=(equity/peak-1)*100 if peak>0 else 0
    open_positions=[]
    for p in s["positions"].values():
        px=p.get("last_mark")
        cost=p["spent"]
        unreal=px*p["shares"]-cost if px is not None else None
        open_positions.append({"usa":p["usa"],"ticker":p["ticker"],"sector":p["sector"],
                               "entry_date":p["entry_date"],"tranches":p["tranche_count"],
                               "shares":number(p["shares"],7),"avg_cost_usd":number(cost/p["shares"],4),
                               "last_price_usd":number(px,4) if px is not None else None,
                               "stop_usd":p["stop_usd"],"market_value_usd":number(px*p["shares"],2) if px is not None else None,
                               "unrealized_usd":number(unreal,2) if unreal is not None else None,
                               "sessions_held":p["sessions_held"],
                               "risk_mode":p.get("risk_mode","NORMAL"),
                               "stop_pct":round(100*p.get("stop_pct",STOP_PCT),1)})
    return {
        "version":VERSION,"is_simulated":True,"start":s["created_at"],
        "last_closed_session":s["last_session"],"initial_capital_usd":INITIAL,
        "cash_usd":number(s["cash"]), "equity_usd":number(equity),
        "return_pct":number(100*(equity/INITIAL-1)),
        "realized_pnl_usd":number(sum(t["pnl_usd"] for t in closed)),
        "max_drawdown_pct":number(min([0]+[(x["equity"]/max([INITIAL]+[z["equity"] for z in s["equity_history"][:i+1]])-1)*100 for i,x in enumerate(s["equity_history"]) ])),
        "closed_count":len(closed),"win_rate_pct":number(100*len(gains)/len(closed)) if closed else None,
        "open_positions":open_positions,"pending_orders":s["orders"],
        "closed_trades":closed[-100:],"fills":s["fills"][-200:],
        "equity_history":s["equity_history"][-150:],"unpriced_symbols":missing,
        "assumptions":{"stop_pct":8,"prudent_stop_pct":6,
             "prudent_max_position_usd":PRUDENT_BUDGET,
             "prudent_reserve_usd":PRUDENT_RESERVE,
             "prudent_max_positions":PRUDENT_SLOTS,
             "fee_bps_each_side":FEE_BPS,
             "slippage_bps_each_side":SLIP_BPS,"reserve_usd":RESERVE,
             "max_position_usd":MAX_POSITION,"max_positions":MAX_SLOTS,
             "entry_tranches":[40,35,25],"time_stop_sessions":MAX_SESSION_HOLD,
             "entry_rule":"SMA21 confirmado/volumen: macro adverso habilita tamaño y stop reducidos, OPEN t+1",
             "data":"USD subyacente USA, OHLC ajustados Yahoo; NO operaciones reales"},
        "disclaimer":"Simulación informativa, órdenes no reales; cierres y gaps revisables, sin precios/CCL/spread CEDEAR BYMA. Histórico desde creación; no reconstruye trades previos."
    }
