"""Cuchillo cayendo, RSI, ATR, volumen, earnings, RR y separación del ledger."""
import sys,unittest,math
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from rebound import (PARAMS,candidate,indicators,proposed_trade,
                     scan_rebounds,PAPER_REBOUND,HIGH_RISK_LABEL,EXCLUDED_LEVERAGED_INVERSE)
from backtest_rebound import simulate,metrics

def frame():
    idx=pd.bdate_range("2025-01-01",periods=250)
    px=np.concatenate([np.full(190,120.),np.linspace(120,65,60)])
    # última vela verde de reversión cerca del low
    opens=px.copy();opens[-1]=64.5
    highs=px+2;lows=px-2;highs[-1]=67;lows[-1]=63
    vol=np.full(250,2_000_000.);vol[-1]=4_000_000
    return pd.DataFrame({"Open":opens,"High":highs,"Low":lows,
                         "Close":px,"Volume":vol},index=idx)
class ReboundTests(unittest.TestCase):
    def test_flags_separate_from_paper(self):
        self.assertFalse(PAPER_REBOUND)
        src=(ROOT/"scripts/paper_sim.py").read_text()
        self.assertNotIn("from rebound import",src)
        self.assertIn("ALTO RIESGO",HIGH_RISK_LABEL)
    def test_reject_etfs_inverse(self):
        f=frame()
        for name in ("TQQQ","SQQQ","SOXL"):
            self.assertIsNone(candidate(f,name))
    def test_requires_rsi_below_30(self):
        f=frame()
        x=indicators(f)
        self.assertIsNotNone(x)
        self.assertIsNone(candidate(f,"AAPL") if x["rsi"]>30 else
                          candidate(f.assign(Close=np.full(250,120.)),"AAPL"))
    def test_earnings_veto_and_rr(self):
        f=frame()
        self.assertIsNone(candidate(f,"AAPL",{"days_until":4}))
        x=indicators(f)
        if x is not None:
            trade=proposed_trade(x)
            if trade:
                self.assertGreaterEqual(trade["rr"],2)
                self.assertLess(trade["stop_usd"],x["price"])
                self.assertGreater(trade["target_usd"],x["price"])
    def test_full_reversal_with_confirmations_and_risk_reward(self):
        from unittest.mock import patch
        f=frame()
        x=indicators(f)
        self.assertIsNotNone(x)
        x.update({"rsi":22.0,"rsi_delta":2.0,"macd_improving":True,
                  "range_position":.85,"green_body":True,"rvol":1.9,
                  "climax_drying":False,"dollar_volume20":40_000_000.,
                  "drawdown_pct":30.,"distance_atr":-3.,
                  "price":65.,"low":63.,"atr":2.,"ma10":72.,"ma21":78.,
                  "recent_low":62.,"recent_high":100.,"ma200":105.})
        with patch("rebound.indicators",return_value=x):
            out=candidate(f,"NVDA")
            self.assertIsNotNone(out)
            self.assertGreaterEqual(out["rr"],2)
            self.assertEqual(out["entry_tranches"],[100])
            self.assertEqual(out["structure"],"CAPITULACIÓN · BAJO SMA200")
            self.assertIsNone(candidate(f,"NVDA",{"days_until":5}))
        for field,value in (("rsi",31),("macd_improving",False),
                            ("range_position",.2),("green_body",False),
                            ("rvol",.3),("dollar_volume20",1000)):
            changed=dict(x);changed[field]=value
            with patch("rebound.indicators",return_value=changed):
                self.assertIsNone(candidate(f,"NVDA"),field)

    def test_next_day_not_used_when_calculating_signals(self):
        f=frame()
        current=indicators(f)
        future=pd.DataFrame({"Open":[42.],"High":[43.],
                    "Low":[40.],"Close":[41.],"Volume":[2e6]},
                    index=[f.index[-1]+pd.offsets.BDay(1)])
        extended=pd.concat([f,future])
        self.assertEqual(indicators(extended.iloc[:-1]),current)

    def test_first_8_only_and_no_trend_contamination(self):
        a=(ROOT/"scripts/actualizar.py").read_text()
        self.assertIn("'rebounds':rebounds",a)
        self.assertIn("'paper_rebound':False",a)
        self.assertFalse(PAPER_REBOUND)
        self.assertEqual(PARAMS.max_rows,8)
        self.assertEqual(PARAMS.time_stop_sessions,7)
    def test_synthetic_stop_gap_more_negative_than_expected(self):
        idx=pd.bdate_range("2026-01-01",periods=5)
        f=pd.DataFrame({"Open":[100,100,87,100,101],
                        "High":[101,103,89,102,102],
                        "Low":[99,99,85,99,100],
                        "Close":[100,101,86,101,101],
                        "Volume":[2e6]*5},index=idx)
        sig={idx[0]:{"entry_ref":100,"stop_usd":95,"target_usd":111,"rr":2.2}}
        trades,curve=simulate(f,sig,"AAPL",fee_bps=0,slip_bps=0)
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["entry_date"],str(idx[1].date()))
        self.assertEqual(trades[0]["exit_date"],str(idx[2].date()))
        self.assertEqual(trades[0]["reason"],"STOP GAP")
        self.assertLess(trades[0]["net_r"],-1)
    def test_target_stop_same_candle_stop_first(self):
        idx=pd.bdate_range("2026-01-01",periods=4)
        f=pd.DataFrame({"Open":[100]*4,"High":[101,120,102,101],
                        "Low":[99,90,98,98],"Close":[100,110,100,100],
                        "Volume":[2e6]*4},index=idx)
        sig={idx[0]:{"entry_ref":100,"stop_usd":95,"target_usd":111,"rr":2.2}}
        trades,_=simulate(f,sig,"AAPL",fee_bps=0,slip_bps=0)
        self.assertEqual(trades[0]["reason"],"STOP MISMA VELA")
    def test_time_stop_fills_at_open_before_intraday_high_target(self):
        # Tras siete ruedas sin salida, la siguiente apertura debe cerrar
        # por tiempo. No puede mirar un máximo futuro de la misma rueda.
        dates=pd.bdate_range("2026-01-01",periods=12)
        opens=[100.]*12
        highs=[101.]*12
        lows=[99.]*12
        closes=[100.]*12
        highs[9]=120.  # Objetivo tocado DESPUÉS de la apertura de salida temporal
        frame=pd.DataFrame({"Open":opens,"High":highs,"Low":lows,
                            "Close":closes,"Volume":[2_000_000]*12},index=dates)
        signal={dates[0]:{"entry_ref":100,"stop_usd":95,
                          "target_usd":111,"rr":2.2}}
        trades,_=simulate(frame,signal,"TEST",fee_bps=0,slip_bps=0,
                          time_stop_sessions=7)
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]["reason"],"TIEMPO")
        self.assertEqual(trades[0]["exit_date"],str(dates[9].date()))
        self.assertEqual(trades[0]["exit"],100.)

    def test_ui_is_experimental_distinct(self):
        html=(ROOT/"docs/index.html").read_text()
        js=(ROOT/"docs/app.js").read_text()
        self.assertIn('data-tab="rebotes"',html)
        self.assertIn('id="reboundRows"',html)
        self.assertIn("EXPERIMENTAL",html)
        self.assertIn("renderRebounds()",js)
        self.assertIn("j.rebounds=[]",js)
        self.assertIn("pageRebotes",js)
if __name__=="__main__":unittest.main()
