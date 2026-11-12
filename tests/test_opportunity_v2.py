"""RS índices, RSI extremos, volumen inusual y macro prudente para acciones y ETF."""
import unittest
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import (relative_strength,opportunity_score,score_penalties,
                            volume_profile,cautious_signal,top_five)
from paper_sim import evaluate_entry


def specimen():
    return {
        "asset_kind":"ETF / INDICE / NO CLASIFICADO","date":"2026-11-11",
        "price":105,"ma20":104,"ma21":103,"ma50":100,"ma200":95,
        "score":80,"rsi14d":58,"rsi21w":55,"rsi21m":60,
        "macd_hist_d":.5,"macd_hist_w":.2,"near20":True,
        "breakout":False,"cross_up21":False,
        "sma21_component":80,"obv_up10":True,"rvol20":1.8,
        "dollar_volume20":35_000_000,"stretch_atr20":.5,
        "volume_confirm_score":90,"rs_spy20":5,"rs_qqq20":6,
        "rs_score":75,"rs_verified":True,
        "high20":106,"low20":98,"invalid_usd":98,"target_2r":119,
        "roc20":6,"volume_score":9
    }


class OpportunityV2Tests(unittest.TestCase):
    def test_relative_strength_to_two_indices_no_future_data(self):
        dates=pd.bdate_range("2026-01-02",periods=70)
        asset=pd.Series(np.linspace(100,120,70),index=dates)
        spy=pd.Series(np.linspace(100,105,70),index=dates)
        qqq=pd.Series(np.linspace(100,108,70),index=dates)
        current=relative_strength(asset,spy,qqq)
        self.assertTrue(current["rs_verified"])
        self.assertGreater(current["rs_spy20"],0)
        self.assertGreater(current["rs_qqq20"],0)
        future=dates[-1]+pd.offsets.BDay(1)
        spy2=pd.concat([spy,pd.Series([300],index=[future])])
        qqq2=pd.concat([qqq,pd.Series([300],index=[future])])
        self.assertEqual(relative_strength(asset,spy2,qqq2),current)
        # Índice sin cierre en la misma fecha => no completar con la rueda siguiente.
        self.assertFalse(relative_strength(asset,spy.iloc[:-1],qqq)["rs_verified"])

    def test_ranking_composition_stock_and_etf(self):
        x=specimen()
        a=opportunity_score(x.copy(),True)
        b=opportunity_score(x.copy(),False)
        self.assertEqual(a,round(.30*80+.20*80+.30*75+.20*90))
        self.assertEqual(b,round(.35*80+.15*80+.30*75+.20*90))
        self.assertTrue(0<=a<=100 and 0<=b<=100)

    def test_rsi_80_penalizes_30_pts_and_prevents_buying(self):
        x=specimen()
        normal=opportunity_score(x.copy(),True)
        over=dict(x,rsi14d=80)
        score=opportunity_score(over,True)
        self.assertEqual(normal-score,30)
        self.assertIn("RSI14 diario",over["rank_penalty_reasons"][0])
        a={"ticker":"IBB","usa":"IBB","sector":"Índices y ETFs",
           "signal":"ESPERAR MACRO","data":over,"earnings":None}
        self.assertFalse(evaluate_entry(a,"DEFENSIVO",18)[0])
        self.assertEqual(top_five([a],None,"DEFENSIVO"),[])

    def test_extreme_oversold_rsi_penalized(self):
        x=specimen()
        baseline=opportunity_score(x.copy(),True)
        oversold=dict(x,rsi14d=25)
        self.assertEqual(baseline-opportunity_score(oversold,True),24)

    def test_below_sma200_deducts_and_is_no_buy(self):
        x=specimen()
        above=opportunity_score(x.copy(),True)
        x["ma200"]=115
        below=opportunity_score(x,True)
        self.assertGreaterEqual(above-below,20)
        self.assertIn("Bajo SMA200",str(x["rank_penalty_reasons"]))
        self.assertNotEqual(cautious_signal(x,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                            "COMPRA CON PRECAUCIÓN")

    def test_missing_relative_strength_is_penalized_and_not_buy(self):
        x=specimen()
        x.update(rs_verified=False,rs_score=None,rs_spy20=None,rs_qqq20=None)
        opportunity_score(x,True)
        self.assertIn("no verificada",str(x["rank_penalty_reasons"]))
        self.assertNotEqual(cautious_signal(x,"DEFENSIVO",18,True,"ESPERAR MACRO")[0],
                            "COMPRA CON PRECAUCIÓN")

    def test_unusual_volume_bullish_beats_bearish_climax(self):
        dates=pd.bdate_range("2026-08-01",periods=45)
        close=np.linspace(100,120,45)
        volume=np.array([2_000_000]*44+[10_000_000])
        make=lambda prices:pd.DataFrame({
            "Open":prices-1,"Close":prices,"High":prices+1,
            "Low":prices-2,"Volume":volume},index=dates)
        bullish=volume_profile(make(close))
        down=close.copy();down[-1]=close[-2]-8
        bearish=volume_profile(make(down))
        self.assertGreater(bullish["rvol20"],4)
        self.assertGreater(bullish["volume_confirm_score"],bearish["volume_confirm_score"])
        self.assertGreater(bullish["volume_confirm_score"],70)

    def test_etf_and_stock_share_macro_exception(self):
        x=specimen()
        x["rank_score"]=opportunity_score(x.copy(),False)
        assert x["rank_score"]>=63
        a={"ticker":"IBB","usa":"IBB","sector":"Índices y ETFs",
           "signal":"ESPERAR MACRO","data":x,"earnings":None}
        sig,_,_=cautious_signal(x,"DEFENSIVO",18,True,"ESPERAR MACRO")
        self.assertEqual(sig,"COMPRA CON PRECAUCIÓN")
        self.assertTrue(evaluate_entry(a,"DEFENSIVO",18)[0])
        q=top_five([a],None,"DEFENSIVO")
        self.assertEqual(q[0]["ticker"],"IBB")
        self.assertEqual(q[0]["relative_spy20"],x["rs_spy20"])
        self.assertEqual(q[0]["relative_qqq20"],x["rs_qqq20"])


if __name__=="__main__":
    unittest.main()
