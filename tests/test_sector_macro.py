"""La vista Sectores debe aplicar la misma excepción macro que los ETFs individuales."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from actualizar import get_signal
from radar_features import cautious_signal


class SectorMacroConsistency(unittest.TestCase):
    def test_sector_proxy_uses_cautious_filter_after_original_signal(self):
        source=(ROOT/"scripts/actualizar.py").read_text(encoding="utf-8")
        sector=source.split("    sector_audit=[]\n    for sector,proxy in SECTORS.items():",1)[1].split("    logging.info(",1)[0]
        self.assertIn("decision=decide(val,macro,vixvalue,fresh).public()",sector)
        self.assertIn("'signal':decision[\"signal\"]",sector)
        self.assertIn("sectors.append(",sector)
        self.assertIn("'sector_signal_counts':",source)

    def test_etf_sector_may_buy_under_qqq_spy_sma50(self):
        d={"price":100,"ma20":99,"ma21":98,"ma50":95,"ma200":90,
           "score":81,"rank_score":74,"trend":"ALCISTA",
           "rsi14d":57,"rsi21w":58,"macd_hist_d":.4,"macd_hist_w":.3,
           "rank_penalty":2,"rvol20":1.2,"dollar_volume20":50000000,
           "volume_confirm_score":80,"obv_up10":True,
           "rs_verified":True,"rs_score":71,"rs_spy20":5,"rs_qqq20":6,
           "stretch_atr20":.5,"near20":True,"breakout":False,
           "cross_up21":True,"sma21_age":1}
        base,_,_=get_signal(d,"DEFENSIVO",True)
        self.assertEqual(base,"ESPERAR MACRO")
        new,_,_=cautious_signal(d,"DEFENSIVO",19,True,base)
        self.assertEqual(new,"COMPRA CON PRECAUCIÓN")
        bad,_,_=cautious_signal(d,"DEFENSIVO",31,True,base)
        self.assertNotEqual(bad,"COMPRA CON PRECAUCIÓN")


if __name__=="__main__":
    unittest.main()
