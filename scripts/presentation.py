"""Public presentation metadata, derived from the actual selected engine."""
import math
import decision_engine_legacy as legacy
import spectrum_config as cfg


def price_history(frame):
    close = frame['Close']
    averages = {n: close.rolling(n).mean() for n in (21, 50, 200)}
    def finite(v):
        return round(float(v), 4) if math.isfinite(float(v)) else None
    return [{'date':str(day.date()), 'close':finite(close.loc[day]),
             **{f'sma{n}':finite(series.loc[day]) for n,series in averages.items()}}
            for day in frame.index[-90:]]


def methodology(spectral=False):
    if spectral:
        return {'engine':'Espectral · candidato sin activar',
                'buy':cfg.BAND_BUY, 'watch':cfg.BAND_WATCH,
                'description':f'Compra desde {cfg.BAND_BUY:g}; precaución desde {cfg.BAND_CAUTION:g}; vigilancia desde {cfg.BAND_WATCH:g}. Deterioro: reducir {cfg.DETERIORATION_REDUCE:g}, salir {cfg.DETERIORATION_EXIT:g}.',
                'macro':f'Macro: hasta ±{cfg.MACRO_SCORE_SWING:g} puntos. VIX ≥{cfg.VIX_STRESS:g} o sin verificar: neutral con tamaño reducido. Sin veto macro.'}
    return {'engine':legacy.RULES_VERSION, 'buy':legacy.BUY_FLOOR, 'watch':legacy.BUY_FLOOR,
            'description':f'Motor vigente: piso de oportunidad {legacy.BUY_FLOOR:g}; prioridad {legacy.PRIORITY_FLOOR:g}. Exige además condiciones técnicas. El espectral sigue en validación.',
            'macro':f'En el motor vigente VIX ≥{legacy.VIX_STRESS_LIMIT:g} o macro sin verificar bloquean compras. Este comportamiento NO corresponde al candidato espectral.'}
