import sys, unittest, copy
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_lectura_espectral import build,FRESH,KNIFE,friendly_macro
import spectrum_config as cfg
from lectura_espectral import story,read,normalized_macro,signal_for
from decision_engine import decide,audit_consistency,top_five_by_decision,hard_vetoes
from spectrum_snapshot import apply_asset,apply_snapshot

class SpectrumIntegrationTests(unittest.TestCase):
    def asset(self,ticker='A',volume=10_000_000):
        return apply_asset({'ticker':ticker,'usa':ticker,'sector':'Tech','data':{'score':0,'rank_score_signal':100}},
                           build(FRESH,volume=volume),None,friendly_macro())

    def test_same_score_display_decision_and_audit(self):
        a=self.asset();self.assertEqual(a['score_decision'],a['data']['rank_score'])
        self.assertEqual(audit_consistency([a],mode='spectrum'),[])
        for key,val in [('signal','HOLD / ESPERAR'),('score_decision',99)]:
            b=copy.deepcopy(a);b[key]=val
            self.assertTrue(audit_consistency([b],mode='spectrum'))

    def test_extreme_vix_and_missing_macro_neutral_not_veto(self):
        f=build(FRESH)
        for macro in (None,{'verified':True,'vix':32,'wind':-1,'size_mult':.9,'label':'EN CONTRA'}):
            r=read(f,macro=macro)
            self.assertEqual(r.macro['wind'],0)
            self.assertEqual(r.macro['label'],'NEUTRAL')
            self.assertLess(r.size_mult,1)
            self.assertTrue(r.frictions)
            self.assertIn(r.signal,('COMPRA CONDICIONAL','COMPRA CON PRECAUCIÓN'))

    def test_macro_clamped_and_partial_not_verified(self):
        self.assertEqual(normalized_macro({'verified':True,'vix':19,'wind':50,'size_mult':5})['wind'],1)
        self.assertFalse(normalized_macro({'verified':True,'wind':1})['verified'])

    def test_exact_boundary_is_visible_boundary(self):
        for score,expected in [(44.9,'HOLD / ESPERAR'),(45,'VIGILAR COMPRA · SCORE'),
                               (54.9,'VIGILAR COMPRA · SCORE'),(55,'COMPRA CON PRECAUCIÓN'),
                               (65.9,'COMPRA CON PRECAUCIÓN'),(66,'COMPRA CONDICIONAL')]:
            self.assertEqual(signal_for(score,0),expected)
        self.assertEqual(signal_for(44,65),'REDUCIR / EVITAR')
        self.assertEqual(signal_for(44,80),'SALIR / EVITAR')

    def test_top_fills_fallback_soft_sector_and_no_duplicates(self):
        rows=[self.asset(str(i)) for i in range(7)]
        for i,a in enumerate(rows):
            a['data']['rank_score']=54-i;a['score_decision']=54-i
            a['data']['spectrum']['score_decision']=54-i
        top=top_five_by_decision(rows,mode='spectrum')
        self.assertEqual(len(top),5);self.assertTrue(all(x['fallback'] for x in top))
        self.assertEqual([x['rank_score'] for x in top],[54,53,52,51,50])
        self.assertTrue(any('CUPO SECTORIAL RELAJADO' in x['tag'] for x in top))
        self.assertEqual(top_five_by_decision(rows,limit=0,mode='spectrum'),[])
        rows[1]['usa']=rows[0]['usa']
        self.assertEqual(len({x['usa'] for x in top_five_by_decision(rows,mode='spectrum')}),5)

    def test_two_per_sector_when_alternatives_exist(self):
        rows=[self.asset(str(i)) for i in range(8)]
        for i,a in enumerate(rows):
            a['sector']='Tech' if i<3 else str(i)
            a['data']['rank_score']=80-i
        top=top_five_by_decision(rows,mode='spectrum')
        self.assertEqual(sum(x['sector']=='Tech' for x in top),2)
        self.assertEqual([x['rank_score'] for x in top],sorted([x['rank_score'] for x in top],reverse=True))

    def test_only_hard_stops_excluded_from_top(self):
        thin=self.asset('THIN',2000);normal=self.asset()
        self.assertEqual(thin['signal'],'NO OPERABLE')
        self.assertEqual([a['ticker'] for a in top_five_by_decision([thin,normal],mode='spectrum')],['A'])
        self.assertEqual(hard_vetoes(normal['data'],'NO VERIFICADO',40,True,{'days_until':1},mode='spectrum'),())

    def test_append_future_does_not_change_reading(self):
        f=build(FRESH);original=read(f).public()
        fut=f.iloc[-1:].copy();fut.index=fut.index+pd.offsets.BDay(1);fut['Close']*=.5
        extended=pd.concat([f,fut])
        self.assertEqual(read(extended.loc[:f.index[-1]]).public(),original)

    def test_weekly_uses_closed_friday_only(self):
        f=build(FRESH)
        # Fixture ends Thursday; its partial week must not enter weekly MACD.
        x=story(f);cut=f[f.index.dayofweek==4].index[-1]
        y=story(f.loc[:cut])
        self.assertEqual(x['macd_hist_w_n'],y['macd_hist_w_n'])

    def test_flat_rsi_and_json_integrity(self):
        import json
        f=build(FRESH);f['Close']=100;f['Open']=100;f['High']=101;f['Low']=99
        self.assertEqual(story(f)['rsi14'],50)
        json.dumps(read(f).public(),allow_nan=False)

    def test_legacy_state_does_not_mutate(self):
        a={'ticker':'A','usa':'A','data':{'rank_score':92},'signal':'OLD'}
        before=copy.deepcopy(a);apply_asset(a,build(FRESH),None,friendly_macro())
        self.assertEqual(a,before)
        self.assertEqual(cfg.ACTIVE_ENGINE,'unified')

if __name__=='__main__':unittest.main()
