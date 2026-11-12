#!/usr/bin/env python3
"""Comparación consistente entre baseline y macro prudente (mismas ruedas y costos).

Agregación ponderada por N operaciones; no constituye walk-forward multi-ventana.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def aggregate(data:dict)->dict:
    rows=[r for r in data["results"] if r.get("estado")=="OK"]
    def period(name):
        r=[x[name] for x in rows if name in x]
        n=sum(x["operaciones"] for x in r)
        m=sum(x["expectancy_r"]*x["operaciones"] for x in r if x.get("expectancy_r") is not None)
        w=sum(x["acierto_pct"]*x["operaciones"]/100 for x in r if x.get("acierto_pct") is not None)
        return {"operaciones":n,"expectancy_r":round(m/n,4) if n else None,
                "acierto_pct":round(w/n*100,2) if n else None}
    full_n=sum(x.get("n_senales_ejecutadas",0) for x in rows)
    return {"instrumentos":len(rows),"operaciones":full_n,
            "in_sample":period("in_sample"),"out_of_sample":period("out_of_sample"),
            "retornos_por_ticker":{x["ticker"]:x["retorno_neto_pct"] for x in rows},
            "max_dd_por_ticker":{x["ticker"]:x["max_drawdown_pct"] for x in rows}}


def compare(base:dict,alternative:dict)->dict:
    if (base["years_requested"],base["fee_bps_per_side"],base["slippage_bps_per_side"]) != (
         alternative["years_requested"],alternative["fee_bps_per_side"],alternative["slippage_bps_per_side"]):
        raise ValueError("Parámetros de comparación distintos")
    if base.get("paper_sizing")!=alternative.get("paper_sizing"):
        raise ValueError("Sizing no comparable entre variantes")
    a,b=aggregate(base),aggregate(alternative)
    if set(a["retornos_por_ticker"])!=set(b["retornos_por_ticker"]):
        raise ValueError("Universo distinto")
    x,y=a["out_of_sample"],b["out_of_sample"]
    return {"baseline":a,"prudente":b,"delta_oos_expectancy_r":
             round(y["expectancy_r"]-x["expectancy_r"],4) if x["expectancy_r"] is not None and y["expectancy_r"] is not None else None,
            "caveat":"Muestra superviviente actual, IS/OOS 60/40, stop fijo referencia sin tramos, earnings ignorado, sin costos BYMA/CCL. No prueba causalidad."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",default="backtest-out/base/resumen.json")
    p.add_argument("--prudente",default="backtest-out/prudente/resumen.json")
    p.add_argument("--out",default="backtest-out/comparacion.json")
    a=p.parse_args()
    report=compare(json.loads(Path(a.base).read_text()),json.loads(Path(a.prudente).read_text()))
    Path(a.out).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
