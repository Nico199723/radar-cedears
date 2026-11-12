"""Regresión determinista del espectro SMA21 y pendientes RSI/MACD.

No usa cotizaciones de red, ni la vela t+1. Verifica puntuación descendente
de un cruce reciente a tendencia madurada, y pérdida precoz de pendiente.
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from radar_features import sma21_priority,opportunity_score,score_penalties


def ranked(row):
    d={"score":78,"sma21_component":row["sma21_component"],
       "volume_confirm_score":85,"rs_score":75,"rs_verified":True,
       "rsi14d":58,"rsi21w":55,"rsi21m":60,
       "price":105,"ma200":95,
       "indicator_slope_penalty":row["indicator_slope_penalty"],
       "indicator_slope_reasons":row["indicator_slope_reasons"]}
    return opportunity_score(d,True),d


class SpectrumTests(unittest.TestCase):
    def test_fresh_cross_beats_ten_sessions_above_21(self):
        # Mismo perfil positivo RSI/MACD, sólo cambia la edad del cruce.
        fresh=pd.Series([100.]*64+[101.])
        mature=pd.Series([100.]*54+[101.]*11)
        a=sma21_priority(fresh,atr=2)
        b=sma21_priority(mature,atr=2)
        self.assertTrue(a["cross_up21"])
        self.assertEqual(a["sma21_age"],1)
        self.assertEqual(b["sma21_age"],11)
        self.assertLess(b["sma21_component"],a["sma21_component"])
        self.assertLess(ranked(b)[0],ranked(a)[0])

    def test_rsi_and_macd_turn_down_while_still_positive(self):
        c=pd.Series([100.]*64+[102.])
        r_up=pd.Series([55.]*61+[56.,57.,58.,59.])
        r_down=pd.Series([55.]*61+[61.,60.,59.,58.])
        m_up=pd.Series([.10]*61+[.13,.16,.19,.22])
        m_down=pd.Series([.10]*61+[.22,.19,.16,.13])
        a=sma21_priority(c,r_up,m_up,atr=2)
        b=sma21_priority(c,r_down,m_down,atr=2)
        self.assertEqual(a["sma21_age"],b["sma21_age"])
        self.assertEqual(a["sma21_component"],b["sma21_component"])
        self.assertEqual(a["indicator_slope_penalty"],0)
        self.assertGreater(b["indicator_slope_penalty"],0)
        self.assertLess(ranked(b)[0],ranked(a)[0])
        self.assertTrue(any("RSI" in s for s in b["indicator_slope_reasons"]))
        self.assertTrue(any("MACD" in s for s in b["indicator_slope_reasons"]))

    def test_single_day_rsi_falling_already_deducts(self):
        c=pd.Series([100.]*64+[102.])
        r=pd.Series([55.]*61+[56.,57.,58.,57.5])
        m=pd.Series([.10]*61+[.13,.15,.18,.19])
        x=sma21_priority(c,r,m,atr=2)
        self.assertGreaterEqual(x["indicator_slope_penalty"],2)
        self.assertLess(x["rsi_delta1"],0)

    def test_trend_age_is_cut_when_price_closes_below_sma21(self):
        c=pd.Series([100.]*55+[103.]*9+[95.])
        x=sma21_priority(c,atr=2)
        self.assertTrue(x["cross_down21"])
        self.assertEqual(x["sma21_age"],0)
        self.assertLess(x["sma21_component"],15)

    def test_flattening_ma21_reduces_timing_score(self):
        # Reversión moderada sin perder el nivel: media21 deja de subir.
        rising=pd.Series(np.linspace(100,110,80))
        flat=pd.Series([100.]*49+list(np.linspace(100,110,21))+[110.]*10)
        a=sma21_priority(rising,atr=2)
        b=sma21_priority(flat,atr=2)
        self.assertGreaterEqual(a["sma21_slope_pct3"],0)
        self.assertLessEqual(b["sma21_slope_pct3"],a["sma21_slope_pct3"])

    def test_unchanged_history_when_appending_future_bar(self):
        c=pd.Series(np.linspace(95,104,70),index=pd.bdate_range("2026-07-01",periods=70))
        orig=sma21_priority(c,atr=2)
        c2=pd.concat([c,pd.Series([80],index=[c.index[-1]+pd.offsets.BDay(1)])])
        self.assertEqual(sma21_priority(c2.iloc[:-1],atr=2),orig)

    def test_macd_positive_but_falling_still_penalized(self):
        m=pd.Series([.10]*61+[.24,.22,.20,.18])
        r=pd.Series([55.]*65)
        x=sma21_priority(pd.Series([100.]*64+[102.]),r,m,atr=2)
        self.assertGreater(x["indicator_slope_penalty"],0)
        self.assertGreater(m.iloc[-1],0)
        self.assertTrue(any("MACD" in s for s in x["indicator_slope_reasons"]))


if __name__=="__main__":
    unittest.main()
