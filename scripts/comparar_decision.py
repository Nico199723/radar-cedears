"""Publicar antes/después actual vs motor unificado, NO activar producción."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path

def summarize(report):
    rows=[x for x in report.get("results",[]) if x.get("estado")=="OK"]
    trades=sum(int(x.get("n_senales_ejecutadas") or 0) for x in rows)
    def weighted(metric):
        vals=[(x.get(metric),int(x.get("n_senales_ejecutadas") or 0)) for x in rows]
        present=[(v,n) for v,n in vals if v is not None and n>0]
        return round(sum(float(v)*n for v,n in present)/sum(n for _,n in present),3) if present else None
    oos=[(x["out_of_sample"],x.get("ticker")) for x in rows]
    oos_n=sum(int(v.get("operaciones") or 0) for v,_ in oos)
    def oos_weighted(metric):
        part=[(float(v[metric]),int(v["operaciones"])) for v,_ in oos if v.get(metric) is not None and v.get("operaciones")]
        return round(sum(val*n for val,n in part)/sum(n for _,n in part),4) if part else None
    return {"tickers_with_data":len(rows),"trades":trades,
            "hit_rate_pct":weighted("win_rate_pct"),
            "mean_r":weighted("r_promedio"),
            "max_drawdown_worst_ticker_pct":max((x.get("max_drawdown_pct") or 0 for x in rows),default=None),
            "worst_losing_streak":max((x.get("peor_racha_perdedora") or 0 for x in rows),default=0),
            "out_of_sample_trades":oos_n,
            "out_of_sample_hit_rate_pct":oos_weighted("acierto_pct"),
            "out_of_sample_mean_r":oos_weighted("expectancy_r")}
def compare(base,proposed):
    left=summarize(base);right=summarize(proposed)
    by={x["ticker"]:x for x in base["results"] if x.get("estado")=="OK"}
    changes=[]
    for x in proposed["results"]:
        if x.get("estado")!="OK" or x["ticker"] not in by:continue
        o=by[x["ticker"]]
        changes.append({"ticker":x["ticker"],"current_trades":o["n_senales_ejecutadas"],
                        "new_trades":x["n_senales_ejecutadas"],
                        "current_hit_pct":o["win_rate_pct"],"new_hit_pct":x["win_rate_pct"],
                        "current_r":o["r_promedio"],"new_r":x["r_promedio"],
                        "current_drawdown_pct":o["max_drawdown_pct"],
                        "new_drawdown_pct":x["max_drawdown_pct"],
                        "current_worst_streak":o.get("peor_racha_perdedora"),
                        "new_worst_streak":x.get("peor_racha_perdedora")})
    return {"current":left,"proposed":right,"per_ticker":changes,
            "current_signal_counts":base.get("signal_counts",{}),
            "proposed_signal_counts":proposed.get("signal_counts",{}),
            "limitations":["10 tickers, no cartera diversificada simulada",
                           "max DD representa peor ticker, NO DD conjunto",
                           "sesgo de supervivencia", "earnings histórico no disponible",
                           "sin optimización walk-forward, sólo split cronológico 60/40",
                           "fills t+1 open, slippage 10bps y fee 5bps por lado"]}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",default="backtest-out/base/resumen.json")
    p.add_argument("--proposal",default="backtest-out/unified/resumen.json")
    p.add_argument("--out",default="backtest-out/comparacion-decision.json")
    a=p.parse_args()
    result=compare(json.loads(Path(a.base).read_text()),json.loads(Path(a.proposal).read_text()))
    Path(a.out).parent.mkdir(exist_ok=True,parents=True)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=["# A/B score unificado (PRODUCCIÓN NO ALTERADA)","","| Métrica | Vigente | Propuesto |","|---|---:|---:|"]
    for key in ["trades","hit_rate_pct","mean_r","max_drawdown_worst_ticker_pct","worst_losing_streak",
                "out_of_sample_trades","out_of_sample_hit_rate_pct","out_of_sample_mean_r"]:
        lines.append(f"| {key} | {result['current'].get(key)} | {result['proposed'].get(key)} |")
    lines.append("\\n**Señales:** recuento de cierres por etiqueta (incluye observaciones repetidas; no son operaciones):")
    for label in sorted(set(result["current_signal_counts"])|set(result["proposed_signal_counts"])):
        lines.append(f"- {label}: actual {result['current_signal_counts'].get(label,0)} / nuevo {result['proposed_signal_counts'].get(label,0)}")
    lines.append("\n**Limitaciones:** peor DD individual, no cartera agregada; muestra actual con sesgo de supervivencia; earnings históricos ausentes.")
    md="\n".join(lines)
    Path(a.out).with_suffix(".md").write_text(md)
    print(md)
if __name__=="__main__":main()
