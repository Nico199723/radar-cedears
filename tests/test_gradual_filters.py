"""Weak verified evidence is scored, missing evidence still blocks execution."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from decision_engine import decide,BUY_SIGNALS,hard_vetoes,audit_consistency,RULES_VERSION
from test_decision_consistency import row,asset


class GradualFiltersTests(unittest.TestCase):
    def test_verified_weak_inputs_do_not_veto_twice(self):
        for field,value in [('price',102),('macd_hist_d',-.001),('macd_hist_w',-.001),('rsi14d',75.01),('obv_up10',False)]:
            r=row(72);r[field]=value
            result=decide(r,'FAVORABLE',18,True)
            self.assertEqual(result.signal,'COMPRA CON PRECAUCIÓN',field)
            self.assertEqual(result.score_decision,72)
            self.assertFalse(result.vetoes)
            self.assertGreater(len(result.reasons),1)
            self.assertEqual(audit_consistency([asset('X',r,result)]),[])

    def test_missing_is_not_weak(self):
        for field in ['ma21','ma200','macd_hist_d','macd_hist_w','rsi14d','obv_up10']:
            r=row(90);r[field]=None
            self.assertNotIn(decide(r,'FAVORABLE',18,True).signal,BUY_SIGNALS,field)
            self.assertTrue(hard_vetoes(r,'FAVORABLE',18,True),field)

    def test_zero_and_threshold_preserved(self):
        for score in [0,69.99]:
            r=row(score);r['obv_up10']=False
            d=decide(r,'FAVORABLE',18,True)
            self.assertEqual(d.score_decision,score)
            self.assertNotIn(d.signal,BUY_SIGNALS)
        self.assertIn(decide(row(70),'FAVORABLE',18,True).signal,BUY_SIGNALS)

    def test_structural_exit_is_not_softened(self):
        r=row(90);r.update(price=90,macd_hist_d=-1,rsi14d=30)
        self.assertEqual(decide(r,'FAVORABLE',18,True).signal,'SALIR / EVITAR')
        r.update(price=110,rsi14d=45)
        self.assertEqual(decide(r,'FAVORABLE',18,True).signal,'REDUCIR / EVITAR')

    def test_risk_vetoes_and_timing_preserved(self):
        for macro,vix,fresh,earnings in [('NO VERIFICADO',18,True,None),('FAVORABLE',30,True,None),('FAVORABLE',None,True,None),('FAVORABLE',18,False,None),('FAVORABLE',18,True,{'days_until':3})]:
            self.assertNotIn(decide(row(95),macro,vix,fresh,earnings).signal,BUY_SIGNALS)
        r=row(72);r.update(near20=False,obv_up10=False)
        self.assertEqual(decide(r,'FAVORABLE',18,True).signal,'VIGILAR COMPRA · GATILLO')
        r['rank_score']=75
        self.assertEqual(decide(r,'FAVORABLE',18,True).signal,'COMPRA CON PRECAUCIÓN')

    def test_version_and_no_jump_on_marginal_macd(self):
        self.assertEqual(RULES_VERSION,'2.1-gradual-confirmations')
        for v in [-.0001,0,.0001]:
            r=row(72);r['macd_hist_d']=v
            self.assertIn(decide(r,'FAVORABLE',18,True).signal,BUY_SIGNALS)
