"""Regresiones de coherencia: compra >=70 Score O, verde real, HOLD alto."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from actualizar import get_signal
from radar_features import (MIN_BUY_SCORE,buy_candidate,cautious_signal,
                            reconcile_buy_label)
from paper_sim import evaluate_entry


def asset(rank=70, kind="ACCION"):
    return {
        "asset_kind":kind,"date":"2026-11-11","price":105,
        "ma20":104,"ma21":103,"ma50":99,"ma200":90,
        "score":80,"trend":"ALCISTA",
        "rsi14d":56,"rsi21w":57,"rsi21m":58,
        "macd_hist_d":.6,"macd_hist_w":.3,
        "near20":True,"breakout":False,"cross_up21":True,"sma21_age":1,
        "rank_score":rank,"rank_score_signal":82,"rank_penalty":0,
        "rank_penalty_signal":0,"obv_up10":True,"rvol20":1.25,
        "dollar_volume20":35_000_000,"volume_confirm_score":80,
        "rs_verified":True,"rs_score":72,"rs_spy20":5,"rs_qqq20":4,
        "stretch_atr20":.5,
    }


class FloorAndGreenTests(unittest.TestCase):
    def test_exact_70_is_minimum_for_buy(self):
        self.assertEqual(MIN_BUY_SCORE,70)
        for macro,base in (("FAVORABLE","COMPRA CONDICIONAL"),
                           ("DEFENSIVO","COMPRA CON PRECAUCIÓN")):
            for kind in ("ACCION","ETF / INDICE / NO CLASIFICADO"):
                low=asset(69.9,kind)
                s,t,r=reconcile_buy_label(low,base,"up",["setup completo"],True)
                self.assertEqual(s,"VIGILAR COMPRA · SCORE")
                self.assertEqual(t,"watch")
                self.assertIn("mínimo de entrada 70",r[-1])
                high=asset(70,kind)
                s,t,r=reconcile_buy_label(high,base,"caution",[],True)
                self.assertEqual(s,base)

    def test_no_score_no_buy(self):
        d=asset(None)
        s,t,_=reconcile_buy_label(d,"COMPRA CONDICIONAL","up",[],True)
        self.assertEqual(s,"ESPERAR")
        self.assertNotEqual(t,"up")
        s,_,_=reconcile_buy_label(asset(69),"COMPRA CON PRECAUCIÓN","caution",[],False)
        self.assertEqual(s,"DATOS VIEJOS")

    def test_high_score_hold_becomes_watch_with_reason(self):
        d=asset(88)
        d["macd_hist_d"]=-.3
        cand=buy_candidate(d,"MANTENER / ESPERAR",True)
        self.assertFalse(cand["eligible"])
        s,t,why=reconcile_buy_label(d,"MANTENER / ESPERAR","hold",
                                    ["Tendencia lateral"],True,cand)
        self.assertEqual(s,"VIGILAR SETUP · SCORE")
        self.assertEqual(t,"watch")
        self.assertIn("MACD",str(why))
        good=asset(88)
        good["near20"]=False
        good["cross_up21"]=False
        eligible=buy_candidate(good,"MANTENER / ESPERAR",True)
        self.assertTrue(eligible["eligible"])
        s,t,why=reconcile_buy_label(good,"MANTENER / ESPERAR","hold",[],True,eligible)
        self.assertEqual(s,"VIGILAR COMPRA · SCORE")
        self.assertTrue(any("gatillo" in x for x in why))

    def test_exit_takes_precedence_over_high_score(self):
        d=asset(95)
        for signal in ("SALIR / EVITAR","REDUCIR / EVITAR","DATOS VIEJOS"):
            got=reconcile_buy_label(d,signal,"down",["riesgo"],True)
            self.assertEqual(got[0],signal)
        got=reconcile_buy_label(d,"MANTENER / ESPERAR","hold",[],False)
        self.assertEqual(got[0],"MANTENER / ESPERAR")

    def test_paper_uses_same_visible_score_floor(self):
        for kind in ("ACCION","ETF / INDICE / NO CLASIFICADO"):
            for macro,signal in (("FAVORABLE","COMPRA CONDICIONAL"),
                                 ("DEFENSIVO","COMPRA CON PRECAUCIÓN")):
                a={"ticker":"XYZ","usa":"XYZ","sector":"Salud",
                   "signal":signal,"data":asset(69.9,kind),"earnings":None}
                self.assertFalse(evaluate_entry(a,macro,18)[0])
                a["data"]["rank_score"]=70
                self.assertTrue(evaluate_entry(a,macro,18)[0])

    def test_75_qualifies_green_caution_without_intraday_trigger(self):
        from radar_features import high_score_precaution
        for macro in ("FAVORABLE","DEFENSIVO","MIXTO"):
            for kind in ("ACCION","ETF / INDICE / NO CLASIFICADO"):
                d=asset(76,kind)
                d.update({"near20":False,"breakout":False,
                          "cross_up21":False,"sma21_age":11})
                self.assertTrue(high_score_precaution(d,macro,18,True)[0])
                cand=buy_candidate(d,"MANTENER / ESPERAR",True)
                s,t,reason=reconcile_buy_label(
                    d,"MANTENER / ESPERAR","hold",[],True,cand,macro,18)
                self.assertEqual(s,"COMPRA CON PRECAUCIÓN")
                self.assertEqual(t,"caution")
                a={"ticker":"AAA","usa":"AAA","sector":"Salud",
                   "signal":s,"data":d,"earnings":None}
                self.assertTrue(evaluate_entry(a,macro,18)[0])

    def test_75_never_overrides_rsi_80_sma200_exit_or_vix_stress(self):
        from radar_features import high_score_precaution
        for key,value in (("rsi14d",80),("price",85),("macd_hist_w",-.2),
                          ("obv_up10",False),("stretch_atr20",2.8),
                          ("dollar_volume20",1000),("rs_verified",False)):
            d=asset(92)
            d[key]=value
            self.assertFalse(high_score_precaution(d,"DEFENSIVO",18,True)[0],key)
            s,_,_=reconcile_buy_label(d,"MANTENER / ESPERAR","hold",[],True,
                                      buy_candidate(d,"MANTENER / ESPERAR",True),
                                      "DEFENSIVO",18)
            self.assertNotEqual(s,"COMPRA CON PRECAUCIÓN",key)
        d=asset(85)
        self.assertFalse(high_score_precaution(d,"DEFENSIVO",31,True)[0])
        self.assertFalse(high_score_precaution(d,"NO VERIFICADO",18,True)[0])
        s,_,_=reconcile_buy_label(d,"MANTENER / ESPERAR","hold",[],True,
                                  buy_candidate(d,"MANTENER / ESPERAR",True),
                                  "NO VERIFICADO",18)
        self.assertNotEqual(s,"COMPRA CON PRECAUCIÓN")

    def test_from_70_to_74_requires_classic_trigger(self):
        d=asset(72)
        d.update({"near20":False,"breakout":False,"cross_up21":False})
        s,t,_=reconcile_buy_label(d,"MANTENER / ESPERAR","hold",[],True,
                                  buy_candidate(d,"MANTENER / ESPERAR",True),
                                  "DEFENSIVO",18)
        self.assertEqual(s,"VIGILAR COMPRA · SCORE")
        a={"ticker":"AAA","usa":"AAA","sector":"Salud",
           "signal":s,"data":d,"earnings":None}
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",18)[0])

    def test_color_is_really_green_not_just_label(self):
        css=(ROOT/"docs/style.css").read_text(encoding="utf-8")
        js=(ROOT/"docs/app.js").read_text(encoding="utf-8")
        html=(ROOT/"docs/index.html").read_text(encoding="utf-8")
        self.assertIn("background-color:#087e42",css)
        self.assertIn("background-color:#1f8e4b",css)
        self.assertIn("tr.buy-strong td",css)
        self.assertIn("tr.buy-cautious td",css)
        self.assertIn("String(s||'').startsWith('VIGILAR')",js)
        self.assertIn("buy-strong",js)
        self.assertIn("buy-cautious",js)
        self.assertIn("Score Oportunidad",html)
        self.assertIn("≥70",html)


if __name__=="__main__":
    unittest.main()
