"""Adaptador compartido por el snapshot y el A/B. Nunca consulta datos futuros."""
from copy import deepcopy
from actualizar import last_complete_daily
from lectura_espectral import story, macro_wind, normalized_macro
from decision_engine import decide, audit_consistency, top_five_by_decision
import spectrum_config as cfg


def prepare_row(row, frame, bench=None):
    row = dict(row or {})
    row['_spectrum_story'] = story(frame, bench) if frame is not None else None
    return row


def apply_asset(asset, frame, bench, wind, fresh=True):
    a = deepcopy(asset)
    d = prepare_row(a.get('data'), frame, bench)
    decision = decide(d, '', None, fresh, a.get('earnings'), mode='spectrum', wind=wind).public()
    a.update(decision)
    from risk_experiment import position_plan
    facts=d.get('_spectrum_story')
    if facts:d['atr_risk_preview']=position_plan(facts['price'],facts['atr14'])
    a['data'] = d
    a['candidate'] = {'eligible':a['signal'].startswith('COMPRA'),
                      'level':a['stage'], 'blockers':[], 'frictions':a['frictions']}
    a['decision_v2_preview'] = None
    a['risk_plan_paper'] = None  # El ledger v2 NO representa el candidato v3.
    return a


def apply_snapshot(snapshot, frames, now):
    result = deepcopy(snapshot)
    frames = {k:last_complete_daily(v,now) for k,v in frames.items()}
    # Macro completa a la misma fecha: una fuente vieja es macro no verificada.
    dates=[v.index[-1].date() for v in frames.values() if len(v)]
    latest=max(dates) if dates else None
    fresh=lambda f: f is not None and len(f)>0 and f.index[-1].date()==latest and 0 <= (now.date()-latest).days <= 5
    s,q,v=(frames.get(k) for k in ('SPY','QQQ','^VIX'))
    wind=normalized_macro(macro_wind(s,q,v['Close'] if v is not None else None)
                          if all(fresh(f) for f in (s,q,v)) else None)
    bench=s['Close'] if s is not None else None
    for collection in ('assets','sectors'):
        result[collection]=[apply_asset(a,frames.get(a.get('usa',a.get('proxy'))),bench,wind,
                              fresh(frames.get(a.get('usa',a.get('proxy')))))
                            for a in result.get(collection,[])]
    violations=audit_consistency(result.get('assets',[])+result.get('sectors',[]),mode='spectrum')
    if violations:raise ValueError(violations)
    result['top5']=top_five_by_decision(result['assets'],mode='spectrum')
    result['top5_proposed']=result['top5']
    result['macro']={'state':wind['label'],'vix':wind.get('vix'),'spectrum':wind}
    result['rebounds']=[]
    result['meta'].update(rules_version=cfg.RULES_VERSION,decision_mode='SPECTRUM CANDIDATE',
        score_bands={'buy':cfg.BAND_BUY,'caution':cfg.BAND_CAUTION,'watch':cfg.BAND_WATCH},
        production_consistency_violations=[],production_consistency_count=0,
        asset_signal_counts={label:sum(a['signal']==label for a in result['assets'])
                             for label in sorted({a['signal'] for a in result['assets']})},
        note='Lectura espectral: score único, deterioro explícito y fricciones de tamaño. Candidato sin activar.',
        paper_rules_version='2.0-unified-decision-active')
    return result
