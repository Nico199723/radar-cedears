"""Pruebas de entradas/salidas escalonadas y contabilidad de USD 2000 ficticios.

La señal se observa al cierre; las ventas se llenan al OPEN siguiente.
Gaps contra stop tienen prioridad sobre una venta parcial pendiente.
"""
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from paper_sim import (new_ledger,open_tranche,sell_fraction,close_position,
                       process_ledger,public_summary,INITIAL)


def candles(opens, lows, closes):
    dates=pd.bdate_range("2026-11-10",periods=len(opens))
    return pd.DataFrame({
        "Open":opens,"High":[max(o,c)+2 for o,c in zip(opens,closes)],
        "Low":lows,"Close":closes,"Volume":[3_000_000]*len(opens)
    },index=dates)


def position(state, day="2026-11-10",price=100):
    order={"side":"BUY","usa":"AAA","ticker":"AAA","sector":"Tecnología e internet",
           "tranche":1,"issued_day":day,"reason":"ENTRADA SMA21"}
    assert open_tranche(state,order,day,price)
    return state["positions"]["AAA"]


class PartialExitsTests(unittest.TestCase):
    def setUp(self):
        self.days=["2026-11-10","2026-11-11","2026-11-12","2026-11-13"]
        self.stock=candles([100,103,120,92],[99,101,119,89],[100,118,120,91])
        self.market=candles([100,101,102,103],[99,100,101,102],[100,101,102,103])
        self.frames={"SPY":self.market,"AAA":self.stock}

    def test_take_profit_50_percent_keeps_remaining_cost_basis(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        p=position(s)
        shares,cost=p["shares"],p["spent"]
        sell_fraction(s,"AAA",self.days[1],120,"OBJETIVO 2R: TOMAR GANANCIA EN 50% Y TRAILING RESTANTE",.5)
        remaining=s["positions"]["AAA"]
        self.assertAlmostEqual(remaining["shares"],shares*.5,places=8)
        self.assertAlmostEqual(remaining["spent"],cost*.5,places=7)
        self.assertTrue(remaining["profit_taken"])
        self.assertTrue(remaining["exit_started"])
        self.assertGreaterEqual(remaining["stop_usd"],cost/shares)
        self.assertEqual(s["fills"][-1]["action"],"VENTA PARCIAL")
        self.assertEqual(s["closed_trades"][0]["exit_fraction_pct"],50)
        self.assertTrue(s["closed_trades"][0]["partial"])
        self.assertEqual(public_summary(s,self.frames)["closed_count"],0)
        self.assertEqual(public_summary(s,self.frames)["partial_exit_count"],1)

    def test_full_cycle_profit_aggregates_all_partial_sales(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        position(s)
        sell_fraction(s,"AAA",self.days[1],120,"OBJETIVO 2R: TOMAR GANANCIA EN 50%",.5)
        close_position(s,"AAA",self.days[2],100,"STOP LOSS TOTAL 8% / TRAILING")
        self.assertEqual(s["positions"],{})
        self.assertEqual(len(s["closed_trades"]),2)
        partial,final=s["closed_trades"]
        self.assertFalse(partial["final"])
        self.assertTrue(final["final"])
        self.assertAlmostEqual(final["lifecycle_pnl_usd"],round(partial["pnl_usd"]+final["pnl_usd"],2),delta=.02)
        public=public_summary(s,self.frames)
        self.assertEqual(public["closed_count"],1)
        self.assertEqual(public["partial_exit_count"],1)
        self.assertAlmostEqual(public["realized_pnl_usd"],round(partial["pnl_usd"]+final["pnl_usd"],2),delta=.02)
        self.assertEqual(public["win_rate_pct"],100)

    def test_reduction_50_percent_is_one_off_no_new_additions(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        p=position(s)
        shares=p["shares"]
        sell_fraction(s,"AAA",self.days[1],98,"REDUCIR 50% POR DETERIORO TÉCNICO",.5)
        self.assertAlmostEqual(s["positions"]["AAA"]["shares"],shares/2,places=8)
        self.assertTrue(s["positions"]["AAA"]["reduction_taken"])
        self.assertFalse(s["positions"]["AAA"]["profit_taken"])
        extra={"side":"BUY","usa":"AAA","ticker":"AAA","sector":"Tecnología e internet",
               "tranche":2,"issued_day":self.days[1]}
        self.assertFalse(open_tranche(s,extra,self.days[2],102))

    def test_closing_signal_at_t_executes_partial_at_open_t1(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        position(s)
        a={"ticker":"AAA","usa":"AAA","sector":"Tecnología e internet",
           "signal":"ESPERAR","data":{"date":self.days[1],"price":118,
              "ma21":110,"macd_hist_d":.4}}
        process_ledger(s,self.frames,[a],"NO VERIFICADO",None,self.days[1])
        self.assertEqual(len(s["orders"]),1)
        self.assertEqual(s["orders"][0]["side"],"SELL")
        self.assertEqual(s["orders"][0]["fraction"],.5)
        self.assertEqual(len(s["closed_trades"]),0)
        process_ledger(s,self.frames,[],"NO VERIFICADO",None,self.days[2])
        self.assertEqual(s["closed_trades"][0]["exit_date"],self.days[2])
        self.assertAlmostEqual(s["closed_trades"][0]["exit_usd"],120*.999,places=4)
        self.assertEqual(len(s["positions"]),1)

    def test_gap_before_partial_order_liquidates_all(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        position(s)
        a={"ticker":"AAA","usa":"AAA","sector":"Tecnología e internet",
           "signal":"ESPERAR","data":{"date":self.days[1],"price":118,
              "ma21":110,"macd_hist_d":.4}}
        process_ledger(s,self.frames,[a],"NO VERIFICADO",None,self.days[1])
        dropped=candles([100,103,88,87],[99,101,83,85],[100,118,87,86])
        process_ledger(s,{"SPY":self.market,"AAA":dropped},[],
                       "NO VERIFICADO",None,self.days[2])
        self.assertEqual(len(s["closed_trades"]),1)
        self.assertTrue(s["closed_trades"][0]["final"])
        self.assertIn("STOP LOSS",s["closed_trades"][0]["reason"])
        self.assertEqual(s["fills"][-1]["action"],"STOP LOSS")
        self.assertEqual(s["positions"],{})

    def test_same_reduction_signal_cannot_sell_half_again_and_again(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        position(s)
        sell_fraction(s,"AAA",self.days[1],98,"REDUCIR 50% POR DETERIORO TÉCNICO",.5)
        series=candles([100,100,99,98],[99,99,97,96],[100,100,99,98])
        a={"ticker":"AAA","usa":"AAA","sector":"Tecnología e internet",
           "signal":"REDUCIR / EVITAR","data":{"date":self.days[1],"price":100,
                "ma21":101,"macd_hist_d":-.1}}
        process_ledger(s,{"SPY":self.market,"AAA":series},[a],"DEFENSIVO",20,self.days[1])
        self.assertFalse(any(o["side"]=="SELL" for o in s["orders"]))

    def test_legacy_ledger_open_positions_work_without_new_flags(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        p=position(s)
        for key in ["profit_taken","reduction_taken","exit_started",
                    "total_invested","realized_pnl_usd"]:
            p.pop(key,None)
        sell_fraction(s,"AAA",self.days[1],120,"OBJETIVO 2R",.5)
        close_position(s,"AAA",self.days[2],110,"VENTA FINAL")
        self.assertEqual(len(s["closed_trades"]),2)
        self.assertEqual(public_summary(s,self.frames)["closed_count"],1)


if __name__=="__main__":
    unittest.main()
