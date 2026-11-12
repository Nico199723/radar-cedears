"""Espectro continuo, elegibilidad explícita y semáforo verde por señal.

Sólo datos sintéticos. El score ALTO no es orden ni modificación retroactiva.
"""
import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import score_penalties,sma21_priority,opportunity_score,buy_candidate,cautious_signal


def sample():
    return {"score":79,"rank_score":79,"rsi14d":58,"rsi21w":55,"rsi21m":54,
            "price":100,"ma21":98,"ma20":99,"ma50":96,"ma200":90,
            "macd_hist_d":.5,"macd_hist_w":.25,"near20":False,"breakout":False,
            "cross_up21":False,"sma21_age":4,"obv_up10":True,
            "rs_verified":True,"rs_spy20":3,"rs_qqq20":4,"rs_score":72,
            "dollar_volume20":25_000_000,"rvol20":1.2,
            "volume_confirm_score":78,"rank_penalty":0,
            "stretch_atr20":.65}


class SmoothScoreTests(unittest.TestCase):
    def test_rsi_around_70_moves_smoothly_without_jump(self):
        vals=[]
        for value in [69.8,69.9,70,70.1,70.2]:
            row=sample();row["rsi14d"]=value
            vals.append(score_penalties(row)[0])
        self.assertEqual(vals,sorted(vals))
        self.assertLess(max(b-a for a,b in zip(vals,vals[1:])),.4)
        self.assertAlmostEqual(score_penalties({**sample(),"rsi14d":80})[0],30)
        self.assertAlmostEqual(score_penalties({**sample(),"rsi14d":25})[0],24)

    def test_sma200_small_break_does_not_immediately_lose_20_points(self):
        d=sample()
        above=score_penalties({**d,"price":90.01})[0]
        just_below=score_penalties({**d,"price":89.99})[0]
        deep=score_penalties({**d,"price":81})[0]
        self.assertLess(just_below-above,1)
        self.assertGreater(deep,just_below)
        self.assertGreater(deep,20)

    def test_rsi_and_macd_turn_without_negative_indicator(self):
        c=pd.Series([100.]*64+[103.])
        r_flat=pd.Series([55.]*65)
        r_down=pd.Series([55.]*61+[57.,56.,55.,54.])
        m_flat=pd.Series([.2]*65)
        m_down=pd.Series([.2]*61+[.25,.24,.23,.22])
        neutral=sma21_priority(c,r_flat,m_flat,atr=2)
        down=sma21_priority(c,r_down,m_down,atr=2)
        self.assertGreater(down["indicator_slope_penalty"],neutral["indicator_slope_penalty"])
        self.assertGreater(down["macd_delta3_pct"]*-1,0)
        self.assertEqual(neutral["indicator_slope_penalty"],0)

    def test_age_spectrum_not_abrupt_bucket(self):
        scores=[]
        for age in range(1,12):
            prices=[100.]*70+[103.]*age
            v=sma21_priority(pd.Series(prices),atr=2)
            scores.append(v["sma21_component"])
        self.assertGreater(scores[0],scores[-1])
        # Aumentar una sola rueda no pierde 12 puntos como antes.
        self.assertLess(max(abs(a-b) for a,b in zip(scores,scores[1:])),12)

    def test_near_flat_volume_signal_does_not_jump_30_pts(self):
        from radar_features import volume_profile
        dates=pd.bdate_range("2026-04-01",periods=50)
        close=np.linspace(100,110,50)
        volume=np.full(50,2_000_000.)
        def build(last):
            v=close.copy();v[-1]=last
            return pd.DataFrame({"Open":v,"High":v+2,"Low":v-2,
                                 "Close":v,"Volume":volume},index=dates)
        previous=close[-2]
        up=volume_profile(build(previous+.01))["volume_confirm_score"]
        down=volume_profile(build(previous-.01))["volume_confirm_score"]
        self.assertLess(abs(up-down),1.0)

    def test_candidate_threshold_and_reasons_without_buy_order(self):
        r=sample()
        s=buy_candidate({**r,"rank_score":61.9},"ESPERAR",True)
        self.assertFalse(s["eligible"])
        watch=buy_candidate({**r,"rank_score":68},"ESPERAR",True)
        self.assertTrue(watch["eligible"])
        self.assertEqual(watch["level"],"CANDIDATA · A CONFIRMAR")
        self.assertTrue(any("gatillo" in x for x in watch["blockers"]))
        priority=buy_candidate({**r,"rank_score":82},"ESPERAR",True)
        self.assertEqual(priority["level"],"PRIORIDAD DE COMPRA · A CONFIRMAR")
        unsafe=buy_candidate({**r,"rank_score":92,"rsi14d":80},"ESPERAR",True)
        self.assertFalse(unsafe["eligible"])
        self.assertIn("RSI",str(unsafe["blockers"]))
        self.assertFalse(buy_candidate(r,"DATOS VIEJOS",False)["eligible"])

    def test_two_green_tones_plus_separate_vigilance(self):
        js=(ROOT/"docs/app.js").read_text(encoding="utf-8")
        css=(ROOT/"docs/style.css").read_text(encoding="utf-8")
        html=(ROOT/"docs/index.html").read_text(encoding="utf-8")
        self.assertIn("s==='COMPRA CONDICIONAL'?'up'",js)
        self.assertIn("s==='COMPRA CON PRECAUCIÓN'?'caution'",js)
        self.assertIn(".pill.up{background:",css)
        self.assertIn(".pill.caution{background:",css)
        self.assertIn('value="vigilancia"',html)
        self.assertIn('value="priority"',html)
        self.assertIn('id="buyCaption"',html)

    def test_paper_does_not_buy_just_because_candidate(self):
        from paper_sim import evaluate_entry
        x=sample()
        x["rank_score"]=92
        a={"ticker":"ABC","usa":"ABC","sector":"Industriales",
           "data":x,"signal":"VIGILAR COMPRA · SCORE","earnings":None}
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",18)[0])


if __name__=="__main__":
    unittest.main()
