import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from comparar_decision import compare
from backtest import Trade,metrics
import pandas as pd
class CompareTests(unittest.TestCase):
    def test_production_variant_includes_cautious_signal(self):
        import inspect
        from backtest import historical_decisions
        source=inspect.getsource(historical_decisions)
        self.assertIn('"production"',source)
        self.assertIn('next_signal,_,_=cautious_signal',source)
    def test_losing_streak(self):
        dates=pd.bdate_range("2026-01-01",periods=7)
        trades=[]
        for i,r in enumerate([-1,-1,1,-1,-1,-1,.5]):
            trades.append(Trade("A","2026-01-01","2026-01-02","2026-01-04",
                 100,95,95,"STOP",r*5,r))
        m=metrics(trades,pd.Series([1,.9,.8,.95,.85,.8,.92],index=dates))
        self.assertEqual(m["peor_racha_perdedora"],3)
    def test_comparison_includes_metrics(self):
        def report(n):
            return {"results":[{"ticker":"AAA","estado":"OK","n_senales_ejecutadas":n,
              "win_rate_pct":50,"r_promedio":.2,"max_drawdown_pct":16,
              "peor_racha_perdedora":2,
              "out_of_sample":{"operaciones":2,"acierto_pct":50,"expectancy_r":.1}}]}
        result=compare(report(5),report(7))
        self.assertEqual(result["current"]["trades"],5)
        self.assertEqual(result["proposed"]["trades"],7)
        self.assertEqual(result["proposed"]["worst_losing_streak"],2)
if __name__=="__main__":unittest.main()
