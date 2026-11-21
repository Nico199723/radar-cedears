"""Dispatch versionado: A congelada y B espectral, sin activación implícita."""
from dataclasses import dataclass
from collections import Counter
import math
import decision_engine_legacy as legacy
from decision_engine_legacy import (BUY_SIGNALS, WATCH_SIGNALS, OPPORTUNITY_SIGNALS,
    BUY_FLOOR, PRIORITY_FLOOR, REDUCE_FLOOR, EXIT_FLOOR, numeric, is_opportunity)
import spectrum_config as cfg
import lectura_espectral as spectrum

RULES_VERSION = legacy.RULES_VERSION if cfg.ACTIVE_ENGINE == 'unified' else cfg.RULES_VERSION

@dataclass
class SpectralDecision:
    reading: spectrum.Reading

    @property
    def signal(self): return self.reading.signal
    @property
    def score_decision(self): return self.reading.score
    @property
    def vetoes(self): return ()  # Compatibilidad del contrato público; fricciones separadas.
    def public(self):
        d = self.reading.public()
        d.update(tone=('up' if self.signal == 'COMPRA CONDICIONAL' else
                       'caution' if self.signal == 'COMPRA CON PRECAUCIÓN' else
                       'watch' if self.signal.startswith('VIGILAR') else
                       'down' if self.signal.startswith(('REDUCIR','SALIR')) else 'hold'),
                 vetoes=[], gate=self.reading.stage, reasons=self.reading.narrative,
                 hard_stops=([self.signal] if self.signal in ('SIN DATOS','NO OPERABLE') else []))
        return d


def hard_vetoes(row, macro, vix, fresh, earnings=None, *, mode=None):
    if (mode or cfg.ACTIVE_ENGINE) == 'unified':
        return legacy.hard_vetoes(row, macro, vix, fresh, earnings)
    f = (row or {}).get('_spectrum_story')
    if f is None: return ('SIN HISTÓRICO',)
    dv = f.get('dollar_volume20')
    return ('LIQUIDEZ INOPERABLE',) if dv is not None and dv < cfg.HARD_MIN_DOLLAR_VOLUME else ()


def decide(row, macro, vix, fresh, earnings=None, *, mode=None, wind=None):
    mode = mode or cfg.ACTIVE_ENGINE
    if mode == 'unified':
        return legacy.decide(row, macro, vix, fresh, earnings)
    if mode != 'spectrum': raise ValueError('Motor desconocido: '+mode)
    reading = spectrum.read_story((row or {}).get('_spectrum_story'), wind,
                                 (earnings or {}).get('days_until'), fresh)
    # Este es el único score público; técnico y rank heredado quedan diagnósticos.
    if row is not None:
        row['rank_score'] = reading.score
        row['score_decision'] = reading.score
        row['spectrum'] = reading.public()
    return SpectralDecision(reading)


def audit_consistency(assets, *, require_score=True, mode=None):
    if (mode or cfg.ACTIVE_ENGINE) == 'unified':
        return legacy.audit_consistency(assets, require_score=require_score)
    errors=[]
    for a in assets:
        d=a.get('data') or {}; r=d.get('spectrum') or a
        score=d.get('rank_score'); shown=a.get('score_decision'); sig=a.get('signal')
        def fail(reason): errors.append({'ticker':a.get('ticker',a.get('proxy','?')), 'reason':reason})
        if sig in ('SIN DATOS','NO OPERABLE','DATOS VIEJOS'):
            if score is not None or shown is not None: fail('unavailable_with_score')
            if r.get('size_mult',0)!=0: fail('unavailable_with_size')
            continue
        det=r.get('deterioration')
        if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in (score,shown,det)):
            fail('missing_or_nonfinite_score');continue
        if score != shown or score != r.get('score_decision'): fail('display_vs_decision_mismatch')
        if not 0<=score<=100: fail('score_out_of_range')
        if spectrum.signal_for(score,det)!=sig: fail('signal_vs_spectrum_mismatch')
        if a.get('vetoes'): fail('obsolete_veto')
    return errors


def top_five_by_decision(assets, limit=5, *, mode=None):
    if (mode or cfg.ACTIVE_ENGINE)=='unified': return legacy.top_five_by_decision(assets,limit)
    if limit<=0:return []
    pool=[a for a in assets if numeric(a.get('data') or {},'rank_score') is not None
          and a.get('usa') and a.get('signal') not in ('SIN DATOS','NO OPERABLE','DATOS VIEJOS')]
    pool.sort(key=lambda a:(-a['data']['rank_score'],a.get('ticker','')))
    selected=[]; deferred=[]; counts=Counter(); seen=set()
    # Diversificar primero; relajar el cupo para llenar los lugares restantes.
    for a in pool:
        if a['usa'] in seen:continue
        seen.add(a['usa'])
        if counts[a.get('sector')]<cfg.SECTOR_SOFT_CAP and len(selected)<limit:
            selected.append(a);counts[a.get('sector')]+=1
        else:deferred.append(a)
    for a in deferred:
        if len(selected)>=limit:break
        selected.append(a)
    selected.sort(key=lambda a:(-a['data']['rank_score'],a.get('ticker','')))
    out=[]; counts=Counter()
    for a in selected:
        d=a['data']; counts[a.get('sector')]+=1
        fallback=d['rank_score']<cfg.BAND_CAUTION
        caution_exit=a['signal'].startswith(('REDUCIR','SALIR'))
        tag=('MEJOR DISPONIBLE · BAJO BANDA DE PRECAUCIÓN' if fallback else 'LECTURA ESPECTRAL')
        if caution_exit:tag+=' · DETERIORO: NO ES COMPRA'
        if counts[a.get('sector')]>cfg.SECTOR_SOFT_CAP:tag+=' · CUPO SECTORIAL RELAJADO'
        out.append({**d, **{k:a.get(k) for k in ('ticker','usa','sector','signal','tone','earnings')},
                    'score_decision':d['rank_score'], 'tag':tag,'fallback':fallback,
                    'relative_spy20':d.get('rs_spy20'),'relative_qqq20':d.get('rs_qqq20'),
                    **(d.get('spectrum') or {})})
    return out
