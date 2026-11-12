"""Macro SPY/QQQ fuera de SMA50 NO equivale a veto general de compras.

Pruebas sin cotizaciones en vivo, sin datos futuros y sin órdenes reales.
Verifica consistencia entre radar y paper USD2000, ETFs incluidos.
"""
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from actualizar import ENABLE_CAUTION_ENTRIES,get_signal
from radar_features import cautious_signal,risk_policy
from paper_sim import (new_ledger,process_ledger,public_summary,evaluate_entry)


def strong(kind="ACCION",symbol="AAA",day="2026-11-11"):
    d={
        "asset_kind":kind,"date":day,"price":100,"ma20":99,"ma21":98,
        "ma50":96,"ma200":90,"score":82,"trend":"ALCISTA",
        "rank_score":77,"rank_penalty":4,"rsi14d":57,"rsi21w":57,
        "macd_hist_d":.5,"macd_hist_w":.3,
        "rvol20":1.2,"dollar_volume20":32_000_000,
        "obv_up10":True,"volume_confirm_score":76,
        "rs_verified":True,"rs_spy20":5,"rs_qqq20":4,"rs_score":71,
        "stretch_atr20":.65,"near20":True,"breakout":False,
        "cross_up21":True,"sma21_age":1,
    }
    return {"ticker":symbol,"usa":symbol,"sector":"Salud" if kind=="ACCION" else "Índices y ETFs",
            "data":d,"signal":"ESPERAR MACRO","earnings":None}


def candles():
    idx=pd.bdate_range("2026-11-10",periods=4)
    prices=[100,100,101,102]
    return pd.DataFrame({"Open":prices,"High":[x+2 for x in prices],
                         "Low":[x-2 for x in prices],"Close":prices,
                         "Volume":[1_000_000]*4},index=idx)


class MacroSizingTests(unittest.TestCase):
    def test_spy_qqq_below_ma50_can_buy_stock_and_etf(self):
        self.assertTrue(ENABLE_CAUTION_ENTRIES)
        for kind in ("ACCION","ETF / INDICE / NO CLASIFICADO"):
            a=strong(kind)
            base,_,_=get_signal(a["data"],"DEFENSIVO",True)
            self.assertEqual(base,"ESPERAR MACRO")
            signal,_,_=cautious_signal(a["data"],"DEFENSIVO",18,True,base)
            self.assertEqual(signal,"COMPRA CON PRECAUCIÓN")
            a["signal"]=signal
            self.assertTrue(evaluate_entry(a,"DEFENSIVO",18)[0])

    def test_vix_28_allowed_with_smaller_exposure_30_blocked(self):
        a=strong()["data"]
        self.assertEqual(cautious_signal(a,"DEFENSIVO",28,True,"ESPERAR MACRO")[0],
                         "COMPRA CON PRECAUCIÓN")
        self.assertEqual(risk_policy("DEFENSIVO",28)["max_position_usd"],120)
        self.assertEqual(risk_policy("DEFENSIVO",30)["max_position_usd"],0)
        self.assertNotEqual(cautious_signal(a,"DEFENSIVO",30,True,"ESPERAR MACRO")[0],
                            "COMPRA CON PRECAUCIÓN")
        self.assertEqual(risk_policy("NO VERIFICADO",18)["max_position_usd"],0)

    def test_no_unconditional_buy_in_defensive_market(self):
        a=strong()["data"]
        for field,value in (("rsi14d",80),("price",89),("macd_hist_w",-.2),
                            ("dollar_volume20",1000),("rs_verified",False),
                            ("rank_penalty",29),("obv_up10",False)):
            trial=dict(a)
            trial[field]=value
            self.assertNotEqual(cautious_signal(trial,"DEFENSIVO",17,True,"ESPERAR MACRO")[0],
                                "COMPRA CON PRECAUCIÓN",field)
        self.assertNotEqual(cautious_signal(a,"DEFENSIVO",17,False,"DATOS VIEJOS")[0],
                            "COMPRA CON PRECAUCIÓN")

    def test_no_new_entry_if_no_trigger_or_too_extended(self):
        a=strong()["data"]
        a.update(near20=False,breakout=False,cross_up21=False,stretch_atr20=1.4)
        self.assertEqual(cautious_signal(a,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                         "VIGILAR COMPRA · MACRO")
        a["stretch_atr20"]=.65
        a["sma21_age"]=3
        self.assertEqual(cautious_signal(a,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                         "COMPRA CON PRECAUCIÓN")

    def test_policy_and_ledger_120_dollars_70pct_cash_and_six_percent_stop(self):
        spy=candles()
        symbols={"SPY":spy}
        assets=[]
        for sym,sec in (("AAA","Salud"),("BBB","Energía"),("CCC","Salud")):
            x=strong(symbol=sym,day="2026-11-11")
            x["sector"]=sec
            x["signal"]="COMPRA CON PRECAUCIÓN"
            assets.append(x)
            symbols[sym]=spy
        s=new_ledger("2026-11-10","2026-11-10T21:00:00Z")
        process_ledger(s,symbols,assets,"DEFENSIVO",18,"2026-11-11")
        self.assertEqual(len(s["orders"]),2)
        self.assertTrue(all(o["budget"]==120 and o["reserve_usd"]==1400 and o["stop_pct"]==.06 for o in s["orders"]))
        self.assertEqual(len({o["sector"] for o in s["orders"]}),2)
        process_ledger(s,symbols,[],"NO VERIFICADO",None,"2026-11-12")
        self.assertEqual(len(s["positions"]),2)
        self.assertAlmostEqual(2000-s["cash"],96,delta=1)
        self.assertGreaterEqual(s["cash"],1400)
        self.assertTrue(all(p["budget"]==120 and p["stop_pct"]==.06 for p in s["positions"].values()))
        self.assertTrue(all(p["tranche_count"]==1 for p in s["positions"].values()))

    def test_favorable_retains_250_8pct_and_50pct_reserve(self):
        p=risk_policy("FAVORABLE",18)
        self.assertEqual((p["max_position_usd"],p["reserve_pct"],p["stop_pct"]),(250,50,8))

    def test_leveraged_etf_has_further_reduced_sizing(self):
        spy=candles()
        a=strong("ETF / INDICE / NO CLASIFICADO","TQQQ")
        a["signal"]="COMPRA CON PRECAUCIÓN"
        s=new_ledger("2026-11-10","2026-11-10T21:00:00Z")
        process_ledger(s,{"SPY":spy,"TQQQ":spy},[a],"DEFENSIVO",18,"2026-11-11")
        self.assertEqual(len(s["orders"]),1)
        self.assertEqual(s["orders"][0]["budget"],60)
        self.assertEqual(s["orders"][0]["stop_pct"],.05)
        self.assertEqual(s["orders"][0]["reserve_usd"],1600)

if __name__=="__main__":
    unittest.main()
