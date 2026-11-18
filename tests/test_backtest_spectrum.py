import sys, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from backtest_spectrum import aggregate,category
from backtest import simulate
from calibrate_spectrum import evaluate

class SpectralABTests(unittest.TestCase):
    def test_dd_is_worst_not_least_negative(self):
        rows=[{'trades':[],'metrics':{'max_drawdown_pct':x,'peor_racha_perdedora':2}} for x in (-3,-20)]
        self.assertEqual(aggregate(rows)['max_drawdown_peor_ticker_pct'],-20)

    def test_t_plus_one_gap_and_costs(self):
        ix=pd.bdate_range('2026-01-01',periods=3)
        f=pd.DataFrame({'Open':[100,110,105],'High':[102,112,108],'Low':[99,109,103],
                        'Close':[101,111,106],'Volume':[1e6]*3},index=ix)
        decisions={ix[0]:{'signal':'COMPRA CONDICIONAL','stop':95},ix[1]:{'signal':'REDUCIR / EVITAR','stop':95}}
        trades,_=simulate(f,decisions,'A');t=trades[0]
        self.assertEqual(t.entry_date,str(ix[1].date()))
        self.assertAlmostEqual(t.entry,110*1.001)
        self.assertEqual(t.exit_date,str(ix[2].date()))
        self.assertLess(t.net_return_pct, (105/110-1)*100)

    def test_distribution_preserves_exits(self):
        self.assertEqual(category('SALIR / EVITAR'),'salir')
        self.assertEqual(category('REDUCIR / EVITAR'),'reducir')
        self.assertEqual(category('SCORE ALTO · VETADO'),'esperar')

    def test_calibration_does_not_change_defaults(self):
        import lectura_espectral as sp
        before=(sp.BAND_BUY,sp.BAND_CAUTION,sp.BAND_WATCH)
        result=evaluate(pd.DataFrame(columns=['ticker']),{},(42,52,63),'2026-01-01','2026-02-01')
        self.assertEqual((sp.BAND_BUY,sp.BAND_CAUTION,sp.BAND_WATCH),before)
        self.assertEqual(result['operaciones'],0)
