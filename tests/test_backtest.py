"""Pruebas deterministas del ejecutor histórico, sin cotizaciones de red."""
import sys
import unittest
from pathlib import Path
import numpy as np
import json
import tempfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from backtest import simulate, macro_history, benchmark, historical_decisions, download


def frame(opens, closes=None, lows=None):
    idx = pd.bdate_range("2025-01-06", periods=len(opens))
    c = list(opens) if closes is None else closes
    low = [min(x,y)-1 for x,y in zip(opens,c)] if lows is None else lows
    return pd.DataFrame({"Open":opens, "High":[max(x,y)+1 for x,y in zip(opens,c)],
                         "Low":low, "Close":c, "Volume":[1_000_000]*len(opens)}, index=idx)


class BacktestTests(unittest.TestCase):
    def test_cache_historico_compartido_no_descarga_dos_veces(self):
        f=frame([100]*270,lows=[99]*270)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            f.to_csv(folder/"AAA.csv")
            (folder/"manifest.json").write_text(json.dumps({
                "symbols":["AAA","BBB"],"years":5,"downloaded":["AAA"],"missing":["BBB"]}))
            result=download(["AAA","BBB"],5,str(folder))
            self.assertEqual(set(result),{"AAA"})
            self.assertEqual(len(result["AAA"]),270)
            with self.assertRaises(ValueError):
                download(["AAA","CCC"],5,str(folder))

    def test_ab_compara_regla_score75_con_mismo_cierre(self):
        from unittest.mock import patch
        f=frame([100]*243,lows=[99]*243)
        last=f.index[-1]
        d={"asset_kind":"ACCION","price":105,"ma21":103,"ma200":90,
           "rank_score":76,"rsi14d":56,"rsi21w":57,"macd_hist_d":.6,
           "macd_hist_w":.3,"obv_up10":True,"rvol20":1.25,
           "dollar_volume20":35_000_000,"volume_confirm_score":80,
           "rs_verified":True,"stretch_atr20":.5,"invalid_usd":92}
        macros={last:"FAVORABLE"}
        with patch("backtest.compute",return_value=d),patch(
                "backtest.get_signal",return_value=("MANTENER / ESPERAR","hold",[])):
            old=historical_decisions(f,macros,"2025-01-01",variant="floor70",
                                     vix_by_day={last:18})
            new=historical_decisions(f,macros,"2025-01-01",variant="score75",
                                     vix_by_day={last:18})
        self.assertEqual(old[last]["signal"],"VIGILAR COMPRA · SCORE")
        self.assertEqual(new[last]["signal"],"COMPRA CON PRECAUCIÓN")
        self.assertEqual(old[last]["stop"],new[last]["stop"])

    def test_entrada_se_ejecuta_en_open_t_mas_uno(self):
        f = frame([100,105,110,120], lows=[99,104,109,119])
        signals={f.index[0]:{"signal":"COMPRA CONDICIONAL","stop":90},
                 f.index[2]:{"signal":"REDUCIR / EVITAR","stop":90}}
        trades, curve = simulate(f,signals,"TEST",fee_bps=0,slippage_bps=0)
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0].entry,105)
        self.assertEqual(trades[0].exit,120)
        self.assertEqual(trades[0].entry_date,str(f.index[1].date()))
        self.assertGreater(curve.iloc[-1],1.0)

    def test_gap_bajista_llena_en_open_peor_que_stop(self):
        f = frame([100,104,90], closes=[100,101,91], lows=[99,98,88])
        signals={f.index[0]:{"signal":"COMPRA CONDICIONAL","stop":95}}
        trades,_ = simulate(f,signals,"TEST",fee_bps=0,slippage_bps=0)
        self.assertEqual(trades[0].exit,90)
        self.assertEqual(trades[0].exit_reason,"STOP/GAP")
        self.assertLess(trades[0].net_r,-1.0)

    def test_stop_intradiario(self):
        f=frame([100,101,110], closes=[100,99,110], lows=[99,94,109])
        trades,_=simulate(f,{f.index[0]:{"signal":"COMPRA CONDICIONAL","stop":95}},"TEST",
                          fee_bps=0,slippage_bps=0)
        self.assertEqual(trades[0].exit,95)
        self.assertEqual(trades[0].entry_date,trades[0].exit_date)

    def test_costos_reducen_resultado(self):
        f=frame([100,100,100], lows=[99,99,99])
        s={f.index[0]:{"signal":"COMPRA CONDICIONAL","stop":90},
           f.index[1]:{"signal":"SALIR / EVITAR","stop":90}}
        no_cost,_=simulate(f,s,"TEST",fee_bps=0,slippage_bps=0)
        cost,_=simulate(f,s,"TEST",fee_bps=5,slippage_bps=10)
        self.assertAlmostEqual(no_cost[0].net_return_pct,0,places=4)
        self.assertLess(cost[0].net_return_pct,0)

    def test_macro_no_lee_futuro(self):
        f=frame([100]*210)
        v=frame([20]*210)
        before=macro_history(f,f,v)
        future=f.copy()
        future.iloc[-1,future.columns.get_loc("Close")]=10000
        after=macro_history(future,f,v)
        self.assertEqual(before[f.index[-2]],after[f.index[-2]])

    def test_benchmark_compra_y_mantener(self):
        f=frame([100,110],closes=[100,110],lows=[99,109])
        b=benchmark(f,f.index,0,0)
        self.assertAlmostEqual(b["retorno_neto_pct"],10.0,places=2)

    def test_sin_senal_no_hay_operaciones(self):
        f=frame([100,101,102,100])
        trades,equity=simulate(f,{},"TEST")
        self.assertEqual(trades,[])
        self.assertTrue(np.allclose(equity.to_numpy(),1.0))

    def test_datos_historicos_no_cambian_al_agregar_futuro(self):
        # Una señal a fecha t debe ser la misma aunque mañana aparezca otra vela.
        idx=pd.bdate_range("2022-01-03", periods=250)
        prices=100+np.arange(len(idx))*0.2
        f=pd.DataFrame({"Open":prices,"High":prices*1.01,"Low":prices*.99,
                        "Close":prices,"Volume":np.full(len(idx),1_000_000)}, index=idx)
        mac={t:"FAVORABLE" for t in idx}
        a=historical_decisions(f,mac,"2022-12-01")
        f2=pd.concat([f,pd.DataFrame({"Open":[300],"High":[303],"Low":[298],
                                     "Close":[300],"Volume":[1_000_000]},
                                     index=[idx[-1]+pd.offsets.BDay(1)])])
        b=historical_decisions(f2,mac,"2022-12-01")
        self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
