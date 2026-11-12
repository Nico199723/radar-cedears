"""Score informativo: penalizaciones, fuerza relativa 20r y volumen confirmado."""
import unittest
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import relative_strength,opportunity_score,volume_profile,top_five


def row():
    return {"score":80,"sma21_component":85,"volume_confirm_score":85,
            "rs_score":70,"rs_verified":True,"rs_spy20":5,"rs_qqq20":4,
            "rsi14d":58,"rsi21w":55,"rsi21m":60,"price":105,"ma200":95,
            "roc20":8,"ma20":102,"ma21":102,"rvol20":1.6,
            "dollar_volume20":25_000_000,"near20":True,"breakout":False,
            "macd_hist_d":.4,"stretch_atr20":.5,"invalid_usd":96,
            "target_2r":124,"sma21_state":"CRUCE RECIENTE","date":"2026-11-11"}


class ScoreComponentTests(unittest.TestCase):
    def test_rs_two_indices_no_future_and_no_duplicate_columns(self):
        dates=pd.bdate_range("2026-01-02",periods=70)
        spy=pd.Series(np.linspace(100,105,70),index=dates)
        qqq=pd.Series(np.linspace(100,110,70),index=dates)
        close=pd.Series(np.linspace(100,125,70),index=dates)
        a=relative_strength(close,spy,qqq)
        self.assertTrue(a["rs_verified"])
        self.assertGreater(a["rs_spy20"],0)
        self.assertGreater(a["rs_qqq20"],0)
        # SPY como activo no debe causar duplicación de columnas pandas.
        b=relative_strength(spy,spy,qqq)
        self.assertEqual(b["rs_spy20"],0)
        future=dates[-1]+pd.offsets.BDay(1)
        spy2=pd.concat([spy,pd.Series([250],index=[future])])
        self.assertEqual(relative_strength(close,spy2,qqq),a)
        self.assertFalse(relative_strength(close,spy.iloc[:-1],qqq)["rs_verified"])

    def test_rsi_80_penaliza_vs_neutro_y_25_sobreventa(self):
        neutral=row()
        a=opportunity_score(neutral,True)
        hot=row()
        hot["rsi14d"]=80
        b=opportunity_score(hot,True)
        self.assertEqual(a-b,30)
        self.assertTrue(any("RSI" in x for x in hot["rank_penalty_reasons"]))
        cold=row()
        cold["rsi14d"]=25
        self.assertEqual(a-opportunity_score(cold,True),24)

    def test_bajo_sma200_pierde_puntos(self):
        good=row()
        normal=opportunity_score(good,True)
        poor=row()
        poor["ma200"]=115
        self.assertGreaterEqual(normal-opportunity_score(poor,True),20)
        self.assertTrue(any("SMA200" in x for x in poor["rank_penalty_reasons"]))

    def test_rs_no_verificado_penaliza_y_top5_no_inventa(self):
        x=row()
        x.update(rs_verified=False,rs_score=None,rs_spy20=None,rs_qqq20=None)
        opportunity_score(x,True)
        self.assertTrue(any("no verificada" in s for s in x["rank_penalty_reasons"]))
        a={"ticker":"AA","usa":"AA","sector":"Salud","signal":"ESPERAR",
           "data":x,"earnings":None}
        self.assertEqual(top_five([a],None,"DEFENSIVO"),[])

    def test_volumen_inusual_bajista_no_puntua_mejor_que_alcista(self):
        dates=pd.bdate_range("2026-08-01",periods=45)
        close=np.linspace(100,120,45)
        volume=np.array([2_000_000]*44+[10_000_000])
        def make(p):
            return pd.DataFrame({"Open":p-1,"Close":p,"High":p+1,"Low":p-2,
                                "Volume":volume},index=dates)
        bull=volume_profile(make(close))
        down=close.copy()
        down[-1]=close[-2]-8
        bear=volume_profile(make(down))
        self.assertGreater(bull["rvol20"],4)
        self.assertGreater(bull["volume_confirm_score"],bear["volume_confirm_score"])

    def test_etf_in_top_five_when_rs_verified(self):
        x=row()
        x["rank_score"]=opportunity_score(x,False)
        a={"ticker":"IBB","usa":"IBB","sector":"Índices y ETFs",
           "signal":"ESPERAR MACRO","data":x,"earnings":None}
        out=top_five([a],{"roc20":3},"DEFENSIVO")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["ticker"],"IBB")
        self.assertEqual(out[0]["relative_qqq20"],4)

if __name__=="__main__":
    unittest.main()
