#!/usr/bin/env python3
"""A/B independiente rebote vs RSI<30 a ciegas. Ni ledger ni páginas.

Ambas estrategias reciben mismo OHLC t y entran open t+1. Comisión 5bps y
slippage 10bps por lado, DD por ticker (no cartera conjunta), datos ajustados.
No existe historial earnings validado: limitación explícita.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
from backtest import download,normalize
from actualizar import read_catalog
from rebound import candidate,indicators,PARAMS

NY=ZoneInfo("America/New_York")
DEFAULT="NVDA,AMD,PLTR,META,INTC,NVO,UNH,PYPL,PAGS,NU,COIN,GOOGL,MRNA,BA"

def build_signals(frame:pd.DataFrame,mode:str)->dict:
    f=normalize(frame)
    decisions={}
    for i in range(260,len(f)):
        day=f.index[i]
        snapshot=f.iloc[:i+1]
        if mode=="rebound":
            item=candidate(snapshot,"STOCK",None)
            if item:
                decisions[day]=item
        else:
            x=indicators(snapshot)
            if x is None or x["rsi"]>=30:continue
            stop=min(x["low"]-.08*x["atr"],x["price"]-1.7*x["atr"])
            risk=x["price"]-stop
            if risk<=0:continue
            decisions[day]={"entry_ref":x["price"],"stop_usd":stop,
                            "target_usd":x["price"]+2*risk,"rr":2,
                            "rsi14":x["rsi"],"signal_date":x["day"]}
    return decisions


def simulate(frame:pd.DataFrame,signals:dict,ticker:str,fee_bps=5,slip_bps=10,
             size_frac=.10,time_stop_sessions=7)->tuple[list[dict],pd.Series]:
    f=normalize(frame)
    cash,shares,entry,held=1.,0.,None,0
    costs=(fee_bps/10000,slip_bps/10000)
    trades,curve=[],{}
    def sell(i,price,reason):
        nonlocal cash,shares,entry,held
        price_exec=price*(1-costs[1])
        payout=shares*price_exec*(1-costs[0])
        cost=entry["spent"]
        net=payout-cost
        at_risk=shares*(entry["price"]-entry["stop"])
        cash+=payout
        trades.append({"ticker":ticker,"signal_date":entry["signal_date"],
                       "entry_date":entry["date"],"exit_date":str(f.index[i].date()),
                       "entry":round(entry["price"],4),"exit":round(price_exec,4),
                       "stop":round(entry["stop"],4),"target":round(entry["target"],4),
                       "reason":reason,"holding_sessions":held,
                       "net_r":round(net/at_risk,4) if at_risk>0 else None,
                       "net_return_pct":round(net/cost*100,3)})
        shares,entry,held=0.,None,0
    for i,day in enumerate(f.index):
        bar=f.iloc[i]
        if shares:
            held+=1
            # El stop temporal se ejecuta al OPEN de la rueda 8 (7 tenidas)
            # ANTES de inspeccionar High/Low futuros de esa misma vela.
            if float(bar["Open"])<=entry["stop"]:
                sell(i,float(bar["Open"]),"STOP GAP")
            elif held>time_stop_sessions:
                sell(i,float(bar["Open"]),"TIEMPO")
            elif float(bar["Low"])<=entry["stop"]:
                sell(i,entry["stop"],"STOP")
            elif float(bar["High"])>=entry["target"]:
                # Si target y stop ocurren en la misma vela, gana el STOP.
                sell(i,entry["target"],"TARGET")
        if not shares and i>0 and day!=f.index[0]:
            previous=f.index[i-1]
            d=signals.get(previous)
            if d and (not trades or trades[-1]["exit_date"]!=str(day.date())):
                open_=float(bar["Open"])
                stop=float(d["stop_usd"]);target=float(d["target_usd"])
                actual=open_*(1+costs[1])
                risk=actual-stop
                # Gap al alza que destruye RR>=2: no entrar en la apertura.
                if 0<risk and (target-actual)/risk>=2:
                    spent=min(size_frac,cash)
                    if spent>0:
                        shares=spent/(actual*(1+costs[0]))
                        cash-=spent
                        entry={"price":actual,"stop":stop,"target":target,
                               "date":str(day.date()),"signal_date":str(previous.date()),
                               "spent":spent}
                        held=0
                        # Si stop y objetivo coexisten el mismo día: stop primero.
                        if float(bar["Low"])<=stop:
                            sell(i,min(open_,stop),"STOP MISMA VELA")
                        elif float(bar["High"])>=target:
                            sell(i,target,"TARGET MISMA VELA")
        curve[day]=cash+shares*float(bar["Close"])
    if shares:
        sell(len(f)-1,float(f.iloc[-1]["Close"]),"CIERRE MUESTRA")
        curve[f.index[-1]]=cash
    return trades,pd.Series(curve,dtype=float)


def metrics(trades:list[dict],curve:pd.Series)->dict:
    rr=[x["net_r"] for x in trades if x["net_r"] is not None]
    losses=sorted(trades,key=lambda x:x["net_r"] if x["net_r"] is not None else 0)[:5]
    worst=streak=0
    for t in trades:
        if t["net_return_pct"]<0:streak+=1;worst=max(worst,streak)
        else:streak=0
    peak=curve.cummax()
    draw=(curve/peak-1).min()*100 if len(curve) else None
    return {"trades":len(trades),"hit_rate_pct":round(100*sum(t["net_return_pct"]>0 for t in trades)/len(trades),2) if trades else None,
            "mean_r":round(statistics.mean(rr),3) if rr else None,
            "max_drawdown_pct":round(abs(draw),3) if draw is not None else None,
            "worst_loss_r":round(min(rr),3) if rr else None,
            "worst_streak":worst,
            "worst_losses":losses}


def run(years=5,tickers=None,cache="backtest-out/rebound-market",out="backtest-out/rebound"):
    tickers=tickers or DEFAULT.split(",")
    universe={x["subyacente_usa"] for x in read_catalog()}
    tickers=[t for t in tickers if t in universe]
    data=download(sorted(tickers),years,cache)
    start=datetime.now(NY).date()-timedelta(days=round(365.25*years))
    report={"source":"Yahoo USD OHLCV ajustado","years":years,"as_of":datetime.now(NY).isoformat(),
            "experimental":True,"paper_rebound":False,
            "execution":"Cierre t -> OPEN t+1; stop conservador incluso si bar toca target",
            "costs":{"fee_bps_side":5,"slippage_bps_side":10},
            "limitations":["sesgo de supervivencia","no hay calendario earnings histórico",
                "max DD es de 1 ticker con size 10%, no cartera agregada",
                "sin selección óptima walk-forward ni disponibilidad BYMA/CCL"],
            "results":[]}
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    for symbol in tickers:
        if symbol not in data:continue
        f=normalize(data[symbol])
        f=f.loc[f.index>=pd.Timestamp(start)-pd.Timedelta(days=450)]
        if len(f)<300:continue
        analysis_days=f.index[f.index>=pd.Timestamp(start)]
        if len(analysis_days)<50:continue
        split=analysis_days[int(len(analysis_days)*.6)]
        result={"ticker":symbol,"split_date":str(split.date())}
        for name in ("blind","rebound"):
            sig=build_signals(f,name)
            # Prehistoria de indicadores es común, pero se ejecuta desde la
            # ventana temporal pedida y no se asignan trades previos.
            eligible={k:v for k,v in sig.items() if k>=pd.Timestamp(start)}
            trades,curve=simulate(f,eligible,symbol)
            oos=[t for t in trades if t["entry_date"]>=str(split.date())]
            result[name]={"signals":len(eligible),"full":metrics(trades,curve),
                          "out_of_sample":metrics(oos,curve.loc[split:])}
            with (output/f"{symbol}-{name}-trades.csv").open("w",newline="") as z:
                w=csv.DictWriter(z,fieldnames=["ticker","signal_date","entry_date","exit_date",
                      "entry","exit","stop","target","reason","holding_sessions",
                      "net_r","net_return_pct"])
                w.writeheader();w.writerows(trades)
        report["results"].append(result)
    def aggregate(name,part):
        vals=[x[name][part] for x in report["results"]]
        n=sum(x["trades"] for x in vals)
        rr=[(x["mean_r"],x["trades"]) for x in vals if x["mean_r"] is not None and x["trades"]]
        hits=[(x["hit_rate_pct"],x["trades"]) for x in vals if x["hit_rate_pct"] is not None and x["trades"]]
        return {"trades":n,
                "mean_r":round(sum(v*m for v,m in rr)/sum(m for _,m in rr),3) if rr else None,
                "hit_rate_pct":round(sum(v*m for v,m in hits)/sum(m for _,m in hits),2) if hits else None,
                "worst_loss_r":min((x["worst_loss_r"] for x in vals if x["worst_loss_r"] is not None),default=None),
                "worst_streak_ticker":max((x["worst_streak"] for x in vals),default=0),
                "worst_drawdown_ticker_pct":max((x["max_drawdown_pct"] or 0 for x in vals),default=None)}
    report["comparison"]={name:{part:aggregate(name,part) for part in ("full","out_of_sample")}
                          for name in ("blind","rebound")}
    report["worst_losses"]={}
    for name in ("blind","rebound"):
        losses=[trade for row in report["results"]
                for trade in row[name]["full"]["worst_losses"]]
        report["worst_losses"][name]=sorted(
            losses,key=lambda t:t["net_r"] if t["net_r"] is not None else 0)[:10]
    (output/"rebound-vs-rsi30.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=["# Rebound EXPERIMENTAL vs RSI<30 a ciegas","","Sin ventaja confirmada; earnings históricos NO cubiertos.",
           "| Variante / muestra | Señales cerradas | Acierto | R promedio | Peor pérdida R | Peor DD ticker | Peor racha |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for n in ("blind","rebound"):
        for p in ("full","out_of_sample"):
            x=report["comparison"][n][p]
            lines.append(f"| {n} / {p} | {x['trades']} | {x['hit_rate_pct']} | {x['mean_r']} | {x['worst_loss_r']} | {x['worst_drawdown_ticker_pct']} | {x['worst_streak_ticker']} |")
    for name in ("blind","rebound"):
        lines.append(f"\\n## Peores pérdidas {name} (R)")
        for t in report["worst_losses"][name][:5]:
            lines.append(f"- {t['ticker']} {t['entry_date']} → {t['exit_date']}: {t['net_r']}R ({t['reason']})")
    result="\n".join(lines)
    (output/"comparison.md").write_text(result)
    print(result)
    return report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--years",type=int,choices=range(5,11),default=5)
    p.add_argument("--tickers",default=DEFAULT)
    p.add_argument("--out",default="backtest-out/rebound")
    p.add_argument("--data-cache",default="backtest-out/rebound-market")
    a=p.parse_args()
    run(a.years,[s.strip().upper() for s in a.tickers.split(",") if s.strip()],a.data_cache,a.out)
if __name__=="__main__":main()
