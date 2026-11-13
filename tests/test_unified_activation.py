"""Tarea1, activación: consistencia end-to-end del score visible y del paper.

Sin datos de red; el motor heredado sigue disponible para backtest A/B.
"""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from decision_engine import decide,audit_consistency,BUY_FLOOR
from radar_features import top_five
from paper_sim import evaluate_entry


def row(score=80):
    return {"asset_kind":"ACCION","date":"2026-11-12",
      "rank_score":score,"score":35,"rank_score_signal":15,
      "price":120.,"ma20":118.,"ma21":117.,"ma50":112.,"ma200":103.,
      "rsi14d":55.,"rsi21w":57.,"macd_hist_d":.5,"macd_hist_w":.1,
      "rvol20":1.3,"dollar_volume20":25_000_000,"obv_up10":True,
      "rs_verified":True,"rs_spy20":3,"rs_qqq20":5,
      "near20":True,"breakout":False,"cross_up21":False,
      "volume_confirm_score":75,"sma21_component":85,"sma21_state":"SOBRE SMA21",
      "rank_penalty":0,"high20":121,"low20":109,"invalid_usd":109}


def asset(ticker,score,market="FAVORABLE",vix=18):
    data=row(score)
    decision=decide(data,market,vix,True).public()
    data["score_decision"]=decision["score_decision"]
    return {"ticker":ticker,"usa":ticker,"sector":"Sector "+ticker,
      "data":data,"signal":decision["signal"],"tone":decision["tone"],
      "score_decision":decision["score_decision"],"vetoes":decision["vetoes"],
      "decision_v2_preview":decision,"reasons":decision["reasons"],
      "earnings":None}


class UnifiedProductionTests(unittest.TestCase):
    def test_score_visible_alone_drives_entries(self):
        a=asset("ONE",80)
        self.assertEqual(a["signal"],"COMPRA CON PRECAUCIÓN")
        self.assertTrue(evaluate_entry(a,"FAVORABLE",18)[0])
        a["data"]["score"]=0
        a["data"]["rank_score_signal"]=0
        self.assertTrue(evaluate_entry(a,"FAVORABLE",18)[0])
        self.assertEqual(a["score_decision"],80)

    def test_no_buy_below_floor_or_with_hard_veto(self):
        a=asset("LOW",69.99)
        self.assertFalse(evaluate_entry(a,"FAVORABLE",18)[0])
        b=asset("VETO",95)
        b["data"]["macd_hist_d"]=-.5
        self.assertFalse(evaluate_entry(b,"FAVORABLE",18)[0])
        self.assertEqual(decide(b["data"],"FAVORABLE",18,True).signal,
                         "SCORE ALTO · VETADO")
        self.assertEqual(audit_consistency([a]),[])
        self.assertEqual(audit_consistency([b]),[])

    def test_macro_under_spy_qqq_sma50_not_veto_if_vix_ok(self):
        a=asset("ETF",80,"DEFENSIVO",19)
        a["data"]["asset_kind"]="ETF / INDICE / NO CLASIFICADO"
        self.assertEqual(a["signal"],"COMPRA CON PRECAUCIÓN")
        self.assertTrue(evaluate_entry(a,"DEFENSIVO",19)[0])
        self.assertFalse(evaluate_entry(a,"NO VERIFICADO",None)[0])

    def test_topfive_order_same_decision_score_and_no_veto(self):
        assets=[asset("A",73),asset("B",92),asset("C",80),
                asset("D",69),asset("E",88),asset("F",96)]
        vetoed=asset("F",96)
        vetoed["data"]["macd_hist_d"]=-.2
        decision=decide(vetoed["data"],"FAVORABLE",18,True).public()
        vetoed.update(signal=decision["signal"],vetoes=decision["vetoes"])
        assets[-1]=vetoed
        top=top_five(assets,None,"FAVORABLE",strict_score=True)
        self.assertEqual([a["ticker"] for a in top],["B","E","C","A"])
        self.assertEqual([a["rank_score"] for a in top],[92,88,80,73])

    def test_main_generated_data_audited_before_writing(self):
        script=(ROOT/"scripts/actualizar.py").read_text(encoding="utf-8")
        self.assertIn("selection=top_five(assets,spy,macro,strict_score=True)",script)
        self.assertIn("production_violations=audit_consistency(",script)
        self.assertIn("if production_violations:",script)
        self.assertIn("'decision_mode':'UNIFIED ACTIVE",script)
        self.assertIn("'rules_version':'2.0-unified-decision-active'",script)

if __name__=="__main__":
    unittest.main()
