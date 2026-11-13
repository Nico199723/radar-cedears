"""Contradicciones con bordes y 1200 escenarios aleatorios sin cotizaciones."""
import sys,unittest,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from decision_engine import decide,hard_vetoes,audit_consistency,top_five_by_decision
from decision_engine import BUY_FLOOR,PRIORITY_FLOOR,REDUCE_FLOOR,EXIT_FLOOR,OPPORTUNITY_SIGNALS

def row(score=75):
    return {"rank_score":score,"score":42,"rank_score_signal":88,
            "price":120,"ma21":117,"ma50":112,"ma200":103,
            "rsi14d":55,"rsi21w":57,"rvol20":1.4,"dollar_volume20":20000000,
            "macd_hist_d":.5,"macd_hist_w":.1,"obv_up10":True,
            "rs_verified":True,"near20":True,"breakout":False,"cross_up21":False}
def asset(ticker,r,decision):
    d=decision.public()
    return {"ticker":ticker,"data":r,"signal":d["signal"],
            "score_decision":d["score_decision"],"vetoes":d["vetoes"]}
class DecisionConsistencyTests(unittest.TestCase):
    def test_thresholds_single_source(self):
        self.assertEqual((BUY_FLOOR,PRIORITY_FLOOR,REDUCE_FLOOR,EXIT_FLOOR),(70,75,35,18))
        self.assertNotIn(decide(row(69.99),"FAVORABLE",18,True).signal,OPPORTUNITY_SIGNALS)
        self.assertIn(decide(row(70),"FAVORABLE",18,True).signal,OPPORTUNITY_SIGNALS)
        r=row(75);r.update(near20=False,cross_up21=False,breakout=False)
        self.assertEqual(decide(r,"DEFENSIVO",18,True).signal,"COMPRA CON PRECAUCIÓN")
    def test_unified_decision_ignores_two_legacy_scores(self):
        r=row(75)
        original=decide(r,"FAVORABLE",18,True)
        r.update(score=0,rank_score_signal=0)
        new=decide(r,"FAVORABLE",18,True)
        self.assertEqual(original.signal,new.signal)
        self.assertEqual(original.score_decision,new.score_decision)
    def test_high_score_with_veto_not_opportunity(self):
        for k,v in [("price",99),("macd_hist_d",-.3),("dollar_volume20",1000),
                    ("rsi14d",80),("rs_verified",False),("obv_up10",False)]:
            r=row(95);r[k]=v
            d=decide(r,"FAVORABLE",18,True)
            self.assertNotIn(d.signal,OPPORTUNITY_SIGNALS,k)
            self.assertTrue(d.vetoes,k)
        d=decide(row(95),"DEFENSIVO",18,True,{"days_until":4})
        self.assertEqual(d.signal,"SCORE ALTO · VETADO")
        self.assertIn("BALANCE EN 7 DIAS",d.vetoes)
        self.assertNotIn(decide(row(95),"NO VERIFICADO",None,True).signal,OPPORTUNITY_SIGNALS)
    def test_macro_defensive_not_veto_by_50sma(self):
        d=decide(row(75),"DEFENSIVO",20,True)
        self.assertEqual(d.signal,"COMPRA CON PRECAUCIÓN")
    def test_audit_identifies_contradictions(self):
        a=asset("AAA",row(69),decide(row(69),"FAVORABLE",18,True))
        self.assertEqual(audit_consistency([a]),[])
        a["signal"]="COMPRA CONDICIONAL"
        self.assertTrue(audit_consistency([a]))
        v=asset("BBB",row(90),decide(row(90),"DEFENSIVO",18,True,{"days_until":2}))
        self.assertEqual(audit_consistency([v]),[])
        v["signal"]="VIGILAR COMPRA · SCORE"
        self.assertTrue(audit_consistency([v]))
    def test_legacy_watch_is_audited_not_mistaken_for_zero(self):
        current=asset("OLD",row(64),decide(row(64),"FAVORABLE",18,True))
        current["signal"]="VIGILAR COMPRA"  # etiqueta legacy que escapaba al audit
        violations=audit_consistency([current])
        self.assertTrue(any(x["reason"]=="opportunity_below_floor" for x in violations))
        blocked=asset("X",row(92),decide(row(92),"FAVORABLE",18,True))
        blocked["signal"]="VIGILAR COMPRA · MACRO"
        blocked["vetoes"]=["PRECIO BAJO SMA200"]
        self.assertTrue(any(x["reason"]=="opportunity_with_hard_veto"
                            for x in audit_consistency([blocked])))

    def test_workflow_distinguishes_production_from_proposed_audit(self):
        source=(ROOT/"scripts/actualizar.py").read_text(encoding="utf-8")
        self.assertIn("'production_consistency_violations':production_violations",source)
        self.assertIn("'proposed_consistency_count':len(consistency_violations)",source)
        self.assertIn("production_violations=audit_consistency(production_audit)",source)

    def test_random_rows_prove_invariants(self):
        rng=random.Random(4101);items=[]
        for i in range(1200):
            r=row(rng.uniform(0,100))
            r["price"]=rng.uniform(60,145)
            r["rsi14d"]=rng.uniform(15,90)
            r["macd_hist_d"]=rng.uniform(-1,1)
            r["dollar_volume20"]=rng.choice([1e4,4e6,20e6])
            r["rs_verified"]=rng.choice([True,False])
            r["near20"]=rng.choice([True,False])
            macro=rng.choice(["FAVORABLE","MIXTO","DEFENSIVO","NO VERIFICADO"])
            vix=rng.choice([10,19,28,30,35,None])
            earnings={"days_until":rng.choice([-2,0,3,8,30,None])}
            decision=decide(r,macro,vix,True,earnings)
            items.append(asset(str(i),r,decision))
        self.assertEqual(audit_consistency(items),[])
        for a in items:
            if a["signal"] in OPPORTUNITY_SIGNALS:
                self.assertGreaterEqual(a["score_decision"],BUY_FLOOR)
                self.assertFalse(a["vetoes"])
    def test_top5_and_table_same_score_order(self):
        rows=[asset(chr(65+i),row(score),decide(row(score),"FAVORABLE",18,True))
              for i,score in enumerate([79,91,70,85,77,90,95])]
        top=top_five_by_decision(rows)
        self.assertEqual(len(top),5)
        self.assertEqual([x["score_decision"] for x in top],
                         sorted([x["score_decision"] for x in top],reverse=True))
if __name__=="__main__":unittest.main()
