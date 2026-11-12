import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import volume_profile,ranking_score,cautious_signal,top_five,sma21_priority,ranking_stock_21,relative_strength,score_penalties
from earnings import parse_earnings,event_label


class FeatureTests(unittest.TestCase):
    def setUp(self):
        idx=pd.bdate_range("2025-01-02",periods=270)
        close=pd.Series(100 + np.arange(270)*.2,index=idx)
        volumes=np.full(270,2_000_000.,dtype=float)
        volumes[-1]=3_000_000
        self.frame=pd.DataFrame({"Close":close,"Open":close,"High":close+2,"Low":close-2,
                                 "Volume":volumes},index=idx)

    def test_sma21_cruce_alcista_solo_con_velas_pasadas(self):
        c=pd.Series([100.]*22+[103.])
        r=sma21_priority(c)
        self.assertTrue(r["cross_up21"])
        self.assertFalse(r["cross_down21"])
        self.assertEqual(r["sma21_component"],100)
        c2=c.copy()
        c2.iloc[-1]=97
        s=sma21_priority(c2)
        self.assertTrue(s["cross_down21"])
        self.assertEqual(s["sma21_component"],0)

    def test_stock_ranking_21_pesa_mas_que_simple_volumen(self):
        baseline={"score":70,"volume_confirm_score":80,"sma21_component":100,
                  "rs_score":60,"rs_verified":True,"rsi14d":56,"price":120,"ma200":100}
        up=ranking_stock_21(baseline)
        down=ranking_stock_21({**baseline,"sma21_component":0})
        self.assertEqual(up-down,20)
        self.assertEqual(up,round(70*.30+80*.20+60*.30+20))

    def test_indice_mantiene_pesos_preexistentes(self):
        from actualizar import compute
        from datetime import datetime,timezone
        with_21=compute(self.frame,datetime(2025,12,31,22,0,tzinfo=timezone.utc),is_stock=True)
        etf=compute(self.frame,datetime(2025,12,31,22,0,tzinfo=timezone.utc),is_stock=False)
        self.assertIsNotNone(with_21["ma21"])
        self.assertEqual(etf["rank_score"],ranking_score(etf))
        self.assertEqual(with_21["rank_score"],ranking_stock_21(with_21))

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
        ranked={"score":80,"volume_confirm_score":90,"sma21_component":80,
                "rs_score":75,"rs_verified":True}
        self.assertEqual(ranking_score(ranked),round(.35*80+.15*80+.30*75+.20*90))
        self.assertIsNone(ranking_score({"score":80,"volume_confirm_score":None,"sma21_component":80}))

    def _sample(self):
        return {"score":85,"price":100,"ma20":99,"ma21":98,"ma50":96,"ma200":90,
                "rsi14d":57,"rsi21w":58,"macd_hist_d":.4,"macd_hist_w":.2,
                "rvol20":1.4,"dollar_volume20":25_000_000,"obv_up10":True,
                "stretch_atr20":.5,"near20":True,"breakout":False,
                "rank_score":81,"rank_penalty":0,"rs_verified":True,
                "rs_score":70,"rs_spy20":5,"rs_qqq20":4,
                "volume_confirm_score":85}

    def test_compra_prudente_no_necesita_spy_qqq_sobre_sma50(self):
        # El régimen DEFENSIVO ya representa que ambos índices pueden estar abajo.
        d=self._sample()
        d["cross_up21"]=True
        d["near20"]=False
        d["breakout"]=False
        sig,tone,note=cautious_signal(d,"DEFENSIVO",19,True,"ESPERAR MACRO")
        self.assertEqual(sig,"COMPRA CON PRECAUCIÓN")
        self.assertEqual(tone,"wait")
        self.assertIn("reserva",note)
        d["ma21"]=d["price"]+1
        sig,_,_=cautious_signal(d,"DEFENSIVO",19,True,"ESPERAR MACRO")
        self.assertNotEqual(sig,"COMPRA CON PRECAUCIÓN")

    def test_cautious_never_buys_without_trigger_or_macro_data(self):
        d=self._sample()
        d["near20"]=False
        d["breakout"]=False
        d["cross_up21"]=False
        d["stretch_atr20"]=1.4
        self.assertEqual(cautious_signal(d,"MIXTO",18,True,"ESPERAR")[0],
                         "VIGILAR COMPRA · MACRO")
        d["cross_up21"]=True
        self.assertEqual(cautious_signal(d,"NO VERIFICADO",18,True,"ESPERAR")[0],
                         "ESPERAR")
        self.assertEqual(cautious_signal(d,"MIXTO",26,True,"ESPERAR")[0],
                         "ESPERAR")

    def test_continuacion_cercana_ma21_es_entrada_prudente(self):
        d=self._sample()
        d.update({"near20":False,"breakout":False,"cross_up21":False,
                  "rank_score":86,"stretch_atr20":.9,"rvol20":.95})
        self.assertEqual(cautious_signal(d,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                         "COMPRA CON PRECAUCIÓN")
        d["stretch_atr20"]=1.5
        self.assertEqual(cautious_signal(d,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                         "VIGILAR COMPRA · MACRO")
        d["stretch_atr20"]=.9
        d["rvol20"]=.70
        self.assertNotEqual(cautious_signal(d,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                            "COMPRA CON PRECAUCIÓN")

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
        q=dict(d);q["near20"]=False;q["stretch_atr20"]=1.4
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

    def test_top5_has_individual_volume_usd_not_last_loop_value(self):
        base=self._sample()
        base.update(rank_score=82,roc20=5,invalid_usd=90,target_2r=120,date="2026-11-11")
        a1=dict(base);a1["dollar_volume20"]=20_000_000
        a2=dict(base);a2["dollar_volume20"]=125_000_000
        items=[{"ticker":"AA","usa":"AA","sector":"Salud","data":a1,"signal":"ESPERAR","earnings":None},
               {"ticker":"BB","usa":"BB","sector":"Industriales","data":a2,"signal":"ESPERAR","earnings":None}]
        ranked=top_five(items,{"roc20":3},"DEFENSIVO")
        got={x["ticker"]:x["dollar_volume20"] for x in ranked}
        self.assertEqual(got["AA"],20_000_000)
        self.assertEqual(got["BB"],125_000_000)

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
