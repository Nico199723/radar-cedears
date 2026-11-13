"""Yahoo entrega OHLC de ayer: conservar ledger, última valuación y publicar sin reset."""
import sys,unittest
from unittest.mock import patch
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from paper_sim import new_ledger,process_ledger,equity_at
from paper_store import load_or_initialize

class RegressionTests(unittest.TestCase):
    def test_restore_newer_state_instead_of_exception(self):
        s=new_ledger("2026-11-12","2026-11-12T21:00:00Z")
        with patch("paper_store.latest_state",return_value=s):
            same=load_or_initialize("2026-11-11","2026-11-13T09:00:00Z")
        self.assertIs(same,s)
        self.assertEqual(same["last_session"],"2026-11-12")
    def test_no_reprocessing_older_session(self):
        s=new_ledger("2026-11-12","2026-11-12T21:00:00Z")
        s["orders"]=[{"side":"BUY","usa":"NVDA","ticker":"NVDA",
                      "issued_day":"2026-11-12","tranche":1,"sector":"Tech"}]
        before=s["orders"][:]
        f=pd.DataFrame({"Open":[100.],"High":[101.],"Low":[99.],
                        "Close":[100.],"Volume":[1000000]},
                       index=pd.to_datetime(["2026-11-11"]))
        state=process_ledger(s,{"SPY":f,"NVDA":f},[],"DEFENSIVO",19,"2026-11-11")
        self.assertIs(state,s)
        self.assertEqual(state["orders"],before)
        self.assertEqual(state["fills"],[])
        self.assertEqual(state["last_session"],"2026-11-12")
    def test_price_backfill_does_not_overwrite_more_recent_mark(self):
        s=new_ledger("2026-11-12","2026-11-12T21:00:00Z")
        s["positions"]["NVDA"]={"shares":1.,"last_mark":110.,
                                 "last_mark_day":"2026-11-12"}
        f=pd.DataFrame({"Close":[90.]},index=pd.to_datetime(["2026-11-11"]))
        eq,pending=equity_at(s,{"NVDA":f},"2026-11-12")
        self.assertEqual(eq,2110)
        self.assertEqual(s["positions"]["NVDA"]["last_mark"],110)
        self.assertEqual(s["positions"]["NVDA"]["last_mark_day"],"2026-11-12")
        self.assertEqual(pending,[])
if __name__=="__main__":unittest.main()
