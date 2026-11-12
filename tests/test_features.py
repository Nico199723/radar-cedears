import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import volume_profile,ranking_score,cautious_signal,top_five
from earnings import parse_earnings,event_label


class FeatureTests(unittest.TestCase):
    def setUp(self):
        idx=pd.bdate_range("2025-01-02",periods=270)
        close=pd.Series(100 + np.arange(270)*.2,index=idx)
        volumes=np.full(270,2_000_000.,dtype=float)
        volumes[-1]=3_000_000
        self.frame=pd.DataFrame({"Close":close,"Open":close,"High":close+2,"Low":close-2,
                                 "Volume":volumes},index=idx)

    def test_rvol_excludes_current_session(self):
        v=volume_profile(self.frame)
        self.assertAlmostEqual(v["rvol20"],1.5,places=2)
        self.assertGreater(v["dollar_volume20"],5_000_000)
        self.assertTrue(v["obv_up10"])
        self.assertGreater(v["atr14"],0)

    def test_volume_score_is_bounded(self):
        f=self.frame.copy()
        f.iloc[-1,f.columns.get_loc("Volume")]=400_000_000
        self.assertLessEqual(volume_profile(f)["volume_score"],10)
        f.iloc[-1,f.columns.get_loc("Volume")]=0
        self.assertGreaterEqual(volume_profile(f)["volume_score"],0)
        self.assertEqual(ranking_score({"score":80,"volume_score":10}),83)
        self.assertIsNone(ranking_score({"score":80,"volume_score":None}))

    def _sample(self):
        return {"score":85,"price":100,"ma20":99,"ma50":96,"ma200":90,
                "rsi14d":57,"rsi21w":58,"macd_hist_d":.4,"macd_hist_w":.2,
                "rvol20":1.4,"dollar_volume20":25_000_000,"obv_up10":True,
                "stretch_atr20":.5,"near20":True,"breakout":False}

    def test_cautious_macro_can_find_exception(self):
        sig,_,note=cautious_signal(self._sample(),"DEFENSIVO",18,True,"ESPERAR MACRO")
        self.assertEqual(sig,"COMPRA CON PRECAUCIÓN")
        self.assertIn("riesgo",note)

    def test_cautious_macro_blocks_vix_or_unknown(self):
        for macro,vix in (("DEFENSIVO",29),("NO VERIFICADO",18),("DEFENSIVO",None)):
            sig,_,_=cautious_signal(self._sample(),macro,vix,True,"ESPERAR MACRO")
            self.assertNotEqual(sig,"COMPRA CON PRECAUCIÓN")

    def test_cautious_never_overrides_exit(self):
        sig,_,_=cautious_signal(self._sample(),"MIXTO",15,True,"REDUCIR / EVITAR")
        self.assertEqual(sig,"REDUCIR / EVITAR")

    def test_cautious_needs_liquidity_weekly_and_entry(self):
        d=self._sample()
        for k,v in (("rvol20",None),("dollar_volume20",1_000),("macd_hist_w",-1),
                    ("obv_up10",False),("stretch_atr20",3)):
            q=dict(d);q[k]=v
            sig,_,_=cautious_signal(q,"MIXTO",17,True,"ESPERAR MACRO")
            self.assertNotEqual(sig,"COMPRA CON PRECAUCIÓN")
        q=dict(d);q["near20"]=False
        sig,_,_=cautious_signal(q,"MIXTO",17,True,"ESPERAR MACRO")
        self.assertEqual(sig,"VIGILAR COMPRA · MACRO")

    def test_balances_future_calendar_is_indicative(self):
        today=date(2026,11,12)
        e=parse_earnings({"Earnings Date":[pd.Timestamp("2026-11-18"),
                                             pd.Timestamp("2027-02-20")]},today)
        self.assertEqual(e["days_until"],6)
        self.assertIn("INDICATIVA",e["status"])
        self.assertEqual(event_label(e,True),"BALANCE <=7 DÍAS")

    def test_balances_unknown_never_means_no_event(self):
        self.assertIsNone(parse_earnings({},date(2026,11,12)))
        self.assertEqual(event_label(None,True),"FECHA SIN VERIFICAR")
        self.assertEqual(event_label(None,False),"FECHA NO CONSULTADA")

    def test_top5_diversifies_excludes_weak_and_thin(self):
        data=self._sample()
        data.update(rank_score=85,roc20=9,invalid_usd=95,target_2r=110,date="2026-11-11")
        assets=[]
        for ticker,sector in (("A","Tecnología"),("B","Tecnología"),("C","Tecnología"),
                              ("D","Consumo"),("E","Salud"),("F","Energía"),("G","Agro")):
            d=dict(data)
            assets.append({"ticker":ticker,"usa":ticker,"sector":sector,
                           "signal":"ESPERAR MACRO","data":d,"earnings":None})
        out=top_five(assets,{"roc20":4},"DEFENSIVO")
        self.assertEqual(len(out),5)
        self.assertLessEqual(sum(x["sector"]=="Tecnología" for x in out),2)
        self.assertTrue(all("RIESGO MACRO" in x["tag"] for x in out))


if __name__=="__main__":
    unittest.main()
