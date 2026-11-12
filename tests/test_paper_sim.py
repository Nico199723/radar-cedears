"""Pruebas offline del track record forward con OHLCV artificial y gaps."""
import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from paper_sim import new_ledger,process_ledger,public_summary,evaluate_entry,check_ledger,STOP_PCT,INITIAL,VERSION,allocation_for,PRUDENT_BUDGET,PRUDENT_STOP_PCT
from paper_store import latest_state,ARTIFACT_NAME


def candles(opens, lows, closes):
    idx=pd.bdate_range("2026-11-10",periods=len(opens))
    return pd.DataFrame({"Open":opens,"High":[max(o,c)+2 for o,c in zip(opens,closes)],
                         "Low":lows,"Close":closes,"Volume":[2_000_000]*len(opens)},index=idx)


def asset(day,code="AAA",sector="Tecnología e internet",price=100):
    data={"asset_kind":"ACCION","date":day,"price":price,"ma21":99,"ma50":93,"ma200":87,
          "score":82,"rank_score":88,"rsi14d":58,"macd_hist_d":.2,
          "rvol20":1.2,"dollar_volume20":60_000_000,"obv_up10":True,
          "stretch_atr20":.3,"cross_up21":True,"rsi21w":59,"macd_hist_w":.3}
    return {"ticker":code,"usa":code,"sector":sector,"signal":"ESPERAR MACRO",
            "earnings":None,"data":data}


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.days=["2026-11-10","2026-11-11","2026-11-12","2026-11-13"]
        self.market=candles([100,101,102,103],[99,100,101,102],[100,101,102,103])
        self.stock=candles([100,101,100,88],[99,100,95,83],[100,101,101,85])
        self.frames={"SPY":self.market,"AAA":self.stock}

    def test_sizing_macro_defensivo_vs_favorable(self):
        prudent=allocation_for("DEFENSIVO")
        normal=allocation_for("FAVORABLE")
        self.assertEqual(prudent["budget"],120)
        self.assertEqual(prudent["reserve"],1400)
        self.assertAlmostEqual(prudent["stop_pct"],.06)
        self.assertEqual(prudent["max_slots"],2)
        self.assertEqual(prudent["max_sector_slots"],1)
        self.assertEqual(normal["budget"],250)
        self.assertEqual(normal["reserve"],1000)
        self.assertAlmostEqual(normal["stop_pct"],.08)
        with self.assertRaises(ValueError):
            allocation_for("NO VERIFICADO")

    def test_defensivo_dos_posiciones_menor_monto_stop_seis(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        assets=[asset(self.days[1],"X"+str(i),sector="Sector "+str(i)) for i in range(4)]
        frames={"SPY":self.market}
        for a in assets:frames[a["usa"]]=self.stock
        process_ledger(s,frames,assets,"DEFENSIVO",18,self.days[1])
        self.assertEqual(len(s["orders"]),2)
        self.assertTrue(all(o["risk_mode"]=="PRUDENTE" for o in s["orders"]))
        process_ledger(s,frames,[],"NO VERIFICADO",None,self.days[2])
        self.assertEqual(len(s["positions"]),2)
        self.assertAlmostEqual(INITIAL-s["cash"],96,delta=1)
        self.assertGreaterEqual(s["cash"],1400)
        self.assertTrue(all(p["stop_pct"]==.06 for p in s["positions"].values()))
        self.assertTrue(all(p["budget"]==120 for p in s["positions"].values()))

    def test_first_run_does_not_retroactively_buy(self):
        s=new_ledger(self.days[1],"2026-11-11T20:00:00Z")
        process_ledger(s,self.frames,[asset(self.days[1])],"DEFENSIVO",18,self.days[1])
        self.assertEqual(s["cash"],INITIAL)
        self.assertEqual(s["orders"],[])
        self.assertEqual(s["closed_trades"],[])

    def test_entry_waits_for_next_open_and_no_double_execution(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        process_ledger(s,self.frames,[asset(self.days[1])],"DEFENSIVO",18,self.days[1])
        self.assertEqual(len(s["orders"]),1)
        self.assertEqual(s["orders"][0]["issued_day"],self.days[1])
        self.assertEqual(s["cash"],INITIAL)
        process_ledger(s,self.frames,[asset(self.days[2])],"NO VERIFICADO",None,self.days[2])
        self.assertEqual(len(s["fills"]),1)
        self.assertEqual(s["fills"][0]["date"],self.days[2])
        self.assertEqual(s["fills"][0]["action"],"COMPRA 1/3")
        self.assertAlmostEqual(s["fills"][0]["price_usd"],100*1.001)
        self.assertLessEqual(INITIAL-s["cash"],100.02)
        count=len(s["fills"])
        process_ledger(s,self.frames,[asset(self.days[2])],"NO VERIFICADO",None,self.days[2])
        self.assertEqual(len(s["fills"]),count)

    def test_stop_gap_is_worse_than_eight_percent(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        process_ledger(s,self.frames,[asset(self.days[1])],"DEFENSIVO",18,self.days[1])
        process_ledger(s,self.frames,[asset(self.days[2])],"NO VERIFICADO",None,self.days[2])
        process_ledger(s,self.frames,[asset(self.days[3])],"NO VERIFICADO",None,self.days[3])
        self.assertEqual(s["positions"],{})
        self.assertEqual(len(s["closed_trades"]),1)
        t=s["closed_trades"][0]
        self.assertIn("STOP LOSS",t["reason"])
        self.assertEqual(t["entry_date"],self.days[2])
        self.assertEqual(t["exit_date"],self.days[3])
        self.assertEqual(t["holding_sessions"],2)
        self.assertEqual(t["calendar_days"],1)
        self.assertLess(t["return_pct"],-8)
        self.assertLess(s["cash"],INITIAL)
        self.assertEqual(s["fills"][-1]["action"],"STOP LOSS")

    def test_paper_admite_continuacion_prudente_sin_cruce_del_dia(self):
        a=asset(self.days[1])
        a["signal"]="COMPRA CON PRECAUCIÓN"
        a["data"].update({"cross_up21":False,"near20":False,
                          "stretch_atr20":.85,"rank_score":84})
        self.assertTrue(evaluate_entry(a,"DEFENSIVO",18)[0])
        a["data"]["stretch_atr20"]=2.0
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",18)[0])

    def test_entry_in_defensive_requires_weekly_and_vix(self):
        a=asset(self.days[1])
        ok,msg=evaluate_entry(a,"DEFENSIVO",18)
        self.assertTrue(ok)
        self.assertIn("SMA21",msg)
        self.assertFalse(evaluate_entry(a,"NO VERIFICADO",18)[0])
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",30)[0])
        a["data"]["macd_hist_w"]=-.1
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",18)[0])

    def test_no_balance_or_etf_entries(self):
        a=asset(self.days[1])
        a["earnings"]={"days_until":5}
        self.assertFalse(evaluate_entry(a,"FAVORABLE",16)[0])
        a["earnings"]=None
        a["data"]["asset_kind"]="ETF / INDICE / NO CLASIFICADO"
        self.assertFalse(evaluate_entry(a,"FAVORABLE",16)[0])

    def test_cash_reserve_and_four_max_slots(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        assets=[]
        for ix in range(7):
            x=asset(self.days[1],"A"+str(ix),sector="Sector "+str(ix))
            assets.append(x)
        frames={"SPY":self.market}
        for x in assets:frames[x["usa"]]=self.stock
        process_ledger(s,frames,assets,"FAVORABLE",16,self.days[1])
        self.assertEqual(len(s["orders"]),4)
        process_ledger(s,frames,[],"NO VERIFICADO",None,self.days[2])
        self.assertEqual(len(s["positions"]),4)
        self.assertGreaterEqual(s["cash"],1000)
        self.assertAlmostEqual(INITIAL-s["cash"],400,delta=1)

    def test_public_summary_is_clearly_simulated(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        d=public_summary(s,{"SPY":self.market})
        self.assertTrue(d["is_simulated"])
        self.assertEqual(d["initial_capital_usd"],2000)
        self.assertEqual(d["equity_usd"],2000)
        self.assertEqual(d["closed_count"],0)
        self.assertIsNone(d["win_rate_pct"])
        self.assertEqual(d["assumptions"]["stop_pct"],8)

    def test_recovery_from_action_artifact_without_commits(self):
        s=new_ledger(self.days[0],"2026-11-10T20:00:00Z")
        buf=io.BytesIO()
        with ZipFile(buf,"w",ZIP_DEFLATED) as z:
            z.writestr("ledger.json",json.dumps(s))
        fake={"total_count":1,"artifacts":[{"name":ARTIFACT_NAME,
             "created_at":"2026-11-12T20:00:00Z","expired":False,
             "archive_download_url":"https://api.github.com/fake"}]}
        with patch("paper_store.api_get_json",return_value=fake),patch(
             "paper_store.artifact_zip",return_value=buf.getvalue()):
            restored=latest_state("Nico199723/radar-cedears","not-real-token")
        self.assertEqual(restored["last_session"],self.days[0])
        self.assertEqual(restored["version"],VERSION)

    def test_failed_remote_read_never_restarts_at_2000(self):
        with patch("paper_store.api_get_json",side_effect=ConnectionError("API caida")):
            with self.assertRaises(ConnectionError):
                latest_state("Nico199723/radar-cedears","not-real-token")

if __name__=="__main__":
    unittest.main()
